#!/usr/bin/env bash
# Maintainer Qt runtime setup, included in the bundled consumer runtime.
set -euo pipefail
cache="${BEND_QT_GENERATOR_CACHE:-$HOME/.cache/bend-qt-generator}"
qt="${1:-$cache/Qt/6.12.0/gcc_64}"
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
plugin="$qt/plugins/webview/libqtwebview_webengine.so"
[[ -x "$qt/bin/qt-configure-module" && -f "$qt/lib/libQt6WebEngineCore.so.6" ]] || {
    echo 'Install the matching Qt WebEngine runtime and development kit first' >&2
    exit 1
}
version="$("$qt/bin/qmake" -query QT_VERSION)"
# CMake's configure_file metadata operations require the Linux filesystem.
work="${BEND_QT_WEBVIEW_BUILD:-$HOME/.cache/bend-qt-webview-$version}"
recipe="$(sha256sum "$root/scripts/setup-qt-webview-backend.sh" | cut -d ' ' -f 1)"
# An installer that ships the backend leaves no build directory here. A
# backend built here is rebuilt whenever this recipe changes.
if [[ -f "$plugin" && ( ! -d "$work" || "$(cat "$work/recipe.sha256" 2>/dev/null)" == "$recipe" ) ]]; then
    printf 'Qt WebView backend ready: %s\n' "$plugin"
    exit 0
fi
for tool in git cmake ninja pkg-config flock; do
    command -v "$tool" >/dev/null || { echo "Missing maintainer tool: $tool" >&2; exit 1; }
done
pkg-config --exists xkbcommon || {
    echo 'Qt WebView backend build requires the maintainer dependency libxkbcommon-dev' >&2
    exit 1
}
pin="$(python3 - "$root/generator/qt_targets.json" "$version" <<'PY'
import json, sys
targets = json.load(open(sys.argv[1]))
if sys.argv[2] not in targets:
    raise SystemExit('No reviewed Qt WebView build target for ' + sys.argv[2])
print(targets[sys.argv[2]]['webview_commit'])
PY
)"
case "$(realpath -m "$work")" in /mnt/*) echo 'Use a Linux filesystem for BEND_QT_WEBVIEW_BUILD' >&2; exit 1;; esac
mkdir -p "$work"
source="$work/source"
if [[ ! -d "$source/.git" ]]; then
    git clone --depth 1 --branch "v$version" https://github.com/qt/qtwebview.git "$source"
fi
[[ "$(git -C "$source" rev-parse HEAD)" == "$pin" ]] || {
    echo "Qt WebView checkout does not match the pinned $version source" >&2; exit 1
}
[[ -z "$(git -C "$source" status --porcelain)" ]] || { echo 'Qt WebView source has local changes' >&2; exit 1; }
# A build directory keeps an earlier recipe's cached options; start clean.
rm -rf "$work/build" "$work/stage" "$work/recipe.sha256"
mkdir -p "$work/build" "$work/stage"
# The linker hashes the plugin into its build ID while it still carries the
# build tree's RPATH, which names the build and Qt directories. Linking with
# the installed RPATH keeps the plugin identical on every machine.
(
    cd "$work/build"
    "$qt/bin/qt-configure-module" "$source" -- \
        -DQT_FEATURE_webview_webengine_plugin=ON -DQT_BUILD_TESTS=OFF \
        -DQT_BUILD_EXAMPLES=OFF -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON
) > "$work/configure.log" 2>&1
flock -x /tmp/bendqt-focused-compile.lock \
    cmake --build "$work/build" --target QWebEngineWebViewPlugin --parallel 1 \
    > "$work/build.log" 2>&1
cmake "-DCMAKE_INSTALL_PREFIX=$work/stage" -DCMAKE_INSTALL_COMPONENT=Unspecified \
    -P "$work/build/src/plugins/webengine/cmake_install.cmake" > "$work/stage.log" 2>&1
mkdir -p "$qt/plugins/webview"
cp "$work/stage/plugins/webview/libqtwebview_webengine.so" "$plugin"
sha256sum "$plugin" > "$work/plugin.sha256"
printf '%s\n' "$recipe" > "$work/recipe.sha256"
printf 'Qt WebView backend ready: %s\n' "$plugin"
