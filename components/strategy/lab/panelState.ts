"use client";

import { useCallback, useEffect, useState } from "react";

// 전략 연구소 패널(좌측 서랍, 채팅 패널)의 열림 상태 — 보는 사람 브라우저에만 남는 편의 값이다.
// 저장소가 막힌 환경(사생활 보호 창 등)에서도 화면은 기본값으로 동작해야 하므로 모든 접근을 감싼다.

export const LAB_PANEL_STORAGE_KEY = "nullstock.strategyLab.panels";

export type LabPanels = { conversations: boolean; chat: boolean };

export const DEFAULT_LAB_PANELS: LabPanels = { conversations: true, chat: true };

export function readLabPanels(storage: Storage | undefined): Partial<LabPanels> {
  try {
    const raw = storage?.getItem(LAB_PANEL_STORAGE_KEY);
    if (!raw) return {};
    const value = JSON.parse(raw) as Record<string, unknown>;
    const out: Partial<LabPanels> = {};
    for (const key of ["conversations", "chat"] as const) {
      if (typeof value[key] === "boolean") out[key] = value[key] as boolean;
    }
    return out;
  } catch {
    return {};
  }
}

export function writeLabPanels(storage: Storage | undefined, panels: LabPanels): void {
  try {
    storage?.setItem(LAB_PANEL_STORAGE_KEY, JSON.stringify(panels));
  } catch {
    // 저장하지 못해도 화면 동작에는 영향이 없다.
  }
}

function safeLocalStorage(): Storage | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

/** 좁은 화면(≤1024px)에서는 서랍을 기본으로 닫고, 저장된 값보다 이 기본을 우선한다(오버레이라 가린다). */
export function useLabPanels(narrow: boolean): [LabPanels, (key: keyof LabPanels, open?: boolean) => void] {
  const [panels, setPanels] = useState<LabPanels>(DEFAULT_LAB_PANELS);

  useEffect(() => {
    const stored = { ...DEFAULT_LAB_PANELS, ...readLabPanels(safeLocalStorage()) };
    setPanels(narrow ? { ...stored, conversations: false } : stored);
  }, [narrow]);

  const toggle = useCallback(
    (key: keyof LabPanels, open?: boolean) => {
      setPanels((prev) => {
        const next = { ...prev, [key]: open ?? !prev[key] };
        if (!narrow || key === "chat") writeLabPanels(safeLocalStorage(), next);
        return next;
      });
    },
    [narrow],
  );

  return [panels, toggle];
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    // matchMedia가 없는 환경(jsdom 등)에서는 넓은 화면으로 둔다.
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const update = () => setMatches(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, [query]);
  return matches;
}
