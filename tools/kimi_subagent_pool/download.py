"""仅下载明确固定的 GitHub release，不接受 latest 或外部 URL。"""
import argparse
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

from support import (ContractError, MAX_FILE, hexhash, keys, manifest, read_json, run,
                     safe, sha256, validate_info, write_json, snapshot, publish_descriptor)
from verify import verify

MEMBERS = {'kimi.exe', 'build_info.json', 'verification.json', 'LICENSE'}


def release_lock(path, recipe_id):
    value = read_json(path)
    keys(value, ['schema', 'repository', 'tag', 'recipe_id', 'artifact_id', 'asset',
                 'archive_sha256', 'exe_sha256', 'verification_receipt_sha256'])
    if value['schema'] != 'nxrouter-kimi-release-lock/v1' or value['recipe_id'] != recipe_id:
        raise ContractError('release lock recipe 不匹配')
    if not isinstance(value['repository'], str) or not re.fullmatch(
            r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', value['repository']):
        raise ContractError('必须为 GitHub owner/repo')
    if not isinstance(value['tag'], str) or not re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value['tag']) or (
            value['tag'].lower() in ('latest', 'main', 'master', 'head')):
        raise ContractError('必须为固定 release tag')
    if not isinstance(value['asset'], str) or not re.fullmatch(
            r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.zip', value['asset']):
        raise ContractError('必须为明确 ZIP asset 文件名')
    for key in ('recipe_id', 'artifact_id', 'archive_sha256', 'exe_sha256',
                'verification_receipt_sha256'):
        hexhash(value[key])
    return value


def extract(archive, destination):
    safe(archive)
    if archive.stat().st_size > MAX_FILE:
        raise ContractError('archive 过大')
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) != len(MEMBERS) or {entry.filename for entry in entries} != MEMBERS:
            raise ContractError('ZIP 必须只有四个唯一规范 member（含 LICENSE）')
        for entry in entries:
            mode = entry.external_attr >> 16
            if entry.flag_bits & 1 or stat.S_ISLNK(mode) or (
                    stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ContractError('ZIP symlink/非普通文件/encrypted member')
            limit = MAX_FILE if entry.filename == 'kimi.exe' else 1024 * 1024
            if entry.file_size > limit or entry.file_size < 0:
                raise ContractError('ZIP member 过大')
            target = safe(destination / entry.filename)
            with bundle.open(entry) as incoming, target.open('xb') as outgoing:
                total = 0
                while chunk := incoming.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise ContractError('ZIP 解压超过限制')
                    outgoing.write(chunk)


def download(lock_path, cache_root, instance=None, manifest_path=None):
    _, recipe_id, _ = manifest(manifest_path)
    lock = release_lock(lock_path, recipe_id)
    cache_root = safe(cache_root)
    if instance is not None:
        instance = safe(instance)
        descriptor = instance / 'kimi-client.json'
        descriptor_before = snapshot(descriptor)
        if descriptor.exists():
            old = read_json(descriptor)
            keys(old, ['schema', 'executable', 'sha256', 'recipe_id', 'artifact_id'])
            if old['schema'] != 'nxrouter-kimi-client/v1':
                raise ContractError('拒绝覆盖非自有 descriptor')
    if cache_root.exists():
        marker = cache_root / '.nxrouter-kimi-cache.json'
        if not marker.exists() or read_json(marker) != {'schema': 'nxrouter-kimi-cache/v1'}:
            raise ContractError('拒绝使用非自有 cache 目录')
    else:
        cache_root.mkdir(parents=True)
        write_json(cache_root / '.nxrouter-kimi-cache.json', {'schema': 'nxrouter-kimi-cache/v1'})
    target = safe(cache_root / lock['artifact_id'])
    if not target.exists():
        with tempfile.TemporaryDirectory(prefix='.download-', dir=cache_root) as temporary:
            workspace = Path(temporary)
            run(['gh', 'release', 'download', lock['tag'], '--repo', lock['repository'],
                 '--pattern', lock['asset'], '--dir', str(workspace)], timeout=300)
            archive = workspace / lock['asset']
            if sha256(archive) != lock['archive_sha256']:
                raise ContractError('archive hash 不匹配')
            stage = workspace / 'artifact'
            stage.mkdir()
            extract(archive, stage)
            info = read_json(stage / 'build_info.json')
            check_lock(stage, info, lock)
            verify(stage, manifest_path)
            os.rename(stage, target)
    if {item.name for item in target.iterdir()} != MEMBERS:
        raise ContractError('cache artifact 含未知 member')
    info = read_json(target / 'build_info.json')
    check_lock(target, info, lock)
    verify(target, manifest_path)
    if instance is not None:
        publish_descriptor(instance, {
            'schema': 'nxrouter-kimi-client/v1', 'executable': str(target / 'kimi.exe'),
            'sha256': lock['exe_sha256'], 'recipe_id': recipe_id,
            'artifact_id': lock['artifact_id']}, descriptor_before)
    return target


def check_lock(directory, info, lock):
    validate_info(info, lock['recipe_id'])
    if info['artifact_id'] != lock['artifact_id'] or info['exe_sha256'] != lock['exe_sha256']:
        raise ContractError('release artifact 身份不匹配')
    if sha256(directory / 'verification.json') != lock['verification_receipt_sha256']:
        raise ContractError('verification receipt hash 不匹配')
    if sha256(directory / 'LICENSE') != sha256(Path(__file__).with_name('UPSTREAM-LICENSE')):
        raise ContractError('上游许可通知缺失或不匹配')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-lock', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--write-descriptor', action='store_true')
    parser.add_argument('--instance-dir', type=Path)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    if args.write_descriptor != (args.instance_dir is not None):
        parser.error('--write-descriptor 与 --instance-dir 必须成对指定')
    try:
        download(args.release_lock, args.cache_root, args.instance_dir, args.manifest)
    except (ContractError, OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
