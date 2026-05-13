import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import StrategyLabPage from "./page";
import { prisma } from "@/lib/prisma";

vi.mock("@/lib/prisma", () => ({
  prisma: {
    strategy: {
      findMany: vi.fn(),
    },
    virtualAccount: {
      findMany: vi.fn(),
    },
  },
}));

vi.mock("./StrategyLabClient", () => ({
  default: ({ strategies }: { strategies: Array<{ name: string; accountCount: number }> }) => (
    <div>
      <div data-testid="strategy-count">{strategies.length}</div>
      {strategies.map((strategy) => (
        <div key={strategy.name}>
          {strategy.name}:{strategy.accountCount}
        </div>
      ))}
    </div>
  ),
}));

const prismaMock = prisma as unknown as {
  strategy: { findMany: ReturnType<typeof vi.fn> };
  virtualAccount: { findMany: ReturnType<typeof vi.fn> };
};

describe("StrategyLabPage", () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.clearAllMocks();
    consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("renders strategies even when virtual account loading fails", async () => {
    prismaMock.strategy.findMany.mockResolvedValue([
      {
        id: "strategy-1",
        name: "PBR 전략",
        description: "저평가 전략",
        settings: JSON.stringify({ universe: "KOSPI200" }),
        strategyType: "value",
        createdAt: new Date("2026-05-06T00:00:00.000Z"),
      },
    ]);
    prismaMock.virtualAccount.findMany.mockRejectedValue(new Error("disk I/O error"));

    render(await StrategyLabPage());

    expect(screen.getByTestId("strategy-count")).toHaveTextContent("1");
    expect(screen.getByText("PBR 전략:0")).toBeInTheDocument();
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[StrategyLabPage] Failed to load virtual accounts",
      expect.any(Error)
    );
  });

  it("renders an empty strategy list when strategy loading fails", async () => {
    prismaMock.strategy.findMany.mockRejectedValue(new Error("disk I/O error"));
    prismaMock.virtualAccount.findMany.mockResolvedValue([]);

    render(await StrategyLabPage());

    expect(screen.getByTestId("strategy-count")).toHaveTextContent("0");
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      "[StrategyLabPage] Failed to load strategies",
      expect.any(Error)
    );
  });
});
