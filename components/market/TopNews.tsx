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
    <div className="glass-card p-6 w-full max-w-full overflow-x-hidden min-w-0">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2">
          <NewspaperIcon className="w-5 h-5 text-blue-400" />
          <h3 className="text-lg font-bold text-white tracking-tight">
            주요 뉴스
          </h3>
        </div>
        <button
          onClick={fetchNews}
          className="text-xs text-gray-400 hover:text-white transition-colors"
        >
          새로고침
        </button>
      </div>

      <div className="space-y-4">
        {news.map((item) => (
          <div
            key={item.id}
            className="group relative p-4 bg-white/5 border border-white/5 rounded-xl hover:bg-white/10 hover:border-blue-500/30 transition-all duration-300 cursor-pointer overflow-hidden"
            onClick={() => item.url && window.open(item.url, "_blank")}
          >
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] font-bold text-blue-400 uppercase tracking-wider bg-blue-400/10 px-2 py-0.5 rounded">
                    {item.category}
                  </span>
                  <span className="text-[11px] text-gray-500 font-medium">
                    {item.source}
                  </span>
                </div>
                <h4 className="text-sm font-bold text-gray-100 group-hover:text-white mb-2 line-clamp-2 leading-snug">
                  {item.title}
                </h4>
                <div className="flex items-center gap-2 text-[10px] text-gray-500 font-medium">
                  {new Date(item.publishedAt).toLocaleDateString("ko-KR", {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              </div>
            </div>
            
            {/* Subtle glow on hover */}
            <div className="absolute inset-0 bg-blue-500/0 group-hover:bg-blue-500/[0.02] transition-colors pointer-events-none" />
          </div>
        ))}
      </div>
    </div>
  );
}

