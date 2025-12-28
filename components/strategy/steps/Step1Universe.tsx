"use client";

import React from "react";
import {
  SparklesIcon,
  GlobeAltIcon,
  TagIcon,
  MagnifyingGlassIcon,
  ShieldExclamationIcon,
  ExclamationTriangleIcon,
  CheckIcon,
  InformationCircleIcon,
  ArrowRightIcon,
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
  return (
    <div className="flex flex-col min-h-full">
      <div className="p-8 max-w-[1440px] mx-auto w-full space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="flex flex-col gap-2 border-b border-gray-800/50 pb-8">
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              placeholder="새로운 전략의 이름을 입력하세요"
              className="text-4xl font-black text-white bg-transparent border-none outline-none placeholder:text-gray-800 tracking-tighter flex-1"
            />
            <div className="px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center gap-2">
               <SparklesIcon className="w-4 h-4 text-blue-400" />
               <span className="text-[10px] font-black text-blue-400 uppercase tracking-widest">Hi-Fi 전략</span>
            </div>
          </div>
          <p className="text-gray-500 text-sm mt-1 font-medium">탐색할 시장의 범위와 기본적인 필터링 조건을 설정하여 나만의 유니버스를 구축하세요.</p>
        </div>

        <div className="space-y-8 max-w-5xl mx-auto w-full">
          {/* Market Selection Section */}
          <div className="space-y-8">
            <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <GlobeAltIcon className="w-6 h-6 text-blue-400" />
                <h3 className="text-lg font-black text-white uppercase tracking-wider">시장 및 규모 선택</h3>
              </div>
              
              <div className="grid grid-cols-3 gap-3">
                {[
                  { id: "kospi", name: "KOSPI", desc: "대형주 중심" },
                  { id: "kosdaq", name: "KOSDAQ", desc: "기술주 중심" },
                  { id: "kospi200", name: "KOSPI 200", desc: "우량주 200" },
                ].map((m) => (
                  <div
                    key={m.id}
                    onClick={() => setUniverse(m.id)}
                    className={`p-4 rounded-xl cursor-pointer transition-all border-2 flex flex-col justify-center text-center group ${
                      universe === m.id
                        ? "bg-blue-600/10 border-blue-500/50 shadow-[0_0_20px_rgba(37,99,235,0.1)]"
                        : "bg-[#151515] border-gray-800/50 hover:border-gray-700"
                    }`}
                  >
                    <div className={`text-base font-black transition-colors ${universe === m.id ? "text-white" : "text-gray-500 group-hover:text-gray-300"}`}>{m.name}</div>
                    <div className="text-xs text-gray-600 mt-1 font-bold">{m.desc}</div>
                  </div>
                ))}
              </div>

              <div className="space-y-8 pt-4 border-t border-gray-800/50">
                <div className="space-y-4">
                  <div className="flex justify-between items-center px-1">
                    <label className="text-sm font-black text-gray-400 uppercase tracking-tight">시가총액 범위</label>
                    <span className="text-sm font-black text-blue-400 tabular-nums">
                      상위 {universeFilters.marketCapRange[0]}% ~ {universeFilters.marketCapRange[1]}%
                    </span>
                  </div>
                  <div className="px-2">
                    <input
                      type="range"
                      min="0"
                      max="100"
                      value={universeFilters.marketCapRange[1]}
                      onChange={(e) => setUniverseFilters({...universeFilters, marketCapRange: [universeFilters.marketCapRange[0], parseInt(e.target.value)]})}
                      className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                    />
                    <div className="flex justify-between text-xs text-gray-600 mt-2 font-black uppercase tracking-tighter">
                      <span>순위 높음</span>
                      <span>전체 범위</span>
                      <span>순위 낮음</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center px-1">
                    <label className="text-sm font-black text-gray-400 uppercase tracking-tight">최소 거래대금 (20일 평균)</label>
                    <span className="text-sm font-black text-emerald-400 tabular-nums">
                      {universeFilters.minTradingVolume === 0 ? "제한 없음" : `${universeFilters.minTradingVolume}억원 이상`}
                    </span>
                  </div>
                  <div className="px-2">
                     <input
                      type="range"
                      min="0"
                      max="100"
                      step="5"
                      value={universeFilters.minTradingVolume}
                      onChange={(e) => setUniverseFilters({...universeFilters, minTradingVolume: parseInt(e.target.value)})}
                      className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <TagIcon className="w-6 h-6 text-emerald-400" />
                  <h3 className="text-lg font-black text-white uppercase tracking-wider">섹터 선택</h3>
                </div>
                <div className="relative">
                  <MagnifyingGlassIcon className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input 
                    type="text"
                    placeholder="섹터 검색..."
                    value={sectorSearchTerm}
                    onChange={(e) => setSectorSearchTerm(e.target.value)}
                    className="pl-9 pr-4 py-2 bg-[#151515] border border-gray-800 rounded-lg text-sm font-bold text-white focus:outline-none focus:border-blue-500 transition-all w-48"
                  />
                </div>
              </div>

              <div className="flex flex-wrap gap-2 pr-2 custom-scrollbar p-1">
                 {ALL_SECTORS.filter(s => s.toLowerCase().includes(sectorSearchTerm.toLowerCase())).map(sector => (
                  <button
                    key={sector}
                    onClick={() => {
                      const next = universeFilters.selectedSectors.includes(sector)
                        ? universeFilters.selectedSectors.filter(s => s !== sector)
                        : [...universeFilters.selectedSectors, sector];
                      setUniverseFilters({...universeFilters, selectedSectors: next});
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all border ${
                      universeFilters.selectedSectors.includes(sector)
                        ? "bg-emerald-600 border-emerald-500 text-white shadow-lg shadow-emerald-900/40"
                        : "bg-[#151515] border-gray-800 text-gray-500 hover:text-gray-300 hover:border-gray-700"
                    }`}
                  >
                    {sector}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Exclusion Filters Section */}
          <div className="space-y-8">
            <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <ShieldExclamationIcon className="w-6 h-6 text-red-500" />
                <h3 className="text-lg font-black text-white uppercase tracking-wider">제외 필터 설정</h3>
              </div>

              <div className="space-y-6">
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => setUniverseFilters({...universeFilters, excludeLossMaking: !universeFilters.excludeLossMaking})}
                    className={`p-3 rounded-xl border transition-all flex items-center gap-3 text-left ${
                      universeFilters.excludeLossMaking 
                        ? "bg-red-500/10 border-red-500/50" 
                        : "bg-[#151515] border-gray-800 hover:border-gray-700"
                    }`}
                  >
                    <ShieldExclamationIcon className={`w-5 h-5 ${universeFilters.excludeLossMaking ? "text-red-400" : "text-gray-600"}`} />
                    <div className="min-w-0">
                      <p className="text-sm font-black text-white truncate">적자 기업 제외</p>
                      <p className="text-xs text-gray-600 font-bold">영업이익 기준</p>
                    </div>
                  </button>

                  <button
                    onClick={() => setUniverseFilters({...universeFilters, excludeCapitalImpaired: !universeFilters.excludeCapitalImpaired})}
                    className={`p-3 rounded-xl border transition-all flex items-center gap-3 text-left ${
                      universeFilters.excludeCapitalImpaired 
                        ? "bg-red-500/10 border-red-500/50" 
                        : "bg-[#151515] border-gray-800 hover:border-gray-700"
                    }`}
                  >
                     <ExclamationTriangleIcon className={`w-5 h-5 ${universeFilters.excludeCapitalImpaired ? "text-red-400" : "text-gray-600"}`} />
                    <div className="min-w-0">
                      <p className="text-sm font-black text-white truncate">자본잠식 제외</p>
                      <p className="text-xs text-gray-600 font-bold">재무 건전성 미달</p>
                    </div>
                  </button>
                </div>

                <div className="bg-[#151515]/50 rounded-xl border border-gray-800/50 p-4">
                  <div className="grid grid-cols-1 gap-y-3.5">
                    {[
                      { id: 'excludePennyStocks', label: '동전주 제외 (1,000원 미만)' },
                      { id: 'excludeNewListings', label: '신규 상장주 제외 (1년 이내)' },
                      { id: 'excludeHighVolatility', label: '急등락주 제외 (변동성 상위)' },
                      { id: 'excludeAdministrative', label: '관리종목 및 거래정지 제외' },
                      { id: 'excludeInvestmentWarning', label: '투자주의 / 경고 / 위험 제외' },
                      { id: 'excludeDelistingPending', label: '정리매매 종목 제외' },
                      { id: 'excludeETF_ETN', label: 'ETF / ETN 제외' },
                      { id: 'excludeSPAC', label: 'SPAC (기업인수목적) 제외' },
                      { id: 'excludeREITs', label: '리츠 (부동산투자) 제외' },
                      { id: 'excludePreferred', label: '우선주 제외' },
                      { id: 'excludeForeignStock', label: '해외 본사 기업 제외' }
                    ].map((item) => (
                      <label key={item.id} className="flex items-center gap-3 cursor-pointer group">
                        <div className="relative flex items-center">
                          <input 
                            type="checkbox" 
                            checked={(universeFilters as any)[item.id]}
                            onChange={(e) => setUniverseFilters({...universeFilters, [item.id]: e.target.checked})}
                            className="peer h-5 w-5 appearance-none rounded border border-gray-700 bg-[#0a0a0a] checked:bg-red-500 checked:border-red-500 transition-all cursor-pointer" 
                          />
                          <CheckIcon className="absolute h-4 w-4 text-white left-0.5 opacity-0 peer-checked:opacity-100 transition-opacity pointer-events-none" />
                        </div>
                        <span className="text-sm font-bold text-gray-500 group-hover:text-gray-300 transition-colors">{item.label}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
            </div>
            <div className="bg-blue-600/5 border border-blue-500/20 rounded-2xl p-6 space-y-4">
                <div className="flex items-center gap-2">
                   <InformationCircleIcon className="w-5 h-5 text-blue-400" />
                   <span className="text-sm font-black text-white uppercase tracking-wider">유니버스 요약</span>
                </div>
                <div className="space-y-3">
                   <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-500 font-bold">대상 시장</span>
                      <span className="text-blue-400 font-black">{universe.toUpperCase()}</span>
                   </div>
                   <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-500 font-bold">섹터 제한</span>
                      <span className="text-white font-black">{universeFilters.selectedSectors.length > 0 ? `${universeFilters.selectedSectors.length}개 선택됨` : "전체 섹터"}</span>
                   </div>
                   <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-500 font-bold">제외 조건</span>
                      <span className="text-red-400 font-black">{Object.values(universeFilters).filter(v => v === true).length}개 활성</span>
                   </div>
                </div>
            </div>
          </div>
        </div>
      </div>
      <div className="sticky bottom-0 bg-[#0f0f0f] z-50 mt-auto">
        <div className="max-w-5xl mx-auto w-full p-6 flex justify-end">
          <button
            onClick={onNext}
            className="px-10 py-4 bg-blue-600 text-white rounded-xl font-black hover:bg-blue-500 flex items-center gap-3 transition-all hover:scale-[1.02] shadow-xl shadow-blue-900/40"
          >
            다음 단계: 매매 조건 설정
            <ArrowRightIcon className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
