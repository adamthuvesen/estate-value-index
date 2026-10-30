# Setup on a fresh clone: `uv sync --all-extras` and `npm ci --prefix web`.

set shell := ["bash", "-euo", "pipefail", "-c"]

# Lint, format check, and tests for Python and web, in parallel. Prints the output of every failed lane.
check:
    #!/usr/bin/env bash
    set -euo pipefail
    uv sync --locked --all-extras
    if [ ! -d web/node_modules ]; then
        echo "web/node_modules is missing. Run: npm ci --prefix web" >&2
        exit 1
    fi
    logs=$(mktemp -d)
    trap 'rm -rf "$logs"' EXIT
    names=()
    pids=()
    lane() {
        local name=$1
        shift
        "$@" >"$logs/$name.log" 2>&1 &
        names+=("$name")
        pids+=($!)
    }
    lane ruff-check uv run --no-sync ruff check .
    lane ruff-format uv run --no-sync ruff format --check .
    lane pytest uv run --no-sync pytest -q --no-cov -p no:cacheprovider
    lane web-lint npm run lint --prefix web
    lane web-tsc npm exec --prefix web -- tsc --noEmit -p web
    lane web-jest npm test --prefix web
    failed=0
    for i in "${!names[@]}"; do
        if wait "${pids[$i]}"; then
            echo "ok    ${names[$i]}"
        else
            echo "FAIL  ${names[$i]}"
            sed 's/^/    /' "$logs/${names[$i]}.log"
            failed=1
        fi
    done
    exit "$failed"

# Apply every safe automatic fix.
fix:
    uv run ruff check --fix .
    uv run ruff format .
    npm exec --prefix web -- eslint src --fix

# Placeholder until the verify skill exists.
verify:
    @echo "verify skill not built yet (Phase 7)" >&2
    @exit 1

# Full Python suite with the coverage gate, plus the web route-runtime check.
slow:
    uv sync --locked --all-extras
    uv run --no-sync pytest -q
    npm run check:routes --prefix web
