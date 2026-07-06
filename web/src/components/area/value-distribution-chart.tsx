"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { VALUE_TIERS, type ValueTier } from "@/lib/value-finder-types";
import { formatRawNumber } from "@/lib/format";

interface ValueDistributionChartProps {
  value_tier_distribution: Record<string, number>;
}

const VALUE_TIER_COLORS: Record<ValueTier, string> = {
  "Excellent Value": "#157F4B",
  "Great Value": "#2E8B57",
  "Good Value": "#4F8A6B",
  "Fair Value": "#6B7280",
  Overvalued: "#C2681C",
  "Highly Overvalued": "#C0392B",
};

export function ValueDistributionChart({ value_tier_distribution }: ValueDistributionChartProps) {
  const data = VALUE_TIERS.filter((tier) => value_tier_distribution[tier] > 0).map((tier) => ({
    name: tier,
    value: value_tier_distribution[tier],
    color: VALUE_TIER_COLORS[tier],
  }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-tactical-border bg-tactical-elevated p-8">
        <p className="text-[13px] text-tactical-muted">No value tier data available.</p>
      </div>
    );
  }

  const total = data.reduce((sum, item) => sum + item.value, 0);

  return (
    <div>
      <div className="mb-3">
        <h3 className="text-[14px] font-semibold tracking-tight text-tactical-text">Value distribution</h3>
        <p className="text-[12px] text-tactical-muted">Properties per value tier</p>
      </div>

      <ResponsiveContainer width="100%" height={Math.max(150, data.length * 34 + 16)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#EDEDE9" horizontal={false} />
          <XAxis type="number" stroke="#E9E9E4" tick={{ fill: "#63666E", fontSize: 11 }} allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="name"
            stroke="#E9E9E4"
            tick={{ fill: "#63666E", fontSize: 11 }}
            width={112}
          />
          <Tooltip
            cursor={{ fill: "rgba(11,98,255,0.06)" }}
            contentStyle={{
              backgroundColor: "#FFFFFF",
              border: "1px solid #E9E9E4",
              borderRadius: "10px",
              boxShadow: "0 4px 14px rgba(16,17,20,0.08)",
              color: "#16171A",
            }}
            formatter={(value: number) => [
              `${formatRawNumber(value)} properties (${((value / total) * 100).toFixed(1)}%)`,
              "Count",
            ]}
            labelStyle={{ fontWeight: 600, color: "#63666E", fontSize: 12 }}
            itemStyle={{ color: "#16171A", fontSize: 13 }}
          />
          <Bar dataKey="value" radius={[0, 6, 6, 0]}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
