"use client";

import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { VALUE_TIERS, type ValueTier } from "@/lib/value-finder-types";

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
  const data = VALUE_TIERS
    .filter((tier) => value_tier_distribution[tier] > 0)
    .map((tier) => ({
      name: tier,
      value: value_tier_distribution[tier],
      color: VALUE_TIER_COLORS[tier],
    }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-tactical-border bg-tactical-elevated p-8">
        <p className="text-[13px] text-tactical-muted">No value tier data available.</p>
      </div>
    );
  }

  const total = data.reduce((sum, item) => sum + item.value, 0);

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-[17px] font-semibold tracking-tight text-tactical-text">Value distribution</h3>
        <p className="text-[13px] text-tactical-muted">Property value tier breakdown</p>
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
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E9E9E4",
                  borderRadius: "10px",
                  boxShadow: "0 4px 14px rgba(16,17,20,0.08)",
                  color: "#16171A",
                }}
                formatter={(value: number) => [
                  `${value} properties (${((value / total) * 100).toFixed(1)}%)`,
                  "Count",
                ]}
                labelStyle={{ fontWeight: 600, color: "#63666E", fontSize: 12 }}
                itemStyle={{ color: "#16171A", fontSize: 13 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="flex flex-col justify-center space-y-2">
          {data.map((item) => (
            <div key={item.name} className="flex items-center justify-between rounded-xl border border-tactical-border bg-tactical-elevated p-3 transition-colors hover:border-tactical-border-emphasis">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }}></div>
                <span className="text-[13px] font-medium text-tactical-text">{item.name}</span>
              </div>
              <div className="text-right">
                <span className="num text-[15px] font-semibold text-tactical-text">{item.value}</span>
                <span className="num ml-1 text-[12px] text-tactical-muted">({((item.value / total) * 100).toFixed(1)}%)</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
