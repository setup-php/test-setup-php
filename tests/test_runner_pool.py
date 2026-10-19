import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('runner_pool', Path(__file__).parents[1] / 'scripts/runner_pool.py')
pool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pool)


class PoolTests(unittest.TestCase):
    def test_matrix_matches_real_host_architectures(self):
        items = pool.matrix('runner-pool-example', 2, 1)['include']
        self.assertEqual([i['os'] for i in items], ['ubuntu-24.04', 'ubuntu-24.04', 'ubuntu-24.04-arm'])
        self.assertEqual(len({(i['arch'], i['slot']) for i in items}), 3)

    def test_capacity_and_environment_are_bounded(self):
        self.assertEqual(len(pool.matrix('runner-pool-test', 20, 10)['include']), 30)
        for counts in [(0, 0), (-1, 2), (30, 1), (1, 'two')]:
            with self.assertRaises(ValueError):
                pool.matrix('runner-pool-test', *counts)
        with self.assertRaises(ValueError):
            pool.matrix('production', 1, 1)

    def test_ubuntu_hosts_preserve_native_compatibility_test_baselines(self):
        for version in ('22.04', '24.04', '26.04'):
            host = 'ubuntu-' + version
            items = pool.matrix('runner-pool-ubuntu', 1, 1, host)['include']
            self.assertEqual([i['os'] for i in items], [host, host + '-arm'])
            for arch, machine in [('x64', 'x86_64'), ('arm64', 'aarch64')]:
                pool.validate_host(host, arch, 'Linux', machine, version)
                for other in ('22.04', '24.04', '26.04'):
                    if other != version:
                        with self.assertRaises(ValueError):
                            pool.validate_host(host, arch, 'Linux', machine, other)
        self.assertEqual(pool.matrix('runner-pool-approval', 1, 0, 'ubuntu-latest')['include'][0]['os'],
                         'ubuntu-latest')
        with self.assertRaises(ValueError):
            pool.matrix('runner-pool-approval', 0, 1, 'ubuntu-latest')
        with self.assertRaises(ValueError):
            pool.validate_host('ubuntu-latest', 'x64', 'Linux', 'x86_64', '26.04')

    def test_macos_labels_match_the_actual_os_and_architecture(self):
        items = pool.matrix('runner-pool-mac', 0, 5, 'macos-14')['include']
        self.assertEqual(len(items), 5)
        self.assertTrue(all(i['os'] == 'macos-14' and i['arch'] == 'arm64' for i in items))
        self.assertEqual([i['os'] for i in pool.matrix('runner-pool-mac', 1, 1, 'macos-15')['include']],
                         ['macos-15-intel', 'macos-15'])
        self.assertEqual(pool.host_spec('macos-14', 'arm64')['package'], 'osx')
        self.assertEqual(pool.host_spec('macos-14', 'arm64')['system'], 'macOS')
        with self.assertRaises(ValueError):
            pool.matrix('runner-pool-mac', 1, 0, 'macos-14')
        with self.assertRaises(ValueError):
            pool.matrix('runner-pool-mac', 0, 1, 'macos-26')

    def test_host_validation_rejects_wrong_deployment_baseline(self):
        pool.validate_host('macos-14', 'arm64', 'Darwin', 'arm64', '14.8.3')
        pool.validate_host('macos-15', 'x64', 'Darwin', 'x86_64', '15.7')
        pool.validate_host('linux', 'arm64', 'Linux', 'aarch64', '24.04')
        for host in [('Darwin', 'arm64', '15.7'), ('Darwin', 'x86_64', '14.8'),
                     ('Linux', 'aarch64', '24.04')]:
            with self.assertRaises(ValueError):
                pool.validate_host('macos-14', 'arm64', *host)

    def test_parent_credentials_and_context_cannot_reach_child(self):
        parent = dict(HOME='/home/runner', PATH='/bin', USER='runner',
                      GITHUB_TOKEN='secret', GH_TOKEN='secret', GITHUB_REPOSITORY='host/repository',
                      ACTIONS_RUNTIME_TOKEN='secret', RUNNER_TRACKING_ID='parent',
                      RUNNER_JIT_CONFIG='secret',
                      GITHUB_ENV='/parent/env', GITHUB_OUTPUT='/parent/output')
        self.assertEqual(pool.child_environment(parent),
                         {'HOME': '/home/runner', 'PATH': '/bin', 'USER': 'runner'})


if __name__ == '__main__':
    unittest.main()
