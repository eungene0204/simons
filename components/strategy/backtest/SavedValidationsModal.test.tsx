import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/validation-storage", () => ({
  listSavedValidations: vi.fn(() => Promise.resolve([])),
  deleteSavedValidation: vi.fn(),
}));

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
});
