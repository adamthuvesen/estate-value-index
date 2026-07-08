"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Cell,
  LabelList,
  ResponsiveContainer,
} from "recharts";
import { VALUE_TIERS, type ValueTier } from "@/lib/value-finder-types";
import { chartPalette, ChartEmpty, usePrefersReducedMotion } from "@/components/charts/chart-theme";

interface ValueDistributionChartProps {
  value_tier_distribution: Record<string, number>;
}

/** Fig. 2 — value-tier counts as horizontal bars, coloured strictly by the
 *  val.* tier scale, with direct end labels `count · share`. */
export function ValueDistributionChart({ value_tier_distribution }: ValueDistributionChartProps) {
  const reduce = usePrefersReducedMotion();
  const data = VALUE_TIERS.filter((tier) => value_tier_distribution[tier] > 0).map((tier) => ({
    name: tier as ValueTier,
    value: value_tier_distribution[tier],
    color: chartPalette.valTiers[tier as ValueTier],
  }));

  if (data.length === 0) {
    return <ChartEmpty message="No value-tier data available." height={150} />;
  }

  const total = data.reduce((sum, item) => sum + item.value, 0);
  const height = data.length * 36 + 8;

  const renderLabel = (props: {
    x?: unknown;
    y?: unknown;
    width?: unknown;
    height?: unknown;
    value?: unknown;
  }) => {
    const x = Number(props.x ?? 0);
    const y = Number(props.y ?? 0);
    const width = Number(props.width ?? 0);
    const barH = Number(props.height ?? 0);
    const value = Number(props.value ?? 0);
    const share = ((value / total) * 100).toFixed(0);
    return (
      <text
        x={x + width + 8}
        y={y + barH / 2}
        dominantBaseline="central"
        fontSize={12}
        className="num"
        fill="var(--color-ledger-text)"
        fontWeight={600}
      >
        {value} · {share} %
      </text>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 72, bottom: 0, left: 0 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="name"
          width={120}
          tick={{ fill: "var(--color-ledger-muted)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <Bar dataKey="value" radius={[0, 3, 3, 0]} isAnimationActive={!reduce} barSize={16}>
          {data.map((entry) => (
            <Cell key={entry.name} fill={entry.color} />
          ))}
          <LabelList dataKey="value" content={renderLabel} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
