#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PATH="$HOME/.bend/bin:$PATH"
export CC=clang-19
mkdir -p build

bend version
bend main.bend --check-only
bend PROOF.bend --verdict
bend main.bend -o build/hello
./build/hello
bend examples/parallel.bend -o build/parallel
result=$(./build/parallel +RTS --threads 2)
printf 'CPU parallel result: %s\n' "$result"
test "$result" = 65536
