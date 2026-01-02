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
        <div className="flex flex-col gap-3 pb-10 border-b border-white/5 relative">
          <div className="flex items-center gap-4">
            <div className="flex-1 relative group">
              <input
                type="text"
                value={strategyName}
                onChange={(e) => setStrategyName(e.target.value)}
                placeholder="새로운 전략의 이름을 입력하세요"
                className="text-5xl font-black text-white bg-transparent border-none outline-none placeholder:text-gray-800 tracking-tighter w-full focus:placeholder:text-gray-700 transition-all"
              />
            </div>
          </div>
          <div className="flex items-center gap-2 text-gray-500">
            <div className="w-1.5 h-1.5 rounded-full bg-blue-500/50" />
            <p className="text-sm font-medium tracking-tight">탐색할 시장의 범위와 기본적인 필터링 조건을 설정하여 나만의 유니버스를 구축하세요.</p>
          </div>
        </div>

        <div className="space-y-8 max-w-full mx-auto w-full">
          {/* Market Selection Section */}
          <div className="space-y-8">
            <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-lg font-black text-white uppercase tracking-wider">시장 및 규모 선택</h3>
              </div>
              
              <div className="grid grid-cols-3 gap-4">
                {[
                  { id: "kospi", name: "KOSPI", desc: "대형주·우량주 중심", icon: "💎", color: "indigo" },
                  { id: "kosdaq", name: "KOSDAQ", desc: "성장주·기술주 중심", icon: "🚀", color: "indigo" },
                  { id: "kospi200", name: "KOSPI 200", desc: "시장 대표 우량종목", icon: "🏆", color: "indigo" },
                ].map((m) => (
                  <div
                    key={m.id}
                    onClick={() => setUniverse(m.id)}
                    className={`relative p-5 rounded-2xl cursor-pointer transition-all duration-300 border-2 overflow-hidden group ${
                      universe === m.id
                        ? `bg-${m.color}-500/5 border-${m.color}-500/50 shadow-[0_0_30px_rgba(59,130,246,0.15)] scale-[1.02]`
                        : "bg-[#111] border-white/5 hover:border-white/10 hover:bg-[#151515]"
                    }`}
                  >
                    {universe === m.id && (
                      <div className={`absolute -right-4 -top-4 w-24 h-24 bg-${m.color}-500/10 rounded-full blur-2xl`} />
                    )}
                    <div className="flex flex-col items-center text-center relative z-10">
                      <span className="text-2xl mb-3 filter grayscale group-hover:grayscale-0 transition-all duration-500 transform group-hover:scale-110">{m.icon}</span>
                      <div className={`text-lg font-black tracking-tight transition-colors ${universe === m.id ? "text-white" : "text-gray-500 group-hover:text-gray-300"}`}>{m.name}</div>
                      <div className={`text-[11px] mt-1.5 font-bold transition-colors ${universe === m.id ? `text-${m.color}-400/80` : "text-gray-600"}`}>{m.desc}</div>
                    </div>
                    {universe === m.id && (
                      <div className={`absolute bottom-0 left-0 right-0 h-1 bg-${m.color}-500 shadow-[0_0_10px_rgba(59,130,246,0.5)]`} />
                    )}
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

              <div className="grid grid-cols-5 md:grid-cols-8 gap-1.5 pr-2 custom-scrollbar p-1">
                 {ALL_SECTORS.filter(s => s.toLowerCase().includes(sectorSearchTerm.toLowerCase())).map(sector => (
                  <button
                    key={sector}
                    onClick={() => {
                      const next = universeFilters.selectedSectors.includes(sector)
                        ? universeFilters.selectedSectors.filter(s => s !== sector)
                        : [...universeFilters.selectedSectors, sector];
                      setUniverseFilters({...universeFilters, selectedSectors: next});
                    }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all border break-keep ${
                      universeFilters.selectedSectors.includes(sector)
                        ? "bg-emerald-600/20 border-emerald-500/50 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.1)]"
                        : "bg-[#111] border-white/5 text-gray-500 hover:text-gray-400 hover:border-white/10"
                    }`}
                  >
                    {sector}
                  </button>
                ))}
              </div>
              
              <div className="flex justify-between items-center pt-2 border-t border-white/5 mt-2">
                <span className="text-xs font-bold text-gray-500">
                  {universeFilters.selectedSectors.length > 0 
                    ? `${universeFilters.selectedSectors.length}개의 섹터가 선택되었습니다.` 
                    : "선택이 없을땐 모든 섹터가 포함됩니다."}
                </span>
                <button 
                  onClick={() => setUniverseFilters({...universeFilters, selectedSectors: []})}
                  className="text-xs font-black text-gray-500 hover:text-white transition-colors uppercase tracking-widest px-2 py-1 hover:bg-white/5 rounded-lg active:scale-95"
                >
                  초기화
                </button>
              </div>
            </div>
          </div>

          {/* Exclusion Filters Section */}
          <div className="space-y-8">
            <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-lg font-black text-white uppercase tracking-wider">제외 필터 설정</h3>
              </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-4">
                    <div className="text-[10px] font-black text-gray-600 uppercase tracking-[0.2em] px-1">Financial Health & Risk</div>
                    <div className="space-y-2">
                      {[
                        { id: 'excludeLossMaking', label: '적자 기업 제외', desc: '영업이익 기준', icon: ShieldExclamationIcon },
                        { id: 'excludeCapitalImpaired', label: '자본잠식 제외', desc: '재무 건전성 미달', icon: ExclamationTriangleIcon },
                        { id: 'excludeAdministrative', label: '관리/정지 종목', desc: '거래 위험 발생', icon: InformationCircleIcon },
                        { id: 'excludeDelistingPending', label: '정리매매 종목', desc: '상장폐지 절차', icon: ExclamationTriangleIcon },
                      ].map((item) => (
                        <div
                          key={item.id}
                          onClick={() => setUniverseFilters({...universeFilters, [item.id]: !(universeFilters as any)[item.id]})}
                          className={`p-3 rounded-xl border transition-all cursor-pointer flex items-center gap-3 group ${
                            (universeFilters as any)[item.id]
                              ? "bg-red-500/10 border-red-500/30"
                              : "bg-[#111] border-white/5 hover:border-white/10"
                          }`}
                        >
                          <div className={`p-1.5 rounded-lg transition-colors ${(universeFilters as any)[item.id] ? "bg-red-500/20 text-red-400" : "bg-white/5 text-gray-600 group-hover:text-gray-400"}`}>
                            <item.icon className="w-4 h-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className={`text-xs font-black transition-colors ${(universeFilters as any)[item.id] ? "text-red-400" : "text-gray-400 group-hover:text-gray-300"}`}>{item.label}</p>
                            <p className="text-[10px] text-gray-600 font-bold">{item.desc}</p>
                          </div>
                          <div className={`w-8 h-4 rounded-full relative transition-colors ${(universeFilters as any)[item.id] ? "bg-red-500" : "bg-gray-800"}`}>
                            <div className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${(universeFilters as any)[item.id] ? "left-4.5" : "left-0.5"}`} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <div className="text-[10px] font-black text-gray-600 uppercase tracking-[0.2em] px-1">Market Type & Properties</div>
                    <div className="bg-[#111] rounded-2xl border border-white/5 p-4 grid grid-cols-1 gap-y-3">
                      {[
                        { id: 'excludeETF_ETN', label: 'ETF / ETN 제외' },
                        { id: 'excludeSPAC', label: 'SPAC (기업인수목적) 제외' },
                        { id: 'excludeREITs', label: '리츠 (부동산투자) 제외' },
                        { id: 'excludePreferred', label: '우선주 제외' },
                        { id: 'excludePennyStocks', label: '동전주 (1천원 미만)' },
                        { id: 'excludeNewListings', label: '신규 상장주 (1년)' },
                        { id: 'excludeHighVolatility', label: '급등락주 (변동성 상위)' },
                        { id: 'excludeForeignStock', label: '해외 본사 기업' }
                      ].map((item) => (
                        <label key={item.id} className="flex items-center justify-between cursor-pointer group">
                          <span className={`text-[11px] font-bold transition-colors ${(universeFilters as any)[item.id] ? "text-white" : "text-gray-500 group-hover:text-gray-300"}`}>{item.label}</span>
                          <div className="relative flex items-center">
                            <input 
                              type="checkbox" 
                              checked={(universeFilters as any)[item.id]}
                              onChange={(e) => setUniverseFilters({...universeFilters, [item.id]: e.target.checked})}
                              className="peer h-4 w-4 appearance-none rounded border border-white/10 bg-[#0a0a0a] checked:bg-red-500 checked:border-red-500 transition-all cursor-pointer" 
                            />
                            <CheckIcon className="absolute h-3 w-3 text-white left-0.5 opacity-0 peer-checked:opacity-100 transition-opacity pointer-events-none" />
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
            </div>
            <div className="space-y-6 bg-[#0a0a0a] rounded-2xl border border-gray-800/50 p-6 shadow-xl">
                <div className="flex items-center gap-2 mb-2">
                   <h3 className="text-lg font-black text-white uppercase tracking-wider">유니버스 설정 요약</h3>
                </div>
                
                <div className="space-y-4">
                   <div className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="w-1 h-1 rounded-full bg-blue-500" />
                        <span className="text-gray-400 font-bold">대상 시장</span>
                      </div>
                      <span className="text-blue-400 font-black tracking-tight">{universe.toUpperCase()}</span>
                   </div>
                   <div className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
                      <div className="flex items-center gap-2">
                        <div className="w-1 h-1 rounded-full bg-emerald-500" />
                        <span className="text-gray-400 font-bold">섹터 필터링</span>
                      </div>
                      <span className="text-white font-black">{universeFilters.selectedSectors.length > 0 ? `${universeFilters.selectedSectors.length}개 섹터` : "모든 섹터"}</span>
                   </div>
                   <div className="flex justify-between items-center text-sm">
                      <div className="flex items-center gap-2">
                        <div className="w-1 h-1 rounded-full bg-red-500" />
                        <span className="text-gray-400 font-bold">활성 제외 조건</span>
                      </div>
                      <span className="text-red-400 font-black">{Object.values(universeFilters).filter(v => typeof v === 'boolean' && v === true).length}개 작동 중</span>
                   </div>
                </div>

                <div className="pt-2">
                  <div className="bg-[#151515] border border-gray-800 rounded-xl px-4 py-3 flex items-center justify-between">
                    <span className="text-[11px] font-bold text-gray-400">예상 종목 규모</span>
                    <span className="text-xs font-black text-white">{Math.floor(Math.random() * 500) + 1500}+ 종목</span>
                  </div>
                </div>
            </div>
          </div>
        </div>
      </div>
      <div className="mt-auto w-full max-w-[1440px] mx-auto p-8 flex justify-end">
          <button
            onClick={onNext}
            className="group px-10 py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl font-black flex items-center gap-3 transition-all hover:scale-[1.02] active:scale-[0.98] shadow-[0_0_30px_rgba(37,99,235,0.3)] hover:shadow-[0_0_40px_rgba(37,99,235,0.5)] border border-white/10"
          >
            다음 단계: 매매 조건 설정
            <ArrowRightIcon className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
          </button>
      </div>
    </div>
  );
}
