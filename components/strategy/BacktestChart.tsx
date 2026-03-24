"use client";

import { useRef, useEffect, useMemo, useCallback } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  ColorType,
  UTCTimestamp,
  LineSeries,
  AreaSeries,
  LineStyle,
  HistogramSeries,
  LineType,
  SeriesMarker,
} from "lightweight-charts";

export interface EquityDataPoint {
  time: string; // YYYY-MM-DD
  equity: number;
  buyHold?: number;
}

export interface DrawdownDataPoint {
  time: string; // YYYY-MM-DD
  drawdown: number;
}

export interface MonthlyReturnDataPoint {
  time: string; // YYYY-MM-DD
  value: number; // Percentage
}

export interface SeasonalDataPoint {
  year: string;
  data: MonthlyReturnDataPoint[];
}

interface BacktestChartProps {
  type: "equity" | "drawdown" | "monthly_returns" | "seasonal_returns";
  equityData?: EquityDataPoint[];
  drawdownData?: DrawdownDataPoint[];
  monthlyData?: MonthlyReturnDataPoint[];
  seasonalData?: SeasonalDataPoint[];
  trades?: { date: string; type: string; price: number | string }[];
  height?: number;
}

// Convert YYYY-MM-DD to timestamp
const dateToTimestamp = (dateStr: string): UTCTimestamp => {
  const date = new Date(dateStr + "T00:00:00Z");
  return (date.getTime() / 1000) as UTCTimestamp;
};

// Format price to compact Korean format
const formatCompactPrice = (price: number): string => {
  if (price >= 100000000) {
    // 1억 이상
    return `${(price / 100000000).toFixed(1)}억`;
  } else if (price >= 10000) {
    // 1만 이상
    return `${(price / 10000).toFixed(0)}만`;
  } else if (price >= 1000) {
    // 1천 이상
    return `${(price / 1000).toFixed(1)}천`;
  }
  return price.toFixed(0);
};

export default function BacktestChart({
  type,
  equityData = [],
  drawdownData = [],
  monthlyData = [],
  seasonalData = [],
  trades = [],
  height = 400,
}: BacktestChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const equitySeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const buyHoldSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const drawdownSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const monthlySeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const seasonalSeriesRefs = useRef<Record<string, ISeriesApi<"Line">>>({});
  const tooltipRef = useRef<HTMLDivElement>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);

  // Prepare equity chart data
  const equityChartData = useMemo(() => {
    if (equityData.length === 0) return [];
    return equityData
      .filter((item) => isFinite(item.equity))
      .map((item) => ({
        time: dateToTimestamp(item.time),
        value: item.equity,
      }));
  }, [equityData]);

  const buyHoldChartData = useMemo(() => {
    if (equityData.length === 0) return [];
    return equityData
      .filter((item) => item.buyHold !== undefined && isFinite(item.buyHold!))
      .map((item) => ({
        time: dateToTimestamp(item.time),
        value: item.buyHold!,
      }));
  }, [equityData]);

  // Prepare drawdown chart data
  const drawdownChartData = useMemo(() => {
    if (drawdownData.length === 0) return [];
    return drawdownData
      .filter((item) => isFinite(item.drawdown))
      .map((item) => ({
        time: dateToTimestamp(item.time),
        value: item.drawdown,
      }));
  }, [drawdownData]);

  // Prepare monthly return chart data
  const monthlyChartData = useMemo(() => {
    if (type !== "monthly_returns" || !monthlyData || monthlyData.length === 0) return [];
    return monthlyData.map((item) => ({
      time: dateToTimestamp(item.time),
      value: item.value,
      color: item.value >= 0 ? "rgba(239, 68, 68, 0.8)" : "rgba(55, 122, 244, 0.8)", // red for gain, blue for loss
    }));
  }, [type, monthlyData]);

  const YEAR_COLORS = useMemo(() => [
    "#ef4444", "#377af4", "#22c55e", "#eab308", "#a855f7", 
    "#f97316", "#06b6d4", "#ec4899", "#8b5cf6", "#10b981"
  ], []);

  // Prepare seasonal chart data (normalized to a single year)
  const seasonalChartData = useMemo(() => {
    if (type !== "seasonal_returns" || !seasonalData) return {};
    
    const res: Record<string, { time: UTCTimestamp, value: number }[]> = {};
    const refYear = 2024; // Normalized year
    
    seasonalData.forEach((yearData: SeasonalDataPoint) => {
      res[yearData.year] = yearData.data.map((item: MonthlyReturnDataPoint) => {
        const parts = item.time.split('-');
        const normalizedDateStr = `${refYear}-${parts[1]}-01`;
        return {
          time: dateToTimestamp(normalizedDateStr),
          value: item.value,
        };
      }).filter((d) => isFinite(d.value) && isFinite(d.time as number))
        .sort((a: {time: UTCTimestamp}, b: {time: UTCTimestamp}) => (a.time as number) - (b.time as number));
    });
    return res;
  }, [type, seasonalData]);

  // Handle resize
  const handleResize = useCallback(() => {
    if (chartContainerRef.current && chartRef.current) {
      const width = chartContainerRef.current.clientWidth;
      const chartHeight = chartContainerRef.current.clientHeight;

      if (width > 0 && chartHeight > 0) {
        chartRef.current.applyOptions({
          width,
          height: chartHeight,
        });
      }
    }
  }, []);

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Clean up existing chart
    if (chartRef.current) {
      try {
        chartRef.current.remove();
      } catch (e) {
        console.warn("Error removing chart:", e);
      }
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    // Wait for container to have dimensions
    const initChart = () => {
      const width = container.clientWidth;
      const chartHeight = container.clientHeight || height;

      if (width === 0 || chartHeight === 0) {
        // Retry after a short delay
        setTimeout(initChart, 100);
        return;
      }

      try {
        const chart = createChart(container, {
          layout: {
            background: { type: ColorType.Solid, color: "#0a0a0a" },
            textColor: "#666",
            fontSize: 10,
          },
          // @ts-ignore - Lightweight charts supports padding in layout
          padding: { top: 4, bottom: 4, left: 8, right: 40 }, 
          grid: {
            vertLines: { color: "#374151", style: 1, visible: true },
            horzLines: { color: "#374151", style: 1, visible: true },
          },
          width,
          height: chartHeight,
          timeScale: {
            timeVisible: true,
            secondsVisible: false,
            borderColor: "#4b5563",
            tickMarkFormatter: (time: UTCTimestamp) => {
              const date = new Date((time as number) * 1000);
              if (type === "seasonal_returns") {
                 return `${date.getMonth() + 1}월`;
              }
              // Default formatting for other types
              return date.toISOString().split('T')[0];
            },
          },
          rightPriceScale: {
            borderColor: "#4b5563",
            autoScale: true,
            scaleMargins: {
              top: 0.2,
              bottom: 0.2,
            },
            alignLabels: true,
          },
          localization: {
            timeFormatter: (timestamp: number) => {
              const date = new Date(timestamp * 1000);
              if (type === "seasonal_returns") {
                 return `${date.getMonth() + 1}월`;
              }
              return date.toISOString().split('T')[0];
            },
          },
        });

        // Verify chart was created successfully
        if (!chart || typeof chart.addSeries !== "function") {
          console.error("Chart creation failed or API mismatch");
          return;
        }

        chartRef.current = chart;

        if (type === "equity") {
          // Create equity line series with custom price format
          const equitySeries = chart.addSeries(LineSeries, {
            color: "rgb(239, 68, 68)", // main-red
            lineWidth: 1,
            lineType: LineType.Curved,
            priceFormat: {
              type: "custom",
              formatter: (price: number) => formatCompactPrice(price),
              tickmarksFormatter: (priceValues: number[]) => {
                return priceValues.map((price) => formatCompactPrice(price));
              },
              minMove: 1,
            },
          });
          equitySeriesRef.current = equitySeries;

          // Create buy & hold line series if data exists
          if (buyHoldChartData.length > 0) {
            const buyHoldSeries = chart.addSeries(LineSeries, {
              color: "rgb(34, 197, 94)", // main-green
              lineWidth: 1,
              lineStyle: LineStyle.Solid,
              lineType: LineType.Curved, // Smooth line
              priceFormat: {
                type: "custom",
                formatter: (price: number) => formatCompactPrice(price),
                tickmarksFormatter: (priceValues: number[]) => {
                  return priceValues.map((price) => formatCompactPrice(price));
                },
                minMove: 1,
              },
            });
            buyHoldSeriesRef.current = buyHoldSeries;
            buyHoldSeries.setData(buyHoldChartData);
          }

          // Set equity data
          if (equityChartData.length > 0) {
            equitySeries.setData(equityChartData);
            chart.timeScale().fitContent();
          }

          // Add trade markers
          if (trades && trades.length > 0) {
            const markers: SeriesMarker<UTCTimestamp>[] = trades
              .map((trade) => ({
                time: dateToTimestamp(trade.date),
                position: trade.type === "buy" ? "belowBar" as const : "aboveBar" as const,
                color: trade.type === "buy" ? "#ef4444" : "#377af4", // red for buy, blue for sell
                shape: trade.type === "buy" ? "arrowUp" as const : "arrowDown" as const,
                text: trade.type === "buy" ? "B" : "S",
              }))
              // sort markers by time to prevent lightweight-charts errors
              .sort((a, b) => (a.time as number) - (b.time as number));

            (equitySeries as any).setMarkers(markers);
          }
        } else if (type === "monthly_returns") {
          // Create monthly returns histogram series
          const monthlySeries = chart.addSeries(HistogramSeries, {
            priceFormat: {
              type: "price",
              precision: 2,
              minMove: 0.01,
            },
            priceScaleId: "right",
          });
          monthlySeriesRef.current = monthlySeries;

          if (monthlyChartData.length > 0) {
            monthlySeries.setData(monthlyChartData);
            chart.timeScale().fitContent();
          }
        } else if (type === "seasonal_returns") {
          // Seasonal charts are multiple line series
          const years = Object.keys(seasonalChartData).sort();
          years.forEach((year, idx) => {
            const series = chart.addSeries(LineSeries, {
              color: YEAR_COLORS[idx % YEAR_COLORS.length],
              lineWidth: 1, // Thinner for multiple lines
              lineType: LineType.Curved, // Make it smooth
              priceFormat: {
                type: "price",
                precision: 2,
                minMove: 0.01,
              },
              title: year,
            });
            seasonalSeriesRefs.current[year] = series;
            series.setData(seasonalChartData[year]);
          });
          chart.timeScale().fitContent();
        } else if (type === "drawdown") {
          // Create drawdown line series
          const drawdownSeries = chart.addSeries(LineSeries, {
            color: "rgb(239, 68, 68)", // main-red
            lineWidth: 1,
            lineType: LineType.Curved,
            priceFormat: {
              type: "price",
              precision: 2,
              minMove: 0.01,
            },
          });
          drawdownSeriesRef.current = drawdownSeries;

          // Set drawdown data
          if (drawdownChartData.length > 0) {
            drawdownSeries.setData(drawdownChartData);
            chart.timeScale().fitContent();
          }
        }

        // Tooltip logic
        const tooltip = tooltipRef.current;
        if (tooltip) {
          chart.subscribeCrosshairMove((param) => {
            if (
              param.point === undefined ||
              !param.time ||
              param.point.x < 0 ||
              param.point.x > container.clientWidth ||
              param.point.y < 0 ||
              param.point.y > container.clientHeight
            ) {
              tooltip.style.display = "none";
              return;
            }

            tooltip.style.display = "block";
            
            // Format time (month)
            const date = new Date((param.time as number) * 1000);
            const monthStr = `${date.getMonth() + 1}월`;
            
            let tooltipContent = `<div class="font-bold text-gray-400 mb-1 border-b border-gray-800 pb-1">${monthStr} 수익률</div>`;
            tooltipContent += `<div class="flex flex-col gap-1 mt-1">`;

            if (type === "seasonal_returns") {
              const years = Object.keys(seasonalSeriesRefs.current).sort().reverse();
              years.forEach((year, idx) => {
                const series = seasonalSeriesRefs.current[year];
                const data = param.seriesData.get(series);
                if (data && "value" in data) {
                  const val = data.value as number;
                  const color = YEAR_COLORS[idx % YEAR_COLORS.length];
                  tooltipContent += `
                    <div class="flex items-center justify-between gap-4">
                      <div class="flex items-center gap-1.5">
                        <div class="w-1.5 h-1.5 rounded-full" style="background-color: ${color}"></div>
                        <span class="text-white text-[10px]">${year}년:</span>
                      </div>
                      <span class="font-mono text-[10px] ${val >= 0 ? "text-main-red" : "text-main-blue"}">${val >= 0 ? "+" : ""}${val.toFixed(2)}%</span>
                    </div>
                  `;
                }
              });
            } else if (type === "equity") {
              const eqSeries = equitySeriesRef.current;
              if (eqSeries) {
                const eqData = param.seriesData.get(eqSeries);
                if (eqData && "value" in eqData) {
                  tooltipContent += `
                    <div class="text-white text-[10px] flex justify-between gap-4">
                      <span>나의 전략:</span>
                      <span class="text-main-red font-mono font-bold">${formatCompactPrice(eqData.value as number)}</span>
                    </div>
                  `;
                }
              }
              const bhSeries = buyHoldSeriesRef.current;
              if (bhSeries) {
                const bhData = param.seriesData.get(bhSeries);
                if (bhData && "value" in bhData) {
                  tooltipContent += `
                    <div class="text-white text-[10px] flex justify-between gap-4">
                      <span>매수후보유:</span>
                      <span class="text-main-green font-mono font-bold">${formatCompactPrice(bhData.value as number)}</span>
                    </div>
                  `;
                }
              }
            } else if (type === "drawdown") {
              const ddSeries = drawdownSeriesRef.current;
              if (ddSeries) {
                const ddData = param.seriesData.get(ddSeries);
                if (ddData && "value" in ddData) {
                  tooltipContent += `
                    <div class="text-white text-[10px] flex justify-between gap-4">
                      <span>낙폭:</span>
                      <span class="text-main-red font-mono font-bold">${(ddData.value as number).toFixed(2)}%</span>
                    </div>
                  `;
                }
              }
            }

            tooltipContent += `</div>`;
            tooltip.innerHTML = tooltipContent;

            // Positioning
            const tooltipWidth = 140;
            const tooltipHeight = 80;
            const margin = 15;
            let left = param.point.x + margin;
            let top = param.point.y + margin;

            if (left + tooltipWidth > container.clientWidth) {
              left = param.point.x - margin - tooltipWidth;
            }
            if (top + tooltipHeight > container.clientHeight) {
              top = param.point.y - margin - tooltipHeight;
            }

            tooltip.style.left = left + "px";
            tooltip.style.top = top + "px";
          });
        }

        // Use ResizeObserver for better resize handling
        resizeObserverRef.current = new ResizeObserver((entries) => {
          for (const entry of entries) {
            const { width, height } = entry.contentRect;
            if (width > 0 && height > 0 && chartRef.current) {
              chartRef.current.applyOptions({ width, height });
            }
          }
        });

        resizeObserverRef.current.observe(container);

        // Fallback to window resize
        window.addEventListener("resize", handleResize);
      } catch (error) {
        console.error("Error creating chart:", error);
      }
    };

    // Start initialization
    initChart();

    return () => {
      window.removeEventListener("resize", handleResize);
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      if (chartRef.current) {
        try {
          chartRef.current.remove();
        } catch (e) {
          console.warn("Error removing chart on cleanup:", e);
        }
        chartRef.current = null;
      }
      // Clear series refs
      equitySeriesRef.current = null;
      buyHoldSeriesRef.current = null;
      drawdownSeriesRef.current = null;
      monthlySeriesRef.current = null;
      seasonalSeriesRefs.current = {};
    };
  }, [type, height, handleResize]); // Re-initialize when type changes

  // Update data when it changes
  useEffect(() => {
    if (!chartRef.current) return;

    if (type === "equity") {
      if (equitySeriesRef.current && equityChartData.length > 0) {
        equitySeriesRef.current.setData(equityChartData);
      }
      if (buyHoldSeriesRef.current && buyHoldChartData.length > 0) {
        buyHoldSeriesRef.current.setData(buyHoldChartData);
      }
      if (equityChartData.length > 0 && chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    } else if (type === "drawdown") {
      if (drawdownSeriesRef.current && drawdownChartData.length > 0) {
        drawdownSeriesRef.current.setData(drawdownChartData);
      }
      if (drawdownChartData.length > 0 && chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    } else if (type === "monthly_returns") {
      if (monthlySeriesRef.current && monthlyChartData.length > 0) {
        monthlySeriesRef.current.setData(monthlyChartData);
      }
      if (monthlyChartData.length > 0 && chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    } else if (type === "seasonal_returns") {
      // Cleanup old series
      Object.values(seasonalSeriesRefs.current).forEach(s => chartRef.current?.removeSeries(s));
      seasonalSeriesRefs.current = {};
      
      const years = Object.keys(seasonalChartData).sort();
      const chart = chartRef.current;
      years.forEach((year, idx) => {
        const series = chart.addSeries(LineSeries, {
          color: YEAR_COLORS[idx % YEAR_COLORS.length],
          lineWidth: 1, // Thinner for multiple lines
          lineType: LineType.Curved, // Make it smooth
          priceFormat: {
            type: "price",
            precision: 2,
            minMove: 0.01,
          },
          title: year,
        });
        seasonalSeriesRefs.current[year] = series;
        series.setData(seasonalChartData[year]);
      });
      if (years.length > 0) {
        chart.timeScale().fitContent();
      }
    }
  }, [type, equityChartData, buyHoldChartData, drawdownChartData, monthlyChartData, seasonalChartData]);

  return (
    <div className="w-full relative group" style={{ height: `${height}px` }}>
      {/* Legend Overlay */}
      <div className="absolute top-4 left-4 z-20 flex flex-col gap-1 b">
        {type !== "seasonal_returns" && (
          <>
            <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
               <div className="w-2.5 h-2.5 rounded-full bg-main-red" />
               <span className="text-[10px] font-bold text-white">나의 전략</span>
            </div>
            <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
               <div className="w-2.5 h-2.5 rounded-full bg-main-green" />
               <span className="text-[10px] font-bold text-white">매수후보유</span>
            </div>
          </>
        )}
        {type === "monthly_returns" && (
          <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
             <div className="flex gap-1">
                <div className="w-2.5 h-2.5 rounded-full bg-main-red" />
                <div className="w-2.5 h-2.5 rounded-full bg-main-blue" />
             </div>
             <span className="text-[10px] font-bold text-white">월간 수익/손실</span>
          </div>
        )}
        {type === "seasonal_returns" && (
          <div className="flex flex-wrap gap-2 max-w-[300px]">
             {Object.keys(seasonalChartData).sort().map((year, idx) => (
                <div key={year} className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#0a0a0a]/80 border border-gray-800 backdrop-blur-sm">
                   <div 
                      className="w-2 h-2 rounded-full" 
                      style={{ backgroundColor: YEAR_COLORS[idx % YEAR_COLORS.length] }} 
                   />
                   <span className="text-[10px] font-bold text-white">{year}년</span>
                </div>
             ))}
          </div>
        )}
      </div>

      {/* Custom Tooltip */}
      <div
        ref={tooltipRef}
        className="absolute z-30 pointer-events-none p-2 px-3 bg-[#0a0a0a]/90 border border-gray-800 rounded-lg shadow-2xl backdrop-blur-md hidden"
        style={{ minWidth: "120px" }}
      />

      <div
        ref={chartContainerRef}
        className="w-full h-full"
      />
    </div>
  );
}
