#!/usr/bin/env bash
set -uo pipefail
. /etc/os-release
mkdir -p reports
version=$1
failed=0
printf 'check\texit_code\n' > reports/check-results.tsv

# Preserve every result, including package health after a PHP/linkage failure.
run_check() {
  local name=$1 status
  shift
  echo "::group::Check $name"
  printf 'Command:'
  printf ' %q' "$@"
  printf '\n'
  "$@" 2>&1 | tee "reports/$name.txt"
  status=${PIPESTATUS[0]}
  printf '%s\t%s\n' "$name" "$status" >> reports/check-results.tsv
  echo "Exit status: $status"
  if [ "$status" -ne 0 ]; then
    failed=1
    echo "::error title=$name::Check failed with exit status $status; see reports/$name.txt"
  fi
  echo '::endgroup::'
}

check_startup() {
  local output status
  output=$(php -d display_startup_errors=stderr -d display_errors=stderr -r '' 2>&1)
  status=$?
  printf '%s\n' "$output"
  [ "$status" -eq 0 ] && [ -z "$output" ]
}

check_linkage() {
  local extension extension_dir output status bad=0
  extension_dir=$(php-config --extension-dir) || return $?
  shopt -s nullglob
  for extension in "$(readlink -f "$(command -v php)")" "$extension_dir"/*.so; do
    printf '\n%s\n' "$extension"
    output=$(ldd "$extension" 2>&1)
    status=$?
    printf '%s\n' "$output"
    if [ "$status" -ne 0 ] || [[ "$output" = *'not found'* ]]; then
      printf 'FAILED: ldd %s (exit %s)\n' "$extension" "$status"
      bad=1
    fi
  done
  return "$bad"
}

check_cache() {
  local suffix= artifact
  [[ "$(uname -m)" = aarch64 ]] && suffix=_arm64
  artifact="/tmp/php_$version-nts+ubuntu${VERSION_ID}${suffix}.tar.zst"
  echo "Expected archive: $artifact"
  if ! test -s "$artifact"; then
    echo "ERROR: archive is missing or empty"
    return 1
  fi
  zstd -t "$artifact" || return $?
  sha256sum "$artifact" | tee reports/cache-sha256.txt
}

check_dpkg() {
  local output status
  output=$(dpkg --audit 2>&1)
  status=$?
  printf '%s' "$output"
  [ "$status" -eq 0 ] && [ -z "$output" ]
}

run_check php-version php -v
run_check version-match php -r 'if (PHP_MAJOR_VERSION . "." . PHP_MINOR_VERSION !== $argv[1]) { fwrite(STDERR, "Expected " . $argv[1] . "; installed " . PHP_VERSION . "\n"); exit(1); } echo PHP_VERSION, "\n";' "$version"
run_check php-modules php -m
run_check php-ini php --ini
run_check php-config php-config --version
run_check phpize phpize --version
run_check composer composer --version
run_check php-binary file -L "$(command -v php)"
run_check php-startup check_startup
run_check php-checks php -r '
  $missing = [];
  foreach (["curl", "dom", "gd", "intl", "mbstring", "mysqli", "pdo_mysql", "pdo_sqlite", "xml", "zip"] as $extension) {
    if (!extension_loaded($extension)) { $missing[] = $extension; }
  }
  if ($missing) { fwrite(STDERR, "Missing extensions: " . implode(", ", $missing) . "\n"); exit(1); }
  if ((new PDO("sqlite::memory:"))->query("SELECT 42")->fetchColumn() != 42) { throw new Exception("SQLite check failed"); }
  if (!imagecreatetruecolor(8, 8)) { throw new Exception("GD check failed"); }
  echo "PHP and extension checks passed\n";
'
run_check linkage check_linkage
run_check cache-archive check_cache
run_check dpkg-audit check_dpkg
run_check apt-check timeout 120 sudo -n apt-get check

# Record build-tool and library-package inventory without changing the runner.
{
  for tool in phpize php-config shtool autoconf automake make gcc; do
    printf '%s: ' "$tool"
    command -v "$tool" || true
  done
  dpkg-query -W -f='${Package}\t${Status}\t${Version}\n' libaspell15 libenchant-2-2 libfbclient2 libmemcached11 libqdbm14 librabbitmq4 libsnmp40 libsybdb5 libtidy5deb1 libzip4 libzmq5 shtool 2>&1 || true
} | tee reports/dependency-inventory.txt

cat reports/check-results.tsv
exit "$failed"
