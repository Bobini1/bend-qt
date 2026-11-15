#!/usr/bin/env bash
# Pinned Bend and Lean for ephemeral CI runners; no account credentials needed.
set -euo pipefail
archive="$(mktemp --suffix=.tar.gz)"
stage="$(mktemp -d)"
trap 'rm -f -- "$archive"; rm -rf -- "$stage"' EXIT
curl --proto '=https' --tlsv1.2 --retry 3 -fsSL \
  https://github.com/bendlang/bend/releases/download/v2.0.40/bend-2.0.40-linux-x64.tar.gz \
  -o "$archive"
printf '%s  %s\n' c9ff8d67bd903fb6ad9a26b43d8a62c01021de82a44d55ce4a3dcd4732113d6b "$archive" | sha256sum -c -
tar -xzf "$archive" -C "$stage"
mkdir -p "$HOME/.bend/bin"
cp -a "$stage/bend/bend2" "$stage/bend/guide" "$HOME/.bend/"
cp "$stage/bend/bin/bend" "$HOME/.bend/bin/bend"
elan toolchain install leanprover/lean4:v4.34.0
export PATH="$HOME/.bend/bin:$PATH"
test "$(bend version)" = 'bend 2.0.40'
if [[ -n "${GITHUB_PATH:-}" ]]; then
  printf '%s\n' "$HOME/.bend/bin" "$HOME/.elan/bin" >> "$GITHUB_PATH"
fi
