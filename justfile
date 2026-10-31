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
    verify_script=.agents/skills/verify-estate-value-index/verify
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
    lane ruff-check uv run --no-sync ruff check . "$verify_script"
    lane ruff-format uv run --no-sync ruff format --check . "$verify_script"
    lane import-linter uv run --no-sync lint-imports --no-cache
    lane types uv run --no-sync basedpyright
    lane types-verify uv run --no-sync basedpyright -p .agents/skills/verify-estate-value-index/pyrightconfig.json
    lane pytest uv run --no-sync pytest -q --no-cov -p no:cacheprovider
    lane web-lint npm run lint --prefix web
    lane web-format npm run format:check --prefix web
    lane web-tsc npm run typecheck --prefix web
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
    uv run ruff check --fix . .agents/skills/verify-estate-value-index/verify
    uv run ruff format . .agents/skills/verify-estate-value-index/verify
    npm exec --prefix web -- oxlint --fix src
    npm run format --prefix web

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

# Drive the real CLIs and API on synthetic fixtures. Args: all, list, control, or drive names.
verify *args:
    uv run --no-sync python .agents/skills/verify-estate-value-index/verify {{args}}

# Full Python suite with the coverage gate, plus the web route-runtime check and the Next.js production build.
slow:
    uv sync --locked --all-extras
    uv run --no-sync pytest -q
    npm run check:routes --prefix web
    npm run build --prefix web
    npm run typecheck --prefix web
