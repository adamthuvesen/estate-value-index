"use client";

import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  axisDefaults,
  chartColors,
  ChartTooltip
} from "@/components/charts/chart-theme";

export interface TrendPoint {
  label: string;
  value: number | null;
  /** Incomplete period — drawn hollow, connected with a dashed segment. */
  partial?: boolean;
}

interface TrendLineChartProps {
  data: TrendPoint[];
  height?: number;
  valueFormat: (value: number) => string;
  axisFormat?: (value: number) => string;
  valueLabel: string;
  /** Hug the data instead of zero-basing the y-axis. */
  hugDomain?: boolean;
  reference?: { value: number; label: string } | null;
  /** Roughly how many x ticks to show. */
  maxTicks?: number;
}

/** Time/ordinal trend line. The final point can be flagged partial: it renders
 *  hollow and its connecting segment is dashed, so an incomplete month never
 *  reads as a real drop. */
export function TrendLineChart({
  data,
  height = 240,
  valueFormat,
  axisFormat,
  valueLabel,
  hugDomain = true,
  reference = null,
  maxTicks = 7,
}: TrendLineChartProps) {
  const axisFmt = axisFormat ?? valueFormat;

  const lastPartialIndex = data.findIndex((p) => p.partial);
  const rows = data.map((p, i) => {
    const solid = p.partial ? null : p.value;
    // The dashed bridge covers the last complete point → the partial point.
    const dashed =
      p.partial || (lastPartialIndex > 0 && i === lastPartialIndex - 1) ? p.value : null;
    return { ...p, solid, dashed };
  });

  const interval = Math.max(0, Math.ceil(data.length / maxTicks) - 1);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 18, right: 16, bottom: 4, left: 4 }}>
        <XAxis dataKey="label" {...axisDefaults} interval={interval} minTickGap={8} />
        <YAxis
          {...axisDefaults}
          width={46}
          tickFormatter={(v) => axisFmt(Number(v))}
          tickCount={4}
          domain={
            hugDomain
              ? [
                  (min: number) => Math.floor((min * 0.96) / 1000) * 1000,
                  (max: number) => Math.ceil((max * 1.04) / 1000) * 1000,
                ]
              : undefined
          }
        />
        {reference && (
          <ReferenceLine
            y={reference.value}
            stroke={chartColors.tick}
            strokeDasharray="4 4"
            label={{
              value: reference.label,
              position: "insideTopRight",
              fill: chartColors.tick,
              fontSize: 10,
            }}
          />
        )}
        <Tooltip
          content={<ChartTooltip />}
          formatter={(value) => [valueFormat(Number(value)), valueLabel]}
          labelFormatter={(label) => {
            const point = data.find((p) => p.label === label);
            return point?.partial ? `${label} · partial` : label;
          }}
        />
        <Line
          type="monotone"
          dataKey="solid"
          stroke={chartColors.accent}
          strokeWidth={1.5}
          connectNulls={false}
          isAnimationActive={false}
          dot={false}
          activeDot={{ r: 4 }}
        />
        <Line
          type="monotone"
          dataKey="dashed"
          stroke={chartColors.accent}
          strokeWidth={1.5}
          strokeDasharray="4 4"
          connectNulls
          isAnimationActive={false}
          dot={(props: { cx?: number; cy?: number; index?: number; payload?: TrendPoint }) => {
            const { cx, cy, index, payload } = props;
            if (cx == null || cy == null || !payload?.partial) return <g key={index} />;
            return (
              <circle
                key={index}
                cx={cx}
                cy={cy}
                r={3.5}
                fill="var(--color-ledger-surface)"
                stroke={chartColors.accent}
                strokeWidth={1.5}
              />
            );
          }}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
