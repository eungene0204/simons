"use client";

import { useState, useEffect } from "react";
import { generateStockPriceData } from "@/lib/mock-stock-data";
import { ArrowUpIcon, ArrowDownIcon } from "@heroicons/react/24/solid";

type TabType = "volume" | "sector" | "theme" | "investor";

interface StockRanking {
  symbol: string;
  name: string;
  currentPrice: number;
  change: number;
  changePercent: number;
  volume: number;
  volumeAmount: number; // 거래량 대금 (현재가 × 거래량)
  sector?: string;
  theme?: string;
}

export default function MarketRankings() {
  const [activeTab, setActiveTab] = useState<TabType>("volume");
  const [volumeRankings, setVolumeRankings] = useState<StockRanking[]>([]);
  const [sectorRankings, setSectorRankings] = useState<{ sector: string; stocks: StockRanking[] }[]>([]);
  const [themeRankings, setThemeRankings] = useState<{ theme: string; stocks: StockRanking[] }[]>([]);
  const [investorTrends, setInvestorTrends] = useState<StockRanking[]>([]);
  const [loading, setLoading] = useState(true);
  const [allStocks, setAllStocks] = useState<Array<{ symbol: string; name: string; sector?: string; theme?: string }>>([]);

  // Helper function to get sector from industry
  const getSectorFromIndustry = (industry: string | null | undefined): string => {
    if (!industry) return "기타";
    if (industry.includes("반도체") || industry.includes("전자부품")) return "반도체";
    if (industry.includes("IT") || industry.includes("소프트웨어") || industry.includes("인터넷")) return "IT서비스";
    if (industry.includes("화학") || industry.includes("배터리")) return "화학";
    if (industry.includes("바이오") || industry.includes("의약품")) return "바이오";
    if (industry.includes("건설") || industry.includes("부동산")) return "건설";
    if (industry.includes("금융") || industry.includes("은행") || industry.includes("보험")) return "금융";
    if (industry.includes("자동차")) return "자동차부품";
    if (industry.includes("철강") || industry.includes("금속")) return "철강";
    return "기타";
  };

  // Helper function to get theme from sector
  const getThemeFromSector = (sector: string): string => {
    if (sector === "반도체") return "반도체";
    if (sector === "IT서비스") return "플랫폼";
    if (sector === "화학") return "배터리";
    if (sector === "바이오") return "바이오";
    if (sector === "건설") return "건설";
    if (sector === "금융") return "금융";
    if (sector === "자동차부품") return "자동차";
    if (sector === "철강") return "철강";
    return "기타";
  };

  // Fallback mock stocks
  const getMockStocks = () => [
    { symbol: "005930", name: "삼성전자", sector: "반도체", theme: "반도체" },
    { symbol: "000660", name: "SK하이닉스", sector: "반도체", theme: "반도체" },
    { symbol: "035420", name: "NAVER", sector: "IT서비스", theme: "플랫폼" },
    { symbol: "035720", name: "카카오", sector: "IT서비스", theme: "플랫폼" },
    { symbol: "051910", name: "LG화학", sector: "화학", theme: "배터리" },
    { symbol: "006400", name: "삼성SDI", sector: "화학", theme: "배터리" },
    { symbol: "207940", name: "삼성바이오로직스", sector: "바이오", theme: "바이오" },
    { symbol: "068270", name: "셀트리온", sector: "바이오", theme: "바이오" },
    { symbol: "028260", name: "삼성물산", sector: "건설", theme: "건설" },
    { symbol: "010130", name: "고려아연", sector: "비철금속", theme: "원자재" },
    { symbol: "003670", name: "포스코홀딩스", sector: "철강", theme: "철강" },
    { symbol: "105560", name: "KB금융", sector: "금융", theme: "금융" },
    { symbol: "055550", name: "신한지주", sector: "금융", theme: "금융" },
    { symbol: "032830", name: "삼성생명", sector: "보험", theme: "금융" },
    { symbol: "012330", name: "현대모비스", sector: "자동차부품", theme: "자동차" },
  ];

  // Load stocks from API
  useEffect(() => {
    const loadStocks = async () => {
      try {
        const response = await fetch("/api/stocks/sync");
        if (response.ok) {
          const data = await response.json();
          const stockList = data.stocks || [];
          console.log(`Loaded ${stockList.length} stocks from API`);
          
          // Get first 100 stocks from the list
          const stocks = stockList.slice(0, 100).map((stock: any) => ({
            symbol: stock.symbol,
            name: stock.name,
            sector: stock.sector || getSectorFromIndustry(stock.industry),
            theme: getThemeFromSector(stock.sector || getSectorFromIndustry(stock.industry)),
          }));
          
          if (stocks.length > 0) {
            console.log(`Setting ${stocks.length} stocks`);
            setAllStocks(stocks);
          } else {
            console.log("No stocks found, using fallback");
            setAllStocks(getMockStocks());
          }
        } else {
          console.error("API response not OK:", response.status);
          // Fallback to mock stocks if API fails
          setAllStocks(getMockStocks());
        }
      } catch (error) {
        console.error("Failed to load stocks:", error);
        // Fallback to mock stocks if API fails
        setAllStocks(getMockStocks());
      }
    };
    loadStocks();
  }, []);

  useEffect(() => {
    if (allStocks.length > 0) {
      generateRankings();
      // Update every 3 seconds
      const interval = setInterval(generateRankings, 3000);
      return () => clearInterval(interval);
    }
  }, [allStocks]);

  const generateRankings = () => {
    if (allStocks.length === 0) return;
    
    // Generate volume rankings
    const volumeData = allStocks.map((stock) => {
      const priceData = generateStockPriceData(stock.symbol);
      return {
        symbol: stock.symbol,
        name: stock.name,
        currentPrice: priceData.currentPrice,
        change: priceData.change,
        changePercent: priceData.changePercent,
        volume: priceData.volume,
        volumeAmount: priceData.currentPrice * priceData.volume, // 거래량 대금
        sector: stock.sector,
        theme: stock.theme,
      };
    });
    
    // Sort by volume (descending) - 거래량이 많은 순으로 정렬
    const sorted = [...volumeData].sort((a, b) => b.volume - a.volume);
    setVolumeRankings(sorted);

    // Generate sector rankings
    const sectorMap = new Map<string, StockRanking[]>();
    volumeData.forEach((stock) => {
      if (stock.sector) {
        if (!sectorMap.has(stock.sector)) {
          sectorMap.set(stock.sector, []);
        }
        sectorMap.get(stock.sector)!.push(stock);
      }
    });
    
    const sectorData = Array.from(sectorMap.entries()).map(([sector, stocks]) => ({
      sector,
      stocks: stocks.sort((a, b) => b.changePercent - a.changePercent).slice(0, 5),
    }));
    setSectorRankings(sectorData);

    // Generate theme rankings
    const themeMap = new Map<string, StockRanking[]>();
    volumeData.forEach((stock) => {
      if (stock.theme) {
        if (!themeMap.has(stock.theme)) {
          themeMap.set(stock.theme, []);
        }
        themeMap.get(stock.theme)!.push(stock);
      }
    });
    
    const themeData = Array.from(themeMap.entries()).map(([theme, stocks]) => ({
      theme,
      stocks: stocks.sort((a, b) => b.changePercent - a.changePercent).slice(0, 5),
    }));
    setThemeRankings(themeData);

    // Generate investor trends (stocks with highest change percent)
    const investorData = [...volumeData].sort((a, b) => b.changePercent - a.changePercent).slice(0, 10);
    setInvestorTrends(investorData);

    setLoading(false);
  };

  const tabs = [
    { id: "volume" as TabType, label: "거래상위" },
    { id: "sector" as TabType, label: "업종상위" },
    { id: "theme" as TabType, label: "테마상위" },
    { id: "investor" as TabType, label: "투자자 동향" },
  ];

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat("ko-KR").format(Math.round(price));
  };

  const formatVolume = (volume: number) => {
    return `${volume.toLocaleString("ko-KR")}주`;
  };

  const formatAmount = (amount: number) => {
    if (amount >= 1000000000) {
      return `${(amount / 1000000000).toFixed(2)}억원`;
    } else if (amount >= 1000000) {
      return `${(amount / 1000000).toFixed(2)}백만원`;
    } else if (amount >= 10000) {
      return `${(amount / 10000).toFixed(2)}만원`;
    }
    return `${amount.toLocaleString("ko-KR")}원`;
  };

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center min-h-[200px]">
          <div className="animate-pulse text-gray-500 dark:text-gray-400">로딩 중...</div>
        </div>
      );
    }

    switch (activeTab) {
      case "volume":
        return (
          <div className="space-y-2">
            <div className="border border-gray-800 rounded-lg overflow-y-auto min-h-[250px] max-h-[400px] h-[400px] lg:h-auto lg:max-h-[450px]">
              <table className="w-full text-xs sm:text-sm table-auto">
                <thead className="sticky top-0 bg-[#1a1a1a] border-gray-800 z-10 shadow-sm">
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 dark:text-gray-300 bg-[#1a1a1a] border-gray-800">순위</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 dark:text-gray-300 bg-[#1a1a1a] border-gray-800">종목명</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300 bg-[#1a1a1a] border-gray-800">현재가</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300 bg-[#1a1a1a] border-gray-800">등락률</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300 bg-[#1a1a1a] border-gray-800">거래량</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300 bg-[#1a1a1a] border-gray-800">거래량 대금</th>
                  </tr>
                </thead>
                <tbody>
                  {volumeRankings.slice(0, 100).map((stock, index) => {
                    const isPositive = stock.change >= 0;
                    const colorClass = isPositive
                      ? "text-red-600 dark:text-red-400"
                      : "text-blue-500 dark:text-blue-400";
                    return (
                      <tr
                        key={stock.symbol}
                        className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                      >
                        <td className="py-2 px-2 text-gray-600 dark:text-gray-400">{index + 1}</td>
                        <td className="py-2 px-2">
                          <div className="font-medium text-white">{stock.name}</div>
                        </td>
                        <td className={`py-2 px-2 text-right font-medium ${colorClass}`}>
                          {formatPrice(stock.currentPrice)}
                        </td>
                        <td className={`py-2 px-2 text-right ${colorClass}`}>
                          <div className="flex items-center justify-end gap-1">
                            {isPositive ? (
                              <ArrowUpIcon className="w-3 h-3" />
                            ) : (
                              <ArrowDownIcon className="w-3 h-3" />
                            )}
                            <span>
                              {isPositive ? "+" : ""}
                              {stock.changePercent.toFixed(2)}%
                            </span>
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right text-white">
                          {formatVolume(stock.volume)}
                        </td>
                        <td className="py-2 px-2 text-right text-white">
                          {formatAmount(stock.volumeAmount)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      case "sector":
        return (
          <div className="space-y-4">
            {sectorRankings.map((sectorData) => (
              <div key={sectorData.sector} className="border border-gray-800 rounded-lg p-3">
                <h4 className="font-semibold text-sm text-white mb-2">{sectorData.sector}</h4>
                <div className="space-y-1">
                  {sectorData.stocks.map((stock, index) => {
                    const isPositive = stock.change >= 0;
                    const colorClass = isPositive
                      ? "text-red-600 dark:text-red-400"
                      : "text-blue-500 dark:text-blue-400";
                    return (
                      <div
                        key={stock.symbol}
                        className="flex items-center justify-between py-1.5 px-2 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-gray-500 dark:text-gray-400 w-4">{index + 1}</span>
                          <div className="text-xs font-medium text-white">{stock.name}</div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-xs font-medium ${colorClass}`}>
                            {formatPrice(stock.currentPrice)}
                          </span>
                          <span className={`text-xs ${colorClass}`}>
                            {isPositive ? "+" : ""}
                            {stock.changePercent.toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        );
      case "theme":
        return (
          <div className="space-y-4">
            {themeRankings.map((themeData) => (
              <div key={themeData.theme} className="border border-gray-800 rounded-lg p-3">
                <h4 className="font-semibold text-sm text-white mb-2">{themeData.theme}</h4>
                <div className="space-y-1">
                  {themeData.stocks.map((stock, index) => {
                    const isPositive = stock.change >= 0;
                    const colorClass = isPositive
                      ? "text-red-600 dark:text-red-400"
                      : "text-blue-500 dark:text-blue-400";
                    return (
                      <div
                        key={stock.symbol}
                        className="flex items-center justify-between py-1.5 px-2 hover:bg-gray-50 dark:hover:bg-gray-700/50 rounded transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] text-gray-500 dark:text-gray-400 w-4">{index + 1}</span>
                          <div className="text-xs font-medium text-white">{stock.name}</div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`text-xs font-medium ${colorClass}`}>
                            {formatPrice(stock.currentPrice)}
                          </span>
                          <span className={`text-xs ${colorClass}`}>
                            {isPositive ? "+" : ""}
                            {stock.changePercent.toFixed(2)}%
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        );
      case "investor":
        return (
          <div className="space-y-2">
            <div className="overflow-x-auto">
              <table className="w-full text-xs sm:text-sm">
                <thead>
                  <tr className="border-b border-gray-800">
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 dark:text-gray-300">순위</th>
                    <th className="text-left py-2 px-2 font-semibold text-gray-700 dark:text-gray-300">종목명</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300">현재가</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300">등락률</th>
                    <th className="text-right py-2 px-2 font-semibold text-gray-700 dark:text-gray-300">거래량</th>
                  </tr>
                </thead>
                <tbody>
                  {investorTrends.map((stock, index) => {
                    const isPositive = stock.change >= 0;
                    const colorClass = isPositive
                      ? "text-red-600 dark:text-red-400"
                      : "text-blue-500 dark:text-blue-400";
                    return (
                      <tr
                        key={stock.symbol}
                        className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
                      >
                        <td className="py-2 px-2 text-gray-600 dark:text-gray-400">{index + 1}</td>
                        <td className="py-2 px-2">
                          <div className="font-medium text-white">{stock.name}</div>
                        </td>
                        <td className={`py-2 px-2 text-right font-medium ${colorClass}`}>
                          {formatPrice(stock.currentPrice)}
                        </td>
                        <td className={`py-2 px-2 text-right ${colorClass}`}>
                          <div className="flex items-center justify-end gap-1">
                            {isPositive ? (
                              <ArrowUpIcon className="w-3 h-3" />
                            ) : (
                              <ArrowDownIcon className="w-3 h-3" />
                            )}
                            <span>
                              {isPositive ? "+" : ""}
                              {stock.changePercent.toFixed(2)}%
                            </span>
                          </div>
                        </td>
                        <td className="py-2 px-2 text-right text-white">
                          {formatVolume(stock.volume)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="bg-[#1a1a1a] border-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm sm:text-base font-semibold text-white">
          시장 정보
        </h3>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-4 border-b border-gray-800">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-2 text-xs sm:text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "text-white bg-[#252525] border-b-2 border-transparent"
                : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="min-h-[200px]">{renderContent()}</div>
    </div>
  );
}

