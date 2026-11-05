#!/usr/bin/env bash
# rollback.sh: restore the code from a backup made by update.sh. No network.
# Keeps data/ and config/config.json. Saves the current code as a backup first.
# Usage: ./rollback.sh [backup-file]   (default: newest .releases/backup-*.tar.gz)
set -euo pipefail
# Re-run from a temp copy, because this file itself gets replaced. The bot dir is
# passed as an argument (not an exported variable) so child processes, such as
# the new release's own tests, never inherit it.
if [[ "${1:-}" != "--from-copy" ]]; then
  tmp=$(mktemp); cp "$0" "$tmp"
  exec bash "$tmp" --from-copy "$(cd "$(dirname "$0")" && pwd)" "$tmp" "$@"
fi
shift; BOT_DIR="$1"; SELF_COPY="$2"; shift 2
REL="$BOT_DIR/.releases"
trap 'rm -f "$SELF_COPY"' EXIT
B="${1:-}"
if [[ -z "$B" ]]; then
  B=$(ls -1t "$REL"/backup-*.tar.gz 2>/dev/null | head -1 || true)
fi
[[ -n "$B" && -f "$B" ]] || { echo "no backup found to roll back to" >&2; exit 66; }
CUR=$(cat "$BOT_DIR/VERSION" 2>/dev/null || echo none)
TS=$(date +%Y%m%d-%H%M%S)
SAFE="$REL/prerollback-$CUR-$TS.tar.gz"
tar -czf "$SAFE" -C "$BOT_DIR" --exclude=./data --exclude=./.releases --exclude=./config/config.json .
find "$BOT_DIR" -mindepth 1 -maxdepth 1 ! -name data ! -name .releases ! -name config -exec rm -rf {} +
find "$BOT_DIR/config" -mindepth 1 ! -name config.json -exec rm -rf {} + 2>/dev/null || true
tar -xzf "$B" -C "$BOT_DIR"
mv "$B" "$REL/used-$(basename "$B")"
NEW=$(cat "$BOT_DIR/VERSION")
echo "$TS rollback $CUR -> $NEW from=$(basename "$B") saved=$(basename "$SAFE")" >> "$REL/HISTORY"
echo "rolled back $CUR -> $NEW (current code saved as .releases/$(basename "$SAFE"))"
