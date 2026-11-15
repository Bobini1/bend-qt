#!/usr/bin/env bash
# Maintainer-only LLD bootstrap; uses a user cache and needs no sudo.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cache="${BEND_QT_GENERATOR_CACHE:-$HOME/.cache/bend-qt-generator}"
if [[ "${BQT_LINKER:-auto}" == system ]]; then
    python3 "$root/generator/native_linker.py"
    exit 0
fi
if command -v ld.lld-19 >/dev/null || command -v ld.lld >/dev/null ||
   [[ -x "$cache/tools/lld-19/usr/bin/ld.lld-19" ]] ||
   [[ "${BQT_LINKER:-auto}" == /* ]]; then
    python3 "$root/generator/native_linker.py"
    exit 0
fi
for tool in apt-get dpkg-deb; do
    command -v "$tool" >/dev/null || { echo 'Install the maintainer package lld-19 or set BQT_LINKER=system' >&2; exit 1; }
done
mkdir -p "$cache/tools"
download="$(mktemp -d "$cache/tools/lld-download.XXXXXXXX")"
(
    cd "$download"
    apt-get download lld-19
)
packages=("$download"/lld-19_*.deb)
[[ ${#packages[@]} == 1 && -f "${packages[0]}" ]] || { echo 'Expected one downloaded lld-19 package' >&2; exit 1; }
dpkg-deb --extract "${packages[0]}" "$cache/tools/lld-19"
python3 "$root/generator/native_linker.py"
