import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import HomePage from "./page";

vi.mock("./analytics/page", () => ({
  default: () => <div>전략연구소 메인 화면</div>,
}));

describe("HomePage", () => {
  it("renders the strategy lab main page at the root path", () => {
    render(<HomePage />);

    expect(screen.getByText("전략연구소 메인 화면")).toBeInTheDocument();
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
  });

  it("renders nullStock terms when the legal query is terms", () => {
    const { container } = render(<HomePage searchParams={{ legal: "terms" }} />);

    expect(screen.getByRole("heading", { name: "nullStock 이용약관" })).toBeInTheDocument();
    expect(screen.getByText("널스페이스")).toBeInTheDocument();
    expect(
      screen.getByText(/투자자문, 투자일임, 금융투자상품 매매·중개/),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제10조 (유료서비스, 결제 및 환불)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제17조 (분쟁 해결 및 준거법)" })).toBeInTheDocument();
    expect(screen.getByText(/청약철회 및 환불 조건을 결제 전 화면에 표시합니다/)).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("bg-[#0f0f0f]", "text-white");
  });

  it("renders nullStock privacy policy when the legal query is privacy", () => {
    const { container } = render(<HomePage searchParams={{ legal: "privacy" }} />);

    expect(screen.getByRole("heading", { name: "nullStock 개인정보처리방침" })).toBeInTheDocument();
    expect(screen.getByText(/개인정보 보호법 제30조에 따라/)).toBeInTheDocument();
    expect(screen.getByText(/고충을 신속하고 원활하게 처리할 수 있도록/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제2조 (처리하는 개인정보 항목)" })).toBeInTheDocument();
    expect(screen.getByText(/Supabase를 통한 Google 로그인/)).toBeInTheDocument();
    expect(screen.queryByText(/암호화된 비밀번호/)).not.toBeInTheDocument();
    expect(screen.getByText(/전략명, 전략 설명, 조건식/)).toBeInTheDocument();
    expect(screen.getByText(/Supabase OAuth 인증과 회사의 JWT 세션/)).toBeInTheDocument();
    expect(screen.getByText(/투자 추천, 종목 추천, 포트폴리오 추천/)).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("bg-[#0f0f0f]", "text-white");
  });
});
