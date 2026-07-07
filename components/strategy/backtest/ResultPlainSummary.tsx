// 검증(워크포워드·몬테카를로) 결과 수치를 일상 언어 문장으로 풀어 주는 "쉽게 이해하기" 섹션.
// 모든 문장은 과거 데이터 서술형으로만 작성한다 — 추천/전망/권유 표현 금지(규제 안전 원칙).

interface WalkForwardPlainSummaryInput {
  windows: Array<{ oos_metrics?: Record<string, any>; error?: string }>;
  /** 값 단위는 퍼센트 (예: avg_oos_cagr = 12.3 → 12.3%) */
  aggregate: Record<string, number>;
  walk_forward_efficiency: number;
  wfe_valid?: boolean;
}

interface MonteCarloPlainSummaryInput {
  nIterations: number;
  mode: "returns" | "trades";
  tradeCount?: number;
  /** 값 단위는 비율 (예: median = 0.123 → 12.3%) */
  cagr: { median: number; p05: number };
  mdd: { p95: number };
  probPositiveCagr: number;
  probMddOver30pct: number;
}

const asNumber = (value: unknown): number | null => {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
};

const pct = (value: number, digits = 1) => `${value.toFixed(digits)}%`;
const ratioPct = (value: number, digits = 1) => pct(value * 100, digits);

export function buildWalkForwardPlainSummary(result: WalkForwardPlainSummaryInput): string[] {
  const items: string[] = [];
  const windowCount = result.windows.length;

  items.push(
    `이 검증은 전체 백테스트 기간을 ${windowCount}개 구간으로 나눠, 구간마다 앞부분(학습) 데이터로 설정을 맞춘 뒤 그 설정을 전략이 한 번도 보지 못한 뒷부분(검증) 데이터에 적용해 성과를 확인한 것입니다.`
  );

  const avgCagr = asNumber(result.aggregate.avg_oos_cagr);
  if (avgCagr !== null) {
    items.push(
      avgCagr >= 0
        ? `처음 보는 검증 구간에서 이 전략은 연평균 ${pct(avgCagr)}의 수익을 기록했습니다.`
        : `처음 보는 검증 구간에서 이 전략은 연평균 ${pct(Math.abs(avgCagr))}의 손실을 기록했습니다.`
    );
  }

  const oosCagrs = result.windows
    .map((window) => asNumber(window.oos_metrics?.cagr))
    .filter((value): value is number => value !== null);
  if (oosCagrs.length > 0) {
    const winCount = oosCagrs.filter((value) => value > 0).length;
    items.push(
      `검증 구간 ${oosCagrs.length}개 중 ${winCount}개 구간에서 수익, ${oosCagrs.length - winCount}개 구간에서 손실이 났습니다.`
    );
  }

  if (result.wfe_valid === false) {
    items.push(
      "학습 구간 평균 수익률이 0 이하라서, 학습 대비 검증 성과 비율(WFE)은 계산할 수 없었습니다. 구간별 결과를 직접 확인해 주세요."
    );
  } else {
    const wfe = result.walk_forward_efficiency;
    if (wfe < 0) {
      items.push(
        "학습 구간에서는 수익이 났지만 검증 구간에서는 평균적으로 손실이 났습니다(WFE 음수). 학습 구간에만 잘 맞는 설정이었을 가능성이 있습니다."
      );
    } else {
      items.push(
        `학습 구간에서 낸 성과의 약 ${Math.round(wfe * 100)}%가 처음 보는 검증 구간에서도 유지되었습니다(WFE). 100%에 가까울수록 학습·검증 성과 차이가 작았다는 뜻이고, 낮을수록 특정 구간에만 맞춰진(과최적화) 결과였을 가능성이 있습니다.`
      );
    }
  }

  const avgMdd = asNumber(result.aggregate.avg_oos_maxDrawdown);
  if (avgMdd !== null) {
    items.push(
      `검증 구간에서 계좌는 고점 대비 평균 ${pct(Math.abs(avgMdd))}까지 하락한 적이 있었습니다. 이 전략을 과거에 그대로 운용했다면 중간에 그 정도의 평가손을 겪었다는 뜻입니다.`
    );
  }

  return items;
}

export function buildMonteCarloPlainSummary(result: MonteCarloPlainSummaryInput): string[] {
  const items: string[] = [];
  const iterations = result.nIterations.toLocaleString();

  items.push(
    result.mode === "trades"
      ? `백테스트에서 나온 완결 거래 ${result.tradeCount?.toLocaleString() ?? "-"}건의 수익률을 무작위로 다시 뽑아 ${iterations}가지 시나리오를 만들었습니다. 거래 순서가 달랐다면 결과가 어떻게 달라졌을지 본 것입니다.`
      : `백테스트의 일별 수익률을 무작위로 다시 섞어 ${iterations}가지 시나리오를 만들었습니다. 같은 전략이라도 시장 흐름의 순서가 달랐다면 결과가 어떻게 달라졌을지 본 것입니다.`
  );

  items.push(
    `시나리오의 절반은 연평균 수익률(CAGR)이 ${ratioPct(result.cagr.median)} 이상, 절반은 그 이하로 끝났습니다.`
  );
  items.push(
    `운이 나쁜 편에 속하는 시나리오(하위 5%)에서는 연평균 수익률이 ${ratioPct(result.cagr.p05)}였습니다.`
  );
  items.push(
    `전체 시나리오 중 ${ratioPct(result.probPositiveCagr)}는 수익으로 끝났고, ${ratioPct(1 - result.probPositiveCagr)}는 손실로 끝났습니다.`
  );

  let mddSentence = `계좌가 고점 대비 30% 넘게 하락한 시나리오는 ${ratioPct(result.probMddOver30pct)}였고, 낙폭이 큰 편(상위 5%)의 시나리오에서는 고점 대비 ${ratioPct(result.mdd.p95)}까지 하락했습니다.`;
  if (result.mode === "trades") {
    mddSentence += " (거래 재표본 방식에서는 거래 도중의 낙폭은 반영되지 않습니다.)";
  }
  items.push(mddSentence);

  return items;
}

export default function ResultPlainSummary({ items }: { items: string[] }) {
  if (items.length === 0) return null;

  return (
    <div data-testid="result-plain-summary" className="rounded-xl border border-white/[0.08] p-4">
      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">쉽게 이해하기</p>
      <ul className="mt-3 space-y-2">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm font-bold leading-6 text-gray-300">
            <span aria-hidden className="text-gray-500">·</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
