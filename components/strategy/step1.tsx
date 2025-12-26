          {currentStep === 1 && (
            <div className="flex flex-col min-h-full">
              <div className="p-8 max-w-3xl mx-auto space-y-12">
              <div className="flex flex-col gap-2 border-b border-gray-800 pb-8">
                <input
                  type="text"
                  value={strategyName}
                  onChange={(e) => setStrategyName(e.target.value)}
                  placeholder="새로운 전략의 이름을 입력하세요"
                  className="text-4xl font-black text-white bg-transparent border-none outline-none placeholder:text-gray-800 tracking-tighter"
                />
                <p className="text-gray-500 text-sm mt-2">탐색할 시장의 범위와 기본적인 필터링 조건을 설정합니다.</p>
              </div>

              <div className="space-y-12">
                {/* Section 1: 시장 및 규모 (Market & Scale) */}
                <div className="space-y-6">
                  <div className="flex items-center gap-2">
                    <GlobeAltIcon className="w-5 h-5 text-blue-400" />
                    <h3 className="text-lg font-bold text-white uppercase tracking-wider">시장 및 규모</h3>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    {[
                      { id: "kospi", name: "KOSPI", desc: "대형주/안정적" },
                      { id: "kosdaq", name: "KOSDAQ", desc: "기술주/성장" },
                      { id: "kospi200", name: "KOSPI 200", desc: "대표 우량 200" },
                    ].map((m) => (
                      <div
                        key={m.id}
                        onClick={() => setUniverse(m.id)}
                        className={`p-5 rounded-xl cursor-pointer transition-all border-2 flex flex-col justify-center text-center ${
                          universe === m.id
                            ? "bg-blue-900/20 border-blue-500/50 shadow-[0_0_15px_rgba(59,130,246,0.15)]"
                            : "bg-[#1a1a1a] border-gray-800 hover:border-gray-700"
                        }`}
                      >
                        <div className="text-md font-bold text-white">{m.name}</div>
                        <div className="text-[11px] text-gray-500 mt-1">{m.desc}</div>
                      </div>
                    ))}
                  </div>

                  <div className="bg-[#1a1a1a] rounded-xl p-6 border border-gray-800 space-y-8">
                    <div className="space-y-4">
                      <div className="flex justify-between items-center">
                        <label className="text-sm font-medium text-gray-300">시가총액 범위 (%)</label>
                        <span className="text-xs text-blue-400 bg-blue-400/10 px-2 py-1 rounded">
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
                        <div className="flex justify-between text-[10px] text-gray-600 mt-2 font-mono">
                          <span>대형주 (0%)</span>
                          <span>중형주 (50%)</span>
                          <span>소형주 (100%)</span>
                        </div>
                      </div>
                    </div>

                    <div className="space-y-4">
                      <div className="flex justify-between items-center">
                        <label className="text-sm font-medium text-gray-300">최소 거래대금 (20일 평균)</label>
                        <span className="text-xs text-green-400 bg-green-400/10 px-2 py-1 rounded">
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
                          className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-green-500"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Section 2: 섹터 선택 (Sector Selection) */}
                <div className="space-y-6">
                  <div className="flex items-center gap-2">
                    <TagIcon className="w-5 h-5 text-green-400" />
                    <h3 className="text-lg font-bold text-white uppercase tracking-wider">섹터 선택</h3>
                  </div>

                  <div className="bg-[#1a1a1a] rounded-xl p-6 border border-gray-800 space-y-6">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                      <label className="text-sm font-medium text-gray-300">포함할 섹터 (미선택 시 전체)</label>
                      <div className="relative">
                        <MagnifyingGlassIcon className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
                        <input 
                          type="text"
                          placeholder="섹터 검색..."
                          value={sectorSearchTerm}
                          onChange={(e) => setSectorSearchTerm(e.target.value)}
                          className="pl-9 pr-4 py-2 bg-[#0a0a0a] border border-gray-800 rounded-lg text-xs text-white focus:outline-none focus:border-blue-500 transition-all w-full sm:w-64"
                        />
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2 max-h-[250px] overflow-y-auto pr-2 custom-scrollbar p-1">
                       {ALL_SECTORS.filter(s => s.toLowerCase().includes(sectorSearchTerm.toLowerCase())).map(sector => (
                        <button
                          key={sector}
                          onClick={() => {
                            const next = universeFilters.selectedSectors.includes(sector)
                              ? universeFilters.selectedSectors.filter(s => s !== sector)
                              : [...universeFilters.selectedSectors, sector];
                            setUniverseFilters({...universeFilters, selectedSectors: next});
                          }}
                          className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all border ${
                            universeFilters.selectedSectors.includes(sector)
                              ? "bg-green-600 border-green-500 text-white shadow-lg shadow-green-600/20"
                              : "bg-[#0a0a0a] border-gray-800 text-gray-500 hover:text-gray-300 hover:border-gray-700"
                          }`}
                        >
                          {sector}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Section 3: 제외 필터 (Exclusion Filters) */}
                <div className="space-y-6">
                  <div className="flex items-center gap-2">
                    <ShieldExclamationIcon className="w-5 h-5 text-red-500" />
                    <h3 className="text-lg font-bold text-white uppercase tracking-wider">제외 필터</h3>
                  </div>

                  <div className="bg-[#1a1a1a] rounded-xl p-6 border border-gray-800 space-y-8">
                    {/* Fundamental Exclusions */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <button
                        onClick={() => setUniverseFilters({...universeFilters, excludeLossMaking: !universeFilters.excludeLossMaking})}
                        className={`p-4 rounded-xl border transition-all flex items-center gap-4 text-left ${
                          universeFilters.excludeLossMaking 
                            ? "bg-red-500/10 border-red-500/50" 
                            : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                        }`}
                      >
                        <ShieldExclamationIcon className={`w-5 h-5 ${universeFilters.excludeLossMaking ? "text-red-400" : "text-gray-500"}`} />
                        <div>
                          <p className="text-sm font-bold text-white">적자 기업 제외</p>
                          <p className="text-[10px] text-gray-500">최근 분기 영업이익 기준</p>
                        </div>
                      </button>

                      <button
                        onClick={() => setUniverseFilters({...universeFilters, excludeCapitalImpaired: !universeFilters.excludeCapitalImpaired})}
                        className={`p-4 rounded-xl border transition-all flex items-center gap-4 text-left ${
                          universeFilters.excludeCapitalImpaired 
                            ? "bg-red-500/10 border-red-500/50" 
                            : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                        }`}
                      >
                         <ExclamationTriangleIcon className={`w-5 h-5 ${universeFilters.excludeCapitalImpaired ? "text-red-400" : "text-gray-500"}`} />
                        <div>
                          <p className="text-sm font-bold text-white">자본잠식 제외</p>
                          <p className="text-[10px] text-gray-500">재무 건전성 미달 종목</p>
                        </div>
                      </button>
                    </div>

                    {/* Checkbox Group: Listing & structural */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-4">
                      {[
                        { id: 'excludePennyStocks', label: '동전주 제외 (1,000원 미만)' },
                        { id: 'excludeNewListings', label: '신규 상장주 제외 (1년 이내)' },
                        { id: 'excludeHighVolatility', label: '급등락주 제외 (변동성 상위)' },
                        { id: 'excludeAdministrative', label: '관리종목 및 거래정지 제외' },
                        { id: 'excludeInvestmentWarning', label: '투자주의 / 경고 / 위험 제외' },
                        { id: 'excludeDelistingPending', label: '정리매매 종목 제외' },
                        { id: 'excludeETF_ETN', label: 'ETF / ETN 제외' },
                        { id: 'excludeSPAC', label: 'SPAC (기업인수목적) 제외' },
                        { id: 'excludeREITs', label: '리츠 (부동산투자) 제외' },
                        { id: 'excludePreferred', label: '우선주 제외' }
                      ].map((item) => (
                        <label key={item.id} className="flex items-center gap-3 cursor-pointer group">
                          <input 
                            type="checkbox" 
                            checked={(universeFilters as any)[item.id]}
                            onChange={(e) => setUniverseFilters({...universeFilters, [item.id]: e.target.checked})}
                            className="w-4 h-4 rounded border-gray-700 bg-gray-900 text-red-500 focus:ring-red-500/20 shadow-sm" 
                          />
                          <span className="text-sm text-gray-400 group-hover:text-gray-200 transition-colors">{item.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

            </div>
            
            {/* Sticky Navigation Footer */}
            <div className="sticky bottom-0 bg-[#0a0a0a]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end z-50 mt-auto">
              <button
                onClick={() => setCurrentStep(2)}
                className="px-10 py-4 bg-blue-600 text-white rounded-xl font-black hover:bg-blue-500 flex items-center gap-3 transition-all hover:scale-[1.02] shadow-xl shadow-blue-900/40"
              >
                다음 단계: 매매 조건 설정
                <ArrowRightIcon className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
