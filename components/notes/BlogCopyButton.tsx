"use client";

import { useState } from "react";
import type { BlogExport } from "@/lib/notes/blogExport";

// 연구노트 요약판을 블로그 붙여 넣기용으로 복사한다 — 로컬 개발 화면에만 렌더된다(app/notes/[slug]/page.tsx).
// 서식(HTML)과 일반 텍스트를 함께 넣어, 에디터가 받을 수 있는 쪽을 고르게 한다.
export function BlogCopyButton({ content }: { content: BlogExport }) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.write([
        new ClipboardItem({
          "text/html": new Blob([content.html], { type: "text/html" }),
          "text/plain": new Blob([content.text], { type: "text/plain" }),
        }),
      ]);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
  }

  return (
    <div className="mt-6 flex flex-wrap items-center gap-3">
      <button
        type="button"
        onClick={copy}
        className="rounded-lg border border-white/[0.16] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-white/[0.06]"
      >
        블로그용 요약 복사
      </button>
      <span role="status" className="text-sm font-bold text-[var(--text-label)]">
        {status === "copied" && "복사했습니다. 블로그 글쓰기 창에 붙여 넣으세요."}
        {status === "failed" && "복사하지 못했습니다. 브라우저의 클립보드 권한을 확인해 주세요."}
      </span>
    </div>
  );
}
