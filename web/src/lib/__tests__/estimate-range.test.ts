import { estimateRange } from "../estimate-range";

describe("estimateRange", () => {
  it("rounds to the nearest 100k and opens ±200k above 6M", () => {
    expect(estimateRange(11_981_389)).toEqual({
      center: 12_000_000,
      min: 11_800_000,
      max: 12_200_000,
      halfWidth: 200_000,
    });
  });

  it("rounds down when closer to the lower step", () => {
    expect(estimateRange(11_930_000).center).toBe(11_900_000);
  });

  it("uses ±100k below 6M", () => {
    expect(estimateRange(3_449_000)).toEqual({
      center: 3_400_000,
      min: 3_300_000,
      max: 3_500_000,
      halfWidth: 100_000,
    });
  });

  it("switches to ±200k exactly at the 6M boundary", () => {
    expect(estimateRange(6_000_000).halfWidth).toBe(200_000);
    expect(estimateRange(5_940_000).halfWidth).toBe(100_000);
  });
});
