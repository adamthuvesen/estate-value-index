"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { ConstructionEraDistribution } from "@/lib/area-types";
import { formatRawNumber } from "@/lib/format";

interface ConstructionEraChartProps {
  construction_era: ConstructionEraDistribution;
}

// Chronological ramp (old -> new): violet, blue, cyan, green, amber.
const ERA_COLORS: Record<string, string> = {
  "Pre-1900": "#7C5CFC",
  "1900-1950": "#0B62FF",
  "1950-1980": "#0891B2",
  "1980-2000": "#2E8B57",
  "2000+": "#C2681C",
};

const ERA_ORDER = ["Pre-1900", "1900-1950", "1950-1980", "1980-2000", "2000+"];

export function ConstructionEraChart({ construction_era }: ConstructionEraChartProps) {
  if (!construction_era.median_year || Object.keys(construction_era.era_distribution).length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-tactical-border bg-tactical-elevated p-8">
        <p className="text-[13px] text-tactical-muted">No construction era data available.</p>
      </div>
    );
  }

  const data = ERA_ORDER.filter((era) => construction_era.era_distribution[era])
    .map((era) => ({
      era,
      count: construction_era.era_distribution[era],
      color: ERA_COLORS[era] || "#0B62FF",
    }))
    .sort((a, b) => ERA_ORDER.indexOf(a.era) - ERA_ORDER.indexOf(b.era));

  const total = data.reduce((sum, item) => sum + item.count, 0);

  return (
    <div>
      <div className="mb-3">
        <h3 className="text-[14px] font-semibold tracking-tight text-tactical-text">Building age distribution</h3>
        <p className="text-[12px] text-tactical-muted">Properties by construction era</p>
      </div>

      <div className="mb-4 grid gap-2 sm:grid-cols-4">
        <div className="rounded-lg border border-tactical-border bg-tactical-elevated px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Median built year</p>
          <p className="num mt-1 text-lg font-semibold text-tactical-text">{construction_era.median_year}</p>
        </div>
        <div className="rounded-lg border border-tactical-border bg-tactical-elevated px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Average age</p>
          <p className="num mt-1 text-lg font-semibold text-tactical-text">
            {construction_era.avg_age ? `${construction_era.avg_age} yrs` : "—"}
          </p>
        </div>
        <div className="rounded-lg border border-tactical-border bg-tactical-elevated px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Oldest building</p>
          <p className="num mt-1 text-lg font-semibold text-tactical-text">{construction_era.oldest || "—"}</p>
        </div>
        <div className="rounded-lg border border-tactical-border bg-tactical-elevated px-3 py-2.5">
          <p className="text-[10px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Newest building</p>
          <p className="num mt-1 text-lg font-semibold text-tactical-text">{construction_era.newest || "—"}</p>
        </div>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#EDEDE9" />
          <XAxis dataKey="era" stroke="#E9E9E4" tick={{ fill: "#63666E", fontSize: 11 }} angle={-15} textAnchor="end" height={60} />
          <YAxis stroke="#E9E9E4" tick={{ fill: "#63666E", fontSize: 11 }} width={50} />
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
          <Bar dataKey="count" radius={[6, 6, 0, 0]}>
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {data.map((item) => (
          <div key={item.era} className="flex items-center justify-between rounded-lg border border-tactical-border bg-tactical-elevated px-3 py-2 transition-colors hover:border-tactical-border-emphasis">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 rounded-full" style={{ backgroundColor: item.color }}></div>
              <span className="text-[13px] font-medium text-tactical-text">{item.era}</span>
            </div>
            <div className="text-right">
              <span className="num text-[15px] font-semibold text-tactical-text">{formatRawNumber(item.count)}</span>
              <span className="num ml-1 text-[12px] text-tactical-muted">({((item.count / total) * 100).toFixed(1)}%)</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
