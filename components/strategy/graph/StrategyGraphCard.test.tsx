import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { confirmedInput, executedInput, META } from "@/lib/strategy-graph/fixtures";
import { resetGraphMetaForTests } from "@/lib/strategy-graph/meta";
import type { StrategyGraphInput } from "@/lib/strategy-graph/types";
import StrategyGraphCard from "./StrategyGraphCard";
import { createGraphSeen } from "./StrategyGraphView";

const fetchMock = vi.fn();
const ok = () => Promise.resolve({ ok: true, json: async () => META });
const urls = () => fetchMock.mock.calls.map((c) => String(c[0]));

beforeEach(() => {
  resetGraphMetaForTests();
  fetchMock.mockReset();
  fetchMock.mockImplementation(ok);
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const renderCard = (input: StrategyGraphInput, title = "확정된 전략") => render(<StrategyGraphCard input={input} title={title} />);
const node = (kind: string, text: string) =>
  Array.from(document.querySelectorAll(`[data-kind="${kind}"]`)).find((n) => n.textContent?.includes(text)) as SVGGElement;

describe("StrategyGraphCard", () => {
  it("shows the confirmed graph without any extra open action and only calls the public metadata endpoint", async () => {
    renderCard(confirmedInput("goldenCrossRsiAnd"));
    expect(await screen.findByTestId("strategy-graph-canvas")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "확정된 전략" })).toBeInTheDocument();
    expect(node("section", "매수 규칙")).toBeTruthy();
    expect(node("condition", "RSI(14) < 70")).toBeTruthy();
    expect(urls()).toEqual(["/api/strategy/graph-meta"]);
  });

  it("starts even a small strategy collapsed; selecting a condition shows its indicator, never the classification", async () => {
    renderCard(confirmedInput("goldenCrossRsiAnd"));
    await screen.findByTestId("strategy-graph-canvas");
    expect(document.querySelector('[data-kind="indicator"]')).toBeNull();
    fireEvent.click(node("condition", "RSI(14) < 70"));
    expect(document.querySelector('[data-kind="indicator"]')).not.toBeNull();
    expect(document.querySelector('[data-kind="class"]')).toBeNull();
  });

  it("starts a large strategy collapsed and opens a condition's details only when it is selected", async () => {
    renderCard(confirmedInput("krComplex"));
    await screen.findByTestId("strategy-graph-canvas");
    expect(document.querySelector('[data-kind="indicator"]')).toBeNull();
    fireEvent.click(node("condition", "RSI(14)"));
    expect(document.querySelectorAll('[data-kind="indicator"]')).toHaveLength(1);
  });

  it("clicking the selected node again deselects it and folds its details", async () => {
    renderCard(confirmedInput("krComplex"));
    await screen.findByTestId("strategy-graph-canvas");
    fireEvent.click(node("condition", "RSI(14)"));
    expect(document.querySelectorAll('[data-kind="indicator"]')).toHaveLength(1);
    fireEvent.click(node("condition", "RSI(14)"));
    expect(document.querySelector('[data-kind="indicator"]')).toBeNull();
    expect(node("condition", "RSI(14)").getAttribute("aria-pressed")).toBe("false");
  });

  it("scrolls the chat so an opened graph clears the fixed bottom dock", async () => {
    const dock = document.createElement("div");
    dock.className = "dock-bottom";
    dock.style.position = "fixed";
    dock.getBoundingClientRect = () => ({ top: 500 }) as DOMRect;
    const scroller = document.createElement("div");
    scroller.style.overflowY = "auto";
    Object.defineProperty(scroller, "scrollHeight", { configurable: true, value: 2000 });
    Object.defineProperty(scroller, "clientHeight", { configurable: true, value: 600 });
    const scrollBy = vi.fn();
    scroller.scrollBy = scrollBy as unknown as typeof scroller.scrollBy;
    document.body.append(dock, scroller);
    const rect = (bottom: number, top = 0) => () => ({ top, bottom }) as DOMRect;
    const proto = Element.prototype;
    const original = proto.getBoundingClientRect;
    proto.getBoundingClientRect = function (this: Element) {
      if (this.tagName.toLowerCase() === "svg") return rect(620)();
      if (this.hasAttribute("data-node-id")) return rect(200, 180)();
      return original.call(this);
    };
    try {
      render(<StrategyGraphCard input={confirmedInput("krComplex")} title="t" />, { container: scroller.appendChild(document.createElement("div")) });
      await screen.findByTestId("strategy-graph-canvas");
      fireEvent.click(node("condition", "RSI(14)"));
      await waitFor(() => expect(scrollBy).toHaveBeenCalled());
      // svg bottom 620 vs dock top 500 - gap 16 → 136 px, within the room above the selected node (180 - 72)
      expect(scrollBy.mock.calls[0][0].top).toBe(108);
    } finally {
      proto.getBoundingClientRect = original;
      dock.remove();
      scroller.remove();
    }
  });

  it("selecting a condition highlights its direct relations and dims the rest", async () => {
    renderCard(confirmedInput("goldenCrossRsiAnd"));
    await screen.findByTestId("strategy-graph-canvas");
    fireEvent.click(node("condition", "RSI(14) < 70"));
    expect(node("condition", "RSI(14) < 70").getAttribute("aria-pressed")).toBe("true");
    expect(node("condition", "RSI(14) < 70").getAttribute("opacity")).toBe("1");
    expect(node("section", "매도 규칙").getAttribute("opacity")).toBe("0.3");
    // classification nodes are not part of the graph view any more
    expect(document.querySelector('[data-kind="class"]')).toBeNull();
  });

  it("starts fitted to the available width, like pressing '화면에 맞추기'", async () => {
    const width = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(500);
    try {
      renderCard(confirmedInput("krComplex"));
      await screen.findByTestId("strategy-graph-canvas");
      const percent = () => Number(screen.getByText(/^\d+%$/).textContent!.replace("%", ""));
      const fitted = percent();
      expect(fitted).toBeLessThan(70); // narrower than the old fixed 70% start
      // Opening an item must not re-fit; zooming by hand switches auto-fit off.
      fireEvent.click(node("condition", "RSI(14)"));
      expect(percent()).toBe(fitted);
      fireEvent.click(screen.getByRole("button", { name: "확대" }));
      expect(percent()).toBeGreaterThan(fitted);
    } finally {
      width.mockRestore();
    }
  });

  it("supports keyboard selection and Escape to clear", async () => {
    renderCard(confirmedInput("goldenCrossRsiAnd"));
    await screen.findByTestId("strategy-graph-canvas");
    const cond = node("condition", "RSI(14) < 70");
    cond.focus();
    fireEvent.keyDown(cond, { key: "Enter" });
    expect(cond.getAttribute("aria-pressed")).toBe("true");
    fireEvent.keyDown(cond, { key: "Escape" });
    expect(cond.getAttribute("aria-pressed")).toBe("false");
  });

  it("clears the highlight when clicking outside a node, but not on a node or the zoom toolbar", async () => {
    renderCard(confirmedInput("goldenCrossRsiAnd"));
    await screen.findByTestId("strategy-graph-canvas");
    const cond = node("condition", "RSI(14) < 70");
    fireEvent.click(cond);
    expect(cond.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "확대" }));
    expect(cond.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(document.body);
    expect(cond.getAttribute("aria-pressed")).toBe("false");
    expect(node("section", "매도 규칙").getAttribute("opacity")).toBe("1");
  });

  it("marks the items drawn in this batch, so the page can scroll to the newly added ones", async () => {
    const seen = createGraphSeen();
    const first = render(<StrategyGraphCard input={confirmedInput("goldenCrossRsiAnd")} title="초안" seen={seen} />);
    await screen.findByTestId("strategy-graph-canvas");
    const all = document.querySelectorAll("[data-item-key]").length;
    expect(document.querySelectorAll('[data-fresh="true"]')).toHaveLength(all);
    first.unmount();

    // A later card of the same conversation: what was already drawn is not fresh any more.
    render(<StrategyGraphCard input={confirmedInput("goldenCrossRsiAnd")} title="초안" seen={seen} />);
    await screen.findByTestId("strategy-graph-canvas");
    expect(document.querySelectorAll('[data-fresh="true"]')).toHaveLength(0);
  });

  it("text view lists the same items as the graph", async () => {
    renderCard(confirmedInput("krComplex"));
    await screen.findByTestId("strategy-graph-canvas");
    const graphLabels = Array.from(document.querySelectorAll("[data-node-id]"))
      .filter((n) => !["strategy", "section", "indicator", "class"].includes(n.getAttribute("data-kind") as string))
      .map((n) => n.getAttribute("data-node-id"));
    // Resolved AND/OR groups are folded into the section label in the graph (the text view still lists them).
    const folded = new Set(["group:entry", "group:filters", "group:exit"]);
    fireEvent.click(screen.getByRole("button", { name: /텍스트로 보기/ }));
    const textIds = Array.from(document.querySelectorAll("[data-outline-id]")).map((n) => n.getAttribute("data-outline-id"));
    expect(textIds.filter((id) => !folded.has(id ?? "")).sort()).toEqual(graphLabels.sort());
  });

  it("separates a metadata failure from the graph and retries only the metadata endpoint", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve({ ok: false, status: 502, json: async () => ({}) }));
    renderCard(confirmedInput("goldenCrossRsiAnd"));
    const banner = await screen.findByTestId("graph-meta-error");
    expect(node("condition", "RSI(14)")).toBeTruthy(); // structure still shown
    expect(document.querySelector('[data-kind="indicator"]')).toBeNull();
    fireEvent.click(within(banner).getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.queryByTestId("graph-meta-error")).toBeNull());
    expect(urls()).toEqual(["/api/strategy/graph-meta", "/api/strategy/graph-meta"]);
  });

  it("retries a graph build error from the same snapshot without any network call", async () => {
    let failures = 1;
    const base = confirmedInput("goldenCrossRsiAnd");
    const request = new Proxy(base.request as object, {
      get(target, key, receiver) {
        if (failures > 0 && key === "universe_id") {
          failures -= 1;
          throw new Error("boom");
        }
        return Reflect.get(target, key, receiver);
      },
    });
    renderCard({ ...base, request: request as never });
    const alert = await screen.findByTestId("graph-build-error");
    const callsBefore = fetchMock.mock.calls.length;
    fireEvent.click(within(alert).getByRole("button", { name: "다시 시도" }));
    await screen.findByTestId("strategy-graph-canvas");
    expect(fetchMock.mock.calls.length).toBe(callsBefore);
  });

  it("shows the no-snapshot state instead of falling back to a current strategy", async () => {
    renderCard({ origin: "none", schema: "none", sourceRef: "history:old" }, "실행된 전략");
    expect(screen.getByTestId("graph-no-snapshot")).toHaveTextContent("이 실행의 전략 스냅샷이 저장되어 있지 않습니다.");
    expect(document.querySelector("[data-node-id]")).toBeNull();
  });

  it("shows an empty state for a strategy without sections", async () => {
    renderCard({ origin: "confirmed", schema: "parsed+request", sourceRef: "c", parsed: {} as never, request: { entry: {}, exit: {}, risk: {} } });
    expect(await screen.findByTestId("graph-empty")).toBeInTheDocument();
  });

  it("executed snapshots use the executed label and keep the confirmed card unchanged", async () => {
    const { unmount } = renderCard(executedInput("goldenCrossRsiAnd"), "실행된 전략");
    await screen.findByTestId("strategy-graph-canvas");
    expect(screen.getByRole("heading", { name: "실행된 전략" })).toBeInTheDocument();
    expect(screen.getByTestId("graph-notes")).toHaveTextContent("미정 항목과 조건별 원문 인용은 확인할 수 없습니다");
    unmount();
  });

  it("animates only what is new: a later card sharing the memory redraws nothing that already existed", async () => {
    const seen = createGraphSeen();
    const enterOf = (key: string) => document.querySelector(`[data-item-key="${key}"] .sg-enter`);
    const first = render(<StrategyGraphCard input={confirmedInput("goldenCrossRsiAnd")} title="초안" seen={seen} />);
    await screen.findByTestId("strategy-graph-canvas");
    // First draw: everything is new and animates in.
    expect(enterOf("node:strategy")).not.toBeNull();
    expect(enterOf("node:cond:entry/entry.1")).not.toBeNull();
    first.unmount();

    // Next turn: a bigger strategy of the same conversation.
    render(<StrategyGraphCard input={confirmedInput("entryOrWithFilters")} title="초안" seen={seen} />);
    await screen.findByTestId("strategy-graph-canvas");
    // Same item keys as before (strategy root, entry section pill, first RSI condition) are not replayed...
    expect(enterOf("node:strategy")).toBeNull();
    expect(enterOf("pill:section:entry:매수 규칙")).toBeNull();
    // ...while items that did not exist before (the filter section) animate in.
    expect(enterOf("pill:section:filters:종목 선정 필터")).not.toBeNull();
    // Existing edges are not redrawn, new ones are.
    const drawn = Array.from(document.querySelectorAll("path.sg-draw")).length;
    const all = document.querySelectorAll("path.sg-edge").length;
    expect(drawn).toBeGreaterThan(0);
    expect(drawn).toBeLessThan(all);
  });

  it("builds a first-drawn graph up one item at a time, each edge leading its item", async () => {
    renderCard(confirmedInput("krComplex"));
    await screen.findByTestId("strategy-graph-canvas");
    const delays = Array.from(document.querySelectorAll<SVGGElement>(".sg-enter")).map((g) => parseFloat(g.style.animationDelay));
    expect(delays.length).toBeGreaterThanOrEqual(4);
    expect(delays).toEqual([...delays].sort((a, b) => a - b));
    expect(new Set(delays).size).toBe(delays.length);
    const edgeDelays = Array.from(document.querySelectorAll<SVGPathElement>("path.sg-draw")).map((p) => parseFloat(p.style.animationDelay));
    expect(Math.min(...edgeDelays)).toBeLessThan(Math.min(...delays) + 1);
    expect(Math.max(...delays)).toBeGreaterThan(1500);
  });

  it("keeps the build-up when the card re-renders right after the first draw", async () => {
    const input = confirmedInput("krComplex");
    const { rerender } = render(<StrategyGraphCard input={input} title="확정된 전략" />);
    await screen.findByTestId("strategy-graph-canvas");
    const before = document.querySelectorAll(".sg-enter").length;
    rerender(<StrategyGraphCard input={input} title="확정된 전략" />);
    expect(before).toBeGreaterThanOrEqual(4);
    expect(document.querySelectorAll(".sg-enter").length).toBe(before);
  });
});

describe("StrategyGraphCard instant draw (backtest result page)", () => {
  it("draws a first-time graph at once, with no build-up animation classes", async () => {
    render(<StrategyGraphCard input={confirmedInput("krComplex")} title="실행된 전략" instant />);
    await screen.findByTestId("strategy-graph-canvas");
    expect(document.querySelectorAll(".sg-enter, .sg-draw")).toHaveLength(0);
  });

  it("keeps the step-by-step build-up on the default path (chat cards)", async () => {
    render(<StrategyGraphCard input={confirmedInput("krComplex")} title="확정된 전략" />);
    await screen.findByTestId("strategy-graph-canvas");
    expect(document.querySelectorAll(".sg-enter").length).toBeGreaterThan(0);
  });
});
