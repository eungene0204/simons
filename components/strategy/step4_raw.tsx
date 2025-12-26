
          {currentStep === 4 && (
            <div className="flex flex-col min-h-full">
              <div className="space-y-6 p-8">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h3 className="text-xl font-black text-white tracking-tight">리스크 관리</h3>
                    <p className="text-sm text-gray-500 mt-1 font-medium">
                      손절매, 익절매 등 자산 보호를 위한 규칙을 설정합니다.
                    </p>
                  </div>
                </div>
              <div className="bg-[#0f0f0f] rounded-2xl border border-gray-800/50 p-8 min-h-[580px] max-w-5xl mx-auto flex items-center justify-center shadow-2xl">
                 <div className="text-center">
                   <div className="w-16 h-16 rounded-2xl bg-orange-500/10 flex items-center justify-center border border-orange-500/20 mx-auto mb-4">
                     <ShieldCheckIcon className="w-8 h-8 text-orange-400" />
                   </div>
                   <h4 className="text-lg font-bold text-white mb-2">리스크 규칙 구성</h4>
                    <p className="text-sm text-gray-500 max-w-sm">여기에 리스크 관리 블록들이 배치될 예정입니다.</p>
                  </div>
               </div>
             </div>

              {/* Sticky Navigation Footer */}
              <div className="sticky bottom-0 bg-[#0a0a0a]/90 backdrop-blur-xl border-t border-gray-800/50 p-6 flex justify-end gap-3 z-50 mt-auto">
                <button
                  onClick={() => setCurrentStep(3)}
                  className="px-6 py-3 bg-[#1a1a1a] border border-gray-800 text-gray-300 rounded-xl text-md font-black hover:bg-gray-800 hover:text-white transition-all flex items-center gap-2"
                >
                  <ArrowLeftIcon className="w-5 h-5" />
                  이전 단계
                </button>
                <button
                  onClick={() => setCurrentStep(5)}
                  className="px-8 py-3 bg-blue-600 text-white rounded-xl text-md font-black hover:bg-blue-500 transition-all flex items-center gap-3 shadow-xl shadow-blue-900/40 hover:scale-[1.02]"
                >
                  다음: 미리보기
                  <ArrowRightIcon className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        )}

