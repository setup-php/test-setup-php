#!/usr/bin/env bash
set -eo pipefail
. action/src/scripts/unix.sh
. /etc/os-release
check_ppa() { return 0; }
mkdir -p reports

start=$(date +%s%N)
check_builds_cache_runner
end=$(date +%s%N)
echo "registered_runner_check_ms=$(((end - start) / 1000000))" | tee reports/detection.txt

for name in blacksmith-forged depot-forged namespace-test; do
  if (RUNNER_NAME=$name; check_builds_cache_runner); then
    echo "Unexpectedly accepted a mismatched runner name: $name"
    exit 1
  fi
done

(
  unset runner RUNNER use_package_cache
  use_builds_cache=true
  fail_fast=true
  read_env
  test "$runner" = github
) | tee -a reports/detection.txt
(
  unset runner RUNNER use_builds_cache
  use_package_cache=true
  read_env
  test "$runner" = github
) | tee -a reports/detection.txt
(
  unset runner RUNNER
  use_builds_cache=false
  use_package_cache=true
  read_env
  test "$runner" = self-hosted
)
(
  unset runner RUNNER use_builds_cache use_package_cache
  read_env
  test "$runner" = self-hosted
)

# Confirm unrelated runner environments do not invoke the new metadata check.
(
  unset runner RUNNER BLACKSMITH_VM_ID
  RUNNER_NAME=namespace-test
  use_builds_cache=true
  check_builds_cache_runner() { echo unexpected-metadata-check; return 0; }
  if output=$(read_env); then
    echo 'Unexpectedly accepted an unrelated runner'
    exit 1
  fi
  [[ "$output" != *unexpected-metadata-check* ]]
)
echo 'Provider checks, name mismatch rejection, fallback, precedence, and narrow scope passed.' | tee -a reports/detection.txt
