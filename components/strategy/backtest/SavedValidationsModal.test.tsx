import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/validation-storage", () => ({
  listSavedValidations: vi.fn(() => Promise.resolve([])),
  deleteSavedValidation: vi.fn(),
}));

import { listSavedValidations } from "@/lib/validation-storage";
import SavedValidationsModal from "./SavedValidationsModal";

describe("SavedValidationsModal", () => {
  it("빈 상태에서 저장 안내 문장을 표시하지 않는다", async () => {
    render(
      <SavedValidationsModal
        open
        onClose={() => {}}
        onSelect={() => {}}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("저장된 검증 결과가 없습니다.")).toBeInTheDocument();
    });
    expect(screen.queryByText(/워크포워드·몬테카를로 결과 화면/)).not.toBeInTheDocument();
    expect(screen.queryByText(/결과 저장/)).not.toBeInTheDocument();
  });

  it("모바일 높이를 제한하고 터치 환경에서 삭제 버튼을 표시한다", async () => {
    vi.mocked(listSavedValidations).mockResolvedValueOnce([
      {
        id: "validation-1",
        modelType: "walkForward",
        strategyName: "저PBR 전략",
        createdAt: Date.now(),
        summary: { wfe: 0.72, nSplits: 5 },
      },
    ] as any);

    render(
      <SavedValidationsModal
        open
        onClose={() => {}}
        onSelect={() => {}}
      />
    );

    expect(await screen.findByText("저PBR 전략")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "저장된 검증 결과" })).toHaveClass(
      "p-2",
      "lg:p-4"
    );
    expect(screen.getByTestId("saved-validations-panel")).toHaveClass(
      "max-h-[calc(100dvh-1rem)]",
      "lg:max-h-[80vh]"
    );
    expect(screen.getByTestId("saved-validations-header")).toHaveClass(
      "px-4",
      "py-3",
      "lg:px-5",
      "lg:py-4"
    );
    expect(screen.getByTestId("saved-validations-list")).toHaveClass(
      "overflow-y-auto",
      "p-3",
      "lg:p-4"
    );
    expect(screen.getByRole("button", { name: "삭제" })).toHaveClass(
      "opacity-100",
      "lg:opacity-0",
      "lg:group-hover:opacity-100"
    );
  });
});
