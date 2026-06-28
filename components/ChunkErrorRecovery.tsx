"use client";

import { useEffect } from "react";

// 지연 로드되는 청크(next/dynamic, lazy import)의 청크 ID는 dev 재컴파일이나
// 배포로 무효화될 수 있다. 이때 이미 열려 있던 탭은 옛 런타임을 들고 있어
// `_next/undefined`를 요청하다 ChunkLoadError로 죽는다(에러 바운더리 없음).
// 신선한 런타임을 받도록 한 번만 새로고침해 스스로 복구한다.
//
// 무한 새로고침 방지: 직전 복구로부터 RELOAD_COOLDOWN_MS 이내면 새로고침하지
// 않는다(청크가 진짜로 사라진 깨진 빌드에서 루프가 돌지 않도록).
const RELOAD_FLAG_KEY = "chunk-reload-at";
const RELOAD_COOLDOWN_MS = 10_000;

function isChunkLoadError(value: unknown): boolean {
  if (!value) return false;
  const name = (value as { name?: string }).name;
  const message = (value as { message?: string }).message ?? "";
  return (
    name === "ChunkLoadError" ||
    /Loading chunk [\w-]+ failed/i.test(message) ||
    /Loading CSS chunk [\w-]+ failed/i.test(message) ||
    /ChunkLoadError/i.test(message)
  );
}

function recoverFromChunkError() {
  const last = Number(sessionStorage.getItem(RELOAD_FLAG_KEY) ?? 0);
  if (Date.now() - last < RELOAD_COOLDOWN_MS) return; // 방금 복구함 — 루프 방지
  sessionStorage.setItem(RELOAD_FLAG_KEY, String(Date.now()));
  window.location.reload();
}

export default function ChunkErrorRecovery() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (isChunkLoadError(event.error) || isChunkLoadError(event)) {
        recoverFromChunkError();
      }
    };
    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadError(event.reason)) {
        recoverFromChunkError();
      }
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
