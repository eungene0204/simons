import { EXAMPLES, type Example } from "@/components/strategy/strategyExamples";
import { STRATEGY_PROMPT_PARAM } from "@/lib/strategy/strategyOpenLink";

// 소개 페이지의 전략 예시 흐름 — 예시 카드가 왼쪽으로 천천히 흐른다. 카드를 누르면 전략연구소가
// 그 문장을 입력창에 채워 연다(`/?prompt=`, 보내기는 방문자가 누른다 — strategyOpenLink.ts).
// 흐름은 같은 목록을 두 번 이어 붙여 끊김 없이 돈다. 두 번째 목록은 읽기·탭 이동에서 뺀다.
// 마우스를 올리거나 키보드 포커스가 들어오면 멈추고, '움직임 줄이기'를 켠 사용자에게는 흐르지 않고 가로로 넘겨 본다.

const CATEGORY_LABEL: Record<Example["category"], string> = {
  가치투자: "가치투자",
  기술분석: "기술분석",
  모멘텀: "모멘텀",
  복합전략: "복합전략",
  ETF: "ETF",
  테마: "테마",
};

export function exampleHref(prompt: string): string {
  return `/?${STRATEGY_PROMPT_PARAM}=${encodeURIComponent(prompt)}&utm_source=landing&utm_medium=example`;
}

function ExampleCard({ example, hidden }: { example: Example; hidden: boolean }) {
  return (
    <a
      href={exampleHref(example.prompt)}
      tabIndex={hidden ? -1 : undefined}
      aria-hidden={hidden || undefined}
      data-example-card
      className="flex h-full w-[300px] shrink-0 flex-col gap-3 rounded-2xl bg-[var(--card-bg)] p-5 text-left transition-colors hover:bg-white/[0.04] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50"
    >
      <span className="w-fit rounded-md bg-white/[0.06] px-2 py-0.5 text-[11px] font-bold text-gray-300">
        {CATEGORY_LABEL[example.category]}
      </span>
      <span className="text-base font-black text-white">{example.title}</span>
      <span className="line-clamp-3 text-xs font-medium leading-6 text-gray-400">{example.prompt}</span>
    </a>
  );
}

// 스타일 문자열에는 따옴표를 쓰지 않는다 — <style> 안의 글자는 서버가 &quot;로 바꿔 보내 하이드레이션이 어긋난다.
const FLOW_CSS = `
.example-flow{overflow:hidden;mask-image:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent);-webkit-mask-image:linear-gradient(90deg,transparent,#000 6%,#000 94%,transparent)}
.example-flow-track{display:flex;width:max-content;animation:example-flow-left 300s linear infinite}
.example-flow:hover .example-flow-track,.example-flow:focus-within .example-flow-track{animation-play-state:paused}
.example-flow-half{display:flex;gap:16px;padding-right:16px}
@keyframes example-flow-left{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@media (prefers-reduced-motion: reduce){
  .example-flow{overflow-x:auto;mask-image:none;-webkit-mask-image:none}
  .example-flow-track{animation:none}
  .example-flow-half[aria-hidden=true]{display:none}
}
`;

export function ExampleFlow() {
  return (
    <div data-testid="example-flow">
      <style>{FLOW_CSS}</style>
      <div className="example-flow" role="region" aria-label="전략 예시 목록">
        <div className="example-flow-track">
          <ul className="example-flow-half list-none">
            {EXAMPLES.map((example) => (
              <li key={example.title}>
                <ExampleCard example={example} hidden={false} />
              </li>
            ))}
          </ul>
          <ul className="example-flow-half list-none" aria-hidden="true">
            {EXAMPLES.map((example) => (
              <li key={`${example.title}-copy`}>
                <ExampleCard example={example} hidden />
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
