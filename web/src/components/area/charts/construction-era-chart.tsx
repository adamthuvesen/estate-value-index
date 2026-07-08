"use client";

import { BarChart, Bar, XAxis, YAxis, LabelList, ResponsiveContainer } from "recharts";
import type { ConstructionEraDistribution } from "@/lib/area-types";
import { ChartEmpty, usePrefersReducedMotion } from "@/components/charts/chart-theme";

interface ConstructionEraChartProps {
  construction_era: ConstructionEraDistribution;
}

const ERA_ORDER = ["Pre-1900", "1900-1950", "1950-1980", "1980-2000", "2000+"];

/** Fig. 4 — construction era, chronological, single hue. Rhymes with Fig. 2.
 *  The old tiles + legend duplication folds into the frame's footnote. */
export function ConstructionEraChart({ construction_era }: ConstructionEraChartProps) {
  const reduce = usePrefersReducedMotion();

  if (
    !construction_era.median_year ||
    Object.keys(construction_era.era_distribution).length === 0
  ) {
    return <ChartEmpty message="No construction-era data available." height={ERA_ORDER.length * 36 + 8} />;
  }

  const data = ERA_ORDER.filter((era) => construction_era.era_distribution[era]).map((era) => ({
    era,
    count: construction_era.era_distribution[era],
  }));
  const total = data.reduce((sum, item) => sum + item.count, 0);
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
        fontWeight={600}
        className="num"
        fill="var(--color-ledger-text)"
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
          dataKey="era"
          width={92}
          tick={{ fill: "var(--color-ledger-muted)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <Bar
          dataKey="count"
          fill="var(--color-ledger-accent)"
          radius={[0, 3, 3, 0]}
          barSize={16}
          isAnimationActive={!reduce}
        >
          <LabelList dataKey="count" content={renderLabel} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
