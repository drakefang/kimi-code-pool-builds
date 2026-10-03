"""只组装已验收的本地产物与固定 release lock；不上传、不安装。"""
import argparse
from pathlib import Path
import os
import tempfile
import zipfile

from support import ContractError, manifest, safe, sha256, write_json
from download import release_lock
from verify import verify

def package(artifact, output, repository, tag, manifest_path=None):
    _, recipe_id, recipe_root = manifest(manifest_path)
    artifact, output = safe(artifact), safe(output)
    if output.exists():
        raise ContractError('拒绝覆盖 package 目录')
    info = verify(artifact, manifest_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.package-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'package'
        stage.mkdir()
        archive = stage / 'kimi-windows-x64.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for name in ('kimi.exe', 'build_info.json', 'verification.json', 'LICENSE'):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                source = safe(recipe_root / 'UPSTREAM-LICENSE') if name == 'LICENSE' else artifact / name
                with bundle.open(entry, 'w', force_zip64=True) as target, source.open('rb') as incoming:
                    while chunk := incoming.read(1024 * 1024):
                        target.write(chunk)
        lock = {'schema': 'nxrouter-kimi-release-lock/v1', 'repository': repository,
                'tag': tag, 'recipe_id': recipe_id, 'artifact_id': info['artifact_id'],
                'asset': archive.name, 'archive_sha256': sha256(archive),
                'exe_sha256': info['exe_sha256'],
                'verification_receipt_sha256': sha256(artifact / 'verification.json')}
        write_json(stage / 'release-lock.json', lock)
        release_lock(stage / 'release-lock.json', recipe_id)
        os.rename(stage, output)
    return lock

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repository', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    try:
        package(args.artifact, args.output, args.repository, args.tag, args.manifest)
    except (ContractError, OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')

if __name__ == '__main__':
    main()

