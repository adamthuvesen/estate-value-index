"use client";

import { BarChart, Bar, XAxis, YAxis, Cell, LabelList, ResponsiveContainer } from "recharts";
import type { PriceBySizeBucket } from "@/lib/area-types";
import { ChartEmpty } from "@/components/charts/chart-theme";
import { formatRawNumber, formatSek, formatShortThousands } from "@/lib/format";

interface SizePriceChartProps {
  price_by_size: PriceBySizeBucket[];
  view: "chart" | "table";
}

const HEIGHT = 220;
const LOW_COUNT = 3;

/** Fig. 3 — median sold price across living-area bands. One hue; buckets with
 *  fewer than 3 sales are muted (thin evidence). Chart ⇄ Table via the frame. */
export function SizePriceChart({ price_by_size, view }: SizePriceChartProps) {
  const data = price_by_size ?? [];

  if (data.length === 0) {
    return <ChartEmpty message="No size data available." height={HEIGHT} />;
  }

  if (view === "table") {
    return (
      <div className="-mx-4 overflow-x-auto sm:-mx-5">
        <table className="w-full min-w-[24rem] border-collapse">
          <thead>
            <tr className="border-b border-ledger-border-emphasis">
              <th className="px-4 py-2 text-left eyebrow text-ledger-dimmed">Size (m²)</th>
              <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">Median price</th>
              <th className="px-4 py-2 text-right eyebrow text-ledger-dimmed">Sold</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ledger-border">
            {data.map((row) => (
              <tr key={row.bucket} className="transition-colors hover:bg-ledger-elevated/50">
                <td className="px-4 py-2 text-body-sm font-medium text-ledger-text">
                  {row.bucket}
                </td>
                <td className="num px-4 py-2 text-right text-body-sm text-ledger-text">
                  {formatSek(row.median_price)}
                </td>
                <td className="num px-4 py-2 text-right text-body-sm text-ledger-muted">
                  {formatRawNumber(row.count)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

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
    const value = Number(props.value ?? 0);
    return (
      <text
        x={x + width / 2}
        y={y - 6}
        textAnchor="middle"
        fontSize={11}
        fontWeight={600}
        className="num"
        fill="var(--color-ledger-text)"
      >
        {formatShortThousands(value)}
      </text>
    );
  };

  return (
    <ResponsiveContainer width="100%" height={HEIGHT}>
      <BarChart data={data} margin={{ top: 22, right: 12, bottom: 4, left: 12 }}>
        <XAxis
          dataKey="bucket"
          tick={{ fill: "var(--color-ledger-muted)", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          interval={0}
        />
        <YAxis hide />
        <Bar dataKey="median_price" radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {data.map((entry) => (
            <Cell
              key={entry.bucket}
              fill="var(--color-ledger-accent)"
              fillOpacity={entry.count < LOW_COUNT ? 0.4 : 1}
            />
          ))}
          <LabelList dataKey="median_price" content={renderLabel} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
