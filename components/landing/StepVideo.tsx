"use client";

import { useEffect, useRef } from "react";

// 소개 페이지 '세 단계' 영상 — 화면에 보일 때만 재생하고 벗어나면 멈춘다(세 편이 동시에 돌지 않게).
// 원본은 scripts/landing_hero/(hero·validate·paper.html, 렌더: render.mjs). 소리가 없어 자동 재생이 허용된다.
// '움직임 줄이기'를 켠 사용자에게는 재생하지 않고 대표 장면(포스터)만 보여 준다.
export type StepVideoName = "hero" | "validate" | "paper";

export function StepVideo({ name, label }: { name: StepVideoName; label: string }) {
  const ref = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    const reduce = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    let visible = false;
    const apply = () => {
      if (visible && !reduce?.matches) {
        // 브라우저 정책으로 거부되면 포스터가 남는다. play()가 약속을 돌려주지 않는 환경(테스트)도 견딘다.
        try {
          void Promise.resolve(video.play()).catch(() => undefined);
        } catch {
          /* 재생할 수 없으면 포스터만 보인다 */
        }
      } else video.pause();
    };
    reduce?.addEventListener("change", apply);
    if (typeof IntersectionObserver === "undefined") {
      visible = true;
      apply();
      return () => reduce?.removeEventListener("change", apply);
    }
    const observer = new IntersectionObserver(
      (entries) => {
        visible = entries.some((entry) => entry.isIntersecting);
        apply();
      },
      { threshold: 0.6 },
    );
    observer.observe(video);
    return () => {
      observer.disconnect();
      reduce?.removeEventListener("change", apply);
    };
  }, []);

  return (
    <video
      ref={ref}
      className="aspect-video w-full rounded-2xl border border-white/[0.09] bg-[var(--card-bg)]"
      muted
      loop
      playsInline
      preload="metadata"
      poster={`/videos/landing-${name}-poster.jpg`}
      aria-label={label}
    >
      <source src={`/videos/landing-${name}.webm`} type="video/webm" />
      <source src={`/videos/landing-${name}.mp4`} type="video/mp4" />
    </video>
  );
}
