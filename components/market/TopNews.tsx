"use client";

import { useEffect, useState } from "react";
import { NewspaperIcon } from "@heroicons/react/24/outline";

interface NewsItem {
  id: number;
  title: string;
  source: string;
  publishedAt: string;
  category: string;
  url?: string;
}

export default function TopNews() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchNews();
  }, []);

  const fetchNews = async () => {
    try {
      const response = await fetch("/api/news/top");
      if (response.ok) {
        const data = await response.json();
        setNews(data.news || []);
      }
    } catch (error) {
      console.error("Failed to fetch news:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-800 rounded w-1/4"></div>
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-gray-800 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (news.length === 0) {
    return (
      <div className="bg-[#1a1a1a] border-gray-800 p-4 sm:p-6 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden">
        <div className="flex items-center gap-2 mb-4">
          <NewspaperIcon className="w-5 h-5 text-gray-400" />
          <h3 className="text-base sm:text-lg font-semibold text-white">
            주요뉴스
          </h3>
        </div>
        <p className="text-gray-400">
          뉴스가 없습니다.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1a1a] border-gray-800 p-3 sm:p-4 rounded-lg shadow-sm border border-gray-800 w-full max-w-full overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <NewspaperIcon className="w-5 h-5 text-gray-400" />
          <h3 className="text-base sm:text-lg font-semibold text-white">
            주요뉴스
          </h3>
        </div>
        <button
          onClick={fetchNews}
          className="text-xs sm:text-sm text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
        >
          새로고침
        </button>
      </div>

      <div className="space-y-3">
        {news.map((item) => (
          <div
            key={item.id}
            className="p-3 sm:p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors cursor-pointer"
            onClick={() => item.url && window.open(item.url, "_blank")}
          >
            <div className="flex items-start gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs sm:text-sm font-medium text-blue-500 dark:text-blue-400">
                    {item.category}
                  </span>
                  <span className="text-xs text-gray-400">
                    {item.source}
                  </span>
                </div>
                <h4 className="text-sm sm:text-base font-semibold text-white mb-1 line-clamp-2">
                  {item.title}
                </h4>
                <p className="text-xs text-gray-400">
                  {new Date(item.publishedAt).toLocaleDateString("ko-KR", {
                    year: "numeric",
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

