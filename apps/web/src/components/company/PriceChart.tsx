import React, { useEffect, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, CandlestickData, ColorType } from "lightweight-charts";

export interface PriceChartProps {
  /**
   * Array of price bar data. Each entry should contain
   * `time` (unix timestamp or ISO string), `open`, `high`, `low`, `close`.
   */
  prices: CandlestickData[];
  /**
   * Optional width/height – defaults to fill parent.
   */
  width?: number;
  height?: number;
}

const PriceChart: React.FC<PriceChartProps> = ({ prices, width = 600, height = 300 }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;
    // Create chart only once
    const chart = createChart(chartContainerRef.current, {
      width,
      height,
      layout: { background: { type: ColorType.Solid, color: "#ffffff" } },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    });
    const series = chart.addCandlestickSeries();
    series.setData(prices);
    chartRef.current = chart;
    seriesRef.current = series;
    return () => {
      chart.remove();
    };
  }, [prices, width, height]);

  // Resize handling – simple approach
  useEffect(() => {
    const handleResize = () => {
      if (chartRef.current) {
        chartRef.current.applyOptions({ width, height });
        chartRef.current.timeScale().fitContent();
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [width, height]);

  return (
    <div
      ref={chartContainerRef}
      style={{ width: `${width}px`, height: `${height}px` }}
      data-test="price-chart"
    />
  );
};

export default PriceChart;
