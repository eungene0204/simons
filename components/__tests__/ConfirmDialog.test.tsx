// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { useConfirmDialog } from "@/components/ui/ConfirmDialog";

function Harness() {
  const { confirm, dialog } = useConfirmDialog();
  const [result, setResult] = useState<string>("idle");
  return (
    <div>
      <button
        onClick={async () => {
          const ok = await confirm({ title: "정말 삭제할까요?", message: "되돌릴 수 없습니다.", confirmLabel: "삭제", danger: true });
          setResult(ok ? "confirmed" : "cancelled");
        }}
      >
        open
      </button>
      <output>{result}</output>
      {dialog}
    </div>
  );
}

describe("useConfirmDialog", () => {
  it("확인을 누르면 true, 취소를 누르면 false로 약속이 끝난다", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("open"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("정말 삭제할까요?");
    // 첫 포커스는 '취소'(실수로 Enter를 눌러도 파괴적 동작이 실행되지 않게)
    expect(document.activeElement).toBe(screen.getByText("취소"));
    await act(async () => {
      fireEvent.click(screen.getByText("삭제"));
    });
    expect(screen.getByRole("status").textContent).toBe("confirmed");
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.click(screen.getByText("open"));
    await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.click(screen.getByText("취소"));
    });
    expect(screen.getByRole("status").textContent).toBe("cancelled");
  });

  it("Esc는 취소로 끝난다", async () => {
    render(<Harness />);
    fireEvent.click(screen.getByText("open"));
    await screen.findByRole("alertdialog");
    await act(async () => {
      fireEvent.keyDown(document, { key: "Escape" });
    });
    expect(screen.getByRole("status").textContent).toBe("cancelled");
  });
});
