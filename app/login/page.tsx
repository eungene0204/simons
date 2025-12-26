"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });

  useEffect(() => {
    if (searchParams.get("registered") === "true") {
      setSuccess("회원가입이 완료되었습니다. 로그인해주세요.");
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    if (!formData.email || !formData.password) {
      setError("이메일과 비밀번호를 입력해주세요.");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (!response.ok) {
        setError(data.error || "로그인에 실패했습니다.");
        setLoading(false);
        return;
      }

      // Success - redirect to home
      router.push("/");
      router.refresh();
    } catch (err) {
      setError("서버 오류가 발생했습니다. 다시 시도해주세요.");
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen grid grid-cols-1 lg:grid-cols-2 overflow-x-hidden max-w-full">
      <section className="flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3">
            <div className="h-10 w-10 rounded bg-gray-900 dark:bg-gray-100" />
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">널스탁</p>
              <h1 className="text-xl font-semibold">Log in to your account</h1>
            </div>
          </div>

          {error && (
            <div className="mb-4 p-3 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {success && (
            <div className="mb-4 p-3 rounded-md bg-blue-50 dark:bg-blue-800/20 border border-blue-200 dark:border-blue-800">
              <p className="text-sm text-blue-500 dark:text-blue-400">
                {success}
              </p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium mb-1">
                Email
              </label>
              <input
                id="email"
                type="email"
                placeholder="you@example.com"
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
                className="w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 outline-none focus:ring-2 focus:ring-gray-900 dark:focus:ring-gray-100"
                required
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label htmlFor="password" className="block text-sm font-medium">
                  Password
                </label>
                <Link
                  href="#"
                  className="text-sm text-blue-500 hover:underline"
                >
                  Forgot your password?
                </Link>
              </div>
              <input
                id="password"
                type="password"
                placeholder="••••••••"
                value={formData.password}
                onChange={(e) =>
                  setFormData({ ...formData, password: e.target.value })
                }
                className="w-full rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 outline-none focus:ring-2 focus:ring-gray-900 dark:focus:ring-gray-100"
                required
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-md bg-gray-900 text-white py-2.5 font-medium hover:opacity-90 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "로그인 중..." : "Log in"}
            </button>

            <p className="text-center text-sm text-gray-600 dark:text-gray-400">
              Don&apos;t have an account?{" "}
              <Link href="/register" className="text-blue-500 hover:underline">
                Create an account
              </Link>
            </p>
          </form>

          <div className="mt-10">
            <p className="text-xs uppercase tracking-wider text-gray-500 mb-3">
              Trusted By
            </p>
            <div className="flex items-center gap-6 opacity-70">
              <div className="h-6 w-20 bg-gray-200 dark:bg-gray-800 rounded" />
              <div className="h-6 w-20 bg-gray-200 dark:bg-gray-800 rounded" />
              <div className="h-6 w-20 bg-gray-200 dark:bg-gray-800 rounded" />
            </div>
          </div>
        </div>
      </section>

      <aside className="hidden lg:block relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600 via-indigo-600 to-purple-600" />
        <div className="relative h-full w-full p-12 flex flex-col justify-between text-white">
          <div>
            <p className="text-sm font-medium opacity-90">The most intuitive</p>
            <h2 className="mt-2 text-3xl font-bold leading-tight">
              Social Media Management Tool
            </h2>
            <p className="mt-4 max-w-md opacity-90">
              Discover, schedule, and publish content effortlessly across
              platforms to grow your audience.
            </p>
          </div>
          <div>
            <p className="text-sm font-medium opacity-90">We support</p>
            <div className="mt-3 flex items-center gap-3">
              <div className="h-8 w-8 rounded bg-white/20" />
              <div className="h-8 w-8 rounded bg-white/20" />
              <div className="h-8 w-8 rounded bg-white/20" />
              <div className="h-8 w-8 rounded bg-white/20" />
            </div>
          </div>
          <div className="text-xs opacity-90">
            <p>
              Terms of Service · Privacy Policy · Disclaimer · Help · Contact Us
            </p>
            <p className="mt-1">© 널스탁</p>
          </div>
        </div>
      </aside>
    </main>
  );
}
