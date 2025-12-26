          {currentStep === 5 && (
            <div className="h-full flex flex-col p-8 gap-6">
                <div className="flex items-center justify-between shrink-0 mb-4">
                  <div>
                    <h3 className="text-xl font-black text-white tracking-tight">전략 검증</h3>
                    <p className="text-sm text-gray-500 mt-1 font-medium">
                      백테스트 결과를 확인하고 전략을 최종 점검하세요
                    </p>
                  </div>
                </div>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 flex-1 min-h-0">
              <div className="xl:col-span-2 space-y-4">
                <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-semibold text-white">미리보기 차트 (최근 1년)</h4>
                    {isBacktesting && (
                      <span className="text-xs text-blue-400 flex items-center gap-1">
                        <ArrowPathIcon className="w-3 h-3 animate-spin" />
                        시뮬레이션 중...
                      </span>
                    )}
                  </div>
                  <div className="h-72 bg-[#0a0a0f] rounded border border-gray-800 overflow-hidden relative">
                    {backtestResult ? (
                      <BacktestChart
                        type="equity"
                        height={288}
                        equityData={backtestResult.dates.map((date: string, i: number) => ({
                          time: date,
                          equity: backtestResult.equity[i],
                          buyHold: backtestResult.initialCapital * (1 + (backtestResult.buyAndHoldReturn || 0) / 100), // Simple approx or need actual data
                        }))}
                      />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
                        {isBacktesting ? "시뮬레이션 데이터를 불러오는 중..." : "데이터 없음"}
                      </div>
                    )}
                  </div>
                </div>
                <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                  <h4 className="text-sm font-semibold text-white mb-3">트레이드 로그</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto text-sm text-gray-300 pr-2 custom-scrollbar">
                    {backtestResult?.tradesList && backtestResult.tradesList.length > 0 ? (
                      backtestResult.tradesList.slice().reverse().map((trade: any, idx: number) => (
                        <div key={idx} className="flex justify-between items-center p-2 rounded bg-[#1a1a1a] border border-gray-800/50">
                          <div className="flex items-center gap-2">
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              trade.type === "buy" ? "bg-red-500/20 text-red-400" : "bg-blue-500/20 text-blue-400"
                            }`}>
                              {trade.type === "buy" ? "매수" : "매도"}
                            </span>
                            <span className="text-gray-400">{trade.date}</span>
                          </div>
                          <div className="flex items-center gap-3">
                            <span>{formatPrice(trade.price)}원</span>
                            <span className="text-gray-500 text-xs">{trade.quantity}주</span>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-center text-gray-500 py-4">
                        거래 기록이 없습니다.
                      </div>
                    )}
                  </div>
                </div>
              </div>
              <div className="space-y-4">
                <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4">
                  <h4 className="text-sm font-semibold text-white mb-3">성과 요약</h4>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="p-3 rounded bg-[#1a1a1a] border border-gray-800">
                      <div className="text-xs text-gray-400 mb-1">수익률</div>
                      <div className={`text-lg font-bold ${
                        (backtestResult?.totalReturn || 0) >= 0 ? "text-red-400" : "text-blue-400"
                      }`}>
                        {backtestResult?.totalReturn.toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-3 rounded bg-[#1a1a1a] border border-gray-800">
                      <div className="text-xs text-gray-400 mb-1">MDD</div>
                      <div className="text-lg font-bold text-blue-400">
                        {backtestResult?.maxDrawdown.toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-3 rounded bg-[#1a1a1a] border border-gray-800">
                      <div className="text-xs text-gray-400 mb-1">승률</div>
                      <div className="text-lg font-bold text-white">
                        {backtestResult?.winRate.toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-3 rounded bg-[#1a1a1a] border border-gray-800">
                      <div className="text-xs text-gray-400 mb-1">총 거래</div>
                      <div className="text-lg font-bold text-white">
                        {backtestResult?.trades}회
                      </div>
                    </div>
                  </div>
                </div>
                <div className="bg-[#0f0f0f] rounded-lg border border-gray-800 p-4 space-y-4">
                  <div className="flex items-center gap-2 text-green-400 mb-1">
                    <CheckCircleIcon className="w-5 h-5" />
                    <span className="text-sm font-bold uppercase tracking-wider">검증 완료</span>
                  </div>
                  <p className="text-xs text-gray-500 leading-relaxed">
                    설정한 조건에 따른 시뮬레이션 결과입니다. 만족하신다면 전략을 저장하고 가상 계좌에 연결하여 실전 테스트를 시작할 수 있습니다.
                  </p>
                  <div className="flex gap-3">
                    <button
                      onClick={() => setCurrentStep(4)}
                      className="flex-1 px-4 py-4 bg-[#1a1a1a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center justify-center gap-2"
                    >
                      <ArrowLeftIcon className="w-5 h-5" />
                      이전 단계
                    </button>
                    <button
                      onClick={handleSave}
                      className="flex-[2] px-4 py-4 bg-red-600 text-white rounded-xl text-md font-black hover:bg-red-500 transition-all shadow-xl shadow-red-900/20 hover:scale-[1.02]"
                    >
                      전략 저장 및 완료
                    </button>
                  </div>
                </div>
              </div>
            </div>
            </div>
          )}
