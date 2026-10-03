"""校验产物身份、静态能力与主控实际 consumer receipt。"""
import argparse
import json
import os
from pathlib import Path
import tempfile

from support import (ContractError, FEATURES, manifest, read_json, run, safe, sha256,
                     validate_info, validate_receipt)


def verify(directory, manifest_path=None, probe=True):
    recipe, recipe_id, _ = manifest(manifest_path)
    directory = safe(directory)
    info = read_json(directory / 'build_info.json')
    validate_info(info, recipe_id)
    for field, expected in {'source_revision': recipe['upstream']['revision'],
                            'patch_sha256': recipe['patches'][0]['sha256'],
                            'lock_sha256': recipe['build']['pnpm_lock_sha256'],
                            'node': recipe['build']['node'], 'pnpm': recipe['build']['pnpm'],
                            'platform': recipe['build']['platform']}.items():
        if info[field] != expected:
            raise ContractError('build_info 与 recipe 不匹配')
    if sha256(directory / 'kimi.exe') != info['exe_sha256']:
        raise ContractError('exe hash 不匹配')
    validate_receipt(read_json(directory / 'verification.json'), info)
    if probe:
        with tempfile.TemporaryDirectory(prefix='kimi-capabilities-') as home:
            environment = {key: value for key, value in os.environ.items()
                           if key.upper() in {'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP'}}
            environment.update({'HOME': home, 'USERPROFILE': home, 'KIMI_HOME': home,
                                'KIMI_CODE_HOME': home})
            capabilities = json.loads(run([str(directory / 'kimi.exe'), '--print-capabilities'],
                                          timeout=30, env=environment))
        if (not isinstance(capabilities, dict) or
                capabilities.get('schema') != 'kimi-code-capabilities/v1' or
                capabilities.get('engine') != 'v2' or
                capabilities.get('features') != FEATURES):
            raise ContractError('能力 probe 缺少所需 features')
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    args = parser.parse_args()
    try:
        verify(args.artifact, args.manifest)
    except (ContractError, OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
