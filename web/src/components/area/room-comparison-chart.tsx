"use client";

import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { PricePerSqmByRooms } from "@/lib/area-types";
import { formatRawNumber, formatSekPerSqm, formatShortThousands } from "@/lib/format";

interface RoomComparisonChartProps {
  price_per_sqm_by_rooms: PricePerSqmByRooms;
}

const ROOM_COLORS: Record<string, string> = {
  "1": "#00ff88",
  "2": "#00cc6a",
  "3": "#ff3333",
  "4+": "#ff4444",
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
      <div className="flex items-center justify-center rounded-tactical bg-tactical-elevated border border-tactical-border p-8">
        <p className="text-xs font-mono text-tactical-muted uppercase">No room comparison data available</p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-lg font-semibold tracking-tactical text-tactical-text font-mono uppercase">Price per M² by Room Count</h3>
        <p className="text-xs text-tactical-muted font-mono tracking-tactical">MEDIAN PRICES ACROSS DIFFERENT PROPERTY SIZES</p>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis dataKey="rooms" stroke="#808080" style={{ fontSize: "10px", fontFamily: "JetBrains Mono, monospace" }} />
          <YAxis tickFormatter={formatShortThousands} stroke="#808080" style={{ fontSize: "10px", fontFamily: "JetBrains Mono, monospace" }} width={60} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f0f0f",
              border: "1px solid #404040",
              borderRadius: "4px",
              boxShadow: "0 0 15px rgba(255,51,51,0.2)",
              fontFamily: "JetBrains Mono, monospace",
            }}
            formatter={(value: number) => [formatSekPerSqm(value), "MEDIAN PRICE/M²"]}
            labelStyle={{ fontWeight: 600, color: "#e0e0e0", marginBottom: "8px", fontSize: "10px", textTransform: "uppercase" }}
            itemStyle={{ color: "#e0e0e0", fontSize: "11px", fontWeight: 600 }}
          />
          <Bar dataKey="median" radius={[8, 8, 0, 0]} name="Median Price/m²">
            {data.map((entry) => (
              <Cell key={`cell-${entry.roomKey}`} fill={ROOM_COLORS[entry.roomKey] || "#16a34a"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="border-b border-tactical-border-emphasis bg-tactical-surface">
            <tr>
              <th className="px-4 py-2 text-left tactical-label">Rooms</th>
              <th className="px-4 py-2 text-right tactical-label">Median</th>
              <th className="px-4 py-2 text-right tactical-label">Average</th>
              <th className="px-4 py-2 text-right tactical-label">Range</th>
              <th className="px-4 py-2 text-right tactical-label">Properties</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-tactical-border">
            {data.map((row) => (
              <tr key={row.roomKey} className="hover:bg-tactical-surface transition-colors duration-tactical">
                <td className="px-4 py-2 font-medium text-tactical-text font-mono text-xs">{row.rooms}</td>
                <td className="px-4 py-2 text-right tabular-nums text-tactical-text font-mono text-xs">{formatSekPerSqm(row.median)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-tactical-muted font-mono text-xs">{formatSekPerSqm(row.mean)}</td>
                <td className="px-4 py-2 text-right tabular-nums text-tactical-muted font-mono text-xs">
                  {formatShortThousands(row.min)} - {formatShortThousands(row.max)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-tactical-text font-mono text-xs">{formatRawNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
