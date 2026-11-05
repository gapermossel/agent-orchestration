#!/usr/bin/env bash
# update.sh: replace this bot's code with a new release from a LOCAL directory or
# .tar.gz. No network. Keeps data/ and config/config.json. Backs up the current
# code to .releases/ first so rollback.sh can undo it.
# Usage: ./update.sh <release-dir | release.tar.gz> [--skip-tests]
set -euo pipefail
# Re-run from a temp copy, because this file itself gets replaced. The bot dir is
# passed as an argument (not an exported variable) so child processes, such as
# the new release's own tests, never inherit it.
if [[ "${1:-}" != "--from-copy" ]]; then
  tmp=$(mktemp); cp "$0" "$tmp"
  exec bash "$tmp" --from-copy "$(cd "$(dirname "$0")" && pwd)" "$tmp" "$@"
fi
shift; BOT_DIR="$1"; SELF_COPY="$2"; shift 2
SRC="${1:-}"; SKIP_TESTS="${2:-}"
[[ -n "$SRC" ]] || { echo "usage: update.sh <release-dir|release.tar.gz> [--skip-tests]" >&2; exit 64; }
[[ "$SRC" =~ ^[a-zA-Z]+:// ]] && { echo "refusing URL source (local copies only, no network): $SRC" >&2; exit 65; }
[[ -e "$SRC" ]] || { echo "source not found: $SRC" >&2; exit 66; }

STAGE=$(mktemp -d); trap 'rm -rf "$STAGE" "$SELF_COPY"' EXIT
if [[ -d "$SRC" ]]; then
  cp -a "$SRC"/. "$STAGE"/
else
  if [[ -f "$SRC.sha256" ]]; then
    want=$(awk '{print $1}' "$SRC.sha256"); got=$(sha256sum "$SRC" | awk '{print $1}')
    [[ "$want" == "$got" ]] || { echo "sha256 mismatch for $SRC" >&2; exit 67; }
    echo "sha256 OK $got"
  fi
  tar -xzf "$SRC" -C "$STAGE"
  # allow a single top-level folder in the tarball
  if [[ ! -f "$STAGE/VERSION" && $(ls -A "$STAGE" | wc -l) -eq 1 ]]; then
    inner="$STAGE/$(ls -A "$STAGE")"; mv "$inner"/* "$inner"/.[!.]* "$STAGE"/ 2>/dev/null || true; rmdir "$inner" 2>/dev/null || true
  fi
fi
[[ -f "$STAGE/VERSION" ]] || { echo "release has no VERSION file" >&2; exit 68; }
rm -rf "$STAGE/data" "$STAGE/.releases" "$STAGE/config/config.json"

OLD=$(cat "$BOT_DIR/VERSION" 2>/dev/null || echo none); NEW=$(cat "$STAGE/VERSION")
if [[ "$SKIP_TESTS" != "--skip-tests" && -d "$STAGE/tests" ]]; then
  echo "running tests of new release $NEW ..."
  (cd "$STAGE" && python3 -m unittest discover -s tests -q) || { echo "new release tests FAILED; nothing changed" >&2; exit 69; }
fi

mkdir -p "$BOT_DIR/.releases"
TS=$(date +%Y%m%d-%H%M%S)
BACKUP="$BOT_DIR/.releases/backup-$OLD-$TS.tar.gz"
tar -czf "$BACKUP" -C "$BOT_DIR" --exclude=./data --exclude=./.releases --exclude=./config/config.json .
echo "$TS update $OLD -> $NEW backup=$(basename "$BACKUP")" >> "$BOT_DIR/.releases/HISTORY"

find "$BOT_DIR" -mindepth 1 -maxdepth 1 ! -name data ! -name .releases ! -name config -exec rm -rf {} +
find "$BOT_DIR/config" -mindepth 1 ! -name config.json -exec rm -rf {} + 2>/dev/null || true
cp -a "$STAGE"/. "$BOT_DIR"/
[[ -f "$BOT_DIR/config/config.json" ]] || cp "$BOT_DIR/config/config.example.json" "$BOT_DIR/config/config.json" 2>/dev/null || true
echo "updated $OLD -> $NEW (backup: .releases/$(basename "$BACKUP"))"
