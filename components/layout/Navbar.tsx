"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useState, useEffect } from "react";

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<{ name: string; email: string } | null>(
    null
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/user")
      .then((res) => res.json())
      .then((data) => {
        if (data.user) {
          setUser(data.user);
        }
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, []);

  const handleLogout = async () => {
    try {
      await fetch("/api/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    } catch (err) {
      console.error("Logout error:", err);
    }
  };

  return (
    <nav className="border-b border-gray-800 bg-[#0f0f0f]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2">
              <div className="h-8 w-8 rounded bg-gray-900 dark:bg-gray-100" />
              <span className="font-semibold text-lg">널스탁</span>
            </Link>
            <div className="hidden md:flex items-center gap-6">
              <Link
                href="/"
                className={`text-sm font-medium transition-colors ${
                  pathname === "/"
                    ? "text-white font-semibold"
                    : "text-gray-400 hover:text-white"
                }`}
              >
                대시보드
              </Link>
              <Link
                href="/portfolio"
                className={`text-sm font-medium transition-colors ${
                  pathname === "/portfolio" || pathname?.startsWith("/portfolio/")
                    ? "text-gray-900 dark:text-white font-semibold"
                    : "text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
                }`}
              >
                포트폴리오
              </Link>
              <Link
                href="/search"
                className={`text-sm font-medium transition-colors ${
                  pathname === "/search" || pathname?.startsWith("/search/")
                    ? "text-gray-900 dark:text-white font-semibold"
                    : "text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white"
                }`}
              >
                주식 검색
              </Link>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {loading ? (
              <div className="h-8 w-8 rounded-full bg-gray-200 dark:bg-gray-800 animate-pulse" />
            ) : user ? (
              <>
                <div className="hidden md:block text-right">
                  <p className="text-sm font-medium text-white">
                    {user.name}
                  </p>
                  <p className="text-xs text-gray-400">
                    {user.email}
                  </p>
                </div>
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 text-sm font-medium text-gray-300 hover:text-white border border-gray-700 rounded-md hover:bg-gray-900"
                >
                  로그아웃
                </button>
              </>
            ) : (
              <Link
                href="/login"
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white border border-gray-300 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                로그인
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
