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
  "에너지", "화학", "소재", "철강", "비철금속", "건설", "조선", "기계", "항공", "운송", 
  "상업서비스", "자동차", "자동차부품", "섬유/의류", "생활용품", "호텔/레저", "화장품", "유통", 
  "식품", "음료", "담배", "제약", "바이오", "의료기기", "건강관리", "은행", "증권", "보험", 
  "다각화금융", "IT서비스", "소프트웨어", "반도체", "디스플레이", "하드웨어", "통신장비", 
  "통신서비스", "유틸리티", "미디어/엔터", "게임"
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
    <div className="flex-1 px-0 pt-8 pb-0 relative z-10 bg-[#0f0f0f]">
      <div className="max-w-full mx-auto px-8 space-y-16 pb-0 mt-0">
        <div className="space-y-12 w-full mx-auto">
          {/* Strategy Name Hero Section */}
          <div className="relative group">
            <input
              type="text"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              placeholder="전략 이름을 입력하세요..."
              className="w-full bg-white/5 hover:bg-white/10 px-6 py-4 rounded-2xl text-3xl font-black text-white placeholder-white/10 outline-none tracking-tight transition-all focus:bg-white/10 focus:placeholder-white/5"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
            <div className="space-y-6 bg-black/20 backdrop-blur-2xl rounded-3xl border border-white/10 p-8 shadow-2xl h-[540px] min-h-[540px]">
              <div className="flex items-center gap-3 mb-4">
                <GlobeAltIcon className="w-6 h-6 text-[rgb(59, 134, 247)]" />
                <h3 className="text-sm font-black text-[#dfdfdf] uppercase tracking-tight">시장 및 규모 선택</h3>
              </div>
              
              <div className="grid grid-cols-3 gap-3">
                {[
                  { id: "kospi", name: "KOSPI", desc: "코스피 전체", color: "white" },
                  { id: "kosdaq", name: "KOSDAQ", desc: "코스닥 전체", color: "white" },
                  { id: "kospi200", name: "KOSPI 200", desc: "코스피 우량주", color: "white" },
                ].map((m) => (
                  <div
                    key={m.id}
                    onClick={() => setUniverse(m.id)}
                    className={`p-5 rounded-2xl cursor-pointer transition-all border group ${
                      universe === m.id
                        ? "bg-white/10 border-white/20 shadow-xl scale-[1.02]"
                        : "bg-white/5 border-white/5 hover:border-white/10 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex flex-col gap-1">
                      <div className={`text-lg font-black transition-colors ${universe === m.id ? "text-white" : "text-[#a0a0a0] group-hover:text-white/60"}`}>{m.name}</div>
                      <div className={`text-[11px] font-black tracking-tight transition-colors ${universe === m.id ? "text-[rgb(59, 134, 247)]" : "text-[#a0a0a0]"}`}>{m.desc}</div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="space-y-8 pt-6 border-t border-white/10">
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-black text-[#a0a0a0] uppercase tracking-widest">시가총액 범위</label>
                    <span className="text-sm font-black text-[#dfdfdf] tabular-nums">
                      상위 {universeFilters.marketCapRange[0]}% ~ {universeFilters.marketCapRange[1]}%
                    </span>
                  </div>
                  <div className="relative h-6 flex items-center">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={universeFilters.marketCapRange[1]}
                      onChange={(e) => setUniverseFilters({...universeFilters, marketCapRange: [universeFilters.marketCapRange[0], parseInt(e.target.value)]})}
                      className="w-full h-1 bg-white/10 rounded-full appearance-none cursor-pointer accent-[rgb(56,122,244)] hover:accent-[rgb(59,134,247)] transition-all"
                    />
                  </div>
                  <p className="text-xs text-[#a0a0a0] font-medium tracking-tight bg-white/5 p-3 rounded-xl">시가총액 기준 상위 {universeFilters.marketCapRange[1]}% 이내 종목을 대상으로 합니다.</p>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-black text-[#a0a0a0] uppercase tracking-widest">최소 거래대금 (일평균)</label>
                    <span className="text-sm font-black text-[#dfdfdf] tabular-nums">
                      {universeFilters.minTradingVolume === 0 ? "제한없음" : `${universeFilters.minTradingVolume}억원 이상`}
                    </span>
                  </div>
                  <div className="relative h-6 flex items-center">
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
                  <p className="text-xs text-[#a0a0a0] font-medium tracking-tight bg-white/5 p-3 rounded-xl">유동성이 일정 수준 이상인 종목만 포함합니다.</p>
                </div>
              </div>
            </div>

            <div className="space-y-6 bg-black/20 backdrop-blur-2xl rounded-3xl border border-white/10 p-8 shadow-2xl h-[540px] min-h-[540px] flex flex-col">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <Squares2X2Icon className="w-6 h-6 text-[rgb(59, 134, 247)]" />
                  <h3 className="text-base font-black text-white uppercase tracking-tight">섹터 선택</h3>
                </div>
                <div className="relative">
                  <MagnifyingGlassIcon className="w-4 h-4 text-white/20 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input 
                    type="text"
                    placeholder="검색..."
                    value={sectorSearchTerm}
                    onChange={(e) => setSectorSearchTerm(e.target.value)}
                    className="pl-9 pr-4 py-2 bg-white/5 border border-white/5 rounded-xl text-sm font-bold text-white placeholder-white/20 focus:outline-none focus:bg-white/10 focus:border-white/20 transition-all w-40"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-3 xl:grid-cols-3 gap-2 pr-2 custom-scrollbar p-1 overflow-y-auto flex-1">
                 {ALL_SECTORS.filter(s => s.toLowerCase().includes(sectorSearchTerm.toLowerCase())).map(sector => (
                  <button
                    key={sector}
                    onClick={() => {
                      const next = universeFilters.selectedSectors.includes(sector)
                        ? universeFilters.selectedSectors.filter(s => s !== sector)
                        : [...universeFilters.selectedSectors, sector];
                      setUniverseFilters({...universeFilters, selectedSectors: next});
                    }}
                    className={`px-4 py-2.5 rounded-xl text-xs font-black transition-all border break-keep ${
                      universeFilters.selectedSectors.includes(sector)
                        ? "bg-[rgb(56,122,244)] border-[rgb(56,122,244)] text-white shadow-lg shadow-blue-500/20"
                        : "bg-white/5 border-white/5 text-[#a0a0a0] hover:text-white/60 hover:border-white/10 hover:bg-white/10"
                    }`}
                  >
                    {sector}
                  </button>
                ))}
              </div>
              
              <div className="flex justify-between items-center pt-4 border-t border-white/10 mt-2">
                <span className="text-xs font-black text-[#a0a0a0] uppercase tracking-tight">
                  {universeFilters.selectedSectors.length > 0 
                    ? `${universeFilters.selectedSectors.length}개의 섹터 선택됨` 
                    : "선택된 섹터 없음 (전체 포함)"}
                </span>
                <button 
                  onClick={() => setUniverseFilters({...universeFilters, selectedSectors: []})}
                  className="text-xs font-black text-[#a0a0a0] hover:text-white transition-colors uppercase tracking-widest px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-full border border-white/5 active:scale-95"
                >
                  초기화
                </button>
              </div>
            </div>
          </div>

          {/* Exclusion Filters Section */}
          <div className="space-y-8">
            <div className="space-y-6 bg-black/20 backdrop-blur-2xl rounded-3xl border border-white/10 p-8 shadow-2xl">
              <div className="flex items-center gap-3 mb-4">
                <ShieldExclamationIcon className="w-6 h-6 text-[rgb(59, 134, 247)]" />
                <h3 className="text-base font-black text-[#dfdfdf] uppercase tracking-tight">제외 필터 설정</h3>
              </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-stretch">
                  <div className="space-y-4 flex flex-col">
                    <div className="text-lg font-normal text-[#a0a0a0] px-1 mb-1">재무 건전성 및 리스크</div>
                    <div className="space-y-2 flex-1 flex flex-col justify-between">
                      {[
                        { id: 'excludeLossMaking', label: '적자 기업 제외', desc: '최근 분기 영업이익 기준' },
                        { id: 'excludeCapitalImpaired', label: '자본잠식 기업 제외', desc: '재무 건전성 미달' },
                        { id: 'excludeAdministrative', label: '관리/거래정지 종목 제외', desc: '거래 위험 요인' },
                        { id: 'excludeDelistingPending', label: '상장폐지/정리매매 제외', desc: '비정상적 거래' },
                      ].map((item) => (
                        <div
                          key={item.id}
                          onClick={() => setUniverseFilters({...universeFilters, [item.id]: !(universeFilters as any)[item.id]})}
                          className={`p-6 rounded-2xl border transition-all cursor-pointer flex items-center gap-6 group ${
                            (universeFilters as any)[item.id]
                              ? "bg-white/10 border-white/10 shadow-xl"
                              : "bg-white/5 border-white/5 hover:border-white/10"
                          }`}
                        >
                          <div className="flex-1">
                            <p className={`text-sm font-black tracking-tight transition-colors ${(universeFilters as any)[item.id] ? "text-white" : "text-[#a0a0a0] group-hover:text-white/60"}`}>{item.label}</p>
                            <p className="text-[10px] font-black uppercase tracking-widest text-[#a0a0a0] mt-1">{item.desc}</p>
                          </div>
                          <div className={`w-11 h-6 rounded-full relative transition-all duration-300 ${(universeFilters as any)[item.id] ? "bg-[rgb(56,122,244)]" : "bg-white/10"}`}>
                            <div className={`absolute top-1 w-4 h-4 rounded-full shadow-lg transition-transform duration-300 bg-[rgb(226,226,225)] ${(universeFilters as any)[item.id] ? "translate-x-[24px]" : "translate-x-[4px]"}`} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-4 flex flex-col">
                    <div className="text-lg font-normal text-[#a0a0a0] px-1 mb-1">시장 분류 및 종목 특성</div>
                    <div className="bg-white/5 rounded-3xl border border-white/5 p-8 grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-4 backdrop-blur-md flex-1">
                      {[
                        { id: 'excludeETF_ETN', label: 'ETF / ETN 제외' },
                        { id: 'excludeSPAC', label: 'SPAC 제외' },
                        { id: 'excludeREITs', label: 'REITs 제외' },
                        { id: 'excludePreferred', label: '우선주 제외' },
                        { id: 'excludePennyStocks', label: '동전주 제외' },
                        { id: 'excludeNewListings', label: '신규 상장주 제외' },
                        { id: 'excludeHighVolatility', label: '고변동성 종목 제외' },
                        { id: 'excludeForeignStock', label: '해외 지주사 제외' }
                      ].map((item) => (
                        <label 
                          key={item.id} 
                          onClick={() => setUniverseFilters({...universeFilters, [item.id]: !(universeFilters as any)[item.id]})}
                          className="flex items-center justify-between cursor-pointer group/toggle py-1 border-b border-white/5 last:border-0 pb-3 last:pb-0"
                        >
                          <span className={`text-xs font-black uppercase tracking-wider transition-colors ${(universeFilters as any)[item.id] ? "text-white" : "text-white/40 group-hover/toggle:text-white/60"}`}>{item.label}</span>
                          <div className={`w-10 h-5 rounded-full relative transition-all duration-300 ${(universeFilters as any)[item.id] ? "bg-[rgb(56,122,244)]" : "bg-white/10"}`}>
                            <div className={`absolute top-0.5 w-4 h-4 rounded-full shadow-lg transition-transform duration-300 bg-[rgb(226,226,225)] ${(universeFilters as any)[item.id] ? "translate-x-[22px]" : "translate-x-[2px]"}`} />
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
            </div>
          </div>
        </div>
      </div>
      <div className="h-8" />

      {/* macOS-style Bottom Toolbar / Status View */}
      <div className="sticky bottom-0 left-0 right-0 bg-[#0f0f0f] backdrop-blur-3xl px-8 py-5 z-50">
        <div className="max-w-full mx-auto flex items-center justify-between">
          <div className="flex items-center gap-12">
            <div className="flex items-center gap-6">
              <div className="w-16 h-16 bg-[rgb(59, 134, 247)] rounded-2xl flex items-center justify-center shadow-[0_0_40px_rgba(0,122,255,0.4)]">
                <ChartPieIcon className="w-8 h-8 text-white" />
              </div>
              <div className="space-y-1">
                <h4 className="text-xl font-black text-[#dfdfdf] tracking-tight uppercase">유니버스 설정 요약</h4>
              </div>
            </div>
            
            <div className="h-12 w-px bg-white/10" />
            
            <div className="flex gap-12">
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">대상 시장</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">{universe.toUpperCase()}</span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">필터링</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">
                  {activeFilterCount > 0 ? `${activeFilterCount}개 선택됨` : "없음"}
                </span>
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-black text-[rgb(59, 134, 247)] uppercase tracking-widest mb-1.5 opacity-80">예상 종목 수</span>
                <span className="text-2xl font-black text-[#dfdfdf] tabular-nums tracking-tight">약 2,400개</span>
              </div>
            </div>
          </div>

          <button 
            onClick={onNext} 
            className="group px-12 py-5 bg-[#161616] text-white rounded-2xl text-lg font-black hover:bg-[#1f1f1f] transition-all flex items-center gap-4 shadow-[0_20px_40px_rgba(0,0,0,0.3)] border border-white/5 hover:border-white/10 hover:scale-105 active:scale-95"
          >
            매매 로직 설계하기 <ArrowRightIcon className="w-6 h-6 group-hover:translate-x-2 transition-transform duration-500 text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
