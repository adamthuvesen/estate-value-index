#!/usr/bin/env node
/**
 * Walk web/src/app/api/** /route.ts and fail if any file lacks
 *   export const runtime = 'nodejs'
 * unless the file is in EDGE_ALLOWLIST.
 *
 * The check is a string scan rather than an AST parse — the rule is simple,
 * a malicious bypass would be obvious in code review, and this avoids pulling
 * in a TS parser as a dev dependency.
 *
 * Run via `npm run check:routes`.
 */
import { readdir, readFile } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

// Routes that intentionally target the Edge runtime. Empty by default — add
// entries here ONLY when an Edge runtime is genuinely required.
export const EDGE_ALLOWLIST = new Set([]);

// Match `export const runtime = 'nodejs'` or `export const runtime = "nodejs"`,
// ignoring whitespace.
const RUNTIME_NODEJS_RE = /export\s+const\s+runtime\s*=\s*['"]nodejs['"]/;

const SCRIPT_DIR = fileURLToPath(new URL('.', import.meta.url));
const WEB_ROOT = join(SCRIPT_DIR, '..');
const API_ROOT = join(WEB_ROOT, 'src', 'app', 'api');

async function* walkRoutes(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      // Skip __tests__ directories — only inspect actual route files.
      if (entry.name === '__tests__') continue;
      yield* walkRoutes(full);
    } else if (entry.isFile() && entry.name === 'route.ts') {
      yield full;
    }
  }
}

async function main() {
  const failures = [];
  for await (const file of walkRoutes(API_ROOT)) {
    const rel = relative(WEB_ROOT, file);
    if (EDGE_ALLOWLIST.has(rel)) continue;

    const source = await readFile(file, 'utf8');
    if (!RUNTIME_NODEJS_RE.test(source)) {
      failures.push(rel);
    }
  }

  if (failures.length > 0) {
    console.error("Route runtime check failed. The following files do not declare `export const runtime = 'nodejs'`:");
    for (const file of failures) {
      console.error(`  - ${file}`);
    }
    console.error("\nAdd `export const runtime = 'nodejs'` near the top of each file, or list the route in EDGE_ALLOWLIST in scripts/check-route-runtime.mjs.");
    process.exit(1);
  }

  console.log('Route runtime check: all API routes declare nodejs runtime.');
}

main().catch((err) => {
  console.error('check-route-runtime: unexpected error');
  console.error(err);
  process.exit(2);
});
