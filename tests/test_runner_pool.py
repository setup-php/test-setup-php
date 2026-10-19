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

    def test_parent_credentials_and_context_cannot_reach_child(self):
        parent = dict(HOME='/home/runner', PATH='/bin', USER='runner',
                      GITHUB_TOKEN='secret', GH_TOKEN='secret', GITHUB_REPOSITORY='host/repository',
                      ACTIONS_RUNTIME_TOKEN='secret', RUNNER_TRACKING_ID='parent',
                      RUNNER_REGISTRATION_TOKEN='secret', RUNNER_REMOVAL_TOKEN='secret',
                      GITHUB_ENV='/parent/env', GITHUB_OUTPUT='/parent/output')
        self.assertEqual(pool.child_environment(parent),
                         {'HOME': '/home/runner', 'PATH': '/bin', 'USER': 'runner'})


if __name__ == '__main__':
    unittest.main()
