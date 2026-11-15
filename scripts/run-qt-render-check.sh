#!/usr/bin/env bash
# Maintainer-only headless OpenGL test. Consumers never run this helper.
set -euo pipefail
cache="${BEND_QT_HEADLESS_TOOLS:-$HOME/.cache/bend-qt-generator/headless-render}"
if [[ -d "$cache/usr/lib/x86_64-linux-gnu" ]]; then
    export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$cache/usr/lib/x86_64-linux-gnu"
fi
if [[ -n "${DISPLAY:-}" ]]; then
    exec "$@"
fi
if ! command -v xvfb-run >/dev/null && [[ -x "$cache/usr/bin/Xvfb" ]]; then
    export PATH="$cache/usr/bin:$PATH"
fi
if ! command -v xvfb-run >/dev/null; then
    echo 'Install the maintainer dependencies xvfb, xauth, x11-xkb-utils and libxcb-cursor0.' >&2
    exit 1
fi
exec xvfb-run -a -e /dev/stderr -s '-screen 0 640x480x24 -nolisten tcp' "$@"
