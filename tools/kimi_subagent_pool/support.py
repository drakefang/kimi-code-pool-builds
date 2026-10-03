"""冻结 recipe 的标准库原语；import 无副作用。"""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tomllib
import uuid

FEATURES = ['subagent-pool-entry/v1', 'subagent-binding-replay/v1']
MAX_FILE = 512 * 1024 * 1024


class ContractError(ValueError):
    pass


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ContractError('字段缺失或未知字段')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def hexhash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ContractError('digest 未冻结或无效')
    return value


def safe(path):
    path = Path(os.path.abspath(path))
    for item in reversed((path, *path.parents)):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ContractError('拒绝 symlink/reparse 路径')
            if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                raise ContractError('拒绝 hardlink')
    return path


def sha256(path):
    path = safe(path)
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ContractError('文件缺失或过大')
    result = hashlib.sha256()
    total = 0
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE:
                raise ContractError('hash 输入超过限制')
            result.update(chunk)
    return result.hexdigest()


def read_json(path):
    path = safe(path)
    if path.stat().st_size > 1024 * 1024:
        raise ContractError('JSON 过大')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ContractError('重复 JSON key')
            out[key] = value
        return out
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def write_json(path, value):
    path = safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run(argv, cwd=None, timeout=120, env=None):
    # gh 输出不转储到日志；保留凭据在既有认证环境中。
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            stdout, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                killer = subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                        capture_output=True, timeout=10,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                if killer.returncode != 0 and process.poll() is None:
                    raise ContractError('进程树未确认停止：recovery_required')
            else:
                process.kill()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired as error:
                raise ContractError('进程树未确认停止：recovery_required') from error
            raise
    except subprocess.TimeoutExpired as error:
        raise ContractError(f'进程超时：{Path(argv[0]).name}') from error
    if process.returncode:
        raise ContractError(f'进程失败：{Path(argv[0]).name}，exit={process.returncode}')
    return stdout.decode('utf-8').strip()


def snapshot(path):
    path = safe(path)
    if not path.exists():
        return None
    if path.stat().st_size > 8192:
        raise ContractError('descriptor 过大')
    with path.open('rb') as stream:
        identity = os.fstat(stream.fileno())
        contents = stream.read(8193)
    if len(contents) > 8192:
        raise ContractError('descriptor 过大')
    return (identity.st_dev, identity.st_ino, identity.st_ctime_ns, contents)


@contextmanager
def config_transaction(instance):
    home = safe(instance / 'kimi')
    home.mkdir(parents=True, exist_ok=True)
    path = safe(home / '.nxr-kimi-config.lock')
    try:
        stream = path.open('xb')
    except FileExistsError as error:
        raise ContractError('配置事务已有锁，停止并保留 descriptor') from error
    with stream:
        identity = os.fstat(stream.fileno())
        try:
            stream.write(b'{"schema":"nxr-kimi-config-lock/v1"}\n')
            stream.flush()
            os.fsync(stream.fileno())
            yield
        finally:
            stream.close()
            current = path.lstat() if path.exists() else None
            if current is not None and (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                path.unlink()


def publish_descriptor(instance, value, expected):
    instance = safe(instance)
    with config_transaction(instance):
        path = instance / 'kimi-client.json'
        if snapshot(path) != expected:
            raise ContractError('下载期间 descriptor 发生并发修改，停止并保留')
        write_json(path, value)


def manifest(path=None):
    path = safe(path or Path(__file__).with_name('manifest.toml'))
    value = tomllib.loads(path.read_text(encoding='utf-8'))
    keys(value, ['schema', 'state', 'upstream', 'build', 'patches', 'verification'])
    if value['schema'] != 'nxrouter-kimi-recipe/v1' or value['state'] != 'frozen':
        raise ContractError('recipe pending，必须先冻结真实 patch hash')
    keys(value['upstream'], ['repository', 'revision'])
    if value['upstream'] != {'repository': 'https://github.com/MoonshotAI/kimi-code.git',
                             'revision': 'f67e6398fb3210ad8ace970e2dfd5bcc984ed61f'}:
        raise ContractError('未知 upstream')
    keys(value['build'], ['platform', 'package_version', 'node', 'pnpm', 'pnpm_lock_sha256'])
    build = value['build']
    if (build['platform'], build['package_version'], build['node'], build['pnpm']) != (
            'windows-x64', '2.1.1', '26.1.0', '10.33.0'):
        raise ContractError('未知 toolchain/platform')
    hexhash(build['pnpm_lock_sha256'])
    if len(value['patches']) != 1:
        raise ContractError('patch 集合不匹配')
    patch = value['patches'][0]
    keys(patch, ['path', 'sha256'])
    if patch['path'] != 'patches/0001-independent-subagent-pool.patch':
        raise ContractError('patch 路径不匹配')
    hexhash(patch['sha256'])
    keys(value['verification'], ['required_features'])
    if value['verification']['required_features'] != FEATURES:
        raise ContractError('features 不匹配')
    return value, digest(value), path.parent


def validate_info(info, recipe_id):
    keys(info, ['schema', 'recipe_id', 'artifact_id', 'exe_sha256', 'source_revision',
                'patch_sha256', 'lock_sha256', 'node', 'pnpm', 'platform'])
    if info['schema'] != 'nxrouter-kimi-artifact/v1' or info['recipe_id'] != recipe_id:
        raise ContractError('artifact recipe 身份不匹配')
    for key in ('recipe_id', 'artifact_id', 'exe_sha256', 'patch_sha256', 'lock_sha256'):
        hexhash(info[key])
    identity = dict(info)
    artifact_id = identity.pop('artifact_id')
    if digest(identity) != artifact_id:
        raise ContractError('artifact_id 不匹配')


def validate_receipt(receipt, info):
    keys(receipt, ['schema', 'recipe_id', 'artifact_id', 'exe_sha256', 'passed',
                   'features', 'consumer_tests'])
    if receipt['schema'] != 'nxrouter-kimi-verification/v1' or receipt['passed'] is not True:
        raise ContractError('缺少通过的 root verification receipt')
    if any(receipt[k] != info[k] for k in ('recipe_id', 'artifact_id', 'exe_sha256')):
        raise ContractError('verification 身份不匹配')
    if receipt['features'] != FEATURES or receipt['consumer_tests'] != {
            'pool_entry': 'passed', 'binding_replay': 'passed'}:
        raise ContractError('实际 consumer tests 未通过')
