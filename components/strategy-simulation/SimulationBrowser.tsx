"use client";

import { useCallback, useEffect, useState } from "react";
import { SimulationCardGrid } from "./SimulationCardGrid";
import { SimulationDetailModal } from "./SimulationDetailModal";

// 서버 PUBLIC_ID_PATTERN과 같은 형식만 딥링크로 받는다.
const PUBLIC_ID = /^[A-Za-z0-9_-]{8,64}$/;

function setUrlId(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("id", id);
  else url.searchParams.delete("id");
  window.history.replaceState(window.history.state, "", url);
}

// 목록 + 상세 모달 — 어떤 카드가 열려 있는지만 들고 있고, 주소의 `?id=`와 맞춰 둔다(딥링크).
export function SimulationBrowser() {
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("id");
    if (id && PUBLIC_ID.test(id)) setOpenId(id);
  }, []);

  const open = useCallback((id: string) => {
    setUrlId(id);
    setOpenId(id);
  }, []);

  // 닫으면 모달을 연 카드로 포커스를 돌려준다(Safari는 클릭으로 버튼에 포커스를 주지 않아 id로 찾는다).
  const close = useCallback(() => {
    setUrlId(null);
    setOpenId((id) => {
      if (id) requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-card-id="${CSS.escape(id)}"]`)?.focus());
      return null;
    });
  }, []);

  return (
    <>
      <SimulationCardGrid onOpen={open} />
      {openId && <SimulationDetailModal publicId={openId} onClose={close} />}
    </>
  );
}
