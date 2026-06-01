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
      <div className="flex items-center justify-center rounded-tactical bg-tactical-elevated border border-tactical-border p-8">
        <p className="text-xs font-mono text-tactical-muted uppercase">Insufficient historical price data</p>
      </div>
    );
  }

  const data = baseData.map((d) => ({
    ...d,
    displayValue: showPerSqm && avgLivingArea ? Math.round(d.price! / avgLivingArea) : d.price!,
  }));

  const formatPrice = (value: number) => {
    if (showPerSqm) {
      return formatShortThousands(value);
    }
    return formatShortSek(value);
  };

  const formatTooltipPrice = (value: number) => {
    return showPerSqm ? formatSekPerSqm(value) : formatSek(value);
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
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold tracking-tactical text-tactical-text font-mono uppercase">Price Trend</h3>
          <p className="text-xs text-tactical-muted font-mono tracking-tactical">
            {showPerSqm ? "MEDIAN PRICE PER M² OVER TIME" : "MEDIAN SOLD PRICES OVER TIME"}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {avgLivingArea && (
            <div className="flex items-center gap-2 rounded-tactical bg-tactical-elevated border border-tactical-border p-1">
              <button
                onClick={() => setShowPerSqm(true)}
                className={`rounded-tactical px-3 py-1.5 text-xs font-mono font-medium transition-all duration-tactical uppercase ${
                  showPerSqm
                    ? "bg-tactical-accent text-tactical-bg border border-tactical-accent"
                    : "text-tactical-muted hover:text-tactical-text border border-transparent"
                }`}
              >
                Price/m²
              </button>
              <button
                onClick={() => setShowPerSqm(false)}
                className={`rounded-tactical px-3 py-1.5 text-xs font-mono font-medium transition-all duration-tactical uppercase ${
                  !showPerSqm
                    ? "bg-tactical-accent text-tactical-bg border border-tactical-accent"
                    : "text-tactical-muted hover:text-tactical-text border border-transparent"
                }`}
              >
                Total Price
              </button>
            </div>
          )}
          {actualDataPoints.length >= 2 && (
            <div className="text-right">
              <p className="tactical-label">
                {actualDataPoints[actualDataPoints.length - 1].monthsAgo === 1 && actualDataPoints[0].monthsAgo === 12
                  ? "12-Month Change"
                  : `${actualDataPoints[0].monthsAgo}-Month Change`}
              </p>
              <p className={`text-2xl font-bold font-mono ${isPositive ? "text-tactical-success" : "text-tactical-accent"}`}>
                {isPositive ? "+" : ""}
                {priceChange.toFixed(1)}%
              </p>
            </div>
          )}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data} margin={{ top: 5, right: 20, bottom: 20, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a2a" />
          <XAxis
            dataKey="month"
            stroke="#808080"
            style={{ fontSize: "10px", fontFamily: "JetBrains Mono, monospace" }}
            interval={0}
            angle={-45}
            textAnchor="end"
            height={60}
          />
          <YAxis tickFormatter={formatPrice} stroke="#808080" style={{ fontSize: "10px", fontFamily: "JetBrains Mono, monospace" }} width={80} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#0f0f0f",
              border: "1px solid #404040",
              borderRadius: "4px",
              boxShadow: "0 0 15px rgba(255,51,51,0.2)",
              fontFamily: "JetBrains Mono, monospace",
            }}
            formatter={(value: number) => [formatTooltipPrice(value), showPerSqm ? "MEDIAN PRICE/M²" : "MEDIAN PRICE"]}
            labelFormatter={(label) => {
              const point = data.find((d) => d.month === label);
              return point ? `${label} (${point.label})` : label;
            }}
            labelStyle={{ fontWeight: 600, color: "#e0e0e0", fontSize: "10px", textTransform: "uppercase" }}
          />
          <Line
            type="monotone"
            dataKey="displayValue"
            stroke="#00ff88"
            strokeWidth={2}
            dot={{ fill: "#00ff88", r: 3 }}
            activeDot={{ r: 6 }}
            name={showPerSqm ? "Median Price/m²" : "Median Price"}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
