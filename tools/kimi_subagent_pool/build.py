"""维护者 prepare/build 入口；不安装全局客户端。"""
import argparse
import os
from pathlib import Path
import shutil
import tempfile

from support import ContractError, digest, keys, manifest, read_json, run, safe, sha256, write_json

PACKAGES = {
    '@moonshot-ai/acp-server', '@moonshot-ai/agent-core-v2', '@moonshot-ai/kaos',
    '@moonshot-ai/kap-server', '@moonshot-ai/klient', '@moonshot-ai/kosong',
    '@moonshot-ai/migration-legacy', '@moonshot-ai/minidb', '@moonshot-ai/kimi-code-sdk',
    '@moonshot-ai/kimi-code-oauth', '@moonshot-ai/pi-tui', '@moonshot-ai/remote-control',
    '@moonshot-ai/kimi-telemetry', '@moonshot-ai/transcript', '@moonshot-ai/tree-sitter-bash',
}


def package_filters(source):
    names = [read_json(path)['name'] for path in sorted((source / 'packages').glob('*/package.json'))]
    if len(names) != 15 or set(names) != PACKAGES:
        raise ContractError('固定源码 package 集合不匹配')
    return [argument for name in sorted(names) for argument in ('--filter', name)]


def validate_source_tree(source, recipe, recipe_root):
    patch = safe(recipe_root / recipe['patches'][0]['path'])
    if sha256(patch) != recipe['patches'][0]['sha256']:
        raise ContractError('patch bytes 漂移')
    # marker 不是源码权威：从 fixed HEAD 与 pinned patch 独立重建预期 index。
    with tempfile.TemporaryDirectory(prefix='kimi-recipe-index-') as temporary:
        environment = dict(os.environ)
        environment['GIT_INDEX_FILE'] = str(Path(temporary) / 'index')
        git = ['git', '-C', str(source), '-c', 'core.autocrlf=false']
        run(git + ['read-tree', recipe['upstream']['revision']], env=environment)
        run(git + ['apply', '--cached', str(patch)], env=environment)
        expected = run(git + ['write-tree'], env=environment)
    actual = run(['git', '-C', str(source), 'write-tree'])
    if actual != expected:
        raise ContractError('源码 index 不等于 fixed HEAD + pinned patch')
    run(['git', '-C', str(source), 'diff', '--quiet'])


def prepare(source, manifest_path=None):
    recipe, recipe_id, root = manifest(manifest_path)
    source = safe(source)
    if source.exists():
        raise ContractError('prepare 只接受不存在的新源码目录')
    patch = safe(root / recipe['patches'][0]['path'])
    if sha256(patch) != recipe['patches'][0]['sha256']:
        raise ContractError('patch hash 不匹配')
    source.parent.mkdir(parents=True, exist_ok=True)
    run(['git', '-c', 'core.autocrlf=false', 'clone', '--no-checkout',
         recipe['upstream']['repository'], str(source)], timeout=600)
    run(['git', '-C', str(source), '-c', 'core.autocrlf=false', 'checkout', '--detach',
         recipe['upstream']['revision']], timeout=120)
    if sha256(source / 'pnpm-lock.yaml') != recipe['build']['pnpm_lock_sha256']:
        raise ContractError('base lock hash 不匹配')
    run(['git', '-C', str(source), '-c', 'core.autocrlf=false', 'apply', '--index', '--check', str(patch)])
    run(['git', '-C', str(source), '-c', 'core.autocrlf=false', 'apply', '--index', str(patch)])
    write_json(source / '.nxrouter-kimi-prepared.json', {
        'schema': 'nxrouter-kimi-prepared/v1', 'recipe_id': recipe_id,
        'source_revision': recipe['upstream']['revision'],
        'patch_sha256': sha256(patch), 'lock_sha256': sha256(source / 'pnpm-lock.yaml'),
        'diff_sha256': digest(run(['git', '-C', str(source), 'diff', '--binary', 'HEAD']))})


def build(source, output, node, pnpm_script, manifest_path=None):
    recipe, recipe_id, recipe_root = manifest(manifest_path)
    source, output = safe(source), safe(output)
    if os.name != 'nt':
        raise ContractError('只支持 Windows x64 维护者构建')
    if output.exists():
        raise ContractError('拒绝覆盖产物目录')
    node, pnpm_script = safe(node), safe(pnpm_script)
    if run([str(node), '--version']) != 'v' + recipe['build']['node']:
        raise ContractError('Node 版本不匹配')
    pnpm = [str(node), str(pnpm_script)]
    if run(pnpm + ['--version']) != recipe['build']['pnpm']:
        raise ContractError('pnpm 版本不匹配')
    if run([str(node), '-p', 'process.platform+"-"+process.arch']) != 'win32-x64':
        raise ContractError('构建平台不匹配')
    prepared = read_json(source / '.nxrouter-kimi-prepared.json')
    keys(prepared, ['schema', 'recipe_id', 'source_revision', 'patch_sha256',
                    'lock_sha256', 'diff_sha256'])
    if (prepared['schema'] != 'nxrouter-kimi-prepared/v1' or
            prepared['source_revision'] != recipe['upstream']['revision'] or
            prepared['patch_sha256'] != recipe['patches'][0]['sha256']):
        raise ContractError('prepared 身份不匹配')
    untracked = run(['git', '-C', str(source), 'ls-files', '--others', '--exclude-standard'])
    if set(untracked.splitlines()) != {'.nxrouter-kimi-prepared.json'}:
        raise ContractError('源码含未知 untracked 文件')
    if prepared.get('recipe_id') != recipe_id or prepared.get('diff_sha256') != digest(
            run(['git', '-C', str(source), 'diff', '--binary', 'HEAD'])):
        raise ContractError('prepared 源码发生变化')
    if run(['git', '-C', str(source), 'rev-parse', 'HEAD']) != recipe['upstream']['revision']:
        raise ContractError('source revision 不匹配')
    validate_source_tree(source, recipe, recipe_root)
    if sha256(source / 'pnpm-lock.yaml') != prepared['lock_sha256']:
        raise ContractError('patched lock 漂移')
    environment = dict(os.environ)
    # 官方 build scripts 内部调用 pnpm，必须与外层使用同一个 pinned runtime。
    environment['PATH'] = str(node.parent) + os.pathsep + environment.get('PATH', '')
    environment['KIMI_CODE_BUILD_TARGET'] = 'win32-x64'
    with tempfile.TemporaryDirectory(prefix='kimi-pnpm-') as shim_dir:
        def cmd_quote(path):
            value = str(path)
            if any(char in value for char in ['%', '\"', '\r', '\n']):
                raise ContractError('pnpm shim 路径含不支持的 cmd 字符')
            return '\"' + value + '\"'
        Path(shim_dir, 'pnpm.cmd').write_text(
            '@' + cmd_quote(node) + ' ' + cmd_quote(pnpm_script) + ' %*\r\n', encoding='utf-8')
        environment['PATH'] = shim_dir + os.pathsep + environment['PATH']
        run(pnpm + ['install', '--frozen-lockfile'], cwd=source, timeout=900, env=environment)
        # 忽略树内 glob filter 可无匹配却 exit 0；枚举全部固定 package name。
        run(pnpm + ['-r'] + package_filters(source) + ['run', 'build'],
            cwd=source, timeout=900, env=environment)
        run(pnpm + ['--filter', '@moonshot-ai/kimi-code', 'run', 'build:native:sea'],
            cwd=source, timeout=900, env=environment)
    exe = source / 'apps/kimi-code/dist-native/bin/win32-x64/kimi.exe'
    exe_hash = sha256(exe)
    info = {'schema': 'nxrouter-kimi-artifact/v1', 'recipe_id': recipe_id,
            'exe_sha256': exe_hash, 'source_revision': recipe['upstream']['revision'],
            'patch_sha256': recipe['patches'][0]['sha256'],
            'lock_sha256': prepared['lock_sha256'], 'node': recipe['build']['node'],
            'pnpm': recipe['build']['pnpm'], 'platform': recipe['build']['platform']}
    info['artifact_id'] = digest(info)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        stage = Path(temporary) / 'artifact'
        stage.mkdir()
        shutil.copyfile(exe, stage / 'kimi.exe')
        write_json(stage / 'build_info.json', info)
        os.rename(stage, output)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('--source', type=Path, required=True)
    compile_parser = commands.add_parser('build')
    for name in ('source', 'output', 'node', 'pnpm-script'):
        compile_parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.source, args.manifest)
        else:
            build(args.source, args.output, args.node, args.pnpm_script, args.manifest)
    except (ContractError, OSError, TimeoutError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
