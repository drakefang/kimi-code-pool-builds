"""artifact recipe 的离线边界回归；不构建、不访问 GitHub。"""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

RECIPE = Path(__file__).resolve().parents[1] / 'kimi_subagent_pool'
# recipe 是直接运行的脚本；隔离其它工具的同名 support 模块。
saved_support = sys.modules.pop('support', None)
saved_verify = sys.modules.pop('verify', None)
saved_download = sys.modules.pop('download', None)
saved_build = sys.modules.pop('build', None)
saved_package = sys.modules.pop('package', None)
sys.path.insert(0, str(RECIPE))
try:
    import support as ks
    import download as kd
    import verify as kv
    import build as kb
    import package as kp
finally:
    sys.path.pop(0)
    sys.modules.pop('support', None)
    sys.modules.pop('verify', None)
    sys.modules.pop('download', None)
    sys.modules.pop('build', None)
    sys.modules.pop('package', None)
    if saved_support is not None:
        sys.modules['support'] = saved_support
    if saved_verify is not None:
        sys.modules['verify'] = saved_verify
    if saved_download is not None:
        sys.modules['download'] = saved_download
    if saved_build is not None:
        sys.modules['build'] = saved_build
    if saved_package is not None:
        sys.modules['package'] = saved_package


class ArtifactRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def lock(self):
        return {'schema': 'nxrouter-kimi-release-lock/v1',
                'repository': 'drakefang/kimi-code-pool-builds', 'tag': 'pool-v1',
                'recipe_id': '1' * 64, 'artifact_id': '2' * 64,
                'asset': 'kimi-windows-x64.zip', 'archive_sha256': '3' * 64,
                'exe_sha256': '4' * 64, 'verification_receipt_sha256': '5' * 64}

    def test_fixed_lock_accepts_repository_and_digest(self):
        path = self.root / 'lock.json'
        ks.write_json(path, self.lock())
        self.assertEqual(kd.release_lock(path, '1' * 64), self.lock())

    def test_lock_rejects_latest_url_unknown_fields_and_pending(self):
        for key, value in [('tag', 'latest'), ('repository', 'https://evil.invalid/x'),
                           ('archive_sha256', 'pending'), ('asset', '../kimi.zip'),
                           ('tag', 1), ('extra', 'x')]:
            with self.subTest(key=key):
                lock = self.lock()
                lock[key] = value
                path = self.root / 'lock.json'
                ks.write_json(path, lock)
                with self.assertRaises(ks.ContractError):
                    kd.release_lock(path, '1' * 64)

    def test_duplicate_json_fields_rejected(self):
        path = self.root / 'duplicate.json'
        path.write_text('{"schema":1,"schema":2}', encoding='utf-8')
        with self.assertRaises(ks.ContractError):
            ks.read_json(path)

    def archive(self, names):
        archive = self.root / 'artifact.zip'
        with zipfile.ZipFile(archive, 'w') as bundle:
            for name in names:
                bundle.writestr(name, b'x')
        destination = self.root / 'stage'
        destination.mkdir(exist_ok=True)
        return archive, destination

    def test_zip_accepts_exact_members(self):
        archive, destination = self.archive(sorted(kd.MEMBERS))
        kd.extract(archive, destination)
        self.assertEqual({p.name for p in destination.iterdir()}, kd.MEMBERS)

    def test_zip_rejects_escape_extra_missing_duplicate(self):
        for names in [['../kimi.exe', 'build_info.json', 'verification.json'],
                      ['kimi.exe', 'build_info.json'],
                      ['kimi.exe', 'build_info.json', 'verification.json', 'LICENSE', 'extra'],
                      ['kimi.exe', 'kimi.exe', 'verification.json']]:
            with self.subTest(names=names):
                archive, destination = self.archive(names)
                with self.assertRaises(ks.ContractError):
                    kd.extract(archive, destination)
                self.assertEqual(list(destination.iterdir()), [])

    def test_zip_rejects_symlink_and_oversized_member(self):
        for symlink in (True, False):
            archive = self.root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                entry = zipfile.ZipInfo('kimi.exe')
                if symlink:
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                bundle.writestr(entry, b'xx')
                bundle.writestr('build_info.json', b'{}')
                bundle.writestr('verification.json', b'{}')
                bundle.writestr('LICENSE', b'license')
            destination = self.root / ('stage-' + str(symlink))
            destination.mkdir()
            with patch.object(kd, 'MAX_FILE', 1 if not symlink else 10000):
                with self.assertRaises(ks.ContractError):
                    kd.extract(archive, destination)

    def info(self):
        info = {'schema': 'nxrouter-kimi-artifact/v1', 'recipe_id': '1' * 64,
                'exe_sha256': '4' * 64, 'source_revision': 'f67e6398fb3210ad8ace970e2dfd5bcc984ed61f',
                'patch_sha256': '6' * 64, 'lock_sha256': '7' * 64,
                'node': '26.1.0', 'pnpm': '10.33.0', 'platform': 'windows-x64'}
        info['artifact_id'] = ks.digest(info)
        return info

    def test_artifact_id_binds_toolchain_and_exe(self):
        info = self.info()
        ks.validate_info(info, '1' * 64)
        info['exe_sha256'] = '8' * 64
        with self.assertRaises(ks.ContractError):
            ks.validate_info(info, '1' * 64)

    def test_package_contains_upstream_notice_and_license_tamper_is_rejected(self):
        artifact = self.root / 'artifact'
        artifact.mkdir()
        for name in ('kimi.exe', 'build_info.json', 'verification.json'):
            (artifact / name).write_bytes(b'x')
        with patch.object(kp, 'manifest', return_value=({}, '1' * 64, RECIPE)), \
                patch.object(kp, 'verify', return_value=self.info()):
            lock = kp.package(artifact, self.root / 'package', 'drakefang/kimi-code-pool-builds', 'pool-v1')
        destination = self.root / 'stage'
        destination.mkdir()
        kd.extract(self.root / 'package/kimi-windows-x64.zip', destination)
        self.assertEqual((destination / 'LICENSE').read_bytes(), (RECIPE / 'UPSTREAM-LICENSE').read_bytes())
        kd.check_lock(destination, self.info(), lock)
        (destination / 'LICENSE').write_bytes(b'edited notice')
        with self.assertRaises(ks.ContractError):
            kd.check_lock(destination, self.info(), lock)

    def test_receipt_requires_actual_consumer_pass(self):
        info = self.info()
        receipt = {'schema': 'nxrouter-kimi-verification/v1',
                   **{key: info[key] for key in ('recipe_id', 'artifact_id', 'exe_sha256')},
                   'passed': True, 'features': ks.FEATURES,
                   'consumer_tests': {'pool_entry': 'passed', 'binding_replay': 'passed'}}
        ks.validate_receipt(receipt, info)
        receipt['consumer_tests']['binding_replay'] = 'skipped'
        with self.assertRaises(ks.ContractError):
            ks.validate_receipt(receipt, info)

    def test_hardlink_hash_rejected(self):
        first, second = self.root / 'a', self.root / 'b'
        first.write_bytes(b'x')
        os.link(first, second)
        with self.assertRaises(ks.ContractError):
            ks.sha256(second)

    def test_failed_download_keeps_descriptor(self):
        lock_path = self.root / 'lock.json'
        ks.write_json(lock_path, self.lock())
        instance = self.root / 'instance'
        descriptor = instance / 'kimi-client.json'
        old = {'schema': 'nxrouter-kimi-client/v1', 'executable': 'C:\\old\\kimi.exe',
               'sha256': 'a' * 64, 'recipe_id': 'b' * 64, 'artifact_id': 'c' * 64}
        ks.write_json(descriptor, old)
        with patch.object(kd, 'manifest', return_value=({}, '1' * 64, RECIPE)), \
                patch.object(kd, 'run', side_effect=ks.ContractError('offline')):
            with self.assertRaises(ks.ContractError):
                kd.download(lock_path, self.root / 'cache', instance)
        self.assertEqual(ks.read_json(descriptor), old)

    def test_foreign_cache_is_not_modified(self):
        path = self.root / 'lock.json'
        ks.write_json(path, self.lock())
        cache = self.root / 'foreign'
        cache.mkdir()
        with patch.object(kd, 'manifest', return_value=({}, '1' * 64, RECIPE)):
            with self.assertRaises(ks.ContractError):
                kd.download(path, cache)
        self.assertEqual(list(cache.iterdir()), [])

    def test_descriptor_publish_obeys_shared_lock_and_preserves_concurrent_edit(self):
        instance = self.root / 'instance'
        path = instance / 'kimi-client.json'
        ks.write_json(path, {'before': True})
        before = ks.snapshot(path)
        with ks.config_transaction(instance):
            with self.assertRaises(ks.ContractError):
                ks.publish_descriptor(instance, {'after': True}, before)
        ks.write_json(path, {'concurrent': True})
        with self.assertRaises(ks.ContractError):
            ks.publish_descriptor(instance, {'after': True}, before)
        self.assertEqual(ks.read_json(path), {'concurrent': True})
        self.assertFalse((instance / 'kimi/.nxr-kimi-config.lock').exists())
        ks.publish_descriptor(instance, {'after': True}, ks.snapshot(path))
        self.assertEqual(ks.read_json(path), {'after': True})

    def test_package_filters_require_all_frozen_packages(self):
        with self.assertRaises(ks.ContractError):
            kb.package_filters(self.root)
        for number, name in enumerate(sorted(kb.PACKAGES)):
            ks.write_json(self.root / 'packages' / str(number) / 'package.json', {'name': name})
        filters = kb.package_filters(self.root)
        self.assertEqual(filters[::2], ['--filter'] * 15)
        self.assertEqual(set(filters[1::2]), kb.PACKAGES)

    def test_build_rejects_tree_even_if_prepared_marker_were_forged(self):
        patch_path = self.root / 'patches' / 'pool.patch'
        patch_path.parent.mkdir()
        patch_path.write_bytes(b'pinned patch')
        recipe = {'patches': [{'path': 'patches/pool.patch', 'sha256': ks.sha256(patch_path)}],
                  'upstream': {'revision': 'f' * 40}}
        with patch.object(kb, 'run', side_effect=['', '', 'expected-tree', 'tampered-tree']):
            with self.assertRaises(ks.ContractError):
                kb.validate_source_tree(self.root, recipe, self.root)

    def test_build_checks_worktree_matches_pinned_index(self):
        patch_path = self.root / 'pool.patch'
        patch_path.write_bytes(b'pinned patch')
        recipe = {'patches': [{'path': 'pool.patch', 'sha256': ks.sha256(patch_path)}],
                  'upstream': {'revision': 'f' * 40}}
        with patch.object(kb, 'run', side_effect=['', '', 'tree', 'tree',
                                                ks.ContractError('worktree changed')]):
            with self.assertRaises(ks.ContractError):
                kb.validate_source_tree(self.root, recipe, self.root)


if __name__ == '__main__':
    unittest.main()
