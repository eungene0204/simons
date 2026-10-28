import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { SimulationDetailModal } from "./SimulationDetailModal";
import { SimulationBrowser } from "./SimulationBrowser";

vi.mock("./SimulationReturnChart", () => ({ SimulationReturnChart: () => <div role="img" aria-label="누적 수익률 그래프" /> }));

const original = {
  status: "ready",
  window: { requestedStart: "2023-10-27", requestedEnd: "2026-10-27", actualStart: "2023-10-27", actualEnd: "2026-10-23", dataAsOf: "2026-10-23", stale: true, limited: false },
  conditions: { initialCapital: 10_000_000, buyFeeRate: 0.00015, sellFeeRate: 0.00015, slippageRate: 0.0005, sellTaxRate: null, sellTaxRateRange: [0.0018, 0.0023], executionTiming: "next_open", executionDelayDays: 1 },
  summary: { initialCapital: 10_000_000, finalEquity: 11_077_600, totalProfit: 1_077_600, totalReturnPct: 10.776, maxDrawdownPct: -12.5, cagrPct: 3.5, sharpe: null, winRatePct: 55.5, trades: 31, unavailableReasons: { sharpe: "수익률 변동이 없어 계산할 수 없습니다." } },
  computedAt: "2026-10-27T01:00:00Z",
  curve: { dates: ["a", "b"], returnPct: [0, 10.776] },
  contributors: { top: [{ symbol: "005930", name: "삼성전자", profit: 900_000 }], bottom: [{ symbol: "000660", name: "SK하이닉스", profit: -120_000 }] },
};
const detail = (over: Record<string, unknown> = {}) => ({
  publicId: "pub1", name: "RSI 전략", description: "설명", strategy: { entry: { conditions: [] }, exit: { conditions: [] }, risk: {} },
  baseSnapshotHash: "h", original: { ...original, ...over }, baseline: null,
});
const respond = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as Response;
const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("SimulationDetailModal", () => {
  it("기간·실행 조건·요약 지표·기여 종목을 저장된 값 그대로 보인다", async () => {
    fetchMock.mockResolvedValue(respond(detail()));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    expect(await screen.findByText("RSI 전략")).toBeTruthy();
    expect(screen.getByText("2023-10-27 ~ 2026-10-27")).toBeTruthy();       // 요청 기간
    expect(screen.getByText("2023-10-27 ~ 2026-10-23")).toBeTruthy();       // 실제 계산 기간
    expect(screen.getByText("2026-10-27 10:00 KST")).toBeTruthy();         // 계산 완료 시각(KST)
    expect(screen.getByText("최신 거래일 데이터가 아직 반영되지 않았을 수 있습니다.")).toBeTruthy();
    expect(screen.getAllByText("0.015%")).toHaveLength(2);              // 매수·매도 수수료 0.00015
    expect(screen.getByText("0.18% ~ 0.23%")).toBeTruthy();             // 기간별 세율 범위
    expect(screen.getByText("₩11,077,600")).toBeTruthy();
    expect(screen.getByText("+10.78%")).toBeTruthy();
    expect(screen.getByText("거래 수(미청산 포함)")).toBeTruthy();
    expect(screen.getByText("삼성전자 (005930)")).toBeTruthy();
    expect(screen.getByText("손익 기여 상위 종목")).toBeTruthy();
    expect(screen.getByText("총 손익은 최종 평가자산에서 초기 자본을 뺀 값으로, 미청산 포지션의 평가손익을 포함하고 수수료·세금·슬리피지를 반영합니다.")).toBeTruthy();   // 총 손익 기준
    expect(screen.getByText("-₩120,000")).toBeTruthy();
    expect(screen.getByRole("img", { name: "누적 수익률 그래프" })).toBeTruthy();
    // 계산 불가 지표는 숨기지 않고 '—'와 사유를 보인다(값을 지어내지도 않는다)
    expect(screen.getByText("샤프 비율")).toBeTruthy();
    expect(screen.getByText("수익률 변동이 없어 계산할 수 없습니다.")).toBeTruthy();
  });

  it("예시 문장에 없어 무작위로 고른 값은 질문과 고른 답을 그대로 보인다", async () => {
    fetchMock.mockResolvedValue(respond({ ...detail(), assumptions: [{ question: "익절 기준을 몇 %로 정할까요?", answer: "익절 20%", random: true }] }));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    expect(await screen.findByText("예시 문장에 없어 정한 값")).toBeTruthy();
    expect(screen.getByText("익절 기준을 몇 %로 정할까요?")).toBeTruthy();
    expect(screen.getByText("익절 20%")).toBeTruthy();
    expect(screen.getByText("무작위 선택")).toBeTruthy();
  });

  it("없는 예시 전략은 안내만 보이고 지표를 보이지 않는다", async () => {
    fetchMock.mockResolvedValue(respond({ code: "NOT_FOUND" }, 404));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    expect(await screen.findByText("존재하지 않는 예시 전략입니다.")).toBeTruthy();
    expect(screen.queryByText("요약 지표")).toBeNull();
  });

  it("원본이 아직 없으면 계산 중 문구만 보이고 요약은 없다", async () => {
    fetchMock.mockResolvedValue(respond({ ...detail(), original: { status: "pending" } }));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    expect(await screen.findByText("원본 결과를 계산하고 있습니다.")).toBeTruthy();
    expect(screen.queryByText("요약 지표")).toBeNull();
  });

  it("기여 종목 합계가 어긋난 결과는 목록 대신 사유를 보인다", async () => {
    fetchMock.mockResolvedValue(respond(detail({ contributors: { top: [], bottom: [], hidden: "INCONSISTENT" } })));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    await screen.findByText("요약 지표");
    expect(screen.getByText("종목별 합계가 총 손익과 일치하지 않아 표시하지 않습니다.")).toBeTruthy();
    expect(screen.queryByText("손익 기여 상위 종목")).toBeNull();
  });

  it("Escape와 배경 클릭, 닫기 버튼으로 닫힌다", async () => {
    fetchMock.mockResolvedValue(respond(detail()));
    const onClose = vi.fn();
    render(<SimulationDetailModal publicId="pub1" onClose={onClose} />);
    await screen.findByText("RSI 전략");
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    fireEvent.click(screen.getByRole("dialog").parentElement!);
    expect(onClose).toHaveBeenCalledTimes(3);
  });
});

describe("모달 접근성", () => {
  it("Tab은 모달 안에서만 돈다 — 마지막에서 첫 요소로, Shift+Tab은 반대로", async () => {
    fetchMock.mockResolvedValue(respond(detail()));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    await screen.findByText("요약 지표");
    const dialog = screen.getByRole("dialog");
    const items = Array.from(dialog.querySelectorAll<HTMLElement>('button, input, a[href], [tabindex]:not([tabindex="-1"])'));
    const first = items[0];
    const last = items[items.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("열 때 닫기 버튼으로 포커스가 가고 모바일에서는 화면 전체 높이를 쓴다", async () => {
    fetchMock.mockResolvedValue(respond(detail()));
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    await screen.findByText("요약 지표");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "닫기" }));
    expect(screen.getByRole("dialog").className).toContain("h-[100dvh]");
  });
});

describe("SimulationBrowser", () => {
  it("카드를 누르면 그 공개 전략의 상세를 열고 닫으면 사라진다", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/pub1") ? respond(detail()) : respond({ items: [{ publicId: "pub1", name: "RSI 전략", status: "pending", description: null }], hasNext: false }));
    render(<SimulationBrowser />);
    const card = await screen.findByRole("button", { name: /RSI 전략/ });
    fireEvent.click(card);
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/api/strategy-simulation/pub1"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(card));        // 닫으면 해당 카드로 포커스 복귀
  });

  it("카드를 열면 주소에 ?id=가 붙고 닫으면 사라진다", async () => {
    window.history.replaceState(null, "", "/strategy-simulation");
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/pub12345") ? respond(detail()) : respond({ items: [{ publicId: "pub12345", name: "RSI 전략", status: "pending", description: null }], hasNext: false }));
    render(<SimulationBrowser />);
    fireEvent.click(await screen.findByRole("button", { name: /RSI 전략/ }));
    await screen.findByRole("dialog");
    expect(window.location.search).toBe("?id=pub12345");
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(window.location.search).toBe("");
  });

  it("주소에 올바른 ?id=가 있으면 그 전략의 모달을 바로 연다", async () => {
    window.history.replaceState(null, "", "/strategy-simulation?id=pub12345");
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/pub12345") ? respond(detail()) : respond({ items: [], hasNext: false }));
    render(<SimulationBrowser />);
    expect(await screen.findByRole("dialog")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/api/strategy-simulation/pub12345"))).toBe(true);
  });

  it("형식이 틀린 ?id=는 무시하고 상세 요청을 보내지 않는다", async () => {
    window.history.replaceState(null, "", "/strategy-simulation?id=../etc");
    fetchMock.mockResolvedValue(respond({ items: [], hasNext: false }));
    render(<SimulationBrowser />);
    await screen.findByText("표시할 예시 전략이 아직 없습니다.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetchMock.mock.calls.every(([u]) => !String(u).includes("/etc"))).toBe(true);
  });
});
