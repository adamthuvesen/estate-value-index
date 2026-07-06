"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, Tooltip, ResponsiveContainer } from "recharts";
import type { PriceBySizeBucket } from "@/lib/area-types";
import { formatRawNumber, formatSek, formatShortThousands } from "@/lib/format";

interface SizePriceChartProps {
  price_by_size: PriceBySizeBucket[];
}

// Light -> dark blue ramp so larger bands read as deeper bars.
const SIZE_COLORS = [
  "#9EC1FF",
  "#79A8FF",
  "#5490FF",
  "#2F78FF",
  "#0B62FF",
  "#0A54DB",
  "#0846B7",
  "#063893",
  "#052B70",
];

export function SizePriceChart({ price_by_size }: SizePriceChartProps) {
  const data = price_by_size ?? [];

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-lg border border-tactical-border bg-tactical-elevated p-8">
        <p className="text-[13px] text-tactical-muted">No size data available.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-3">
        <h3 className="text-[14px] font-semibold tracking-tight text-tactical-text">Sold price by size</h3>
        <p className="text-[12px] text-tactical-muted">Median sold price across living-area bands (m²)</p>
      </div>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#EDEDE9" />
          <XAxis
            dataKey="bucket"
            stroke="#E9E9E4"
            tick={{ fill: "#63666E", fontSize: 11 }}
            label={{ value: "Living area (m²)", position: "insideBottom", offset: -2, fill: "#8A8D94", fontSize: 11 }}
            height={34}
          />
          <YAxis
            tickFormatter={formatShortThousands}
            stroke="#E9E9E4"
            tick={{ fill: "#63666E", fontSize: 11 }}
            width={48}
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
            formatter={(value: number, _name, item) => [
              `${formatSek(value)} · ${formatRawNumber(item?.payload?.count ?? 0)} sold`,
              "Median price",
            ]}
            labelFormatter={(label: string) => `${label} m²`}
            labelStyle={{ fontWeight: 600, color: "#63666E", marginBottom: 8, fontSize: 12 }}
            itemStyle={{ color: "#16171A", fontSize: 13, fontWeight: 600 }}
          />
          <Bar dataKey="median_price" radius={[6, 6, 0, 0]} name="Median price">
            {data.map((entry, index) => (
              <Cell key={entry.bucket} fill={SIZE_COLORS[index % SIZE_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-tactical-border">
            <tr>
              <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Size (m²)</th>
              <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Median price</th>
              <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Properties</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-tactical-border">
            {data.map((row) => (
              <tr key={row.bucket} className="transition-colors hover:bg-tactical-elevated/50">
                <td className="px-4 py-2 text-[13px] font-medium text-tactical-text">{row.bucket}</td>
                <td className="num px-4 py-2 text-right text-[13px] text-tactical-text">{formatSek(row.median_price)}</td>
                <td className="num px-4 py-2 text-right text-[13px] text-tactical-muted">{formatRawNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
