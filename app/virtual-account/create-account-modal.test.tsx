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

  it("only shows the auto trading toggle and keeps it on by default", async () => {
    const onCreate = await renderAndSelectStrategy();

    expect(screen.getByText("매매 방식")).toBeInTheDocument();
    const autoTradingButton = screen.getByRole("button", { name: "전략 시뮬레이션 ON" });
    expect(autoTradingButton).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("ON")).toBeInTheDocument();
    expect(screen.getByText("전략 신호가 발생하면 현재가로 모의 주문이 실행됩니다.")).toBeInTheDocument();

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
      "auto"
    );
  });

  it("creates strategy accounts with manual mode after turning the toggle off", async () => {
    const onCreate = await renderAndSelectStrategy();
    const autoTradingButton = screen.getByRole("button", { name: "전략 시뮬레이션 ON" });

    await act(async () => {
      fireEvent.click(autoTradingButton);
    });

    const disabledAutoTradingButton = screen.getByRole("button", { name: "전략 시뮬레이션 OFF" });
    expect(disabledAutoTradingButton).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("OFF")).toBeInTheDocument();

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

describe("CreateAccountModal presetStrategy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const preset = {
    name: "KOSPI 저PBR 백테스트 전략",
    description: "KOSPI에서 PBR 1배 이하 종목을 매수",
    summaryRows: [
      { label: "유니버스", values: ["KOSPI"] },
      { label: "진입 신호", values: ["PBR 1배 이하"] },
      { label: "리스크", values: ["최대 10종목", "분기 리밸런싱"] },
    ],
  };

  it("전략 드롭다운 대신 백테스트 전략을 고정해 보여주고 계좌 이름을 미리 채운다", async () => {
    mockFetch();

    render(
      <CreateAccountModal isOpen={true} onClose={vi.fn()} onCreate={vi.fn()} presetStrategy={preset} />
    );

    expect(await screen.findByTestId("bound-strategy-name")).toHaveTextContent(preset.name);
    expect(screen.queryByText("전략 선택")).not.toBeInTheDocument();
    // 칩이 아니라 결과 화면 '내 전략'과 같은 라벨·값 행으로 보인다.
    const rows = screen.getByTestId("bound-strategy-rows");
    expect(rows).toHaveTextContent("진입 신호");
    expect(rows).toHaveTextContent("PBR 1배 이하");
    expect(rows).toHaveTextContent("분기 리밸런싱");
    // 계좌 이름은 전략 이름(20자 이내)으로 미리 채워 바로 만들 수 있게 한다.
    expect(screen.getByPlaceholderText("예: 저PBR 전략, 모멘텀 전략, 가치주 전략...")).toHaveValue(
      preset.name.slice(0, 20)
    );
    // 전략 목록은 불러오지 않는다.
    expect(vi.mocked(fetch).mock.calls.map((c) => String(c[0]))).not.toContain("/api/strategy");
  });

  it("고정 전략으로 만들면 strategyId 없이 전략 이름과 매매 방식을 전달한다", async () => {
    const onCreate = vi.fn().mockResolvedValue(undefined);
    mockFetch();

    render(
      <CreateAccountModal isOpen={true} onClose={vi.fn()} onCreate={onCreate} presetStrategy={preset} />
    );

    await screen.findByTestId("bound-strategy-name");
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    await waitFor(() =>
      expect(onCreate).toHaveBeenCalledWith(
        preset.name.slice(0, 20),
        10_000_000,
        undefined,
        preset.name,
        "auto"
      )
    );
  });

  it("전략 시뮬레이션을 기본 ON으로 연다", async () => {
    mockFetch();

    render(
      <CreateAccountModal isOpen={true} onClose={vi.fn()} onCreate={vi.fn()} presetStrategy={preset} />
    );

    const toggle = await screen.findByRole("button", { name: /전략 시뮬레이션/ });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });

  it("모달 높이를 화면에 맞춰 고정하고 내용은 모달 안에서 스크롤한다", async () => {
    mockFetch();

    render(
      <CreateAccountModal isOpen={true} onClose={vi.fn()} onCreate={vi.fn()} presetStrategy={preset} />
    );

    await screen.findByTestId("bound-strategy-name");
    expect(screen.getByTestId("create-account-panel")).toHaveClass(
      "max-h-[calc(100dvh-2rem)]",
      "lg:max-h-[85vh]",
      "flex",
      "flex-col",
      "overflow-hidden"
    );
    expect(screen.getByTestId("create-account-body")).toHaveClass(
      "flex-1",
      "min-h-0",
      "overflow-y-auto",
      "overscroll-contain"
    );
  });

  it("계좌 생성이 이유를 담아 실패하면 그 문구를 그대로 보여준다", async () => {
    const onCreate = vi.fn().mockRejectedValue(new Error("전략 저장 한도에 도달했습니다."));
    mockFetch();

    render(
      <CreateAccountModal isOpen={true} onClose={vi.fn()} onCreate={onCreate} presetStrategy={preset} />
    );

    await screen.findByTestId("bound-strategy-name");
    fireEvent.click(screen.getByRole("button", { name: "만들기" }));

    expect(await screen.findByText("전략 저장 한도에 도달했습니다.")).toBeInTheDocument();
  });
});
