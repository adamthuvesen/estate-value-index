import { validateBooliUrl } from '../booli-url';

function isError(result: ReturnType<typeof validateBooliUrl>): result is { error: string } {
  return typeof (result as { error?: string }).error === 'string';
}

describe('validateBooliUrl', () => {
  describe('accepts legitimate Booli URLs', () => {
    it('accepts https://booli.se/annons/123', () => {
      const result = validateBooliUrl('https://booli.se/annons/123');
      expect(isError(result)).toBe(false);
      expect((result as URL).hostname).toBe('booli.se');
      expect((result as URL).pathname).toBe('/annons/123');
    });

    it('accepts https://www.booli.se/bostad/456', () => {
      const result = validateBooliUrl('https://www.booli.se/bostad/456');
      expect(isError(result)).toBe(false);
      expect((result as URL).hostname).toBe('www.booli.se');
    });
  });

  describe('rejects userinfo bypasses', () => {
    it('rejects https://booli.se@evil.com/ (the bug-hunt bypass)', () => {
      const result = validateBooliUrl('https://booli.se@evil.com/');
      expect(isError(result)).toBe(true);
    });

    it('rejects https://user:pass@booli.se/ (userinfo with password)', () => {
      const result = validateBooliUrl('https://user:pass@booli.se/');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('userinfo not allowed');
    });
  });

  describe('rejects wrong hosts', () => {
    it('rejects https://booli.se.evil.com/ (subdomain typosquat)', () => {
      const result = validateBooliUrl('https://booli.se.evil.com/');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('unsupported host');
    });

    it('rejects https://b00li.se/ (typosquat)', () => {
      const result = validateBooliUrl('https://b00li.se/');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('unsupported host');
    });

    it('rejects percent-encoded host bypass https://booli.se%2eevil.com/', () => {
      // The URL constructor either rejects this outright or canonicalises the
      // host to something that is not in the allow-list. Either way it must
      // not be accepted.
      const result = validateBooliUrl('https://booli.se%2eevil.com/');
      expect(isError(result)).toBe(true);
    });
  });

  describe('rejects unsupported schemes', () => {
    it('rejects javascript:alert(1)', () => {
      const result = validateBooliUrl('javascript:alert(1)');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('unsupported scheme');
    });

    it('rejects file:///etc/passwd', () => {
      const result = validateBooliUrl('file:///etc/passwd');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('unsupported scheme');
    });
  });

  describe('rejects unexpected ports', () => {
    it('rejects http://booli.se:8080/', () => {
      const result = validateBooliUrl('http://booli.se:8080/');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('unexpected port');
    });
  });

  describe('rejects malformed input', () => {
    it('rejects "not-a-url"', () => {
      const result = validateBooliUrl('not-a-url');
      expect(isError(result)).toBe(true);
      expect((result as { error: string }).error).toBe('invalid url');
    });

    it('rejects empty string', () => {
      const result = validateBooliUrl('');
      expect(isError(result)).toBe(true);
    });
  });
});
