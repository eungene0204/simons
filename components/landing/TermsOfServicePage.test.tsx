import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { __resetLanguageForTests, setLanguage } from "@/lib/i18n";
import { TermsOfServicePage } from "./TermsOfServicePage";

afterEach(() => {
  vi.unstubAllEnvs();
  __resetLanguageForTests();
});

describe("TermsOfServicePage", () => {
  it("renders the refund policy terms", () => {
    render(<TermsOfServicePage />);

    expect(screen.getByText(/널스페이스가 널스탁 유료서비스를 제공하는 경우/)).toBeInTheDocument();
    expect(screen.getByText(/유료 기능을 단 한 번도 이용하지 않은 경우에는/)).toBeInTheDocument();
    expect(screen.getByText(/유료 기능을 1회 이상 이용한 경우에는/)).toBeInTheDocument();
    expect(screen.getByText(/중복 결제, 시스템 오류로 인한 잘못된 결제/)).toBeInTheDocument();
    expect(screen.getByText(/이용기간 연장 또는 전액 환불 중 하나의 조치/)).toBeInTheDocument();
    expect(screen.getByText(/다음 결제일부터는 추가 과금이 이루어지지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText(/영업일 기준 3~7일 이내/)).toBeInTheDocument();
  });

  it("renders business information from environment variables", () => {
    vi.stubEnv("COMPANY_NAME", "널스페이스");
    vi.stubEnv("SERVICE_NAME", "널스탁");
    vi.stubEnv("BUSINESS_REPRESENTATIVE_NAME", "이응준");
    vi.stubEnv("BUSINESS_ADDRESS", "서울 서대문구 이화여대7길 37, 3층 - S88호");
    vi.stubEnv("BUSINESS_REGISTRATION_NUMBER", "898-50-00737");
    vi.stubEnv("BUSINESS_MAIL_ORDER_NUMBER", "2026-서울서대문-0758");
    vi.stubEnv("BUSINESS_PHONE", "070-8027-2252");
    vi.stubEnv("BUSINESS_EMAIL", "nullspace.support@gmail.com");

    const { container } = render(<TermsOfServicePage />);

    expect(screen.queryByText("운영 전 확정 항목")).not.toBeInTheDocument();
    expect(screen.queryByText("부칙")).not.toBeInTheDocument();
    expect(screen.queryByText("이 약관은 2026년 7월 8일부터 시행합니다.")).not.toBeInTheDocument();
    expect(screen.getByText("널스탁으로 돌아가기")).toBeInTheDocument();
    expect(screen.getByText("사업자 정보")).toBeInTheDocument();
    expect(screen.getByText("상호")).toBeInTheDocument();
    expect(screen.getAllByText("널스페이스").length).toBeGreaterThan(0);
    expect(screen.getByText("대표자")).toBeInTheDocument();
    expect(screen.getByText("이응준")).toBeInTheDocument();
    expect(screen.getByText("주소")).toBeInTheDocument();
    expect(screen.getByText("서울 서대문구 이화여대7길 37, 3층 - S88호")).toBeInTheDocument();
    expect(screen.getByText("사업자등록번호")).toBeInTheDocument();
    expect(screen.getByText("898-50-00737")).toBeInTheDocument();
    expect(screen.getByText("전화번호")).toBeInTheDocument();
    expect(screen.getByText("070-8027-2252")).toBeInTheDocument();
    expect(screen.getByText("이메일")).toBeInTheDocument();
    expect(screen.getByText("nullspace.support@gmail.com")).toBeInTheDocument();
    // 전자상거래법 제10조 표시 항목 전부와 그 순서(푸터 표기와 동일).
    expect(Array.from(container.querySelectorAll("dl dt")).map((el) => el.textContent)).toEqual([
      "상호",
      "사업자등록번호",
      "통신판매업신고번호",
      "대표자",
      "주소",
      "전화번호",
      "이메일",
    ]);
    expect(screen.getByText("2026-서울서대문-0758")).toBeInTheDocument();
    expect(screen.queryByText("미정")).not.toBeInTheDocument();
  });

  it("영문(글로벌) 페이지에서는 사업자 정보 값도 영어로 표시된다", () => {
    vi.stubEnv("COMPANY_NAME", "널스페이스");
    vi.stubEnv("BUSINESS_REPRESENTATIVE_NAME", "이응준");
    vi.stubEnv("BUSINESS_ADDRESS", "서울특별시 서대문구 이화여대7길 37, 3층 S88호(대현동)");
    vi.stubEnv("BUSINESS_REGISTRATION_NUMBER", "898-50-00737");
    vi.stubEnv("BUSINESS_MAIL_ORDER_NUMBER", "2026-서울서대문-0758");
    vi.stubEnv("BUSINESS_EMAIL", "nullspace.support@gmail.com");
    setLanguage("en");

    render(<TermsOfServicePage />);

    expect(screen.getByText("Business information")).toBeInTheDocument();
    expect(screen.getAllByText("nullspace").length).toBeGreaterThan(0);
    expect(screen.getByText("Eungjun Lee")).toBeInTheDocument();
    expect(
      screen.getByText("3F S88, 37 Ewhayeodae 7-gil, Seodaemun-gu, Seoul (Daehyeon-dong)")
    ).toBeInTheDocument();
    expect(screen.getByText("E-commerce registration number")).toBeInTheDocument();
    expect(screen.getByText("2026-Seoul Seodaemun-0758")).toBeInTheDocument();
    expect(screen.queryByText("이응준")).not.toBeInTheDocument();
    expect(screen.queryByText(/서울특별시 서대문구/)).not.toBeInTheDocument();
  });
});
