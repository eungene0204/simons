"use client";

import { usePathname } from "next/navigation";
import { useCallback } from "react";
import { regionFromPathname, withRegionPath, type Region } from "./region";

/** 현재 브라우저 경로에서 파생한 지역. 라우터 컨텍스트 밖(테스트 등)에선 kr. */
export function useRegion(): Region {
  return regionFromPathname(usePathname());
}

/**
 * 내부 링크·router.push 경로에 지역 프리픽스를 부여하는 헬퍼.
 * 사용: `const regionHref = useRegionHref(); <Link href={regionHref("/pricing")} />`
 */
export function useRegionHref(): (href: string) => string {
  const region = useRegion();
  return useCallback((href: string) => withRegionPath(region, href), [region]);
}
