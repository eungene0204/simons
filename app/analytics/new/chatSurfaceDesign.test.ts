import { describe, expect, it } from "vitest";
import { readFileSync } from "fs";
import path from "path";

// 전략연구소 대화 표면의 디자인 계약 가드. 아래 항목들은 실제로 회귀한 적이 있어
// 소스 스캔으로 고정한다(chatInputText.test.ts와 같은 방식).
const read = (relative: string) =>
  readFileSync(path.join(process.cwd(), relative), "utf-8");

describe("폰트 배선", () => {
  const tailwindConfig = read("tailwind.config.js");
  const globals = read("app/globals.css");

  // tailwind에 fontFamily 확장이 없어 font-outfit·font-inter가 정의되지 않은
  // 죽은 클래스였고(22개 파일이 사용 중), 실제 렌더 폰트는 globals.css의 Arial이었다.
  it("font-outfit·font-inter 유틸리티가 정의돼 있다", () => {
    expect(tailwindConfig).toMatch(/fontFamily:\s*\{/);
    expect(tailwindConfig).toMatch(/\boutfit:\s*\[/);
    expect(tailwindConfig).toMatch(/\binter:\s*\[/);
    expect(tailwindConfig).toMatch(/\bsans:\s*\[/);
  });

  // 본문 폰트는 Arial로 되돌렸다(2026-07-25) — Inter/Outfit 웹폰트를 스택 앞에
  // 세우면 수치 자형이 바뀌어 백테스트 결과 화면에서 눈에 띈다.
  it("모든 스택이 Arial로 시작하고 웹폰트 변수를 앞세우지 않는다", () => {
    const stacks = tailwindConfig.match(/\b(?:sans|inter|outfit):\s*\[[^\]]*\]/g) ?? [];
    expect(stacks).toHaveLength(3);
    for (const stack of stacks) {
      expect(stack).toMatch(/\[\s*'Arial'/);
      expect(stack).not.toContain("--font-inter");
      expect(stack).not.toContain("--font-outfit");
    }
  });

  it("한글 글리프를 커버하는 폰트가 스택에 있다", () => {
    expect(tailwindConfig).toContain("Pretendard");
    expect(tailwindConfig).toContain("Apple SD Gothic Neo");
    expect(tailwindConfig).toContain("Malgun Gothic");
  });

  it("globals.css가 body에서 폰트 스택을 덮어쓰지 않는다", () => {
    const bodyRule = globals.match(/\bbody\s*\{[^}]*\}/)?.[0] ?? "";
    expect(bodyRule).not.toContain("font-family");
  });
});

describe("감속 설정(prefers-reduced-motion) 존중", () => {
  const globals = read("app/globals.css");
  const page = read("app/analytics/new/page.tsx");

  it("대화 진입·로딩 연출이 감속 블록에 들어있다", () => {
    const reduceBlocks = globals.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\n\}/g,
    );
    expect(reduceBlocks).toBeTruthy();
    const covered = reduceBlocks!.join("\n");
    for (const selector of [
      ".animate-dot-fill",
      ".chat-enter",
      ".chat-card-enter",
      ".chat-headline-char",
      ".shimmer::after",
    ]) {
      expect(covered).toContain(selector);
    }
  });

  // 인라인 style의 animation 선언은 CSS로 끌 수 없어 감속 설정을 무시한다.
  it("연출을 인라인 style animation으로 넣지 않는다", () => {
    expect(page).not.toMatch(/style=\{\{[^}]*animation:/);
    expect(page).not.toContain("softChatCardEnter");
    expect(page).not.toContain("softChatSurfaceEnter");
  });

  it("계속 도는 스피너 아이콘은 motion-reduce로 멈춘다", () => {
    const spinners = page.match(/className="[^"]*animate-spin[^"]*"/g) ?? [];
    expect(spinners.length).toBeGreaterThan(0);
    for (const spinner of spinners) {
      expect(spinner).toContain("motion-reduce:animate-none");
    }
  });
});

describe("강조색 단일화(Color Consistency Lock)", () => {
  const page = read("app/analytics/new/page.tsx");

  // 이전에는 amber·yellow·orange·sky·blue·indigo 그라디언트가 한 화면에 섞여
  // 색이 의미를 잃었다. 장식 목적 강조는 --chat-accent 하나만 쓴다.
  it("장식용 색상 유틸리티를 쓰지 않는다", () => {
    const decorative =
      /\b(?:text|bg|border|from|to)-(?:sky|yellow|amber|orange|indigo|purple|emerald)-\d{3}\b/g;
    expect(page.match(decorative) ?? []).toEqual([]);
  });

  // tailwind는 `[var(--x)]/50` 같은 투명도 수정자에서 아무 클래스도 생성하지 않는다.
  // 조용히 사라지므로(2026-07-25 'AI 모델 로드 실패' 배지가 배경·테두리 없이
  // 렌더되던 기존 결함) 투명도 단계는 CSS 변수로 만들어 쓴다.
  it("CSS 변수에 투명도 수정자를 붙이지 않는다", () => {
    expect(page.match(/\[var\(--[a-z0-9-]+\)\]\/\d+/g) ?? []).toEqual([]);
  });

  it("강조색과 의미색이 토큰으로 분리돼 있다", () => {
    expect(page).toContain("var(--chat-accent)");
    // 상승/하락·에러는 의미색이므로 강조색으로 대체하지 않는다.
    expect(page).toContain("var(--error-red)");
  });
});

describe("레이아웃 기본", () => {
  const page = read("app/analytics/new/page.tsx");

  // 100vh는 iOS Safari에서 주소창 높이 때문에 레이아웃이 튄다.
  it("전체 높이 계산에 100vh 대신 100dvh를 쓴다", () => {
    expect(page).not.toMatch(/\b100vh\b/);
    expect(page).toContain("100dvh");
  });

  it("대화 표면 위계가 상수로 분리돼 있다", () => {
    for (const token of [
      "USER_CHAT_BUBBLE_CLASS",
      "ARTIFACT_CARD_CLASS",
      "CHOICE_CHIP_CLASS",
      "BACK_CONTROL_CLASS",
    ]) {
      expect(page).toContain(token);
    }
  });

  // 세로 레일(강조색 3px, 산문 헤어라인, 오류 레드)은 전부 사용자 요청으로
  // 제거했다(2026-07-25). 산문은 카드가 없다는 사실 자체로 구분된다.
  it("세로 레일을 쓰지 않는다", () => {
    expect(page).not.toMatch(/\bborder-l\b/);
    expect(page).not.toMatch(/border-l-\[/);
  });

  // '돌아가기'를 회색 텍스트로만 두면 정적 캡션으로 읽혀 사용자가 되돌릴 길을
  // 찾지 못한다(2026-07-25 제보). 색이 아니라 테두리·면·눌림으로 컨트롤임을 알린다.
  it("돌아가기 컨트롤이 클릭 가능한 형태를 갖는다", () => {
    const backControl = page.match(/const BACK_CONTROL_CLASS =\s*\n\s*"([^"]*)"/)?.[1];
    expect(backControl).toBeTruthy();
    expect(backControl).toContain("border");
    expect(backControl).toContain("hover:");
    expect(backControl).toContain("active:");
    expect(backControl).toContain("focus-visible:");
    // 되묻기 카드의 돌아가기 버튼이 실제로 이 클래스를 쓴다.
    expect(page).toMatch(
      /className=\{BACK_CONTROL_CLASS\}[\s\S]{0,300}\{CONFIRMATION_BACK_CHIP\}/,
    );
  });

  // 사용자 발화와 산출물이 같은 표면을 쓰면 화자와 블록 종류가 구별되지 않는다
  // (이전에는 USER_CHAT_BUBBLE_CLASS와 COACH_CHAT_BUBBLE_CLASS가 문자열까지 같았다).
  it("사용자 발화는 채워진 면, 산출물은 테두리 카드다", () => {
    const userClass = page.match(/const USER_CHAT_BUBBLE_CLASS = "([^"]*)"/)?.[1];
    const cardClass = page.match(/const ARTIFACT_CARD_CLASS =\s*"?\s*"([^"]*)"/)?.[1];
    expect(userClass).toContain("bg-[var(--chat-user-surface)]");
    expect(cardClass).toContain("border");
    expect(userClass).not.toEqual(cardClass);
  });

  // 전략 재진술 첫 문장("…전략이군요.")은 요약 카드와 같은 내용을 반복해 정보값이
  // 없다는 사용자 판단으로 제거됐다(2026-07-31). 다시 살아나지 않게 고정한다.
  it("전략 재진술 문장을 렌더링하지 않는다", () => {
    expect(page).not.toContain("strategy-restatement");
    expect(page).not.toContain("buildStrategyRestatement");
  });
});
