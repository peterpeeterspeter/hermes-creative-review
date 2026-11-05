#!/usr/bin/env bash
# Run every Creative Review check in one go.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
plugin="$(cd "$here/.." && pwd)"
hermes_agent="${HERMES_AGENT_REPO:-$HOME/.hermes/hermes-agent}"
py="$hermes_agent/venv/bin/python"

echo "=== 1. catalog validation (the CI gate) ==="
hermes plugins validate "$plugin" --install-deps || exit 1

echo; echo "=== 2. plugin doctor ==="
hermes plugins doctor "$plugin" || exit 1

echo; echo "=== 3. unit + tool contract tests ==="
( cd "$plugin/tests" && HERMES_AGENT_REPO="$hermes_agent" "$py" -m unittest discover -s . -p 'test_*.py' -v ) || exit 1

echo; echo "=== 4. backend integration (real ASGI app) ==="
PYTHONPATH="$hermes_agent" "$py" "$plugin/tests/integration_backend.py" || exit 1

echo; echo "=== 5. desktop registration harness ==="
node "$plugin/tests/desktop_harness.mjs" || exit 1

echo; echo "All Creative Review checks passed."