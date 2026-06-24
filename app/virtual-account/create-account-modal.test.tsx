import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CreateAccountModal from "@/components/ui/CreateAccountModal";

const savedStrategy = {
  id: "strategy-1",
  name: "저PBR 자동매매 전략",
  description: "KOSPI 저PBR 종목을 매매합니다.",
  universe: "kospi",
  entry: {
    conditions: [
      {
        id: "pbr",
        type: "filter",
        params: { operator: "<=", value: 1 },
      },
    ],
  },
  exit: { conditions: [] },
  risk: {
    max_positions: 8,
    stop_loss_pct: 12,
    rebalancing_period: "monthly",
  },
};

describe("CreateAccountModal trading mode", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function renderAndSelectStrategy() {
    const onCreate = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => [savedStrategy],
      })
    );

    render(
      <CreateAccountModal
        isOpen={true}
        onClose={vi.fn()}
        onCreate={onCreate}
      />
    );

    const selectButton = await screen.findByRole("button", { name: /전략을 선택하세요/i });
    await act(async () => {
      fireEvent.click(selectButton);
    });
    const strategyButton = await screen.findByRole("button", { name: savedStrategy.name });
    await act(async () => {
      fireEvent.click(strategyButton);
    });

    return onCreate;
  }

  function fillAndSubmit(amount = "100") {
    fireEvent.change(screen.getByPlaceholderText("예: 저PBR 전략, 모멘텀 전략, 가치주 전략..."), {
      target: { value: "자동 계좌" },
    });
    fireEvent.change(screen.getByPlaceholderText("100"), {
      target: { value: amount },
    });
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));
  }

  it("only shows the auto trading toggle and keeps it off by default", async () => {
    const onCreate = await renderAndSelectStrategy();

    expect(screen.getByText("매매 방식")).toBeInTheDocument();
    const autoTradingButton = screen.getByRole("button", { name: "자동매매 OFF" });
    expect(autoTradingButton).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("OFF")).toBeInTheDocument();
    expect(screen.queryByText("신호 알림만")).not.toBeInTheDocument();
    expect(screen.queryByText("알림 받고 직접 매매")).not.toBeInTheDocument();
    expect(screen.getByText("자동매매는 꺼져 있습니다. 계좌 생성 후에도 직접 켤 수 있습니다.")).toBeInTheDocument();

    await act(async () => {
      fillAndSubmit();
    });

    expect(onCreate).toHaveBeenCalledWith(
      "자동 계좌",
      1_000_000,
      savedStrategy.id,
      savedStrategy.name,
      "manual"
    );
  });

  it("allows investment amounts above 1000만원", async () => {
    const onCreate = await renderAndSelectStrategy();

    expect(screen.getByText("최소 100만원")).toBeInTheDocument();

    await act(async () => {
      fillAndSubmit("1,500");
    });

    expect(onCreate).toHaveBeenCalledWith(
      "자동 계좌",
      15_000_000,
      savedStrategy.id,
      savedStrategy.name,
      "manual"
    );
    expect(screen.queryByText("최대 투자금액은 1000만원입니다.")).not.toBeInTheDocument();
  });

  it("creates strategy accounts with auto mode after turning the toggle on", async () => {
    const onCreate = await renderAndSelectStrategy();
    const autoTradingButton = screen.getByRole("button", { name: "자동매매 OFF" });

    await act(async () => {
      fireEvent.click(autoTradingButton);
    });

    const enabledAutoTradingButton = screen.getByRole("button", { name: "자동매매 ON" });
    expect(enabledAutoTradingButton).toHaveAttribute("aria-pressed", "true");
    expect(enabledAutoTradingButton.className).not.toContain("bg-blue-500/10");
    expect(screen.getByText("ON")).toBeInTheDocument();
    expect(
      screen.getByText("전략 신호가 발생하면 현재가로 자동 주문이 실행됩니다.").className
    ).not.toContain("bg-blue-500/10");

    await act(async () => {
      fillAndSubmit();
    });

    expect(onCreate).toHaveBeenCalledWith(
      "자동 계좌",
      1_000_000,
      savedStrategy.id,
      savedStrategy.name,
      "auto"
    );
  });
});
