import boolCases from '../../../../tests/fixtures/bool_coercion_cases.json';
import { coerceBool, extractFloorFromText, extractListingId } from '@/lib/booli-listing-parser';

describe('coerceBool', () => {
  it.each(boolCases as Array<{ input: unknown; expected: boolean | null }>)(
    'fixture input %p -> %p',
    ({ input, expected }) => {
      expect(coerceBool(input)).toBe(expected);
    }
  );
});

describe('extractFloorFromText', () => {
  it('detects ground floor phrases', () => {
    expect(extractFloorFromText('Entréplan med hiss')).toBe(0);
  });

  it('parses våning N', () => {
    expect(extractFloorFromText('Våning 3 med balkong')).toBe(3);
  });
});

describe('extractListingId', () => {
  it('parses annons path', () => {
    const url = new URL('https://www.booli.se/annons/123');
    expect(extractListingId(url)).toBe('123');
  });
});
