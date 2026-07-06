"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { PricePerSqmByRooms } from "@/lib/area-types";
import { formatRawNumber, formatSekPerSqm, formatShortThousands } from "@/lib/format";

interface RoomComparisonChartProps {
  price_per_sqm_by_rooms: PricePerSqmByRooms;
}

const ROOM_COLORS: Record<string, string> = {
  "1": "#0B62FF",
  "2": "#0B62FF",
  "3": "#0B62FF",
  "4+": "#0B62FF",
};

export function RoomComparisonChart({ price_per_sqm_by_rooms }: RoomComparisonChartProps) {
  const roomOrder = ["1", "2", "3", "4+"];
  const data = roomOrder
    .filter((roomKey) => price_per_sqm_by_rooms[roomKey])
    .map((roomKey) => {
      const stats = price_per_sqm_by_rooms[roomKey];
      return {
        rooms: `${roomKey} Room${roomKey !== "1" ? "s" : ""}`,
        roomKey,
        median: stats.median,
        mean: stats.mean,
        count: stats.count,
        min: stats.min,
        max: stats.max,
      };
    });

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-tactical-border bg-tactical-elevated p-8">
        <p className="text-[13px] text-tactical-muted">No room comparison data available.</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-[17px] font-semibold tracking-tight text-tactical-text">Price per m² by room count</h3>
        <p className="text-[13px] text-tactical-muted">Median prices across different property sizes</p>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#EDEDE9" />
          <XAxis dataKey="rooms" stroke="#E9E9E4" tick={{ fill: "#63666E", fontSize: 11 }} />
          <YAxis tickFormatter={formatShortThousands} stroke="#E9E9E4" tick={{ fill: "#63666E", fontSize: 11 }} width={60} />
          <Tooltip
            cursor={{ fill: "rgba(11,98,255,0.06)" }}
            contentStyle={{
              backgroundColor: "#FFFFFF",
              border: "1px solid #E9E9E4",
              borderRadius: "10px",
              boxShadow: "0 4px 14px rgba(16,17,20,0.08)",
              color: "#16171A",
            }}
            formatter={(value: number) => [formatSekPerSqm(value), "Median price/m²"]}
            labelStyle={{ fontWeight: 600, color: "#63666E", marginBottom: 8, fontSize: 12 }}
            itemStyle={{ color: "#16171A", fontSize: 13, fontWeight: 600 }}
          />
          <Bar dataKey="median" radius={[6, 6, 0, 0]} name="Median Price/m²">
            {data.map((entry) => (
              <Cell key={`cell-${entry.roomKey}`} fill={ROOM_COLORS[entry.roomKey] || "#0B62FF"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full">
          <thead className="border-b border-tactical-border">
            <tr>
              <th className="px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Rooms</th>
              <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Median</th>
              <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Average</th>
              <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Range</th>
              <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">Properties</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-tactical-border">
            {data.map((row) => (
              <tr key={row.roomKey} className="transition-colors hover:bg-tactical-elevated/50">
                <td className="px-4 py-2 text-[13px] font-medium text-tactical-text">{row.rooms}</td>
                <td className="num px-4 py-2 text-right text-[13px] text-tactical-text">{formatSekPerSqm(row.median)}</td>
                <td className="num px-4 py-2 text-right text-[13px] text-tactical-muted">{formatSekPerSqm(row.mean)}</td>
                <td className="num px-4 py-2 text-right text-[13px] text-tactical-muted">
                  {formatShortThousands(row.min)} – {formatShortThousands(row.max)}
                </td>
                <td className="num px-4 py-2 text-right text-[13px] text-tactical-text">{formatRawNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
