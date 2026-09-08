// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useRef } from "react";
import { useDialogBehavior } from "./useDialogBehavior";

function Dialog({ open, onClose, label = "dialog" }: { open: boolean; onClose: () => void; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useDialogBehavior({ open, onClose, containerRef: ref });
  if (!open) return null;
  return (
    <div ref={ref} role="dialog" aria-label={label} tabIndex={-1}>
      <button>{label}-first</button>
      <button>{label}-last</button>
    </div>
  );
}

describe("useDialogBehavior", () => {
  it("Esc로 닫히고, 닫힌 뒤 열기 전 요소로 포커스가 돌아간다", () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <>
        <button>opener</button>
        <Dialog open={false} onClose={onClose} />
      </>,
    );
    const opener = screen.getByText("opener");
    opener.focus();
    expect(document.activeElement).toBe(opener);

    rerender(
      <>
        <button>opener</button>
        <Dialog open onClose={onClose} />
      </>,
    );
    expect(document.activeElement).toBe(screen.getByText("dialog-first"));

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(
      <>
        <button>opener</button>
        <Dialog open={false} onClose={onClose} />
      </>,
    );
    expect(document.activeElement).toBe(opener);
  });

  it("Tab이 컨테이너 안에서 순환한다(포커스 트랩)", () => {
    render(<Dialog open onClose={() => {}} />);
    const first = screen.getByText("dialog-first");
    const last = screen.getByText("dialog-last");
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);
  });

  it("열려 있는 동안 body 스크롤을 잠그고 닫히면 되돌린다", () => {
    const { unmount } = render(<Dialog open onClose={() => {}} />);
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("");
  });

  it("겹쳐 열린 다이얼로그는 맨 위 것만 Esc·Tab을 받는다", () => {
    const closeBottom = vi.fn();
    const closeTop = vi.fn();
    render(
      <>
        <Dialog open onClose={closeBottom} label="bottom" />
        <Dialog open onClose={closeTop} label="top" />
      </>,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(closeTop).toHaveBeenCalledTimes(1);
    expect(closeBottom).not.toHaveBeenCalled();
  });
});
