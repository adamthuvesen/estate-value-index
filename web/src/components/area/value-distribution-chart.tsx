"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { VALUE_TIERS, type ValueTier } from "@/lib/value-finder-types";

interface ValueDistributionChartProps {
  value_tier_distribution: Record<string, number>;
}

const VALUE_TIER_COLORS: Record<ValueTier, string> = {
  "Excellent Value": "#00ff88",
  "Great Value": "#00ff88",
  "Good Value": "#e0e0e0",
  "Fair Value": "#a0a0a0",
  Overvalued: "#ff4444",
  "Highly Overvalued": "#ff3333",
};

export function ValueDistributionChart({ value_tier_distribution }: ValueDistributionChartProps) {
  const data = VALUE_TIERS
    .filter((tier) => value_tier_distribution[tier] > 0)
    .map((tier) => ({
      name: tier,
      value: value_tier_distribution[tier],
      color: VALUE_TIER_COLORS[tier],
    }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-tactical bg-tactical-elevated border border-tactical-border p-8">
        <p className="text-xs font-mono text-tactical-muted uppercase">No value tier data available</p>
      </div>
    );
  }

  const total = data.reduce((sum, item) => sum + item.value, 0);

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-lg font-semibold tracking-tactical text-tactical-text font-mono uppercase">Value Distribution</h3>
        <p className="text-xs text-tactical-muted font-mono tracking-tactical">PROPERTY VALUE TIER BREAKDOWN</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                labelLine={false}
                outerRadius={100}
                fill="#8884d8"
                dataKey="value"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f0f0f",
                  border: "1px solid #404040",
                  borderRadius: "4px",
                  boxShadow: "0 0 15px rgba(255,51,51,0.2)",
                  fontFamily: "JetBrains Mono, monospace",
                  color: "#e0e0e0",
                }}
                formatter={(value: number) => [
                  `${value} PROPERTIES (${((value / total) * 100).toFixed(1)}%)`,
                  "COUNT",
                ]}
                labelStyle={{ fontWeight: 600, color: "#e0e0e0", fontSize: "10px", textTransform: "uppercase" }}
                itemStyle={{ color: "#e0e0e0", fontSize: "10px", textTransform: "uppercase" }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-col justify-center space-y-2">
          {data.map((item) => (
            <div key={item.name} className="flex items-center justify-between rounded-tactical border border-tactical-border bg-tactical-elevated p-3 hover:border-tactical-border-emphasis transition-colors duration-tactical">
              <div className="flex items-center gap-3">
                <div className="h-4 w-4 rounded" style={{ backgroundColor: item.color }}></div>
                <span className="text-xs font-mono font-medium text-tactical-text">{item.name}</span>
              </div>
              <div className="text-right">
                <span className="text-lg font-bold text-tactical-text font-mono">{item.value}</span>
                <span className="ml-1 text-xs text-tactical-muted font-mono">({((item.value / total) * 100).toFixed(1)}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
