# Temporary Ubuntu runner pool

This branch provides disposable Ubuntu 24.04 x64 and ARM64 runners to a target
repository. Each host workflow job has a 360-minute timeout, accepts one target
job, and exits. An unassigned runner exits after 15 minutes. No artifacts or
caches are uploaded by the host workflow.

From an authenticated local checkout, launch a two-host trial with:

```sh
python3 scripts/dispatch_pool.py launch --host OWNER/HOST --target OWNER/TARGET --x64 1 --arm64 1
```

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
as `pool`, plus `x64-count` and `arm64-count` (1–30 hosts in total). Use small
batches that can start promptly. Additional jobs require a new
batch of fresh hosts and JIT configurations. The target workflow must request the matching
`ubuntu-24.04` or `ubuntu-24.04-arm` label.

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
