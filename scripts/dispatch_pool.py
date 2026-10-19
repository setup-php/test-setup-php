"""Dispatch/clean a batch using local gh authentication, never upload that token."""
import argparse
import datetime
import json
import os
from pathlib import Path
import secrets
import subprocess
import time

from runner_pool import matrix

BRANCH = 'feature/ephemeral-runner-pool'


def gh(path, method='GET', data=None):
    command = ['gh', 'api', path, '--method', method]
    if data is not None:
        command += ['--input', '-']
    response = subprocess.run(command, input=json.dumps(data).encode() if data is not None else None,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if response.returncode:
        raise RuntimeError('GitHub API operation failed: ' + method + ' ' + path.split('/actions/')[0])
    return json.loads(response.stdout) if response.stdout else None


def launch(args):
    pool = 'runner-pool-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(3)
    matrix(pool, args.x64, args.arm64)
    directory = Path(args.state_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = {'pool': pool, 'host': args.host, 'target': args.target, 'branch': BRANCH,
             'x64': args.x64, 'arm64': args.arm64, 'run_id': None}
    path = directory / (pool + '.json')
    path.write_text(json.dumps(state, indent=2))
    gh(f'repos/{args.host}/environments/{pool}', 'PUT', {
        'deployment_branch_policy': {'protected_branches': False, 'custom_branch_policies': True},
    })
    gh(f'repos/{args.host}/environments/{pool}/deployment-branch-policies', 'POST', {'name': BRANCH, 'type': 'branch'})
    values = {
        'RUNNER_TARGET_REPOSITORY': args.target,
        'RUNNER_REGISTRATION_TOKEN': gh(f'repos/{args.target}/actions/runners/registration-token', 'POST')['token'],
        'RUNNER_REMOVAL_TOKEN': gh(f'repos/{args.target}/actions/runners/remove-token', 'POST')['token'],
    }
    for key, value in values.items():
        subprocess.run(['gh', 'secret', 'set', key, '-R', args.host, '--env', pool],
                       input=value.encode(), stdout=subprocess.DEVNULL, check=True)
    values.clear()
    gh(f'repos/{args.host}/actions/workflows/runner-pool.yml/dispatches', 'POST', {
        'ref': BRANCH, 'inputs': {'pool': pool, 'x64-count': str(args.x64), 'arm64-count': str(args.arm64)},
    })
    for _ in range(30):
        runs = gh(f'repos/{args.host}/actions/workflows/runner-pool.yml/runs?per_page=30')['workflow_runs']
        match = next((run for run in runs if run['display_title'] == 'Runner pool ' + pool), None)
        if match:
            state['run_id'] = match['id']
            path.write_text(json.dumps(state, indent=2))
            print(json.dumps({'state': str(path), 'url': match['html_url'], 'x64': args.x64, 'arm64': args.arm64}))
            return
        time.sleep(2)
    raise RuntimeError('Dispatch accepted; run not visible yet. Recover its ID using the saved pool name.')


def cleanup(args):
    path = Path(args.state).expanduser()
    state = json.loads(path.read_text())
    host, target, ident = state['host'], state['target'], state['run_id']
    run = gh(f'repos/{host}/actions/runs/{ident}')
    if run['status'] != 'completed':
        raise RuntimeError('Host run has not completed')
    candidates = []
    page = 1
    while True:
        result = gh(f'repos/{target}/actions/runners?per_page=100&page={page}')
        candidates += [r for r in result['runners'] if r['name'].startswith(f'pool-{ident}-')]
        if page * 100 >= result['total_count']:
            break
        page += 1
    if any(r['busy'] or r['status'] != 'offline' for r in candidates):
        raise RuntimeError('A batch runner is still active; refusing cleanup')
    for runner in candidates:
        gh(f'repos/{target}/actions/runners/{runner["id"]}', 'DELETE')
    gh(f'repos/{host}/environments/{state["pool"]}', 'DELETE')
    state['cleaned'] = True
    path.write_text(json.dumps(state, indent=2))
    print(json.dumps({'cleaned': state['pool'], 'conclusion': run['conclusion'], 'removed_offline_runners': len(candidates)}))


if __name__ == '__main__':
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('launch')
    start.add_argument('--host', required=True)
    start.add_argument('--target', required=True)
    start.add_argument('--x64', type=int, default=1)
    start.add_argument('--arm64', type=int, default=1)
    start.add_argument('--state-dir', default='~/.local/share/temporary-runner-pools')
    clean = commands.add_parser('cleanup')
    clean.add_argument('state')
    args = parser.parse_args()
    launch(args) if args.command == 'launch' else cleanup(args)
