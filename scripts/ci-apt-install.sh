#!/usr/bin/env bash
# Maintainer and headless test packages for the Qt build runners. Downloaded
# archives are kept in ~/apt-archives for the workflow cache: the Ubuntu mirror
# has delivered them at 100 kB/s, and the canonical gate starts several runners.
set -euo pipefail
packages=(
  clang-19 libclang-19-dev llvm-19-dev lld-19 libstdc++-13-dev cmake ninja-build git
  python3-venv curl elan zstd qt6-base-dev qt6-declarative-dev
  libx11-dev libasound2-dev libxkbcommon-dev libxkbcommon-x11-0
  libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
  libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1
  xvfb xauth x11-xkb-utils libgl1-mesa-dri libegl1 libopengl0
  libpulse0 libnss3 libnspr4 libxcomposite1 libxdamage1 libxrandr2
  libxtst6 libfontconfig1 libdbus-1-3 libatk1.0-0t64
  libatk-bridge2.0-0t64 libcups2t64 libdrm2 libgbm1 libpango-1.0-0
  libpcsclite1 libxkbfile1 libwayland-client0 libwayland-cursor0
  libx11-xcb1 libxcb-util1 libxcb-shape0 libxcb-randr0 libxcb-sync1
  libxcb-xfixes0 libxcb-shm0 libxcb-dri3-0 libgssapi-krb5-2
  libglx-mesa0
)
archives="$HOME/apt-archives"
cache=/var/cache/apt/archives
mkdir -p "$archives"
sudo apt-get update
if compgen -G "$archives/*.deb" > /dev/null; then
  sudo cp "$archives"/*.deb "$cache"/
  # Drop versions the mirror no longer offers, so the cache does not grow.
  sudo apt-get autoclean
fi
sudo apt-get install -y --no-install-recommends --download-only "${packages[@]}"
rm -f "$archives"/*.deb
if compgen -G "$cache/*.deb" > /dev/null; then
  cp "$cache"/*.deb "$archives"/
fi
sudo apt-get install -y --no-install-recommends "${packages[@]}"
