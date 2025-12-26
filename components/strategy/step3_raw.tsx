          {currentStep === 3 && (
            <div className="flex flex-col min-h-full">
              <div className="space-y-6 p-8">
               <div className="flex items-center justify-between mb-6">
                 <div>
                   <h3 className="text-xl font-black text-white tracking-tight">포지션 & 비중 설정</h3>
                   <p className="text-sm text-gray-500 mt-1 font-medium">
                     자산 배분 방식과 매매 체결 시점, 리밸런싱 주기를 구성합니다.
                   </p>
                 </div>
               </div>

                <div className="bg-[#0f0f0f] rounded-2xl border border-gray-800/50 p-8 min-h-[580px] max-w-5xl mx-auto shadow-2xl">
                 <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                   {/* Section 1: Capital & Max Positions */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center border border-blue-500/20 shadow-inner">
                         <BanknotesIcon className="w-5 h-5 text-blue-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">자산 및 포트폴리오</h4>
                         <p className="text-[11px] text-gray-500">운용 규모와 분산 투자 범위를 설정합니다.</p>
                       </div>
                     </div>
                     
                     <div className="space-y-6 bg-[#1a1a1a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <div>
                         <label className="text-[10px] text-gray-500 font-black mb-2.5 block uppercase tracking-widest">초기 자본금</label>
                         <div className="relative group">
                           <input 
                             type="number" 
                             value={initialCapital}
                             onChange={(e) => setInitialCapital(Number(e.target.value))}
                             className="w-full bg-[#0a0a0a] border border-gray-800 rounded-xl px-5 py-3.5 text-white font-black text-lg focus:border-blue-500/50 focus:ring-4 focus:ring-blue-500/5 outline-none transition-all group-hover:border-gray-700"
                           />
                           <span className="absolute right-5 top-1/2 -translate-y-1/2 text-gray-600 font-bold text-sm">KRW</span>
                         </div>
                       </div>
                       
                       <div>
                         <div className="flex justify-between items-end mb-3">
                           <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">최대 보유 종목 수</label>
                           <span className="text-lg font-black text-blue-400">{maxPositions}<span className="text-xs ml-0.5 text-gray-500">개</span></span>
                         </div>
                         <div className="flex items-center gap-4">
                           <input 
                             type="range" 
                             min="1" 
                             max="100" 
                             value={maxPositions}
                             onChange={(e) => setMaxPositions(Number(e.target.value))}
                             className="flex-1 h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                           />
                         </div>
                         <p className="text-[10px] text-gray-500 mt-3 font-medium">동시에 최대 {maxPositions}개의 종목까지 매수합니다.</p>
                       </div>
                     </div>
                   </div>

                   {/* Section 2: Allocation Strategy */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center border border-red-500/20 shadow-inner">
                         <ChartPieIcon className="w-5 h-5 text-red-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">비중 배분 정책</h4>
                         <p className="text-[11px] text-gray-500">개별 종목당 자산 투입 비중을 결정합니다.</p>
                       </div>
                     </div>

                     <div className="space-y-6 bg-[#1a1a1a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <div className="flex p-1 bg-[#0a0a0a] rounded-xl border border-gray-800">
                         <button 
                           onClick={() => setAllocationType("equal")}
                           className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                             allocationType === "equal" 
                               ? "bg-red-500 text-white shadow-lg shadow-red-900/40" 
                               : "text-gray-500 hover:text-gray-300"
                           }`}
                         >
                           동일 비중
                         </button>
                         <button 
                           onClick={() => setAllocationType("fixed_pct")}
                           className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                             allocationType === "fixed_pct" 
                               ? "bg-red-500 text-white shadow-lg shadow-red-900/40" 
                               : "text-gray-500 hover:text-gray-300"
                           }`}
                         >
                           고정 비중 (%)
                         </button>
                       </div>

                       <div className="min-h-[80px]">
                         {allocationType === "fixed_pct" ? (
                           <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                             <div className="flex justify-between items-end mb-3">
                               <label className="text-[10px] text-gray-500 font-black uppercase tracking-widest">종목당 투입 비중</label>
                               <span className="text-lg font-black text-red-400">{allocationValue}<span className="text-xs ml-0.5 text-gray-500">%</span></span>
                             </div>
                             <div className="flex items-center gap-4">
                               <input 
                                 type="range" 
                                 min="1" 
                                 max="100" 
                                 value={allocationValue}
                                 onChange={(e) => setAllocationValue(Number(e.target.value))}
                                 className="flex-1 h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-red-500"
                               />
                             </div>
                             <p className="text-[10px] text-gray-500 mt-3 font-medium">거래 건마다 가용 자산의 {allocationValue}%를 고정적으로 투자합니다.</p>
                           </div>
                         ) : (
                           <div className="animate-in fade-in duration-300">
                             <div className="p-4 bg-red-500/5 border border-red-500/10 rounded-xl">
                               <p className="text-[11px] text-red-400/80 leading-relaxed font-bold italic">
                                 "최대 보유 종목 수({maxPositions}개)에 맞춰 모든 자산을 균등하게 배분합니다. 종목당 배정 목표는 약 {Number(100/maxPositions).toFixed(1)}% 입니다."
                               </p>
                             </div>
                           </div>
                         )}
                       </div>
                     </div>
                   </div>

                   {/* Section 3: Execution Timing */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center border border-orange-500/20 shadow-inner">
                         <ClockIcon className="w-5 h-5 text-orange-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">체결 시점 선택</h4>
                         <p className="text-[11px] text-gray-500">조건 충족 시 실제 주문이 나가는 타이밍입니다.</p>
                       </div>
                     </div>

                     <div className="grid grid-cols-1 gap-3 bg-[#1a1a1a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <button 
                         onClick={() => setExecutionTiming("next_open")}
                         className={`px-5 py-4 rounded-xl border transition-all text-left flex items-start gap-4 ${
                           executionTiming === "next_open"
                             ? "bg-orange-500/10 border-orange-500/30 ring-1 ring-orange-500/20"
                             : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                         }`}
                       >
                         <div className={`w-2 h-2 rounded-full mt-1.5 ${executionTiming === "next_open" ? "bg-orange-400 animate-pulse" : "bg-gray-700"}`} />
                         <div>
                           <div className={`text-sm font-black mb-1 ${executionTiming === "next_open" ? "text-orange-400" : "text-gray-400"}`}>익일 시가 (Next Open)</div>
                           <div className="text-[11px] text-gray-500 leading-tight">신호가 발생한 다음 영업일 아침 시가에 즉시 체결합니다. 가장 일반적인 방식입니다.</div>
                         </div>
                       </button>
                       <button 
                         onClick={() => setExecutionTiming("current_close")}
                         className={`px-5 py-4 rounded-xl border transition-all text-left flex items-start gap-4 ${
                           executionTiming === "current_close"
                             ? "bg-orange-500/10 border-orange-500/30 ring-1 ring-orange-500/20"
                             : "bg-[#0a0a0a] border-gray-800 hover:border-gray-700"
                         }`}
                       >
                         <div className={`w-2 h-2 rounded-full mt-1.5 ${executionTiming === "current_close" ? "bg-orange-400 animate-pulse" : "bg-gray-700"}`} />
                         <div>
                           <div className={`text-sm font-black mb-1 ${executionTiming === "current_close" ? "text-orange-400" : "text-gray-400"}`}>당일 종가 (Direct Close)</div>
                           <div className="text-[11px] text-gray-500 leading-tight">신호가 발생한 당일 장 마감 직전 종가로 체결합니다. 빠른 대응이 가능합니다.</div>
                         </div>
                       </button>
                     </div>
                   </div>

                   {/* Section 4: Rebalancing */}
                   <div className="space-y-6">
                     <div className="flex items-center gap-3.5 mb-2">
                       <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center border border-emerald-500/20 shadow-inner">
                         <ArrowPathIcon className="w-5 h-5 text-emerald-400" />
                       </div>
                       <div>
                         <h4 className="text-md font-black text-white">리밸런싱 설정</h4>
                         <p className="text-[11px] text-gray-500">보유 종목의 비중을 정기적으로 재조정합니다.</p>
                       </div>
                     </div>

                     <div className="bg-[#1a1a1a]/40 p-6 rounded-2xl border border-gray-800/40 backdrop-blur-sm">
                       <div className="flex p-1 bg-[#0a0a0a] rounded-xl border border-gray-800 mb-5">
                         {[
                           { id: "none", label: "안함" },
                           { id: "daily", label: "매일" },
                           { id: "weekly", label: "매주" },
                           { id: "monthly", label: "매월" }
                         ].map((period) => (
                           <button
                             key={period.id}
                             onClick={() => setRebalancingPeriod(period.id as any)}
                             className={`flex-1 py-2.5 rounded-lg text-xs font-black transition-all ${
                               rebalancingPeriod === period.id
                                 ? "bg-emerald-500 text-white shadow-lg shadow-emerald-900/40"
                                 : "text-gray-500 hover:text-gray-300"
                             }`}
                           >
                             {period.label}
                           </button>
                         ))}
                       </div>
                       <div className="p-4 bg-emerald-500/5 border border-emerald-500/10 rounded-xl">
                         <p className="text-[11px] text-emerald-400/80 leading-relaxed font-medium">
                           {rebalancingPeriod === "none" 
                             ? "💡 포지션 진입 시점의 비중을 그대로 유지하며 별도의 도중 조정을 하지 않습니다."
                             : `💡 정해진 주기(${rebalancingPeriod === "daily" ? "매일" : rebalancingPeriod === "weekly" ? "매주" : "매월"})마다 포트폴리오 비중을 배분 정책에 맞춰 다시 계산합니다.`}
                         </p>
                       </div>
                     </div>
                   </div>
                 </div>
               </div>

                </div>
              </div>
            </div>

              {/* Sticky Navigation Footer */}
                <div className="sticky bottom-0 bg-[#0a0a0a]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end gap-3 z-50 mt-auto">
                 <button
                   onClick={() => setCurrentStep(2)}
                   className="px-6 py-3 bg-[#1a1a1a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2 shadow-xl"
                 >
                   <ArrowLeftIcon className="w-5 h-5" />
                   이전 단계
                 </button>
                 <button
                   onClick={() => setCurrentStep(4)}
                   className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40 hover:scale-[1.02]"
                 >
                   다음: 리스크 관리
                   <ArrowRightIcon className="w-5 h-5" />
                 </button>
               </div>
             </div>
           )}
