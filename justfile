# Setup on a fresh clone: `uv sync --all-extras` and `npm ci --prefix web`.

set shell := ["bash", "-euo", "pipefail", "-c"]

web_types := "web/src/lib/generated/api-types.ts"
json2ts := "npm exec --prefix web -- json2ts --unreachableDefinitions --additionalProperties false --bannerComment '/* Generated from the Pydantic models by `just types` (scripts/export_web_schema.py). Do not edit. */'"

# Lint, format check, types, and tests for Python and web, in parallel. Prints the output of every failed lane.
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
    lane import-linter uv run --no-sync lint-imports --no-cache
    lane types uv run --no-sync basedpyright
    lane pytest uv run --no-sync pytest -q --no-cov -p no:cacheprovider
    lane web-lint npm run lint --prefix web
    lane web-tsc npm exec --prefix web -- tsc --noEmit -p web
    lane web-jest npm test --prefix web
    lane web-types just types-check
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
fix: types
    uv run ruff check --fix .
    uv run ruff format .
    npm exec --prefix web -- eslint src --fix

# Regenerate the web TypeScript types from the Pydantic models' JSON Schema.
types:
    uv run python -m scripts.export_web_schema | {{json2ts}} > {{web_types}}

# Fail when the generated web types differ from the Pydantic models.
types-check:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! uv run --no-sync python -m scripts.export_web_schema | {{json2ts}} | diff -u {{web_types}} -; then
        echo "{{web_types}} is stale. Run: just types" >&2
        exit 1
    fi

# Placeholder until the verify skill exists.
verify:
    @echo "verify skill not built yet (Phase 7)" >&2
    @exit 1

# Full Python suite with the coverage gate, plus the web route-runtime check.
slow:
    uv sync --locked --all-extras
    uv run --no-sync pytest -q
    npm run check:routes --prefix web
