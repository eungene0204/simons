"use client";

import { DevicePhoneMobileIcon } from "@heroicons/react/24/outline";

export default function AppPromotion() {
  return (
    <div className="bg-white dark:bg-gray-800 p-3 sm:p-4 md:p-5 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 w-full max-w-full overflow-x-hidden min-w-0">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-6 items-center min-w-0">
        {/* Left: Mobile App Screenshots */}
        <div className="flex justify-center xl:justify-start gap-2 sm:gap-3 min-w-0">
          <div className="flex flex-col gap-2 sm:gap-3 min-w-0">
            {/* Mobile Screen 1 */}
            <div className="relative w-16 sm:w-20 md:w-24 lg:w-28 xl:w-32 flex-shrink-0">
              <div className="bg-white dark:bg-gray-900 rounded-[2rem] p-1.5 sm:p-2 shadow-2xl border-2 sm:border-4 border-gray-200 dark:border-gray-700">
                <div className="bg-gray-100 dark:bg-gray-800 rounded-[1.5rem] aspect-[9/19.5] overflow-hidden">
                  {/* Status Bar */}
                  <div className="bg-white dark:bg-gray-900 px-2 sm:px-4 py-0.5 sm:py-1 flex justify-between items-center text-[10px] sm:text-xs">
                    <span>9:41</span>
                    <div className="flex gap-1">
                      <div className="w-4 h-2 border border-gray-900 dark:border-gray-100 rounded-sm"></div>
                      <div className="w-1 h-1 bg-gray-900 dark:bg-gray-100 rounded-full"></div>
                    </div>
                  </div>
                  {/* Content */}
                  <div className="p-2 sm:p-4 h-full bg-white dark:bg-gray-900">
                    <div className="text-center mb-2 sm:mb-4">
                      <div className="w-10 h-10 sm:w-16 sm:h-16 bg-blue-100 dark:bg-blue-800 rounded-full mx-auto mb-1 sm:mb-2 flex items-center justify-center">
                        <span className="text-lg sm:text-2xl font-bold text-blue-500 dark:text-blue-400">
                          S
                        </span>
                      </div>
                      <h3 className="text-[10px] sm:text-sm font-semibold text-gray-900 dark:text-white mb-1 sm:mb-2">
                        THE CIRCLE
                      </h3>
                      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-2 sm:p-3 mb-1 sm:mb-2">
                        <div className="text-[8px] sm:text-xs text-gray-600 dark:text-gray-400 mb-0.5 sm:mb-1">
                          NOT FOLLOWING BACK
                        </div>
                        <div className="text-lg sm:text-2xl font-bold text-yellow-500">124</div>
                      </div>
                      <button className="w-full bg-blue-600 text-white text-[10px] sm:text-xs py-1 sm:py-2 rounded-lg">
                        Who are them
                      </button>
                    </div>
                  </div>
                  {/* Bottom Navigation */}
                  <div className="absolute bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-2 py-1">
                    <div className="flex justify-around text-[8px] text-gray-500 dark:text-gray-400">
                      <div className="text-center">
                        <div className="w-4 h-4 mx-auto mb-0.5 bg-gray-300 dark:bg-gray-600 rounded"></div>
                        <span>HOME</span>
                      </div>
                      <div className="text-center">
                        <div className="w-4 h-4 mx-auto mb-0.5 bg-gray-300 dark:bg-gray-600 rounded"></div>
                        <span>MY TWEETS</span>
                      </div>
                      <div className="text-center">
                        <div className="w-4 h-4 mx-auto mb-0.5 bg-blue-600 rounded"></div>
                        <span className="text-blue-500 dark:text-blue-400">THE CIRCLE</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Mobile Screen 2 */}
          <div className="relative w-16 sm:w-20 md:w-24 lg:w-28 xl:w-32 mt-4 sm:mt-6 flex-shrink-0">
            <div className="bg-white dark:bg-gray-900 rounded-[2rem] p-1.5 sm:p-2 shadow-2xl border-2 sm:border-4 border-gray-200 dark:border-gray-700">
              <div className="bg-gray-100 dark:bg-gray-800 rounded-[1.5rem] aspect-[9/19.5] overflow-hidden">
                {/* Status Bar */}
                <div className="bg-white dark:bg-gray-900 px-2 sm:px-4 py-0.5 sm:py-1 flex justify-between items-center text-[10px] sm:text-xs">
                  <span>9:41</span>
                  <div className="flex gap-1">
                    <div className="w-4 h-2 border border-gray-900 dark:border-gray-100 rounded-sm"></div>
                    <div className="w-1 h-1 bg-gray-900 dark:bg-gray-100 rounded-full"></div>
                  </div>
                </div>
                {/* Content */}
                <div className="p-2 sm:p-4 h-full bg-white dark:bg-gray-900">
                  <h3 className="text-[10px] sm:text-sm font-semibold text-gray-900 dark:text-white mb-1.5 sm:mb-3">
                    FOLLOWERS GROWTH
                  </h3>
                  <div className="space-y-1 sm:space-y-2 mb-1.5 sm:mb-3">
                    <div className="text-[8px] sm:text-xs text-gray-600 dark:text-gray-400">
                      Most Followers 132 (March 26)
                    </div>
                    <div className="text-[8px] sm:text-xs text-gray-600 dark:text-gray-400">
                      Monthly Diff 110 (March 2021)
                    </div>
                  </div>
                  <div className="flex gap-0.5 sm:gap-1 mb-1.5 sm:mb-3">
                    <button className="px-1.5 sm:px-2 py-0.5 sm:py-1 text-[8px] sm:text-xs bg-gray-100 dark:bg-gray-800 rounded">
                      1D
                    </button>
                    <button className="px-1.5 sm:px-2 py-0.5 sm:py-1 text-[8px] sm:text-xs bg-gray-100 dark:bg-gray-800 rounded">
                      1W
                    </button>
                    <button className="px-1.5 sm:px-2 py-0.5 sm:py-1 text-[8px] sm:text-xs bg-blue-600 text-white rounded">
                      1M
                    </button>
                  </div>
                  <div className="h-16 sm:h-32 bg-blue-100 dark:bg-blue-800 rounded-lg flex items-end justify-center">
                    <div className="w-full h-3/4 bg-blue-600 rounded-t-lg"></div>
                  </div>
                </div>
                {/* Bottom Navigation */}
                <div className="absolute bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-2 py-1">
                  <div className="flex justify-around text-[8px] text-gray-500 dark:text-gray-400">
                    <div className="text-center">
                      <div className="w-4 h-4 mx-auto mb-0.5 bg-gray-300 dark:bg-gray-600 rounded"></div>
                      <span>HOME</span>
                    </div>
                    <div className="text-center">
                      <div className="w-4 h-4 mx-auto mb-0.5 bg-gray-300 dark:bg-gray-600 rounded"></div>
                      <span>ANALYTICS</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Mobile Screen 3 */}
          <div className="relative w-16 sm:w-20 md:w-24 lg:w-28 xl:w-32 mt-4 sm:mt-6 flex-shrink-0 hidden md:block">
            <div className="bg-white dark:bg-gray-900 rounded-[2rem] p-1.5 sm:p-2 shadow-2xl border-2 sm:border-4 border-gray-200 dark:border-gray-700">
              <div className="bg-gray-100 dark:bg-gray-800 rounded-[1.5rem] aspect-[9/19.5] overflow-hidden">
                {/* Status Bar */}
                <div className="bg-white dark:bg-gray-900 px-2 sm:px-4 py-0.5 sm:py-1 flex justify-between items-center text-[10px] sm:text-xs">
                  <span>9:41</span>
                  <div className="flex gap-1">
                    <div className="w-4 h-2 border border-gray-900 dark:border-gray-100 rounded-sm"></div>
                    <div className="w-1 h-1 bg-gray-900 dark:bg-gray-100 rounded-full"></div>
                  </div>
                </div>
                {/* Content */}
                <div className="p-2 sm:p-4 h-full bg-white dark:bg-gray-900 overflow-y-auto">
                  <h3 className="text-[10px] sm:text-sm font-semibold text-gray-900 dark:text-white mb-1.5 sm:mb-3">
                    THE CIRCLE
                  </h3>
                  <div className="space-y-1 sm:space-y-2">
                    {[
                      "Not Following Back",
                      "Fake / Spam Friends",
                      "Inactive Friends",
                      "Overactive Friends",
                    ].map((item, idx) => (
                      <div
                        key={idx}
                        className="p-1 sm:p-2 bg-gray-50 dark:bg-gray-800 rounded-lg flex items-center justify-between"
                      >
                        <span className="text-[8px] sm:text-xs text-gray-700 dark:text-gray-300">
                          {item}
                        </span>
                        <span className="text-[8px] sm:text-xs text-gray-400">→</span>
                      </div>
                    ))}
                  </div>
                </div>
                {/* Bottom Navigation */}
                <div className="absolute bottom-0 left-0 right-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 px-2 py-1">
                  <div className="flex justify-around text-[8px] text-gray-500 dark:text-gray-400">
                    <div className="text-center">
                      <div className="w-4 h-4 mx-auto mb-0.5 bg-blue-600 rounded"></div>
                      <span className="text-blue-500 dark:text-blue-400">THE CIRCLE</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right: App Promotion Text */}
        <div className="text-center xl:text-left min-w-0">
          <div className="flex items-center justify-center xl:justify-start gap-2 mb-2 sm:mb-3">
            <DevicePhoneMobileIcon className="w-5 h-5 sm:w-6 sm:h-6 text-blue-500 dark:text-blue-400 flex-shrink-0" />
            <h2 className="text-lg sm:text-xl md:text-2xl lg:text-3xl font-bold text-gray-900 dark:text-white break-words">
              Manage your stock portfolio on the go!
            </h2>
          </div>
          <p className="text-xs sm:text-sm md:text-base text-gray-600 dark:text-gray-400 mb-4 sm:mb-5 leading-relaxed break-words">
            With 널스탁 App, you manage your stock portfolio while you&apos;re mobile! 
            널스탁 App works the same as our web version. Get it now on the App Store.
          </p>
          
          {/* App Store Badge */}
          <div className="flex justify-center xl:justify-start">
            <a
              href="#"
              className="inline-block"
              onClick={(e) => {
                e.preventDefault();
                // App Store link would go here
              }}
            >
              <div className="bg-black dark:bg-white rounded-lg px-4 py-2 sm:px-5 sm:py-2.5 flex items-center gap-2 hover:opacity-90 transition-opacity">
                <svg
                  className="w-5 h-5 sm:w-6 sm:h-6 text-white dark:text-black"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09l.01-.01zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
                </svg>
                <span className="text-white dark:text-black font-semibold text-xs sm:text-sm">
                  Available on the App Store
                </span>
              </div>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

