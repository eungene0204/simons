import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";

import OptimizationSettingsModal from "./OptimizationSettingsModal";

describe("OptimizationSettingsModal", () => {
  it("기본 최적화 설정과 기술 지표 파라미터 범위를 표시한다", () => {
    render(<OptimizationSettingsModal open onOpenChange={() => {}} />);

    expect(screen.getByRole("dialog", { name: "전략 최적화" })).toBeInTheDocument();
    expect(screen.getByText("선택한 파라미터의 값을 자동으로 탐색하여 가장 좋은 결과를 찾습니다.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Grid Search/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Bayesian Optimization/ })).not.toBeChecked();
    expect(screen.getByLabelText("최적화 목표")).toHaveValue("sharpe");
    expect(screen.getByRole("option", { name: "MDD (최소)" })).toBeInTheDocument();

    expect(screen.getByText("이동평균 (SMA)")).toBeInTheDocument();
    expect(screen.getAllByText("허용범위 2~250일").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("이동평균 (SMA) 최소값")).toHaveValue(5);
    expect(screen.getByLabelText("이동평균 (SMA) 최대값")).toHaveValue(120);
    expect(screen.getByLabelText("이동평균 (SMA) Step")).toHaveValue(5);
    expect(screen.getByText("거래량 증가 배수")).toBeInTheDocument();
    expect(screen.getByText("선택된 파라미터 0개")).toBeInTheDocument();
    expect(screen.getAllByText("예상 테스트 0회").length).toBeGreaterThan(0);
  });

  it("Grid Search 선택 파라미터의 예상 테스트 수와 입력 오류를 즉시 표시한다", async () => {
    const user = userEvent.setup();
    render(<OptimizationSettingsModal open onOpenChange={() => {}} />);

    await user.click(screen.getByRole("checkbox", { name: /이동평균 \(SMA\)/ }));
    await user.click(screen.getByRole("checkbox", { name: /^EMA\b/ }));

    expect(screen.getByText("선택된 파라미터 2개")).toBeInTheDocument();
    expect(screen.getAllByText("예상 테스트 576회").length).toBeGreaterThan(0);
    expect(screen.getAllByText("예상 시간 약 2분").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("이동평균 (SMA) 최소값"), { target: { value: "1" } });
    expect(screen.getByText("허용범위 2~250를 벗어났습니다.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("이동평균 (SMA) 최소값"), { target: { value: "120" } });
    expect(screen.getByText("최소값은 최대값보다 작아야 합니다.")).toBeInTheDocument();
    expect(screen.getAllByText("예상 테스트 0회").length).toBeGreaterThan(0);
  });

  it("Bayesian Optimization 전환 시 Step을 숨기고 입력값을 유지한다", async () => {
    const user = userEvent.setup();
    render(<OptimizationSettingsModal open onOpenChange={() => {}} />);

    await user.click(screen.getByRole("checkbox", { name: /이동평균 \(SMA\)/ }));
    fireEvent.change(screen.getByLabelText("이동평균 (SMA) 최소값"), { target: { value: "10" } });

    await user.click(screen.getByRole("radio", { name: /Bayesian Optimization/ }));

    expect(screen.getByRole("radio", { name: /Bayesian Optimization/ })).toBeChecked();
    expect(screen.queryByLabelText("이동평균 (SMA) Step")).not.toBeInTheDocument();
    expect(screen.getByLabelText("최대 시도 횟수")).toHaveValue("2");
    expect(screen.getAllByText("100").length).toBeGreaterThan(0);
    expect(screen.getByText("선택된 파라미터 1개")).toBeInTheDocument();
    expect(screen.getAllByText("예상 테스트 100회").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("radio", { name: /Grid Search/ }));

    expect(screen.getByLabelText("이동평균 (SMA) 최소값")).toHaveValue(10);
    expect(screen.getByLabelText("이동평균 (SMA) Step")).toHaveValue(5);
  });

  it("닫기 버튼으로 모달을 닫는다", async () => {
    const onOpenChange = vi.fn();
    render(<OptimizationSettingsModal open onOpenChange={onOpenChange} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "전략 최적화 닫기" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("검증 오류가 없으면 설정 저장으로 모달을 닫는다", async () => {
    const onOpenChange = vi.fn();
    render(<OptimizationSettingsModal open onOpenChange={onOpenChange} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "설정 저장" }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
