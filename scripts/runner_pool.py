"""One disposable runner per host VM. Never forward parent workflow credentials."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

VERSION = '2.338.0'
ARCHES = {
    'x64': ('ubuntu-24.04', 'af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32'),
    'arm64': ('ubuntu-24.04-arm', '628b4a7258487b80c1d3c221095a7ded349f5ae0175fd3dfab708d07428f041b'),
}


def matrix(pool, x64, arm64):
    if not re.fullmatch(r'runner-pool-[a-z0-9-]{1,60}', pool):
        raise ValueError('Invalid pool environment')
    counts = [int(x64), int(arm64)]
    if any(n < 0 or n > 30 for n in counts) or not 1 <= sum(counts) <= 30:
        raise ValueError('Select 1 to 30 runners in total')
    return {'include': [
        {'arch': arch, 'os': ARCHES[arch][0], 'slot': str(slot), 'secret': f'RUNNER_JIT_{arch.upper()}_{slot}'}
        for arch, count in zip(ARCHES, counts) for slot in range(1, count + 1)
    ]}


def child_environment(parent):
    # In particular, omit GITHUB_*, ACTIONS_*, RUNNER_*, GH_TOKEN and our
    # registration secrets. The nested runner creates its own job context.
    allowed = ('HOME', 'USER', 'LOGNAME', 'PATH', 'LANG', 'LC_ALL', 'SHELL', 'TERM')
    return {key: parent[key] for key in allowed if key in parent}


def download_runner(directory, arch):
    archive = directory / 'runner.tar.gz'
    url = f'https://github.com/actions/runner/releases/download/v{VERSION}/actions-runner-linux-{arch}-{VERSION}.tar.gz'
    with urllib.request.urlopen(url, timeout=120) as response, archive.open('wb') as output:
        shutil.copyfileobj(response, output)
    with archive.open('rb') as downloaded:
        checksum = hashlib.file_digest(downloaded, 'sha256').hexdigest()
    if checksum != ARCHES[arch][1]:
        raise RuntimeError('Runner archive verification failed')
    with tarfile.open(archive) as package:
        package.extractall(directory, filter='data')
    archive.unlink()


def stop(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGINT)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def serve():
    os.umask(0o077)
    jit = os.environ.pop('RUNNER_JIT_CONFIG')
    arch = os.environ.pop('POOL_ARCH')
    slot = os.environ.pop('POOL_SLOT')
    if not re.fullmatch(r'[A-Za-z0-9+/=]+', jit):
        raise ValueError('Missing or invalid single-runner configuration')
    if arch not in ARCHES or not re.fullmatch(r'[1-9][0-9]?', slot):
        raise ValueError('Invalid runner slot')
    machine = {'x64': 'x86_64', 'arm64': 'aarch64'}[arch]
    release = Path('/etc/os-release').read_text()
    if platform.machine() != machine or 'VERSION_ID="24.04"' not in release:
        raise ValueError('Host does not match the advertised runner label')
    env = child_environment(os.environ)
    process = None
    directory = Path(tempfile.mkdtemp(prefix='temporary-runner-', dir=os.environ['RUNNER_TEMP']))
    def interrupted(signum, frame):
        raise InterruptedError('Host workflow interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        download_runner(directory, arch)
        print('Pinned runner download verified.', flush=True)
        with (directory / 'host.log').open('wb') as log:
            # Runner diagnostics and console output stay on this disposable VM.
            # The target workflow controls its own logs and package storage.
            # A JIT credential can start only this pre-registered, one-job
            # runner. It cannot register additional runners for the repository.
            print('Starting temporary runner for one job.', flush=True)
            process = subprocess.Popen(['./run.sh', '--jitconfig', jit], cwd=directory, env=env,
                                       stdout=log, stderr=log, start_new_session=True)
            jit = ''
            started = time.monotonic()
            assigned = False
            while process.poll() is None:
                assigned = assigned or any((directory / '_diag').glob('Worker_*.log'))
                elapsed = time.monotonic() - started
                # Do not hold an unused host for six hours. Once assigned,
                # allow the complete job to finish before the host deadline.
                if not assigned and elapsed >= 15 * 60:
                    raise TimeoutError('No job assigned within 15 minutes')
                if elapsed >= 350 * 60:
                    raise TimeoutError('Runner exceeded its execution deadline')
                time.sleep(2)
            if process.returncode != 0 or not assigned:
                raise RuntimeError('Temporary runner did not complete a job')
            print('Temporary runner finished its job.', flush=True)
    finally:
        stop(process)
        # Successful JIT runners deregister themselves. External cleanup uses
        # local admin credentials for interrupted/unassigned registrations.
        # Container workspaces can contain root-owned files; destroy only our
        # dedicated temporary tree, never the parent runner workspace.
        subprocess.run(['sudo', 'rm', '-rf', '--', str(directory)], check=False)


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['matrix']:
            result = matrix(os.environ['POOL'], os.environ['X64_COUNT'], os.environ['ARM64_COUNT'])
            with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                output.write('matrix=' + json.dumps(result, separators=(',', ':')) + '\n')
        elif sys.argv[1:] == ['serve']:
            serve()
        else:
            raise ValueError('Unknown command')
    except BaseException as error:
        # Exception strings can contain secret URLs or registration arguments.
        print(f'::error::Temporary runner failed ({type(error).__name__}); inspect the target job status.', file=sys.stderr)
        sys.exit(1)
