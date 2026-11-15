#!/usr/bin/env bash
set -euo pipefail

# Keep the existing shell configuration and add Bend to both shell entry paths.
for startup in "$HOME/.profile" "$HOME/.bashrc"; do
  if ! grep -Fq '# Bend2 user installation' "$startup"; then
    cat >> "$startup" <<'EOF'

# Bend2 user installation
case ":$PATH:" in
  *":$HOME/.bend/bin:"*) ;;
  *) export PATH="$HOME/.bend/bin:$PATH" ;;
esac
EOF
  fi
done
