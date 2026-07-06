"use client";

import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { formatSek, formatSekPerSqm, formatShortSek, formatShortThousands } from "@/lib/format";

interface PriceTrendChartProps {
  median_price_3m: number | null;
  median_price_6m: number | null;
  median_price_12m: number | null;
  monthly_prices?: {
    month_1?: number | null;
    month_2?: number | null;
    month_3?: number | null;
    month_4?: number | null;
    month_5?: number | null;
    month_6?: number | null;
    month_7?: number | null;
    month_8?: number | null;
    month_9?: number | null;
    month_10?: number | null;
    month_11?: number | null;
    month_12?: number | null;
  };
  avgLivingArea?: number | null;
}

export function PriceTrendChart({ median_price_3m, median_price_6m, median_price_12m, monthly_prices, avgLivingArea }: PriceTrendChartProps) {
  const [showPerSqm, setShowPerSqm] = useState(true);
  const canShowPerSqm = Boolean(avgLivingArea && avgLivingArea > 0);
  const displayPerSqm = showPerSqm && canShowPerSqm;
  const unitLabel = displayPerSqm ? "kr/m²" : "kr";
  const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const now = new Date();
  const currentMonth = now.getMonth();

  // Build 12-month timeline; prefer monthly_prices, fall back to 3m/6m/12m medians
  const monthlyData: Array<{ month: string, price: number | null, monthsAgo: number, label: string, hasData: boolean }> = [];

  for (let i = 12; i >= 1; i--) {
    const monthIndex = (currentMonth - i + 12) % 12;
    const monthLabel = monthNames[monthIndex];

    let price: number | null = null;
    let hasData = false;

    if (monthly_prices && monthly_prices[`month_${i}` as keyof typeof monthly_prices]) {
      price = monthly_prices[`month_${i}` as keyof typeof monthly_prices] as number;
      hasData = true;
    } else if (i === 12) {
      price = median_price_12m;
      hasData = price !== null;
    } else if (i === 6) {
      price = median_price_6m;
      hasData = price !== null;
    } else if (i === 3) {
      price = median_price_3m;
      hasData = price !== null;
    }

    monthlyData.push({
      month: monthLabel,
      price,
      monthsAgo: i,
      label: i === 1 ? "Last month" : `${i}mo ago`,
      hasData
    });
  }

  // Forward-fill, then backward-fill, missing months
  let lastKnownPrice: number | null = null;
  for (let i = 0; i < monthlyData.length; i++) {
    if (monthlyData[i].price !== null) {
      lastKnownPrice = monthlyData[i].price;
    } else if (lastKnownPrice !== null) {
      monthlyData[i].price = lastKnownPrice;
    }
  }
  for (let i = monthlyData.length - 1; i >= 0; i--) {
    if (monthlyData[i].price !== null) {
      lastKnownPrice = monthlyData[i].price;
    } else if (lastKnownPrice !== null) {
      monthlyData[i].price = lastKnownPrice;
    }
  }

  const baseData = monthlyData.filter((d) => d.price !== null);

  if (baseData.length === 0) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-tactical-border bg-tactical-elevated p-8">
        <p className="text-[13px] text-tactical-muted">Not enough historical price data.</p>
      </div>
    );
  }

  const data = baseData.map((d) => ({
    ...d,
    displayValue: displayPerSqm ? Math.round(d.price! / avgLivingArea!) : d.price!,
  }));

  const formatPrice = (value: number) => {
    if (displayPerSqm) {
      return formatShortThousands(value);
    }
    return formatShortSek(value);
  };

  const formatTooltipPrice = (value: number) => {
    return displayPerSqm ? formatSekPerSqm(value) : formatSek(value);
  };

  // Use only real data points (not filled) for the change calculation
  const actualDataPoints = data.filter(d => d.hasData);
  let priceChange = 0;
  let isPositive = false;

  if (actualDataPoints.length >= 2) {
    const earliestPoint = actualDataPoints[0];
    const latestPoint = actualDataPoints[actualDataPoints.length - 1];
    priceChange = ((latestPoint.displayValue! - earliestPoint.displayValue!) / earliestPoint.displayValue!) * 100;
    isPositive = priceChange > 0;
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="text-[14px] font-semibold tracking-tight text-tactical-text">Price trend</h3>
          <p className="text-[12px] text-tactical-muted">
            {displayPerSqm ? "Median price per m² over time" : "Median sold prices over time"}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {canShowPerSqm && (
            <div className="flex items-center gap-1 rounded-pill border border-tactical-border bg-tactical-elevated p-1">
              <button
                onClick={() => setShowPerSqm(true)}
                className={`rounded-pill px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  showPerSqm
                    ? "bg-tactical-text text-white"
                    : "text-tactical-muted hover:text-tactical-text"
                }`}
              >
                Price/m²
              </button>
              <button
                onClick={() => setShowPerSqm(false)}
                className={`rounded-pill px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  !showPerSqm
                    ? "bg-tactical-text text-white"
                    : "text-tactical-muted hover:text-tactical-text"
                }`}
              >
                Total price
              </button>
            </div>
          )}
          {actualDataPoints.length >= 2 && (
            <div className="text-right">
              <p className="text-[11px] font-semibold uppercase tracking-tactical-wide text-tactical-dimmed">
                {actualDataPoints[actualDataPoints.length - 1].monthsAgo === 1 && actualDataPoints[0].monthsAgo === 12
                  ? "12-month change"
                  : `${actualDataPoints[0].monthsAgo}-month change`}
              </p>
              <p className={`num text-lg font-semibold ${isPositive ? "text-val-exc" : "text-val-high"}`}>
                {isPositive ? "+" : ""}
                {priceChange.toFixed(1)}%
              </p>
            </div>
          )}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={data} margin={{ top: 5, right: 20, bottom: 20, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#EDEDE9" />
          <XAxis
            dataKey="month"
            stroke="#E9E9E4"
            tick={{ fill: "#63666E", fontSize: 11 }}
            interval={0}
            angle={-45}
            textAnchor="end"
            height={60}
          />
          <YAxis
            tickFormatter={formatPrice}
            stroke="#E9E9E4"
            tick={{ fill: "#63666E", fontSize: 11 }}
            width={80}
            label={{
              value: unitLabel,
              angle: -90,
              position: "insideLeft",
              fill: "#63666E",
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#FFFFFF",
              border: "1px solid #E9E9E4",
              borderRadius: "10px",
              boxShadow: "0 4px 14px rgba(16,17,20,0.08)",
              color: "#16171A",
            }}
            formatter={(value: number) => [formatTooltipPrice(value), displayPerSqm ? "Median price/m²" : "Median price"]}
            labelFormatter={(label) => {
              const point = data.find((d) => d.month === label);
              return point ? `${label} (${point.label})` : label;
            }}
            labelStyle={{ fontWeight: 600, color: "#63666E", fontSize: 12 }}
            itemStyle={{ color: "#16171A", fontSize: 13 }}
          />
          <Line
            type="monotone"
            dataKey="displayValue"
            stroke="#0B62FF"
            strokeWidth={2}
            dot={{ fill: "#0B62FF", r: 3 }}
            activeDot={{ r: 6 }}
            name={displayPerSqm ? "Median price/m²" : "Median price"}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
