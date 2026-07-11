import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const planUsage = {
  plan: { planId: "FREE", name: "Free", initialInvestmentAmount: 10_000_000 },
  accounts: { used: 0, limit: 1 },
  strategies: { used: 0, limit: 3, unlimited: false },
  backtests: { used: 0, limit: 30 },
};

function mockFetch(accountsUsed = 0, accountsLimit = 1) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/user/plan") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...planUsage,
            accounts: { used: accountsUsed, limit: accountsLimit },
          }),
        });
      }
      // /api/strategy
      return Promise.resolve({ ok: true, json: async () => [savedStrategy] });
    })
  );
}

describe("CreateAccountModal trading mode", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function renderAndSelectStrategy() {
    const onCreate = vi.fn();
    mockFetch();

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

  function fillNameAndSubmit() {
    fireEvent.change(screen.getByPlaceholderText("예: 저PBR 전략, 모멘텀 전략, 가치주 전략..."), {
      target: { value: "자동 계좌" },
    });
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));
  }

  it("only shows the auto trading toggle and keeps it off by default", async () => {
    const onCreate = await renderAndSelectStrategy();

    expect(screen.getByText("매매 방식")).toBeInTheDocument();
    const autoTradingButton = screen.getByRole("button", { name: "전략 시뮬레이션 OFF" });
    expect(autoTradingButton).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("OFF")).toBeInTheDocument();
    expect(screen.getByText("전략 시뮬레이션은 꺼져 있습니다. 계좌 생성 후에도 직접 켤 수 있습니다.")).toBeInTheDocument();

    await act(async () => {
      fillNameAndSubmit();
    });

    expect(onCreate).toHaveBeenCalledWith(
      "자동 계좌",
      10_000_000,
      savedStrategy.id,
      savedStrategy.name,
      "manual"
    );
  });

  it("계좌당 초기 투자금을 플랜 기준으로 표시하고 그 금액으로 생성한다", async () => {
    const onCreate = await renderAndSelectStrategy();

    expect(screen.getByText("계좌당 초기 모의 투자금")).toBeInTheDocument();
    expect(screen.getByText("10,000,000원")).toBeInTheDocument();

    await act(async () => {
      fillNameAndSubmit();
    });

    expect(onCreate).toHaveBeenCalledWith(
      "자동 계좌",
      10_000_000,
      savedStrategy.id,
      savedStrategy.name,
      "manual"
    );
  });

  it("creates strategy accounts with auto mode after turning the toggle on", async () => {
    const onCreate = await renderAndSelectStrategy();
    const autoTradingButton = screen.getByRole("button", { name: "전략 시뮬레이션 OFF" });

    await act(async () => {
      fireEvent.click(autoTradingButton);
    });

    const enabledAutoTradingButton = screen.getByRole("button", { name: "전략 시뮬레이션 ON" });
    expect(enabledAutoTradingButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("ON")).toBeInTheDocument();

    await act(async () => {
      fillNameAndSubmit();
    });

    expect(onCreate).toHaveBeenCalledWith(
      "자동 계좌",
      10_000_000,
      savedStrategy.id,
      savedStrategy.name,
      "auto"
    );
  });

  it("계좌 한도에 도달하면 만들기 버튼을 비활성화한다", async () => {
    const onCreate = vi.fn();
    mockFetch(1, 1);

    render(
      <CreateAccountModal isOpen={true} onClose={vi.fn()} onCreate={onCreate} />
    );

    const submit = await screen.findByRole("button", { name: "만들기" });
    expect(submit).toBeDisabled();
    expect(
      screen.getByText(/가상계좌 수 한도에 도달/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "업그레이드" })).toHaveAttribute(
      "href",
      "/pricing"
    );
  });

  it("계좌 생성 요청이 끝날 때까지 생성중 상태를 표시한다", async () => {
    let resolveCreate: () => void = () => {};
    const onCreate = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveCreate = resolve;
        })
    );
    const onClose = vi.fn();
    mockFetch();

    render(
      <CreateAccountModal
        isOpen={true}
        onClose={onClose}
        onCreate={onCreate}
      />
    );

    const selectButton = await screen.findByRole("button", { name: /전략을 선택하세요/i });
    fireEvent.click(selectButton);
    fireEvent.click(await screen.findByRole("button", { name: savedStrategy.name }));
    fireEvent.change(screen.getByPlaceholderText("예: 저PBR 전략, 모멘텀 전략, 가치주 전략..."), {
      target: { value: "생성 대기 계좌" },
    });

    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    const pendingButton = await screen.findByRole("button", {
      name: "계좌 생성중...",
    });
    expect(pendingButton).toBeDisabled();
    expect(pendingButton).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "취소" })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();

    await act(async () => {
      resolveCreate();
    });

    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });
});
