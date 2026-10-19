# Temporary runner pool

This branch provides disposable Ubuntu 24.04 x64/ARM64, macOS 14 ARM64,
and macOS 15 Intel/ARM64 runners to a target
repository. Each host workflow job has a 360-minute timeout, accepts one target
job, and exits. An unassigned runner exits after 15 minutes. No artifacts or
caches are uploaded by the host workflow.

From an authenticated local checkout, launch a two-host trial with:

```sh
python3 scripts/dispatch_pool.py launch --host OWNER/HOST --target OWNER/TARGET --x64 1 --arm64 1
```

For five macOS 14 ARM64 hosts, use `--platform macos-14 --x64 0 --arm64 5`.
For macOS 15, use `--platform macos-15` and the desired architecture counts.
macOS 15 Intel hosts advertise `macos-15-intel`; ARM64 hosts advertise
`macos-14` or `macos-15` matching their real OS. No alternate OS labels are
registered. macOS uses a Python runtime outside Homebrew so target cleanup
cannot remove the parent runner supervisor.

The helper creates a unique environment restricted to this branch, saves the
target and per-runner JIT configurations as environment secrets, dispatches the batch,
and prints a local state path. After the host run completes, remove its secrets
and any idle registrations with `python3 scripts/dispatch_pool.py cleanup STATE`.
State files are private local files and contain no tokens.

Each `RUNNER_JIT_<ARCH>_<SLOT>` secret authorizes exactly one pre-registered
ephemeral runner. It cannot register additional runners. The target repository
is saved separately as `RUNNER_TARGET_REPOSITORY`. Administration credentials
remain on the dispatching machine.

Dispatch `runner-pool.yml` on `feature/ephemeral-runner-pool` with that environment
as `pool`, plus `platform`, `x64-count` and `arm64-count` (1–30 hosts in total). Use small
batches that can start promptly. Additional jobs require a new
batch of fresh hosts and JIT configurations. The target workflow must request the matching
host OS/architecture label.

The runner binary is pinned and SHA-256 verified. Registration output and runner
diagnostics remain on the disposable VM. Parent workflow credentials and file
command paths are excluded from the nested runner environment. Build secrets,
logs, and output policies come from the target workflow.

After completion, the cleanup helper deletes the batch environment and removes
offline runner IDs recorded in its local state. It refuses to remove active
runners. Normal ephemeral runners deregister automatically after their job.
Interrupted or unused registrations require this external cleanup.

The hosting account's Actions concurrency limits still apply. Use only for
trusted workflows in the target repository.
