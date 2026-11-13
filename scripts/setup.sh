#!/bin/sh
# One-time setup on macOS / Linux. Run from anywhere: sh scripts/setup.sh
set -e
cd "$(dirname "$0")/.."

fail=0
for tool in git uv gh; do
  if command -v "$tool" >/dev/null 2>&1; then
    echo "[ok] $tool"
  else
    echo "[missing] $tool"
    case "$tool" in
      uv) echo "  install uv: https://docs.astral.sh/uv/getting-started/installation/"; fail=1 ;;
      gh) echo "  install gh: https://cli.github.com (then: gh auth login)" ;;
      git) fail=1 ;;
    esac
  fi
done
[ "$fail" -eq 0 ] || exit 1

uv sync
uv run pytest -q

echo ""
echo "Skills in this repo:"
for d in .agents/skills/*/; do echo "  - $(basename "$d")"; done
echo ""
echo "Ready. Open your agent in this folder and check it lists the skills above."
echo "Read docs/COM-TREBALLEM.md next."
