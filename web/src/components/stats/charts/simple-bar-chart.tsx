"use client";

import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  axisDefaults,
  ChartTooltip
} from "@/components/charts/chart-theme";

export interface SimpleBar {
  label: string;
  value: number;
  /** Rendered muted (thin evidence). */
  muted?: boolean;
  /** Extra tooltip line, e.g. sample size. */
  note?: string;
}

interface SimpleBarChartProps {
  data: SimpleBar[];
  height?: number;
  layout?: "horizontal" | "vertical";
  /** Format the value for tooltip + end label. */
  valueFormat: (value: number) => string;
  valueLabel: string;
  /** Direct-label each bar with the formatted value. */
  showLabels?: boolean;
  /** Category axis width (vertical layout). */
  categoryWidth?: number;
  /** Horizontal layout: cap the number of x labels (default: show all). */
  maxLabels?: number;
}

const LOW = "var(--color-ledger-accent)";

/** Single-hue categorical bars — vertical (labels on Y) or horizontal (labels
 *  on X). Low-evidence buckets fade. Shared across the size/room/era/floor cuts. */
export function SimpleBarChart({
  data,
  height = 220,
  layout = "horizontal",
  valueFormat,
  valueLabel,
  showLabels = true,
  categoryWidth = 96,
  maxLabels,
}: SimpleBarChartProps) {
  const xInterval = maxLabels ? Math.max(0, Math.ceil(data.length / maxLabels) - 1) : 0;

  const tooltip = (
    <Tooltip
      cursor={{ fill: "var(--color-ledger-elevated)", opacity: 0.5 }}
      content={<ChartTooltip />}
      formatter={(value, _name, entry) => {
        const note = (entry?.payload as SimpleBar | undefined)?.note;
        return [`${valueFormat(Number(value))}${note ? ` · ${note}` : ""}`, valueLabel];
      }}
    />
  );

  if (layout === "vertical") {
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 64, bottom: 0, left: 0 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={categoryWidth}
            tick={{ fill: "var(--color-ledger-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
          />
          {tooltip}
          <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={16} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={i} fill={LOW} fillOpacity={d.muted ? 0.4 : 1} />
            ))}
            {showLabels && (
              <LabelList dataKey="value" content={(p) => <EndLabel {...p} format={valueFormat} />} />
            )}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 22, right: 8, bottom: 4, left: 8 }}>
        <XAxis
          dataKey="label"
          {...axisDefaults}
          interval={xInterval}
          minTickGap={4}
          tick={{ fill: "var(--color-ledger-muted)", fontSize: 11 }}
        />
        <YAxis hide />
        {tooltip}
        <Bar dataKey="value" radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={LOW} fillOpacity={d.muted ? 0.4 : 1} />
          ))}
          {showLabels && (
            <LabelList dataKey="value" content={(p) => <TopLabel {...p} format={valueFormat} />} />
          )}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

type LabelProps = {
  x?: unknown;
  y?: unknown;
  width?: unknown;
  height?: unknown;
  value?: unknown;
  format: (value: number) => string;
};

function TopLabel({ x, y, width, value, format }: LabelProps) {
  return (
    <text
      x={Number(x ?? 0) + Number(width ?? 0) / 2}
      y={Number(y ?? 0) - 6}
      textAnchor="middle"
      fontSize={11}
      fontWeight={600}
      className="num"
      fill="var(--color-ledger-text)"
    >
      {format(Number(value ?? 0))}
    </text>
  );
}

function EndLabel({ x, y, width, height, value, format }: LabelProps) {
  return (
    <text
      x={Number(x ?? 0) + Number(width ?? 0) + 8}
      y={Number(y ?? 0) + Number(height ?? 0) / 2}
      dominantBaseline="central"
      fontSize={12}
      fontWeight={600}
      className="num"
      fill="var(--color-ledger-text)"
    >
      {format(Number(value ?? 0))}
    </text>
  );
}
