#!/usr/bin/env bash
# Thin Claude Code adapter (kgsmith19/agent-extensions#68). Cloud sessions
# only: ensure an agent-extensions checkout, run its provider-neutral
# bootstrap/session-start.sh (provision when absent, ~/bin on PATH, queue
# head), then this repo's own dependencies. Never fails the session.
set -uo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
EXT="${AGENT_EXTENSIONS_DIR:-$HOME/.agent-extensions}"
EXT_URL="${AGENT_EXTENSIONS_REPO_URL:-https://github.com/kgsmith19/agent-extensions.git}"

if [ -d "$EXT/.git" ]; then
  git -C "$EXT" pull -q --ff-only 2>/dev/null || echo "extensions: degraded (could not update $EXT; using it as is)"
elif git clone -q --depth 1 "$EXT_URL" "$EXT" 2>/dev/null; then
  echo "extensions: ok (cloned to $EXT)"
else
  echo "extensions: degraded (clone of $EXT_URL failed)"
fi
if [ -f "$EXT/bootstrap/session-start.sh" ]; then
  AGENT_EXTENSIONS_DIR="$EXT" AES_STANDARD_DIR="$ROOT" bash "$EXT/bootstrap/session-start.sh" --env-file "${CLAUDE_ENV_FILE:-}"
else
  echo "session-start: degraded (no $EXT/bootstrap/session-start.sh)"
fi
exit 0
