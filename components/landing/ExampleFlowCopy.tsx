"use client";

import { useEffect, useRef } from "react";

// 예시 흐름의 두 번째 목록 — 끊김 없는 흐름을 위한 장식용 복제본이라 서버 HTML에 싣지 않고,
// 마운트 뒤 바로 앞 목록을 복사해 채운다(카드 82장이 HTML·RSC 페이로드에 두 번씩 실리던 무게, 2026-11-04).
// 읽기·탭 이동에서는 빠진다(aria-hidden·tabIndex=-1). React는 이 ul의 자식을 그리지 않는다.
export function ExampleFlowCopy() {
  const ref = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const copy = ref.current;
    const source = copy?.previousElementSibling;
    if (!copy || !source) return;
    const items = Array.from(source.children, (item) => item.cloneNode(true) as HTMLElement);
    for (const item of items) {
      for (const link of item.querySelectorAll("a")) {
        link.tabIndex = -1;
        link.setAttribute("aria-hidden", "true");
      }
    }
    copy.replaceChildren(...items);
  }, []);

  return <ul ref={ref} className="example-flow-half list-none" aria-hidden="true" data-testid="example-flow-copy" />;
}
