#!/usr/bin/env bash
set -euo pipefail
. /etc/os-release
mkdir -p reports
version=$1
php -v | tee reports/php-version.txt
php -m | tee reports/php-modules.txt
php --ini | tee reports/php-ini.txt
php-config --version | tee reports/php-config.txt
phpize --version | tee reports/phpize.txt
composer --version | tee reports/composer.txt
file -L "$(command -v php)" | tee reports/php-binary.txt
php -r '
  foreach (["curl", "dom", "gd", "intl", "mbstring", "mysqli", "pdo_mysql", "pdo_sqlite", "xml", "zip"] as $extension) {
    if (!extension_loaded($extension)) { throw new Exception("Missing extension: " . $extension); }
  }
  if ((new PDO("sqlite::memory:"))->query("SELECT 42")->fetchColumn() != 42) { throw new Exception("SQLite check failed"); }
  if (!imagecreatetruecolor(8, 8)) { throw new Exception("GD check failed"); }
  echo "PHP and extension checks passed\n";
' | tee reports/php-checks.txt

ldd "$(readlink -f "$(command -v php)")" > reports/linkage.txt
extension_dir=$(php-config --extension-dir)
for extension in "$extension_dir"/*.so; do
  printf '\n%s\n' "$extension" >> reports/linkage.txt
  ldd "$extension" >> reports/linkage.txt
done
if grep -F 'not found' reports/linkage.txt; then
  exit 1
fi

suffix=
[[ "$(uname -m)" = aarch64 ]] && suffix=_arm64
artifact="/tmp/php_$version-nts+ubuntu${VERSION_ID}${suffix}.tar.zst"
test -s "$artifact"
zstd -t "$artifact"
sha256sum "$artifact" | tee reports/cache-sha256.txt
dpkg --audit | tee reports/dpkg-audit.txt
test ! -s reports/dpkg-audit.txt
sudo apt-get check | tee reports/apt-check.txt
