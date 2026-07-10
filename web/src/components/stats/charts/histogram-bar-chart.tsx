"use client";

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Histogram } from "@/lib/overall-statistics-types";
import { binIndexForValue, histogramBars } from "@/lib/histogram";
import {
  axisDefaults,
  chartColors,
  ChartTooltip,
  usePrefersReducedMotion,
} from "@/components/charts/chart-theme";
import { formatNumber } from "@/lib/format";

interface HistogramBarChartProps {
  hist: Histogram;
  height?: number;
  /** Format a bin edge for the axis and tooltip. */
  xFormat: (value: number) => string;
  /** Tooltip series name for the count. */
  countLabel?: string;
  /** Draw a dashed reference line at this value (e.g. the median). */
  reference?: { value: number; label: string } | null;
  /**
   * Diverging color split: bars whose bin start is ≥ threshold use `val-over`
   * (above ask), the rest stay neutral. Emphasizes the threshold line.
   */
  diverging?: { threshold: number } | null;
}

/** Pre-binned histogram → single-hue bars (or a diverging split around a
 *  threshold). Reference line and tooltip read real bin edges. */
export function HistogramBarChart({
  hist,
  height = 240,
  xFormat,
  countLabel = "sales",
  reference = null,
  diverging = null,
}: HistogramBarChartProps) {
  const reduce = usePrefersReducedMotion();
  const bars = histogramBars(hist);
  const tickInterval = Math.max(0, Math.ceil(bars.length / 6) - 1);

  const referenceIndex = reference ? binIndexForValue(hist, reference.value) : null;
  const thresholdIndex = diverging ? binIndexForValue(hist, diverging.threshold) : null;

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={bars} margin={{ top: 18, right: 12, bottom: 4, left: 4 }} barCategoryGap={1}>
        <XAxis
          dataKey="index"
          {...axisDefaults}
          interval={tickInterval}
          tickFormatter={(index) => xFormat(bars[Number(index)]?.start ?? 0)}
          minTickGap={4}
        />
        <YAxis {...axisDefaults} width={36} tickFormatter={(v) => formatNumber(Number(v))} />
        {referenceIndex !== null && reference && (
          <ReferenceLine
            x={referenceIndex}
            stroke={chartColors.accent}
            strokeDasharray="4 3"
            label={{
              value: reference.label,
              position: "top",
              fill: chartColors.accent,
              fontSize: 10,
              fontWeight: 600,
            }}
          />
        )}
        {thresholdIndex !== null && (
          <ReferenceLine
            x={thresholdIndex}
            stroke={chartColors.axisLine}
            strokeWidth={1.5}
          />
        )}
        <Tooltip
          cursor={{ fill: "var(--color-ledger-elevated)", opacity: 0.5 }}
          content={<ChartTooltip />}
          formatter={(value) => [formatNumber(Number(value)), countLabel]}
          labelFormatter={(index) => {
            const bar = bars[Number(index)];
            return bar ? `${xFormat(bar.start)} – ${xFormat(bar.end)}` : "";
          }}
        />
        <Bar dataKey="count" isAnimationActive={!reduce}>
          {bars.map((bar) => {
            const above = diverging ? bar.start >= diverging.threshold : false;
            return (
              <Cell
                key={bar.index}
                fill={
                  diverging
                    ? above
                      ? "var(--color-val-over)"
                      : "var(--color-ledger-neutral)"
                    : "var(--color-ledger-accent)"
                }
                fillOpacity={diverging ? 0.9 : 0.88}
              />
            );
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
