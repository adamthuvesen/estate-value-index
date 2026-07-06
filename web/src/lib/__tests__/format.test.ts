import {
  AREA_DATA_STALE_DAYS,
  formatDateSv,
  formatNumber,
  formatNumberOrDash,
  formatPercent,
  formatSek,
  formatSekPerSqm,
  formatShortSek,
  getStaleInfo,
} from "../format";

// Intl.NumberFormat's sv-SE group separator (and, for currency style, the
// separator before the unit) is U+00A0 (NBSP), not a regular space — spelled
// out explicitly so a future edit can't silently swap it for a breaking space.
const NBSP = " ";

describe("formatNumberOrDash", () => {
  it("returns em-dash for null", () => {
    expect(formatNumberOrDash(null, 1)).toBe("—");
  });

  it("returns em-dash for undefined", () => {
    expect(formatNumberOrDash(undefined, 1)).toBe("—");
  });

  it("formats zero with the requested decimals", () => {
    expect(formatNumberOrDash(0, 1)).toBe("0.0");
  });

  it("rounds to the requested decimals", () => {
    expect(formatNumberOrDash(1.234, 2)).toBe("1.23");
  });

  it("preserves the sign on negative numbers", () => {
    expect(formatNumberOrDash(-1.5, 1)).toBe("-1.5");
  });
});

describe("shared Swedish formatters", () => {
  it("formats rounded numbers and SEK values", () => {
    expect(formatNumber(1234.6)).toBe(`1${NBSP}235`);
    // formatSek uses Intl's currency style, which puts NBSP both between the
    // number groups and before the unit — unlike formatSekPerSqm below, which
    // concatenates " kr/m²" onto a plain formatNumber() and keeps a regular space.
    expect(formatSek(1234.4)).toBe(`1${NBSP}234${NBSP}kr`);
    expect(formatSekPerSqm(98765.4)).toBe(`98${NBSP}765 kr/m²`);
  });

  it("formats nullable display values", () => {
    expect(formatNumber(null)).toBe("N/A");
    expect(formatSek(undefined)).toBe("N/A");
    expect(formatPercent(null)).toBe("—%");
  });

  it("formats percentages, short values, and dates", () => {
    expect(formatPercent(12.345)).toBe("12.3%");
    expect(formatShortSek(1_250_000)).toBe("1.3M kr");
    expect(formatShortSek(43_200)).toBe("43k kr");
    expect(formatDateSv("2026-05-31T12:00:00Z")).toBe("2026-05-31");
  });
});

describe("getStaleInfo", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date("2026-05-31T12:00:00Z"));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("returns null for missing or invalid dates", () => {
    expect(getStaleInfo(null)).toBeNull();
    expect(getStaleInfo("not-a-date")).toBeNull();
  });

  it("calculates age and staleness with the shared threshold", () => {
    const fresh = getStaleInfo("2026-05-30T12:00:00Z");
    const stale = getStaleInfo("2026-05-20T12:00:00Z");

    expect(fresh?.ageDays).toBe(1);
    expect(fresh?.isStale).toBe(false);
    expect(stale?.ageDays).toBe(11);
    expect(stale?.isStale).toBe(true);
    expect(AREA_DATA_STALE_DAYS).toBe(8);
  });
});
