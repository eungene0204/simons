import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SimulationDetailModal } from "./SimulationDetailModal";

vi.mock("./SimulationReturnChart", () => ({
  SimulationReturnChart: ({ modified }: { modified?: unknown }) => <div role="img" aria-label="누적 수익률 그래프" data-modified={modified ? "yes" : "no"} />,
}));

const PERIOD = "entry.conditions.0.params.period";
const summary = { initialCapital: 1e7, finalEquity: 11e6, totalProfit: 1e6, totalReturnPct: 10, maxDrawdownPct: -10, trades: 30 };
const detail = {
  publicId: "pub1", name: "RSI 전략", description: null, strategy: { entry: { conditions: [] }, exit: { conditions: [] }, risk: {} },
  baseSnapshotHash: "hash1",
  original: {
    status: "ready", dataAsOf: "2026-10-23", summary,
    window: { actualStart: "2023-10-27", actualEnd: "2026-10-23", dataAsOf: "2026-10-23" },
    conditions: { initialCapital: 1e7 }, contributors: { top: [{ symbol: "005930", name: "삼성전자", profit: 900000 }], bottom: [] }, curve: { dates: ["a", "b"], returnPct: [0, 10] },
    editableParams: [{ path: PERIOD, role: "entry", index: 0, original: 14, editable: true, label: "RSI 기간", unit: "일", minimum: 2, maximum: 100, integer: true }],
  },
};
const modifiedBody = {
  status: "ready", summary: { ...summary, totalProfit: 5e5, totalReturnPct: 5, maxDrawdownPct: -14, trades: 20 }, curve: { dates: ["a", "b"], returnPct: [0, 5] },
  contributors: { top: [{ symbol: "035720", name: "카카오", profit: 400000 }], bottom: [] },
};
const respond = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body }) as Response;
const fetchMock = vi.fn();
const runCalls = () => fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/run"));

async function open() {
  fetchMock.mockImplementation(async (url: string) => (String(url).endsWith("/run") ? respond(modifiedBody) : respond(detail)));
  render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
  await screen.findByText("지표 값 바꿔 보기");
  return screen.getByLabelText(/RSI 기간/) as HTMLInputElement;
}
const type = (input: HTMLInputElement, value: string) => fireEvent.change(input, { target: { value } });
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("지표 값 수정", () => {
  it("입력을 멈춘 600ms 뒤에 한 번만 계산하고 원본 대비 차이를 %p로 보인다", async () => {
    const input = await open();
    vi.useFakeTimers();
    type(input, "2"); type(input, "21");
    await advance(599);
    expect(runCalls()).toHaveLength(0);
    await advance(1);
    expect(runCalls()).toHaveLength(1);
    expect(JSON.parse(String(runCalls()[0][1].body))).toEqual({ overrides: [{ path: PERIOD, value: 21 }], baseSnapshotHash: "hash1", dataAsOf: "2026-10-23" });
    expect(screen.getByText("-5.00%p")).toBeTruthy();            // 수익률 5 − 10
    expect(screen.getByText("-4.00%p")).toBeTruthy();            // 낙폭 -14 − (-10)
    expect(screen.getByText("-10")).toBeTruthy();                // 거래 수
    expect(screen.getByRole("img", { name: "누적 수익률 그래프" }).getAttribute("data-modified")).toBe("yes");
  });

  it("수정 결과는 요약 비교·종목별 손익·차트에 함께 반영되고 '사용자 수정 시뮬레이션'으로 표시된다", async () => {
    const input = await open();
    vi.useFakeTimers();
    type(input, "21");
    await advance(600);
    expect(screen.getAllByText("사용자 수정 시뮬레이션").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("카카오 (035720)")).toBeTruthy();          // 수정본 종목 기여
    expect(screen.getByText("삼성전자 (005930)")).toBeTruthy();        // 원본 종목 기여는 그대로
    expect(screen.getByText("-₩500,000")).toBeTruthy();                // 총 손익 차이(전체 지표 비교)
  });

  it("모달을 닫았다 다시 열면 원본 값으로 시작하고 이전 수정 결과가 남지 않는다", async () => {
    const input = await open();
    vi.useFakeTimers();
    type(input, "21");
    await advance(600);
    expect(screen.getByText("-5.00%p")).toBeTruthy();
    cleanup();
    render(<SimulationDetailModal publicId="pub1" onClose={() => {}} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect((screen.getByLabelText(/RSI 기간/) as HTMLInputElement).value).toBe("14");
    expect(screen.queryByText(/%p/)).toBeNull();
  });

  it("범위를 벗어나거나 정수가 아니면 계산하지 않고 이유를 보인다", async () => {
    const input = await open();
    vi.useFakeTimers();
    for (const [raw, message] of [["1", "2 ~ 100 범위의 값을 입력해 주세요."], ["14.5", "정수를 입력해 주세요."], ["", "숫자를 입력해 주세요."], ["abc", "숫자를 입력해 주세요."]]) {
      type(input, raw);
      await advance(700);
      expect(screen.getByRole("alert").textContent).toBe(message);
    }
    expect(runCalls()).toHaveLength(0);
  });

  it("마지막 입력만 반영한다 — 늦게 도착한 앞선 응답은 버린다", async () => {
    const input = await open();
    vi.useFakeTimers();
    let releaseFirst!: (r: Response) => void;
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => (releaseFirst = resolve)));
    type(input, "21");
    await advance(600);
    fetchMock.mockImplementationOnce(async () => respond({ ...modifiedBody, summary: { ...modifiedBody.summary, totalReturnPct: 7 } }));
    type(input, "30");
    await advance(600);
    await act(async () => releaseFirst(respond(modifiedBody)));
    expect(runCalls()).toHaveLength(2);
    expect(screen.getByText("-3.00%p")).toBeTruthy();            // 7 − 10 (두 번째 값)
    expect(screen.queryByText("-5.00%p")).toBeNull();
  });

  it("원래 값으로 되돌리거나 초기화하면 요청 없이 수정 결과가 사라진다", async () => {
    const input = await open();
    vi.useFakeTimers();
    type(input, "21");
    await advance(600);
    expect(screen.getByText("-5.00%p")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "원본 값으로 초기화" }));
    await advance(700);
    expect(input.value).toBe("14");
    expect(screen.queryByText("-5.00%p")).toBeNull();
    expect(runCalls()).toHaveLength(1);
    type(input, "14");
    await advance(700);
    expect(runCalls()).toHaveLength(1);                          // 원본과 같은 값은 계산하지 않는다
  });

  it("원본이 갱신된 경우(409)에는 다시 불러오기를 안내하고 수정 결과를 보이지 않는다", async () => {
    const input = await open();
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(async () => respond({ code: "BASELINE_CHANGED", reason: "CHANGED" }, 409));
    type(input, "21");
    await advance(600);
    expect(screen.getByRole("alert").textContent).toContain("원본 결과가 갱신되었습니다.");
    expect(screen.getByRole("button", { name: "다시 불러오기" })).toBeTruthy();
    expect(screen.queryByText(/%p/)).toBeNull();
  });

  it("429·서버 오류도 0%나 거래 없음처럼 보이지 않고 오류 문구만 보인다", async () => {
    const input = await open();
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce(async () => respond({ code: "RATE_LIMITED", retryAfterSeconds: 60 }, 429));
    type(input, "21");
    await advance(600);
    expect(screen.getByRole("alert").textContent).toContain("요청이 많아");
    fetchMock.mockImplementationOnce(async () => respond({ code: "INCONSISTENT_RESULT" }, 500));
    type(input, "22");
    await advance(600);
    expect(screen.getByRole("alert").textContent).toContain("수정 결과를 계산하지 못했습니다.");
    expect(screen.queryByText(/%p/)).toBeNull();
  });
});
