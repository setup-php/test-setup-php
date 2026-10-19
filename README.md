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
target and freshly minted tokens as environment secrets, dispatches the batch,
and prints a local state path. After the host run completes, remove its secrets
and any idle registrations with `python3 scripts/dispatch_pool.py cleanup STATE`.
State files are private local files and contain no tokens.

Prepare a unique `runner-pool-*` Actions environment before dispatch. Its secrets
are `RUNNER_TARGET_REPOSITORY`, `RUNNER_REGISTRATION_TOKEN`, and
`RUNNER_REMOVAL_TOKEN`. Obtain fresh registration and removal tokens from the
target repository's runner REST API; they expire after one hour. Long-lived
administration credentials remain on the dispatching machine.

Dispatch `runner-pool.yml` on `feature/ephemeral-runner-pool` with that environment
as `pool`, plus `x64-count` and `arm64-count` (1–20 hosts in total). Use small
batches that can start within the token lifetime. Additional jobs require a new
batch of fresh hosts and tokens. The target workflow must request the matching
`ubuntu-24.04` or `ubuntu-24.04-arm` label.

The runner binary is pinned and SHA-256 verified. Registration output and runner
diagnostics remain on the disposable VM. Parent workflow credentials and file
command paths are excluded from the nested runner environment. Build secrets,
logs, and output policies come from the target workflow.

After completion, delete the batch environment and remove any offline runner
whose name starts with `pool-<host-run-id>-`; do not remove busy runners. Normal
ephemeral runners deregister automatically after their job. Cancellation after
the removal token expires requires this external cleanup.

The hosting account's Actions concurrency limits still apply. Use only for
trusted workflows in the target repository.
