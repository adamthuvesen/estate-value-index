"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { ConstructionEraDistribution } from "@/lib/area-types";
import { formatRawNumber } from "@/lib/format";

interface ConstructionEraChartProps {
  construction_era: ConstructionEraDistribution;
}

const ERA_COLORS: Record<string, string> = {
  "Pre-1900": "#ff4444",
  "1900-1950": "#ff3333",
  "1950-1980": "#808080",
  "1980-2000": "#00cc6a",
  "2000+": "#00ff88",
};

const ERA_ORDER = ["Pre-1900", "1900-1950", "1950-1980", "1980-2000", "2000+"];

export function ConstructionEraChart({ construction_era }: ConstructionEraChartProps) {
  if (!construction_era.median_year || Object.keys(construction_era.era_distribution).length === 0) {
    return (
      <div className="flex items-center justify-center rounded-tactical bg-tactical-elevated border border-tactical-border p-8">
        <p className="text-xs font-mono text-tactical-muted uppercase">No construction era data available</p>
      </div>
    );
  }

  const data = ERA_ORDER.filter((era) => construction_era.era_distribution[era])
    .map((era) => ({
      era,
      count: construction_era.era_distribution[era],
      color: ERA_COLORS[era] || "#64748b",
    }))
    .sort((a, b) => ERA_ORDER.indexOf(a.era) - ERA_ORDER.indexOf(b.era));

  const total = data.reduce((sum, item) => sum + item.count, 0);

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-lg font-semibold tracking-tactical text-tactical-text font-mono uppercase">Building Age Distribution</h3>
        <p className="text-xs text-tactical-muted font-mono tracking-tactical">PROPERTIES BY CONSTRUCTION ERA</p>
      </div>

      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
          <p className="tactical-label">Median Built Year</p>
          <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">{construction_era.median_year}</p>
        </div>
        <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
          <p className="tactical-label">Average Age</p>
          <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">
            {construction_era.avg_age ? `${construction_era.avg_age} YRS` : "N/A"}
          </p>
        </div>
        <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
          <p className="tactical-label">Oldest Building</p>
          <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">{construction_era.oldest || "N/A"}</p>
        </div>
        <div className="rounded-tactical bg-tactical-elevated border border-tactical-border p-4">
          <p className="tactical-label">Newest Building</p>
          <p className="mt-2 text-2xl font-bold text-tactical-text font-mono">{construction_era.newest || "N/A"}</p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis dataKey="era" stroke="#808080" style={{ fontSize: "10px", fontFamily: "JetBrains Mono, monospace" }} angle={-15} textAnchor="end" height={60} />
          <YAxis stroke="#808080" style={{ fontSize: "10px", fontFamily: "JetBrains Mono, monospace" }} width={50} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f0f0f",
              border: "1px solid #404040",
              borderRadius: "4px",
              boxShadow: "0 0 15px rgba(255,51,51,0.2)",
              fontFamily: "JetBrains Mono, monospace",
            }}
            formatter={(value: number) => [
              `${formatRawNumber(value)} PROPERTIES (${((value / total) * 100).toFixed(1)}%)`,
              "COUNT",
            ]}
            labelStyle={{ fontWeight: 600, color: "#e0e0e0", fontSize: "10px", textTransform: "uppercase" }}
          />
          <Bar dataKey="count" radius={[8, 8, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((item) => (
          <div key={item.era} className="flex items-center justify-between rounded-tactical border border-tactical-border bg-tactical-elevated p-3 hover:border-tactical-border-emphasis transition-colors duration-tactical">
            <div className="flex items-center gap-3">
              <div className="h-4 w-4 rounded" style={{ backgroundColor: item.color }}></div>
              <span className="text-xs font-mono font-medium text-tactical-text">{item.era}</span>
            </div>
            <div className="text-right">
              <span className="text-lg font-bold text-tactical-text font-mono">{formatRawNumber(item.count)}</span>
              <span className="ml-1 text-xs text-tactical-muted font-mono">({((item.count / total) * 100).toFixed(1)}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
