"use client";

import React, { useState } from "react";
import {
  Globe,
  Stack,
  SquaresFour,
  ChartBar,
  TextAlignLeft,
  X,
  Plus,
  ArrowRight
} from "phosphor-react";

interface Step1UniverseProps {
  strategyName: string;
  setStrategyName: (val: string) => void;
  universe: string;
  setUniverse: (val: string) => void;
  universeFilters: {
    marketCapRange: number[];
    minTradingVolume: number;
    excludeLossMaking: boolean;
    excludeCapitalImpaired: boolean;
    selectedSectors: string[];
    excludeAdministrative: boolean;
    excludePreferred: boolean;
    excludeETF_ETN: boolean;
    excludeSPAC: boolean;
    excludeREITs: boolean;
    excludeInvestmentWarning: boolean;
    excludeDelistingPending: boolean;
    excludeForeignStock: boolean;
    excludePennyStocks: boolean;
    excludeNewListings: boolean;
    excludeHighVolatility: boolean;
  };
  setUniverseFilters: (filters: any) => void;
  sectorSearchTerm: string;
  setSectorSearchTerm: (term: string) => void;
  onNext: () => void;
}

const ALL_SECTORS = [
  "반도체", "이차전지", "디스플레이/부품", "IT 하드웨어", "소프트웨어/플랫폼", "게임", 
  "바이오/제약", "의료기기", "반도체 소재", "자동차", "자동차부품", "에너지/원자력", "화학", 
  "철강/금속", "조선/해운", "기계/장비", "우주항공/방산", "건설", "운송/물류", 
  "은행/금융지주", "증권/보험", "유통/상사", "화장품/패션", "식품/음료", "미디어/엔터", "통신/유틸리티", "교육", "부동산", "종이", "가구/인테리어", "시멘트", "수산", "수산가공", "욕실", "사료/축산", "목재", "기타 서비스", "기타 제조업"
];

export default function Step1Universe({
  strategyName,
  setStrategyName,
  universe,
  setUniverse,
  universeFilters,
  setUniverseFilters,
  sectorSearchTerm,
  setSectorSearchTerm,
  onNext,
}: Step1UniverseProps) {

  const [showSectorSelector, setShowSectorSelector] = useState(false);

  const getMarketCapLabel = () => {
    if (universeFilters.marketCapRange[0] === 0 && universeFilters.marketCapRange[1] === 50) return "대형주";
    if (universeFilters.marketCapRange[0] === 50 && universeFilters.marketCapRange[1] === 80) return "중형주";
    if (universeFilters.marketCapRange[0] === 80 && universeFilters.marketCapRange[1] === 100) return "소형주";
    return "사용자 지정";
  };

  const getMarketCapDesc = () => {
    if (universeFilters.marketCapRange[0] === 0 && universeFilters.marketCapRange[1] === 50) return "상위 50% 선택됨";
    return `상위 ${universeFilters.marketCapRange[0]}% - ${universeFilters.marketCapRange[1]}% 선택됨`;
  };

  const setMarketCap = (type: string) => {
    if (type === "대형주") {
      setUniverseFilters({...universeFilters, marketCapRange: [0, 50]});
    } else if (type === "중형주") {
      setUniverseFilters({...universeFilters, marketCapRange: [50, 80]});
    } else if (type === "소형주") {
      setUniverseFilters({...universeFilters, marketCapRange: [80, 100]});
    }
  };

  const currentCap = getMarketCapLabel();

  // Volume mapping for slider
  const getVolumeDisplay = () => {
    if (universeFilters.minTradingVolume === 0) return "제한없음";
    return `${universeFilters.minTradingVolume}억원 이상`;
  };

  const handleReset = () => {
    setUniverse("kospi");
    setUniverseFilters({
      ...universeFilters,
      marketCapRange: [0, 50],
      minTradingVolume: 0,
      selectedSectors: []
    });
  };

  return (
    <div className="flex-1 w-full bg-[#0a0a0a] min-h-screen text-white flex justify-center relative">
      
      <div className="flex w-full h-full">
        
        {/* Left Main Content */}
        <div className="flex-1 flex flex-col overflow-y-auto">
          
          <div className="w-full px-8 pt-8 lg:px-12">
            {/* Header section */}
            <div className="mb-14">
              <h1 className="text-3xl font-bold tracking-tight text-white mb-2">
                유니버스 설정
              </h1>
              <p className="text-sm font-medium text-white/50 mb-12">전략의 대상이 되는 시장과 종목 필터링 규칙을 정의합니다.</p>

              <div className="relative flex items-center max-w-3xl">
                <input
                  type="text"
                  value={strategyName}
                  onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="전략의 이름을 입력하세요 (예: 나의 첫 알파 전략)"
                  className="w-full bg-transparent border-b-2 border-white/10 py-5 text-3xl font-black text-white placeholder-white/20 outline-none focus:outline-none focus:ring-0 transition-all focus:border-blue-500/50"
                />
              </div>
            </div>

            <div className="flex flex-col gap-6">
              
              {/* Panel 1 */}
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <Globe className="w-5 h-5 text-blue-500" />
                  <h2 className="text-lg font-bold text-white">시장 선택</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {[
                    { id: "kospi", name: "KOSPI", desc: "우량주 및 대형주 중심 시장" },
                    { id: "kosdaq", name: "KOSDAQ", desc: "기술주 및 성장주 중심 시장" },
                    { id: "kospi200", name: "KOSPI 200", desc: "코스피 대표 우량 종목" }
                  ].map((m) => (
                    <div
                      key={m.id}
                      onClick={() => setUniverse(m.id)}
                      className={`p-6 rounded-xl cursor-pointer transition-all border ${
                        universe === m.id
                          ? "bg-[#111] border-blue-500/50"
                          : "bg-[#111] border-transparent hover:border-white/10"
                      }`}
                    >
                      <h3 className="text-base font-bold mb-2 text-white">{m.name}</h3>
                      <p className="text-[11px] text-white/40 font-medium leading-relaxed">{m.desc}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4 mb-4">
                {/* Panel 2 */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <Stack className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-bold text-white">시가총액 및 거래대금</h2>
                  </div>
                  
                  <div className="bg-[#111] rounded-xl p-6 flex flex-col flex-1 shadow-lg border border-transparent hover:border-white/5 transition-colors">
                    
                    <div className="mb-8">
                      <div className="flex items-center justify-between mb-4">
                        <span className="text-sm font-medium text-white/70">시가총액 필터</span>
                        <span className="text-xs font-medium text-white/40 bg-white/5 px-2.5 py-1 rounded-md">{getMarketCapDesc()}</span>
                      </div>
                      <div className="flex gap-2">
                        {["대형주", "중형주", "소형주"].map((cap) => (
                          <button
                            key={cap}
                            onClick={() => setMarketCap(cap)}
                            className={`flex-1 py-2.5 text-sm font-bold rounded-lg transition-all ${
                              currentCap === cap
                                ? "bg-blue-500 text-white shadow-[0_0_15px_rgba(59,130,246,0.2)]"
                                : "text-white/50 bg-[#0a0a0a] hover:text-white hover:bg-white/5"
                            }`}
                          >
                            {cap}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="flex-1 flex flex-col justify-end mt-auto pt-4 border-t border-white/5">
                      <div className="flex items-center justify-between mb-6">
                        <span className="text-sm font-medium text-white/70">최소 거래대금</span>
                        <span className="text-sm font-bold text-blue-500">{getVolumeDisplay()}</span>
                      </div>
                      <div className="relative px-2">
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="5"
                          value={universeFilters.minTradingVolume}
                          onChange={(e) => setUniverseFilters({...universeFilters, minTradingVolume: parseInt(e.target.value)})}
                          className="w-full h-1.5 bg-[#0a0a0a] rounded-full appearance-none cursor-pointer accent-blue-500"
                        />
                        <div className="flex justify-between items-center mt-3 text-[9px] font-bold text-white/30 uppercase tracking-wider">
                          <span>0억원</span>
                          <span>50억원</span>
                          <span>100억원+</span>
                        </div>
                      </div>
                    </div>

                  </div>
                </div>

                {/* Panel 3 */}
                <div className="flex flex-col">
                  <div className="flex items-center gap-2 mb-4">
                    <SquaresFour className="w-5 h-5 text-blue-500" />
                    <h2 className="text-lg font-bold text-white">섹터 필터링</h2>
                  </div>
                  
                  <div className="bg-[#111] rounded-xl p-6 relative flex flex-col flex-1 shadow-lg border border-transparent hover:border-white/5 transition-colors">
                    <div className="flex flex-wrap gap-2.5 relative z-10 w-full">
                      {universeFilters.selectedSectors.map(sector => (
                        <div key={sector} className="flex items-center gap-1.5 bg-blue-500 text-white px-3 py-1.5 rounded-full text-xs font-bold shadow-sm">
                          <span>{sector}</span>
                          <button 
                            onClick={() => {
                              setUniverseFilters({
                                ...universeFilters, 
                                selectedSectors: universeFilters.selectedSectors.filter(s => s !== sector)
                              });
                            }}
                            className="hover:bg-black/20 rounded-full p-0.5 transition-colors"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                      
                      <div className="flex">
                        <button 
                          onClick={() => setShowSectorSelector(true)}
                          className="flex items-center gap-1.5 bg-[#0a0a0a] border border-white/10 text-white/60 hover:text-white hover:border-white/30 hover:bg-white/5 px-3 py-1.5 rounded-full text-xs font-medium transition-all"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>섹터 추가</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Buttons at the bottom of the main content */}
              <div className="flex items-center justify-end gap-4 border-t border-white/5 pt-8 mb-12">
                <button 
                  onClick={onNext}
                  className="py-3 px-8 rounded-lg bg-blue-500 hover:bg-blue-400 active:bg-blue-600 text-sm font-bold text-white transition-all shadow-[0_0_15px_rgba(59,130,246,0.3)] flex items-center gap-2"
                >
                  <span>매매 조건</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>

            </div>
          </div>
        </div>

        {/* Right Fixed Sidebar (Summary) */}
        <div className="hidden lg:block w-[320px] xl:w-[380px] bg-[#141414] border-l border-white/5 h-full overflow-y-auto shrink-0 p-8">
          
          <div className="mb-10">
            <h3 className="text-xl font-bold text-white tracking-widest">유니버스 설정 요약</h3>
          </div>

          <div className="space-y-8">
            
            <div>
              <div className="mb-3">
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">선택된 시장</span>
              </div>
              <span className="text-2xl font-black text-white block tracking-tight">{universe.toUpperCase()}</span>
            </div>

            <div>
              <div className="mb-3">
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">시가총액 범위</span>
              </div>
              <span className="text-2xl font-black text-white block tracking-tight">{getMarketCapDesc().replace(" 선택됨", "")}</span>
            </div>

            <div>
               <div className="mb-3">
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">최소 일일 거래대금</span>
              </div>
              <span className="text-2xl font-black text-white block tracking-tight">{getVolumeDisplay()}</span>
            </div>

            <div>
               <div className="mb-4">
                <span className="text-sm font-black text-white/40 uppercase tracking-widest">섹터 필터</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {universeFilters.selectedSectors.length > 0 ? (
                  universeFilters.selectedSectors.map(s => (
                    <span key={s} className="px-3.5 py-1.5 border-2 border-blue-500/30 bg-blue-500/10 text-blue-400 text-sm font-black rounded-lg">{s}</span>
                  ))
                ) : (
                  <span className="text-xs font-medium text-white/30 italic">전체 포함됨</span>
                )}
              </div>
            </div>

          </div>

        </div>
      </div>

      {/* Sector Selection Modal */}
      {showSectorSelector && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="w-full max-w-[500px] bg-[#1a1a1a] border border-white/10 rounded-3xl shadow-2xl p-8 animate-in zoom-in duration-200">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <SquaresFour className="w-5 h-5 text-blue-500" />
                <h3 className="text-lg font-bold text-white">섹터 선택</h3>
              </div>
              <button 
                onClick={() => {
                  setShowSectorSelector(false);
                  setSectorSearchTerm(""); // Reset search on close
                }}
                className="p-2 hover:bg-white/5 rounded-full transition-all text-white/40 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Search Input */}
            <div className="mb-4">
              <div className="relative">
                <input
                  type="text"
                  value={sectorSearchTerm}
                  onChange={(e) => setSectorSearchTerm(e.target.value)}
                  placeholder="섹터 검색..."
                  className="w-full bg-[#0a0a0a] border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/30 focus:outline-none focus:border-blue-500/50 transition-colors"
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2 h-[400px] overflow-y-auto custom-scrollbar pr-2 mb-6 content-start">
              {ALL_SECTORS
                .filter(sector => sector.toLowerCase().includes(sectorSearchTerm.toLowerCase()))
                .map(sector => {
                const isSelected = universeFilters.selectedSectors.includes(sector);
                return (
                  <button
                    key={sector}
                    onClick={() => {
                      if (isSelected) {
                        setUniverseFilters({
                          ...universeFilters,
                          selectedSectors: universeFilters.selectedSectors.filter(s => s !== sector)
                        });
                      } else {
                        setUniverseFilters({
                          ...universeFilters,
                          selectedSectors: [...universeFilters.selectedSectors, sector]
                        });
                      }
                    }}
                    className={`text-center px-2 py-3 rounded-xl text-[11px] font-bold transition-all border ${
                      isSelected 
                        ? "bg-blue-500 border-blue-400 text-white" 
                        : "bg-[#0a0a0a] border-transparent text-white/50 hover:border-white/10 hover:text-white"
                    }`}
                  >
                    {sector}
                  </button>
                );
              })}
            </div>

            <button 
              onClick={() => setShowSectorSelector(false)}
              className="w-full py-4 bg-blue-500 hover:bg-blue-400 text-white text-sm font-bold rounded-2xl transition-all shadow-lg"
            >
              선택 완료
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


