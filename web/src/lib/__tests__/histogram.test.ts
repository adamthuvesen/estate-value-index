import { binIndexForValue, histogramBars, maxCount } from "../histogram";
import type { Histogram } from "../overall-statistics-types";

const hist: Histogram = {
  min: 0,
  max: 100,
  bin_width: 25,
  counts: [2, 8, 5, 1],
  p1: 3,
  p25: 20,
  p50: 45,
  p75: 70,
  p99: 96,
  sample_size: 16,
};

describe("histogramBars", () => {
  it("resolves one row per bin with correct edges and centers", () => {
    const bars = histogramBars(hist);
    expect(bars).toHaveLength(4);
    expect(bars[0]).toMatchObject({ index: 0, start: 0, end: 25, center: 12.5, count: 2 });
    expect(bars[3]).toMatchObject({ index: 3, start: 75, end: 100, center: 87.5, count: 1 });
  });
});

describe("binIndexForValue", () => {
  it("maps a value to its bin", () => {
    expect(binIndexForValue(hist, 0)).toBe(0);
    expect(binIndexForValue(hist, 45)).toBe(1);
    expect(binIndexForValue(hist, 80)).toBe(3);
  });

  it("clamps out-of-range values to the edge bins", () => {
    expect(binIndexForValue(hist, -50)).toBe(0);
    expect(binIndexForValue(hist, 1000)).toBe(3);
  });

  it("returns the first bin when bin_width is degenerate", () => {
    expect(binIndexForValue({ ...hist, bin_width: 0 }, 45)).toBe(0);
  });
});

describe("maxCount", () => {
  it("returns the tallest bin count", () => {
    expect(maxCount(hist)).toBe(8);
  });

  it("returns 0 for an empty histogram", () => {
    expect(maxCount({ ...hist, counts: [] })).toBe(0);
  });
});
