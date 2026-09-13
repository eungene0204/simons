import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import HomePage from "./page";

vi.mock("./analytics/page", () => ({
  default: () => <div>전략연구소 메인 화면</div>,
}));

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("HomePage", () => {
  it("renders the strategy lab main page without the business footer at the root path", () => {
    vi.stubEnv("COMPANY_NAME", "널스페이스");
    vi.stubEnv("BUSINESS_REPRESENTATIVE_NAME", "이응준");
    vi.stubEnv("BUSINESS_REGISTRATION_NUMBER", "898-50-00737");
    vi.stubEnv("BUSINESS_EMAIL", "nullspace.support@gmail.com");

    const { container } = render(<HomePage />);

    expect(screen.getByText("전략연구소 메인 화면")).toBeInTheDocument();
    // 홈에만 구조화 데이터(JSON-LD)를 싣는다 — 검색엔진이 사이트·앱 정보를 읽는 정본.
    const jsonLd = container.querySelector('script[type="application/ld+json"]');
    expect(jsonLd).not.toBeNull();
    const graph = (JSON.parse(jsonLd!.textContent ?? "{}") as { "@graph": Array<{ "@type": string; name?: string }> })["@graph"];
    expect(graph.map((node) => node["@type"])).toEqual(["Organization", "WebSite", "WebApplication"]);
    expect(graph[2].name).toBe("널스탁");
    expect(screen.queryByRole("contentinfo")).not.toBeInTheDocument();
    expect(screen.queryByText("상호명")).not.toBeInTheDocument();
    expect(screen.queryByText("대표자명")).not.toBeInTheDocument();
    expect(screen.queryByText("사업자등록번호")).not.toBeInTheDocument();
    expect(screen.queryByText("nullspace.support@gmail.com")).not.toBeInTheDocument();
  });

  it("renders 널스탁 terms when the legal query is terms", () => {
    const { container } = render(<HomePage searchParams={{ legal: "terms" }} />);

    expect(screen.getByRole("heading", { name: "서비스 이용약관" })).toBeInTheDocument();
    expect(container.querySelector('script[type="application/ld+json"]')).toBeNull();
    expect(screen.getAllByText("널스페이스").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/투자자문업, 투자일임업, 투자매매업, 투자중개업 등 금융투자업 및 유사투자자문업을 영위하지 않습니다/),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제8조 (AI 분석 기능에 관한 고지)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제11조 (플랜 및 이용 한도)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제12조 (환불 정책)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제20조 (분쟁 해결 및 준거법)" })).toBeInTheDocument();
    expect(screen.getByText(/유료 기능을 단 한 번도 이용하지 않은 경우에는/)).toBeInTheDocument();
    expect(screen.getByText(/영업일 기준 3~7일 이내/)).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("bg-[var(--background)]", "text-white");
  });

  it("renders 널스탁 privacy policy when the legal query is privacy", () => {
    const { container } = render(<HomePage searchParams={{ legal: "privacy" }} />);

    expect(screen.getByRole("heading", { name: "개인정보처리방침" })).toBeInTheDocument();
    expect(screen.getByText(/개인정보 보호법 제30조에 따라/)).toBeInTheDocument();
    expect(screen.getByText(/고충을 신속하고 원활하게 처리할 수 있도록/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제2조 (처리하는 개인정보 항목)" })).toBeInTheDocument();
    expect(screen.getByText(/Supabase를 통한 Google 로그인/)).toBeInTheDocument();
    expect(screen.getByText(/이용자의 비밀번호를 직접 수집하거나 저장하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText(/전략명, 전략 설명, 조건식/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "제6조 (처리 위탁 및 국외 이전)" })).toBeInTheDocument();
    expect(screen.getByText(/Supabase OAuth 인증과 회사의 JWT 세션/)).toBeInTheDocument();
    expect(screen.getByText(/AI 모델 학습에 사용하지 않습니다/)).toBeInTheDocument();
    expect(screen.getByText(/만 14세 미만 아동의 회원가입을 허용하지 않으며/)).toBeInTheDocument();
    expect(screen.getByText(/투자 추천, 종목 추천, 포트폴리오 추천/)).toBeInTheDocument();
    expect(container.querySelector("main")).toHaveClass("bg-[var(--background)]", "text-white");
  });
});

describe("HomePage metadata", () => {
  it("uses the absolute keyword-led site title and hreflang pair on the Korean home", async () => {
    const { generateMetadata } = await import("./page");
    const metadata = generateMetadata({});

    expect(metadata.title).toEqual({ absolute: "널스탁 | 퀀트 전략 백테스트·시뮬레이션 플랫폼" });
    expect(metadata.description).toMatch(/퀀트.*백테스트/);
    expect(metadata.alternates).toEqual({
      canonical: "/",
      languages: { "ko-KR": "/", "en-US": "/us", "x-default": "/" },
    });
    expect(metadata.openGraph).toMatchObject({ siteName: "널스탁", locale: "ko_KR", url: "/" });
  });

  it("gives the legal query views their own title and no canonical/hreflang", async () => {
    const { generateMetadata } = await import("./page");

    // Next 14.2가 루트 경로 canonical의 쿼리를 떨어뜨리므로 홈 canonical을 물려받지 않게 비운다.
    // 루트 page.tsx는 layout 템플릿(`%s | 널스탁`)을 받지 않아 사이트명을 직접 붙인다(실측 2026-09-13).
    expect(generateMetadata({ searchParams: { legal: "terms" } })).toEqual({
      title: { absolute: "서비스 이용약관 | 널스탁" },
      alternates: null,
    });
    expect(generateMetadata({ searchParams: { legal: ["privacy"] } })).toEqual({
      title: { absolute: "개인정보처리방침 | 널스탁" },
      alternates: null,
    });
  });
});
