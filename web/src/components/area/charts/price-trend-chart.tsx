"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { MonthlySeries, PriceUnit } from "@/lib/price-trend";
import {
  axisDefaults,
  chartColors,
  ChartTooltip,
  usePrefersReducedMotion,
} from "@/components/charts/chart-theme";
import {
  formatSek,
  formatSekPerSqm,
  formatShortSek,
  formatShortThousands,
} from "@/lib/format";

interface PriceTrendChartProps {
  series: MonthlySeries;
  unit: PriceUnit;
}

const HEIGHT = 240;

/** Fig. 1 — honest price trend. Line when ≥3 real months; a direct-labeled
 *  3/6/12-month medians dumbbell otherwise. Never fabricates a filled line. */
export function PriceTrendChart({ series, unit }: PriceTrendChartProps) {
  const reduce = usePrefersReducedMotion();
  const perSqm = unit === "per_sqm";
  const axisFormat = (v: number) => (perSqm ? formatShortThousands(v) : formatShortSek(v));
  const fullFormat = (v: number) => (perSqm ? formatSekPerSqm(v) : formatSek(v));

  if (series.mode === "empty") {
    return (
      <div
        className="flex items-center justify-center rounded-sm border border-dashed border-ledger-border bg-ledger-elevated px-6 text-center"
        style={{ height: HEIGHT }}
      >
        <p className="text-body-sm text-ledger-muted">Not enough historical price data.</p>
      </div>
    );
  }

  if (series.mode === "medians") {
    return <MediansDumbbell series={series} format={fullFormat} />;
  }

  const median12 = series.medians.find((m) => m.key === "12m")?.value ?? null;
  const realIndices = series.points
    .map((p, i) => (p.isReal ? i : -1))
    .filter((i) => i >= 0);
  const lastRealIndex = realIndices[realIndices.length - 1];

  return (
    <ResponsiveContainer width="100%" height={HEIGHT}>
      <LineChart data={series.points} margin={{ top: 16, right: 44, bottom: 4, left: 4 }}>
        <XAxis dataKey="month" {...axisDefaults} interval={1} minTickGap={8} />
        <YAxis
          {...axisDefaults}
          width={52}
          tickFormatter={axisFormat}
          // Hug the data — a zero baseline flattens a 105–120k series into a
          // sliver at the top of the plot.
          domain={[
            (dataMin: number) => Math.floor((dataMin * 0.94) / 1000) * 1000,
            (dataMax: number) => Math.ceil((dataMax * 1.04) / 1000) * 1000,
          ]}
          tickCount={4}
        />
        {median12 !== null && (
          <ReferenceLine
            y={median12}
            stroke={chartColors.tick}
            strokeDasharray="4 4"
            label={{
              value: "12-mo median",
              position: "insideTopRight",
              fill: chartColors.tick,
              fontSize: 10,
            }}
          />
        )}
        <Tooltip
          content={<ChartTooltip />}
          formatter={(value) => [fullFormat(Number(value)), perSqm ? "Median / m²" : "Median"]}
          labelFormatter={(label) => {
            const point = series.points.find((p) => p.month === label);
            return point ? `${label} · ${point.label}` : label;
          }}
        />
        <Line
          type="monotone"
          dataKey="value"
          stroke={chartColors.accent}
          strokeWidth={1.5}
          connectNulls={false}
          isAnimationActive={!reduce}
          dot={(props: { cx?: number; cy?: number; index?: number; payload?: { isReal?: boolean } }) => {
            const { cx, cy, index, payload } = props;
            if (cx == null || cy == null || !payload?.isReal) {
              return <g key={index} />;
            }
            const isLast = index === lastRealIndex;
            return (
              <g key={index}>
                <circle cx={cx} cy={cy} r={2.5} fill={chartColors.accent} />
                {isLast && (
                  <text
                    x={cx}
                    y={cy - 10}
                    textAnchor="middle"
                    fontSize={11}
                    fontWeight={600}
                    fill={chartColors.ink}
                  >
                    {axisFormat(series.points[index]?.value ?? 0)}
                  </text>
                )}
              </g>
            );
          }}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Medians fallback — 3/6/12-month medians as a direct-labeled dumbbell. Plain
 *  HTML/SVG so it renders in SSR (unlike the recharts line). */
function MediansDumbbell({
  series,
  format,
}: {
  series: MonthlySeries;
  format: (v: number) => string;
}) {
  const points = series.medians.filter((m) => m.value !== null);
  const values = points.map((p) => p.value as number);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return (
    <div data-chart-mode="medians" className="py-2">
      <p className="eyebrow text-ledger-dimmed">Median snapshot</p>
      <p className="mt-1 text-caption text-ledger-muted">
        Too few monthly sales for a trend line — showing 3/6/12-month medians instead.
      </p>
      <ul className="mt-4 space-y-3">
        {points.map((point) => {
          const pct = (((point.value as number) - min) / range) * 100;
          return (
            <li key={point.key} className="flex items-center gap-3">
              <span className="eyebrow w-24 shrink-0 text-ledger-dimmed">{point.label}</span>
              <span className="relative h-2 flex-1 rounded-pill bg-ledger-elevated">
                <span
                  className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full bg-ledger-accent"
                  style={{ left: `calc(${pct}% - 6px)` }}
                  aria-hidden
                />
              </span>
              <span className="num w-28 shrink-0 text-right text-body-sm font-semibold text-ledger-text">
                {format(point.value as number)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
