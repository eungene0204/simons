import Link from "next/link";
import { LoginReturnVeil } from "./LoginReturnVeil";
import { StartButton } from "./StartButton";
import { StepVideo } from "./StepVideo";
import { ExampleFlow } from "./ExampleFlow";
import { LandingIcon, type LandingIconName } from "./LandingIcon";
import { PLANS, PLAN_ORDER, type Plan } from "@/lib/plans";

// 비로그인 방문자가 `/`에서 처음 만나는 소개 페이지(한국어 전용 서버 컴포넌트).
// 도구(전략연구소)는 `/analytics`, 로그인 사용자와 `/?prompt=` 딥링크는 `/`가 도구를 그대로 연다(app/page.tsx).
// 문구는 규제 안전 원칙을 따른다 — 연구·백테스트·시뮬레이션 플랫폼이며 추천·전망·수익 보장 표현을 쓰지 않는다.

export const LANDING_START_HREF = "/analytics";


// '설계 → 검증 → 모의투자' 세 단계. 영상은 scripts/landing_hero/의 장면에서 렌더한다(StepVideo).
const STEPS = [
  {
    no: "01",
    title: "설계",
    video: "hero",
    label: "전략 문장을 입력하면 조건이 그래프로 정리되고, 빠진 정보를 질문한 뒤 백테스트 결과 화면이 나오는 과정을 보여 주는 영상",
    body: "떠오른 아이디어를 평소 말투로 적으면 매수·매도 조건, 종목 수, 손절 같은 항목으로 정리해 보여줍니다. 빠진 값은 임의로 채우지 않고 되묻습니다.",
  },
  {
    no: "02",
    title: "검증",
    video: "validate",
    label: "워크포워드 분석이 학습 구간과 검증 구간을 번갈아 나누고, 몬테카를로 시뮬레이션이 결과를 다시 섞어 만든 가상 경로와 분포를 보여 주는 영상",
    body: "과거 데이터로 백테스트하고, 워크포워드와 몬테카를로로 결과가 한 구간·한 경로에만 기댄 것은 아닌지 점검합니다.",
  },
  {
    no: "03",
    title: "모의투자",
    video: "paper",
    label: "가상계좌를 만들고 저장된 전략을 연결하면 전략 시뮬레이션이 시작되고, 보유 종목과 거래 내역, 성과 분석을 확인하는 과정을 보여 주는 영상",
    body: "저장된 전략을 가상계좌에 연결하면 실제 돈 없이 가상 체결로 시뮬레이션이 이어집니다. 가상 체결과 포트폴리오, 거래 내역을 그대로 확인할 수 있습니다.",
  },
] as const;

// 누구를 위한 서비스인가 — 나이·자산·성향이 아니라 '하고 싶은 일'로 나눈다(개인 맞춤형 조언 표현 회피).
const AUDIENCES: readonly { icon: LandingIconName; title: string; body: string }[] = [
  {
    icon: "ChatCircleText",
    title: "코딩 없이 전략을 검증해 보고 싶은 분",
    body: "RSI, PER, ROE, 이동평균, 거래대금 등 원하는 조건을 일상적인 문장으로 입력하면, 복잡한 설정 없이 투자 전략을 만들 수 있습니다.",
  },
  {
    icon: "ChartLineUp",
    title: "과거 데이터로 투자 전략의 성과를 확인하고 싶은 분",
    body: "과거 시장 데이터로 전략을 테스트하고, 연평균 수익률(CAGR), 최대 낙폭, 샤프 비율, 손익비 등 주요 지표와 거래 통계, 수익 곡선을 통해 성과를 확인할 수 있습니다.",
  },
  {
    icon: "ShieldCheck",
    title: "백테스트 결과를 한 번 더 검증하고 싶은 분",
    body: "워크포워드와 몬테카를로 분석으로 투자 성과가 우연이나 특정 시장 상황에 치우친 결과는 아닌지 확인합니다.",
  },
  {
    icon: "Flask",
    title: "실시간 시장 데이터로 투자 전략을 검증하고 싶은 분",
    body: "실시간 시장 데이터를 바탕으로 가상계좌에서 투자 전략을 실행하고 성과를 확인합니다. 모든 거래는 모의투자로 진행되며, 실제 주문은 발생하지 않습니다.",
  },
] as const;

const FAQ = [
  {
    q: "투자 자문이나 종목 추천을 해주는 서비스인가요?",
    a: "아닙니다. 널스탁은 투자 연구·시뮬레이션 플랫폼입니다. 전략은 사용자가 직접 만들고, 시스템은 계산과 백테스트, 과거 데이터 표시만 합니다. 종목·전략 추천이나 매수·매도 시점 제안은 제공하지 않습니다.",
  },
  {
    q: "백테스트 결과가 좋으면 앞으로도 그렇게 되나요?",
    a: "그렇지 않습니다. 모든 결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다. 그래서 워크포워드와 몬테카를로 같은 검증 도구를 함께 제공합니다.",
  },
  {
    q: "모의투자에서 실제 돈이 오가나요?",
    a: "아닙니다. 가상계좌의 투자금은 시뮬레이션용 가상 금액이며 실제 거래나 입출금은 없습니다.",
  },
  {
    q: "투자 지식이 많지 않아도 쓸 수 있나요?",
    a: "투자 아이디어를 자유롭게 입력하면 전략 조건으로 정리하고, 필요한 정보는 추가로 질문합니다. 아래 예시를 누르면 입력창에 내용이 채워져 쉽게 시작할 수 있습니다.",
  },
] as const;

function formatWon(value: number): string {
  return `₩${value.toLocaleString("ko-KR")}`;
}

function planLines(plan: Plan): string[] {
  return [
    `월 백테스트 ${plan.monthlyBacktestLimit.toLocaleString("ko-KR")}회`,
    `가상계좌 ${plan.maxVirtualAccounts}개`,
    plan.isUnlimitedStrategies ? "전략 저장 무제한" : `전략 저장 ${plan.maxStrategies}개`,
  ];
}

const PRIMARY_BUTTON =
  "inline-flex items-center justify-center rounded-xl bg-[var(--chat-accent)] px-6 py-3.5 text-sm font-black text-[var(--chat-accent-ink)] transition-opacity hover:opacity-90";
const SECONDARY_BUTTON =
  "inline-flex items-center justify-center rounded-xl border border-white/[0.12] px-6 py-3.5 text-sm font-bold text-white transition-colors hover:bg-white/[0.06]";
const SECTION = "px-4 py-16 sm:px-6 sm:py-24";
const SECTION_TITLE = "font-serif text-3xl font-bold tracking-normal text-white sm:text-4xl";

export function HomeLanding() {
  return (
    <main
      data-testid="home-landing"
      className="min-h-[100dvh] bg-[var(--background)] pt-[var(--top-menu-bar-height,76px)] text-white"
    >
      <LoginReturnVeil />
      <section className="px-4 pb-16 pt-14 sm:px-6 sm:pb-24 sm:pt-24">
        <div className="mx-auto max-w-5xl text-center">
          <p className="text-xs font-black tracking-[0.18em] text-[var(--chat-accent)]">
            투자 연구 · 백테스트 · 시뮬레이션 플랫폼
          </p>
          <h1 className="mt-5 font-serif text-3xl font-bold leading-[1.25] tracking-normal text-white sm:text-4xl sm:leading-[1.25] lg:text-5xl lg:leading-[1.25]">
            {/* md 이상에서는 두 줄 고정 — 글자 크기는 두 번째 줄이 한 줄에 들어가는 폭으로 잡았다. */}
            <span className="md:whitespace-nowrap">투자 전략을 입력하면,</span>
            <br />
            <span className="md:whitespace-nowrap">백테스트로 성과를 분석해 드립니다.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base font-medium leading-8 text-gray-300 sm:text-lg">
            떠오른 전략을 평소 말투로 적어 보세요. 조건으로 정리하고, 백테스트와 워크포워드·몬테카를로로
            점검한 뒤, 가상계좌 모의투자까지 한곳에서 이어서 진행합니다.
          </p>
          <div className="mt-9 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
            <StartButton href={LANDING_START_HREF} className={PRIMARY_BUTTON}>
              무료로 시작하기
            </StartButton>
          </div>
          <p className="mt-4 text-xs font-bold text-[var(--text-label)]">
            Free 플랜으로 월 {PLANS.FREE.monthlyBacktestLimit}회 백테스트를 바로 해볼 수 있습니다.
          </p>
        </div>
      </section>

      <section id="how-it-works" className={`${SECTION} border-t border-white/[0.08]`}>
        <div className="mx-auto max-w-5xl">
          <h2 className={`${SECTION_TITLE} text-center`}>설계에서 모의투자까지, 세 단계</h2>
          <ol className="mt-12 flex flex-col gap-16 sm:gap-24">
            {STEPS.map((step) => (
              <li key={step.no}>
                <div className="max-w-2xl">
                  <span className="text-sm font-black text-[var(--chat-accent)]">{step.no}</span>
                  <h3 className="mt-3 text-2xl font-black text-white sm:text-3xl">{step.title}</h3>
                  <p className="mt-3 text-sm font-medium leading-7 text-gray-400 sm:text-base sm:leading-8">{step.body}</p>
                </div>
                {/* 세 단계 영상은 같은 폭으로 크게 보여 준다(설계 영상과 같은 크기). */}
                <div className="mt-6 sm:mt-8">
                  <StepVideo name={step.video} label={step.label} />
                </div>
              </li>
            ))}
          </ol>

          {/* 전략 예시들 — 세 단계를 본 뒤 바로 해볼 수 있도록 03 모의투자 아래에 둔다. */}
          <div className="mt-20 sm:mt-28">
            <h3 className="text-center text-2xl font-black text-white sm:text-3xl">
              전략 예시들
            </h3>
            <div className="mt-6">
              <ExampleFlow />
            </div>
          </div>
        </div>
      </section>

      <section className={`${SECTION} border-t border-white/[0.08]`} aria-labelledby="landing-audience">
        <div className="mx-auto max-w-5xl">
          <h2 id="landing-audience" className={`${SECTION_TITLE} text-center`}>
            널스탁은 누구를 위한 서비스인가요?
          </h2>
          <ul className="mt-10 grid gap-4 sm:grid-cols-2">
            {AUDIENCES.map(({ icon, title, body }) => (
              <li key={title} className="flat-card rounded-2xl border border-white/[0.09] bg-[var(--card-bg)] p-6">
                <LandingIcon name={icon} className="text-gray-300" />
                <h3 className="mt-4 text-base font-black text-white">{title}</h3>
                <p className="mt-2 text-sm font-medium leading-7 text-gray-400">{body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className={`${SECTION} border-t border-white/[0.08]`} aria-labelledby="landing-plans">
        <div className="mx-auto max-w-5xl">
          <h2 id="landing-plans" className={`${SECTION_TITLE} text-center`}>
            요금제
          </h2>
          <ul className="mt-10 grid gap-4 md:grid-cols-3">
            {PLAN_ORDER.map((planId) => {
              const plan = PLANS[planId];
              return (
                <li key={planId} className="flat-card rounded-2xl border border-white/[0.09] bg-[var(--card-bg)] p-6">
                  <h3 className="text-lg font-black text-white">{plan.name}</h3>
                  <p className="mt-1 text-sm font-medium text-gray-400">{plan.description}</p>
                  <p className="mt-5 text-3xl font-black text-white">
                    {plan.monthlyPrice === 0 ? "무료" : formatWon(plan.monthlyPrice)}
                    {plan.monthlyPrice > 0 && (
                      <span className="ml-1 text-sm font-bold text-[var(--text-label)]">/ 월</span>
                    )}
                  </p>
                  <ul className="mt-5 space-y-2 text-sm font-medium text-gray-300">
                    {planLines(plan).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      <section className={`${SECTION} border-t border-white/[0.08]`}>
        <div className="mx-auto max-w-3xl">
          <h2 className={`${SECTION_TITLE} text-center`}>자주 묻는 질문</h2>
          <div className="mt-8 divide-y divide-white/[0.08] border-y border-white/[0.08]">
            {FAQ.map((item) => (
              <details key={item.q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-base font-black text-white [&::-webkit-details-marker]:hidden">
                  {item.q}
                  <span aria-hidden="true" className="text-[var(--text-label)] transition-transform group-open:rotate-45">
                    +
                  </span>
                </summary>
                <p className="mt-3 text-sm font-medium leading-7 text-gray-400">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="border-t border-white/[0.08] px-4 py-16 sm:px-6 sm:py-24">
        <div className="mx-auto max-w-3xl text-center">
          <LandingIcon name="Funnel" size={28} className="mx-auto text-gray-300" />
          <h2 className="mt-5 font-serif text-3xl font-bold tracking-normal text-white sm:text-4xl">
            첫 전략을 직접 적어 보세요
          </h2>
          <div className="mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row sm:items-center">
            <StartButton href={LANDING_START_HREF} className={PRIMARY_BUTTON}>
              무료로 시작하기
            </StartButton>
            <Link href="/guide" className={SECONDARY_BUTTON}>
              백테스트 가이드 읽기
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/[0.08] px-4 py-10 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <p className="text-xs font-bold leading-relaxed text-[var(--text-label)]">
            널스탁은 투자 자문·투자 추천을 제공하지 않는 투자 연구 및 시뮬레이션 플랫폼입니다. 모든 결과는 과거 데이터
            기반 시뮬레이션이며 미래 수익은 보장되지 않습니다. 투자 판단과 그에 따른 책임은 사용자에게 있습니다.
          </p>
          <nav aria-label="약관 및 정책" className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-xs font-bold text-gray-400">
            <Link href="/?legal=terms" className="hover:text-white">
              서비스 이용약관
            </Link>
            <Link href="/?legal=privacy" className="hover:text-white">
              개인정보처리방침
            </Link>
            <Link href="/guide" className="hover:text-white">
              백테스트 가이드
            </Link>
            <Link href="/board" className="hover:text-white">
              자유게시판
            </Link>
          </nav>
        </div>
      </footer>
    </main>
  );
}
