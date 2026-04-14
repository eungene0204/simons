import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { StrategyExampleTabs } from "@/components/strategy/StrategyExampleTabs";

describe("StrategyExampleTabs", () => {
  it("각 숙련도 탭마다 예시가 6개씩 보인다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    expect(screen.getAllByRole("button", { name: /입력 예시/i })).toHaveLength(6);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "중급자 예시" }));
    });
    expect(screen.getAllByRole("button", { name: /입력 예시/i })).toHaveLength(6);

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "전문가 예시" }));
    });
    expect(screen.getAllByRole("button", { name: /입력 예시/i })).toHaveLength(6);
  });

  it("기본으로 초보자 예시를 보여주고 탭 전환 시 해당 숙련도 예시만 노출한다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    expect(screen.getByText("저PBR 대형주 장기보유")).toBeInTheDocument();
    expect(screen.queryByText("중형주 퀄리티-밸류-모멘텀 결합")).not.toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "전문가 예시" }));
    });

    expect(screen.getByText("중형주 퀄리티-밸류-모멘텀 결합")).toBeInTheDocument();
    expect(screen.queryByText("저PBR 대형주 장기보유")).not.toBeInTheDocument();
  });

  it("선택된 등급 버튼은 main-blue 배경을 사용한다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    const beginnerTab = screen.getByRole("button", { name: "초보자 예시" });
    expect(beginnerTab.className).toContain("bg-[var(--main-blue)]");
    expect(beginnerTab.className).toContain("text-white");

    await act(async () => {
      await user.click(screen.getByRole("button", { name: "중급자 예시" }));
    });

    const intermediateTab = screen.getByRole("button", { name: "중급자 예시" });
    expect(intermediateTab.className).toContain("bg-[var(--main-blue)]");
    expect(intermediateTab.className).toContain("text-white");
  });

  it("예시 카드를 누르면 해당 프롬프트를 입력창으로 보낼 수 있다", async () => {
    const onSelectExample = vi.fn();
    const user = userEvent.setup();

    render(<StrategyExampleTabs onSelectExample={onSelectExample} />);

    await user.click(screen.getByRole("button", { name: /이평선 골든크로스 따라가기/i }));

    expect(onSelectExample).toHaveBeenCalledWith(
      "차트를 보니까 단기 이동평균선이 장기 이동평균선을 위로 뚫을 때 많이들 들어간다고 하더라고요. KOSPI 종목 중 골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도하는 식으로 간단하게 만들어 주세요. 종목은 최대 10개, 손절은 -8%로 부탁드립니다."
    );
  });
});
