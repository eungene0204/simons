"use client";

import React from "react";
import {
  SparklesIcon,
  GlobeAltIcon,
  MagnifyingGlassIcon,
  ShieldExclamationIcon,
  ExclamationTriangleIcon,
  CheckIcon,
  InformationCircleIcon,
  ArrowRightIcon,
  ChartPieIcon,
  Squares2X2Icon,
} from "@heroicons/react/24/outline";

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
  const activeFilterCount = Object.keys(universeFilters).filter(
    (key) => key.startsWith("exclude") && (universeFilters as any)[key] === true
  ).length;

  return (
    <div className="flex-1 px-8 pt-8 pb-12 relative z-10 bg-[#0f0f0f] grid grid-cols-[1fr_280px] gap-x-8 gap-y-12 max-w-[1920px] mx-auto w-full items-start">
      
      {/* Row 1: Title */}
      <div className="col-start-1 col-end-2 min-w-0">
        <h3 className="text-xl font-black text-[#dfdfdf] tracking-tight">유니버스 설정</h3>
        <p className="text-sm text-[#a0a0a0] mt-1 font-medium">
          전략의 대상이 되는 시장과 종목 필터링 규칙을 정의합니다.
        </p>
      </div>
      
      {/* Row 2: Strategy Name Hero Section */}
      <div className="col-start-1 col-end-2 min-w-0 relative group">
        <input
          type="text"
          value={strategyName}
          onChange={(e) => setStrategyName(e.target.value)}
          placeholder="전략 이름을 입력하세요..."
          className="w-full bg-white/5 hover:bg-white/10 px-6 py-4 rounded-2xl text-3xl font-black text-white placeholder-white/10 outline-none tracking-tight transition-all focus:bg-white/10 focus:placeholder-white/5"
        />
      </div>

      {/* Row 3: Left Config Content */}
      <div className="col-start-1 col-end-2 row-start-3 flex flex-col gap-4 min-w-0 self-stretch">
        {/* Market Selection Card */}
            <div className="space-y-4 bg-black/20 backdrop-blur-2xl rounded-2xl border border-white/10 p-5 shadow-2xl flex flex-col">
              <div className="flex items-center gap-2 mb-2">
                <GlobeAltIcon className="w-5 h-5 text-[rgb(59, 134, 247)]" />
                <h3 className="text-sm font-black text-[#dfdfdf] uppercase tracking-tight">시장 및 규모 선택</h3>
              </div>
              
              <div className="grid grid-cols-3 gap-2">
                {[
                  { id: "kospi", name: "KOSPI", desc: "코스피 전체" },
                  { id: "kosdaq", name: "KOSDAQ", desc: "코스닥 전체" },
                  { id: "kospi200", name: "KOSPI 200", desc: "코스피 우량주" },
                ].map((m) => (
                  <div
                    key={m.id}
                    onClick={() => setUniverse(m.id)}
                    className={`p-3 rounded-xl cursor-pointer transition-all border group ${
                      universe === m.id
                        ? "bg-white/10 border-white/20 shadow-md scale-[1.02]"
                        : "bg-white/5 border-white/5 hover:border-white/10 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex flex-col gap-0.5">
                      <div className={`text-base font-black transition-colors ${universe === m.id ? "text-white" : "text-[#a0a0a0] group-hover:text-white/60"}`}>{m.name}</div>
                      <div className={`text-[10px] font-black tracking-tight transition-colors ${universe === m.id ? "text-[rgb(59, 134, 247)]" : "text-[#a0a0a0]"}`}>{m.desc}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="space-y-5 pt-4 border-t border-white/10 flex-1">
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-black text-[#a0a0a0] uppercase tracking-widest">시가총액 범위</label>
                    <span className="text-sm font-black text-[#dfdfdf] tabular-nums">
                      상위 {universeFilters.marketCapRange[0]}% ~ {universeFilters.marketCapRange[1]}%
                    </span>
                  </div>
                  <div className="relative h-4 flex items-center">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={universeFilters.marketCapRange[1]}
                      onChange={(e) => setUniverseFilters({...universeFilters, marketCapRange: [universeFilters.marketCapRange[0], parseInt(e.target.value)]})}
                      className="w-full h-1 bg-white/10 rounded-full appearance-none cursor-pointer accent-[rgb(56,122,244)] hover:accent-[rgb(59,134,247)] transition-all"
                    />
                  </div>
                  <p className="text-xs text-[#a0a0a0] font-medium tracking-tight bg-white/5 p-2 rounded-lg">상위 {universeFilters.marketCapRange[1]}% 이내 종목 포함.</p>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-black text-[#a0a0a0] uppercase tracking-widest">최소 거래대금</label>
                    <span className="text-sm font-black text-[#dfdfdf] tabular-nums">
                      {universeFilters.minTradingVolume === 0 ? "제한없음" : `${universeFilters.minTradingVolume}억원 이상`}
                    </span>
                  </div>
                  <div className="relative h-4 flex items-center">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      value={universeFilters.minTradingVolume}
                      onChange={(e) => setUniverseFilters({...universeFilters, minTradingVolume: parseInt(e.target.value)})}
                      className="w-full h-1 bg-white/10 rounded-full appearance-none cursor-pointer accent-[rgb(56,122,244)] hover:accent-[rgb(59,134,247)] transition-all"
                    />
                  </div>
                  <p className="text-xs text-[#a0a0a0] font-medium tracking-tight bg-white/5 p-2 rounded-lg">유동성이 일정 수준 이상인 종목 포함.</p>
                </div>
              </div>
            </div>

            {/* Sector Selection Card */}
            <div className="space-y-3 bg-black/20 backdrop-blur-2xl rounded-2xl border border-white/10 p-5 shadow-2xl flex flex-col h-[280px]">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Squares2X2Icon className="w-5 h-5 text-[rgb(59, 134, 247)]" />
                  <h3 className="text-sm font-black text-white uppercase tracking-tight">섹터 선택</h3>
                </div>
                <div className="relative">
                  <MagnifyingGlassIcon className="w-3 h-3 text-white/20 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input 
                    type="text"
                    placeholder="검색..."
                    value={sectorSearchTerm}
                    onChange={(e) => setSectorSearchTerm(e.target.value)}
                    className="pl-7 pr-3 py-1.5 bg-white/5 border border-white/5 rounded-lg text-xs font-bold text-white placeholder-white/20 focus:outline-none focus:bg-white/10 focus:border-white/20 transition-all w-36"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 lg:grid-cols-3 gap-1.5 pr-1.5 custom-scrollbar p-0.5 overflow-y-auto flex-1">
                 {ALL_SECTORS.filter(s => s.toLowerCase().includes(sectorSearchTerm.toLowerCase())).map(sector => (
                  <button
                    key={sector}
                    onClick={() => {
                      const next = universeFilters.selectedSectors.includes(sector)
                        ? universeFilters.selectedSectors.filter(s => s !== sector)
                        : [...universeFilters.selectedSectors, sector];
                      setUniverseFilters({...universeFilters, selectedSectors: next});
                    }}
                    className={`px-2 py-1.5 rounded-lg text-[11px] font-black transition-all border break-keep ${
                      universeFilters.selectedSectors.includes(sector)
                        ? "bg-[rgb(56,122,244)] border-[rgb(56,122,244)] text-white shadow-sm shadow-blue-500/20"
                        : "bg-white/5 border-white/5 text-[#a0a0a0] hover:text-white/60 hover:border-white/10 hover:bg-white/10"
                    }`}
                  >
                    {sector}
                  </button>
                ))}
              </div>
              
              <div className="flex justify-between items-center pt-3 border-t border-white/10 mt-1">
                <span className="text-[10px] font-black text-[#a0a0a0] uppercase tracking-tight">
                  {universeFilters.selectedSectors.length > 0 
                    ? `${universeFilters.selectedSectors.length}개 선택됨` 
                    : "선택 안됨 (전체)"}
                </span>
                <button 
                  onClick={() => setUniverseFilters({...universeFilters, selectedSectors: []})}
                  className="text-[10px] font-black text-white hover:text-white transition-all uppercase tracking-widest px-2.5 py-1 bg-[#161616] hover:bg-[#1f1f1f] rounded-full border border-white/5 hover:border-white/10 active:scale-95"
                >
                  초기화
                </button>
              </div>
            </div>

          <div className="space-y-4">
            <div className="space-y-4 bg-black/20 backdrop-blur-2xl rounded-2xl border border-white/10 p-5 shadow-2xl">
              <div className="flex items-center gap-2 mb-3">
                <ShieldExclamationIcon className="w-5 h-5 text-[rgb(59, 134, 247)]" />
                <h3 className="text-sm font-black text-[#dfdfdf] uppercase tracking-tight">제외 필터 설정</h3>
              </div>

                <div className="space-y-3 flex flex-col">
                  <div className="text-xs font-normal text-[#a0a0a0] px-1 mb-0.5">시장 분류 및 종목 특성</div>
                  <div className="bg-white/5 rounded-2xl border border-white/5 p-4 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-4 backdrop-blur-md flex-1">
                    {[
                      { id: 'excludeETF_ETN', label: 'ETF / ETN' },
                      { id: 'excludeSPAC', label: 'SPAC' },
                      { id: 'excludeREITs', label: 'REITs' },
                      { id: 'excludePreferred', label: '우선주' },
                      { id: 'excludePennyStocks', label: '동전주' },
                      { id: 'excludeNewListings', label: '신규상장' },
                      { id: 'excludeHighVolatility', label: '고변동성' },
                      { id: 'excludeForeignStock', label: '해외지주상장' }
                    ].map((item) => (
                      <label 
                        key={item.id} 
                        onClick={() => setUniverseFilters({...universeFilters, [item.id]: !(universeFilters as any)[item.id]})}
                        className="flex items-center justify-between cursor-pointer group/toggle py-1"
                      >
                        <span className={`text-[10px] font-black uppercase tracking-wider transition-colors ${(universeFilters as any)[item.id] ? "text-white" : "text-white/40 group-hover/toggle:text-white/60"}`}>{item.label}</span>
                        <div className={`w-8 h-4 rounded-full relative transition-all duration-300 ${(universeFilters as any)[item.id] ? "bg-[rgb(56,122,244)]" : "bg-white/10"}`}>
                          <div className={`absolute top-0.5 w-3 h-3 rounded-full shadow-sm transition-transform duration-300 bg-[rgb(226,226,225)] ${(universeFilters as any)[item.id] ? "translate-x-[16px]" : "translate-x-[2px]"}`} />
                        </div>
                      </label>
                    ))}
                  </div>
                </div>
            </div>
          </div>
        </div>

      {/* Row 3: Right Sidebar - Settings Summary */}
      <div className="col-start-2 col-end-3 row-start-3 flex flex-col self-stretch">
        <div className="bg-[#121212] border border-white/10 rounded-3xl p-6 shadow-2xl flex flex-col flex-1 relative overflow-hidden h-full">
          
          {/* Subtle gradient background effect */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-[rgb(59,134,247)]/10 rounded-full blur-[100px] pointer-events-none" />

          {/* Summary Header */}
          <div className="flex items-center gap-4 border-b border-white/10 pb-6 mb-6">
            <div className="w-12 h-12 bg-black/40 rounded-xl flex items-center justify-center border border-white/10">
              <ChartPieIcon className="w-6 h-6 text-[rgb(59,134,247)]" />
            </div>
            <div>
              <h4 className="text-xl font-black text-white tracking-tight uppercase">설정 요약</h4>
              <p className="text-[11px] font-black tracking-widest text-[#a0a0a0] uppercase mt-1">EPRI Universe</p>
            </div>
          </div>

          {/* Summary Items */}
          <div className="space-y-6 flex-1 overflow-y-auto custom-scrollbar pr-2 pb-4">
            
            <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
              <span className="text-[10px] font-black text-[rgb(59,134,247)] uppercase tracking-widest block mb-2 opacity-90">대상 시장</span>
              <span className="text-xl font-black text-white tracking-tight">{universe.toUpperCase()}</span>
            </div>

            <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
              <span className="text-[10px] font-black text-[rgb(59,134,247)] uppercase tracking-widest block mb-2 opacity-90">시가총액 범위</span>
              <span className="text-xl font-black text-white tracking-tight tabular-nums">
                상위 {universeFilters.marketCapRange[0]}% ~ {universeFilters.marketCapRange[1]}%
              </span>
            </div>

            <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
              <span className="text-[10px] font-black text-[rgb(59,134,247)] uppercase tracking-widest block mb-2 opacity-90">최소 거래대금</span>
              <span className="text-xl font-black text-white tracking-tight">
                {universeFilters.minTradingVolume === 0 ? "제한없음" : `${universeFilters.minTradingVolume}억원 이상`}
              </span>
            </div>



            <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
              <span className="text-[10px] font-black text-[rgb(59,134,247)] uppercase tracking-widest block mb-2 opacity-90">선택된 섹터</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {universeFilters.selectedSectors.length > 0 ? (
                  universeFilters.selectedSectors.slice(0, 5).map(s => (
                    <span key={s} className="px-2 py-1 bg-white/10 text-white text-[10px] font-black rounded-lg">{s}</span>
                  ))
                ) : (
                  <span className="text-sm font-black text-[#a0a0a0]">전체 포함</span>
                )}
                {universeFilters.selectedSectors.length > 5 && (
                  <span className="px-2 py-1 bg-white/5 text-[#a0a0a0] text-[10px] font-black rounded-lg">
                    +{universeFilters.selectedSectors.length - 5}
                  </span>
                )}
              </div>
            </div>

            <div className="bg-white/5 p-4 rounded-2xl border border-white/5">
              <span className="text-[10px] font-black text-[rgb(59,134,247)] uppercase tracking-widest block mb-2 opacity-90">예상 유니버스 종목 수</span>
              <span className="text-xl font-black text-white tracking-tight tabular-nums">약 2,400개</span>
            </div>

          </div>

          <div className="pt-4 border-t border-white/10 mt-auto">
            <button 
              onClick={onNext} 
              className="w-full group px-6 py-4 bg-[rgb(59,134,247)] hover:bg-[rgb(56,122,244)] text-white rounded-2xl text-sm font-black transition-all flex items-center justify-between shadow-[0_10px_30px_rgba(0,122,255,0.2)] hover:shadow-[0_15px_40px_rgba(0,122,255,0.4)] hover:-translate-y-0.5"
            >
              <span>매매 로직 설계하기</span>
              <div className="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center group-hover:bg-white/30 transition-colors">
                <ArrowRightIcon className="w-4 h-4 text-white group-hover:translate-x-0.5 transition-transform" />
              </div>
            </button>
          </div>

        </div>
      </div>

    </div>
  );
}
