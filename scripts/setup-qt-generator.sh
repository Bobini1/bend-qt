#!/usr/bin/env bash
# Maintainer setup only. This script is never part of a BendHub consumer build.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cache="${BEND_QT_GENERATOR_CACHE:-$HOME/.cache/bend-qt-generator}"
version=6.12.0
base_only=0
while (($#)); do
    case "$1" in
        --qt-version) version="${2:?--qt-version needs an exact version}"; shift 2;;
        --base-only) base_only=1; shift;;
        *) echo "Unknown setup option: $1" >&2; exit 2;;
    esac
done
target="$(python3 - "$root/generator/qt_targets.json" "$version" <<'PY'
import json, sys
targets = json.load(open(sys.argv[1]))
if sys.argv[2] not in targets:
    raise SystemExit('No reviewed Qt/PySide build target for ' + sys.argv[2])
t = targets[sys.argv[2]]
print(t['shiboken_commit'], t['installer_arch'])
PY
)"
read -r pin arch <<< "$target"
for tool in python3 cmake ninja git clang++-19 llvm-config-19 llvm-readobj-19 llvm-nm-19; do
    command -v "$tool" >/dev/null || { echo "Missing maintainer tool: $tool" >&2; exit 1; }
done
if [[ ! -f /usr/lib/llvm-19/include/clang-c/Index.h ]]; then
    echo 'Install maintainer dependencies: libclang-19-dev llvm-19-dev python3-venv' >&2
    exit 1
fi
# Native modules are compiled against GCC 13's C++ library on every host.
if [[ ! -f /usr/lib/gcc/x86_64-linux-gnu/13/crtbeginS.o || ! -d /usr/include/c++/13 ]]; then
    echo 'Install the maintainer dependency libstdc++-13-dev' >&2
    exit 1
fi
mkdir -p "$cache"
bash "$root/scripts/setup-qt-linker.sh"
if [[ ! -x "$cache/venv/bin/aqt" ]]; then
    python3 -m venv "$cache/venv"
    "$cache/venv/bin/pip" install 'aqtinstall==3.3.0'
fi
if ! "$cache/venv/bin/python" -c 'from importlib.metadata import version; assert version("reuse") == "5.1.1"' >/dev/null 2>&1; then
    "$cache/venv/bin/pip" install 'reuse==5.1.1'
fi
qt="$cache/Qt/$version/gcc_64"
if [[ ! -x "$qt/bin/qt-cmake" || ! -f "$qt/lib/libicui18n.so.73" ]]; then
    "$cache/venv/bin/aqt" install-qt linux desktop "$version" "$arch" \
        --archives qtbase icu --outputdir "$cache/Qt"
fi
if [[ "$base_only" == 0 && ! -f "$qt/include/QtQuick/QtQuick" ]]; then
    "$cache/venv/bin/aqt" install-qt linux desktop "$version" "$arch" \
        --archives qtdeclarative --outputdir "$cache/Qt"
fi
if [[ "$base_only" == 0 ]] && ! python3 - "$root/generator/qt612/profile.json" "$qt" "$root/generator/qt_targets.json" "$version" <<'PY'
import json, sys
from pathlib import Path
profile, qt = Path(sys.argv[1]), Path(sys.argv[2])
unavailable = json.load(open(sys.argv[3]))[sys.argv[4]]['unavailable_modules']
sys.exit(any(not (qt / 'include' / name / name).exists()
             for name in json.loads(profile.read_text())['qt_modules'] if name not in unavailable))
PY
then
    canvas=(); [[ "$version" == 6.10.3 ]] || canvas=(qtcanvaspainter)
    "$cache/venv/bin/aqt" install-qt linux desktop "$version" "$arch" \
        --archives qtbase qtdeclarative qtsvg qttools icu \
        --modules qt3d "${canvas[@]}" qtcharts qtconnectivity qtdatavis3d \
        qtgraphs qthttpserver qtlocation qtmultimedia qtnetworkauth qtpdf \
        qtpositioning qtquick3d qtquicktimeline qtremoteobjects qtscxml qtsensors qtserialbus \
        qtserialport qtshadertools qtspeech qtwebchannel qtwebengine \
        qtwebsockets qtwebview --outputdir "$cache/Qt"
fi
if [[ "$base_only" == 0 && ! -f "$qt/lib/libQt6QuickTimeline.so.6" ]]; then
    # Quick3D's asset importer links this QML runtime dependency even though
    # PySide has no separate C++ type-system module for it.
    "$cache/venv/bin/aqt" install-qt linux desktop "$version" "$arch" \
        --noarchives --modules qtquicktimeline --outputdir "$cache/Qt"
fi
source="$cache/pyside-setup"
build="$cache/build"
if [[ "$version" != 6.12.0 ]]; then
    source="$cache/pyside-setup-$version"
    build="$cache/build-$version"
fi
if [[ ! -d "$source/.git" ]]; then
    git clone --depth 1 --branch "v$version" https://github.com/pyside/pyside-setup.git "$source"
fi
[[ "$(git -C "$source" rev-parse HEAD)" == "$pin" ]] || {
    echo "Shiboken checkout does not match the pinned $version commit" >&2
    exit 1
}
"$qt/bin/qt-cmake" -S "$root/generator" -B "$build" -G Ninja \
    "-DSHIBOKEN_SOURCE=$source" "-DBQT_QT_VERSION=$version" -DCMAKE_CXX_COMPILER=clang++-19 -DCMAKE_BUILD_TYPE=Release
cmake --build "$build" --parallel 4
if [[ "$base_only" == 0 ]]; then
    bash "$root/scripts/setup-qt-webview-backend.sh" "$qt"
fi
printf 'Extractor ready: %s\nQt development kit: %s\n' "$build/bend-qt-extract" "$qt"
