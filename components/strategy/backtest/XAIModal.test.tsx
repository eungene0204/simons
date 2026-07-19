import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", () => ({
  motion: new Proxy({}, {
    get: () => ({ children, ...props }: any) => <div {...props}>{children}</div>,
  }),
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

import XAIModal from "./XAIModal";

const fetchMock = vi.fn();

describe("XAIModal responsive layout", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        symbol: "005930",
        date: "2025-01-02",
        status: "ok",
        attention_map: [0.1, 0.2],
        shap_matrix: [[0.1, -0.1], [0.2, -0.2]],
        feature_importance_directional: [0.2, -0.1],
        features: ["ret_open", "ret_close"],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  it("uses the mobile viewport height and restores the desktop modal size", async () => {
    render(
      <XAIModal
        isOpen
        onClose={vi.fn()}
        symbol="005930"
        date="2025-01-02"
      />
    );

    expect(screen.getByRole("dialog", { name: "AI 의사결정 분석 (XAI)" })).toHaveClass(
      "max-h-[calc(100dvh-1rem)]",
      "rounded-2xl",
      "lg:max-h-[75vh]",
      "lg:rounded-3xl"
    );

    await waitFor(() => expect(screen.getByText("시계열 특징 기여도 (SHAP Heatmap)")).toBeInTheDocument());
    expect(screen.getByTestId("xai-heatmap-header")).toHaveClass(
      "flex-col",
      "lg:flex-row",
      "lg:items-center",
      "lg:justify-between"
    );
    expect(screen.getByTestId("xai-heatmap-scroll")).toHaveClass(
      "min-w-0",
      "overflow-x-auto"
    );
  });

  it("provides an accessible close action", () => {
    const onClose = vi.fn();
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(
      <XAIModal
        isOpen
        onClose={onClose}
        symbol="005930"
        date="2025-01-02"
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "XAI 분석 닫기" }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
