/**
 * Validates a user-supplied URL against the Booli host allow-list.
 *
 * Uses the platform `URL` constructor rather than a regex so that encoding
 * tricks (userinfo, percent-encoded host, alternate scheme, non-default port)
 * cannot bypass the host check before we hand the URL to `fetch`.
 *
 * Returns the parsed `URL` on success; otherwise `{ error }` describing the
 * rejection reason. Callers should pass `result.toString()` to `fetch`, never
 * the raw input.
 */

const ALLOWED_HOSTNAMES = new Set(['booli.se', 'www.booli.se']);
const ALLOWED_PORTS = new Set(['', '80', '443']);

export function validateBooliUrl(input: string): URL | { error: string } {
  if (typeof input !== 'string' || input.trim() === '') {
    return { error: 'invalid url' };
  }

  let parsed: URL;
  try {
    parsed = new URL(input);
  } catch {
    return { error: 'invalid url' };
  }

  if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
    return { error: 'unsupported scheme' };
  }

  if (parsed.username !== '' || parsed.password !== '') {
    return { error: 'userinfo not allowed' };
  }

  if (!ALLOWED_PORTS.has(parsed.port)) {
    return { error: 'unexpected port' };
  }

  if (!ALLOWED_HOSTNAMES.has(parsed.hostname)) {
    return { error: 'unsupported host' };
  }

  return parsed;
}
