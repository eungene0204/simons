import { t } from "@/lib/i18n";
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
  blockSize?: number;
  tradeCount?: number;
  /** 값 단위는 비율 (예: median = 0.123 → 12.3%) */
  cagr: { median: number; p05: number };
  mdd: { p95: number };
  probPositiveCagr: number;
  probMddOver30pct: number;
  /**
   * 원래 순서(재표본 안 함) MDD와 그 분포 내 위치. 구버전 저장 결과에는 없을 수 있다.
   * CAGR은 순서와 무관해(성장배수의 곱) 위치를 서술하지 않는다 — 부트스트랩 분포는 관측
   * 평균을 중심으로 만들어져 관측 CAGR이 늘 한가운데에 오므로 "상단 치우침" 해석이 성립하지 않는다.
   */
  observed?: { mdd: number; mddPct: number };
  /** trades 모드의 거래 비용 반영 여부. 구버전엔 없을 수 있다(=gross). */
  tradeCosts?: "net" | "gross";
  /** 낙폭 지속(회복까지) 스텝 분포 — returns=거래일, trades=거래. 구버전엔 없을 수 있다. */
  underwater?: { median: number; p95: number };
  /** 표본 충분성. 구버전엔 없을 수 있다. */
  sufficiency?: { effectiveSamples: number; low: boolean };
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
    t("이 검증은 전체 백테스트 기간을 {0}개 구간으로 나눠, 구간마다 앞부분(학습) 데이터로 설정을 맞춘 뒤 그 설정을 전략이 한 번도 보지 못한 뒷부분(검증) 데이터에 적용해 성과를 확인한 것입니다.", windowCount)
  );

  const avgCagr = asNumber(result.aggregate.avg_oos_cagr);
  if (avgCagr !== null) {
    items.push(
      avgCagr >= 0
        ? t("처음 보는 검증 구간에서 이 전략은 연평균 {0}의 수익을 기록했습니다.", pct(avgCagr))
        : t("처음 보는 검증 구간에서 이 전략은 연평균 {0}의 손실을 기록했습니다.", pct(Math.abs(avgCagr)))
    );
  }

  const oosCagrs = result.windows
    .map((window) => asNumber(window.oos_metrics?.cagr))
    .filter((value): value is number => value !== null);
  if (oosCagrs.length > 0) {
    const winCount = oosCagrs.filter((value) => value > 0).length;
    items.push(
      t("검증 구간 {0}개 중 {1}개 구간에서 수익, {2}개 구간에서 손실이 났습니다.", oosCagrs.length, winCount, oosCagrs.length - winCount)
    );
  }

  if (result.wfe_valid === false) {
    items.push(
      t("학습 구간 평균 수익률이 0 이하라서, 학습 대비 검증 성과 비율(WFE)은 계산할 수 없었습니다. 구간별 결과를 직접 확인해 주세요.")
    );
  } else {
    const wfe = result.walk_forward_efficiency;
    if (wfe < 0) {
      items.push(
        t("학습 구간에서는 수익이 났지만 검증 구간에서는 평균적으로 손실이 났습니다(WFE 음수). 학습 구간에만 잘 맞는 설정이었을 가능성이 있습니다.")
      );
    } else {
      items.push(
        t("학습 구간에서 낸 성과의 약 {0}%가 처음 보는 검증 구간에서도 유지되었습니다(WFE). 100%에 가까울수록 학습·검증 성과 차이가 작았다는 뜻이고, 낮을수록 특정 구간에만 맞춰진(과최적화) 결과였을 가능성이 있습니다.", Math.round(wfe * 100))
      );
    }
  }

  const avgMdd = asNumber(result.aggregate.avg_oos_maxDrawdown);
  if (avgMdd !== null) {
    items.push(
      t("검증 구간에서 계좌는 고점 대비 평균 {0}까지 하락한 적이 있었습니다. 이 전략을 과거에 그대로 운용했다면 중간에 그 정도의 평가손을 겪었다는 뜻입니다.", pct(Math.abs(avgMdd)))
    );
  }

  return items;
}

export function buildMonteCarloPlainSummary(result: MonteCarloPlainSummaryInput): string[] {
  const items: string[] = [];
  const iterations = result.nIterations.toLocaleString();

  items.push(
    result.mode === "trades"
      ? t("백테스트에서 나온 완결 거래 {0}건의 수익률을 무작위로 다시 뽑아 {1}가지 시나리오를 만들었습니다. 거래 순서가 달랐다면 결과가 어떻게 달라졌을지 본 것입니다.", result.tradeCount?.toLocaleString() ?? "-", iterations)
      : t("백테스트의 일별 수익률을 무작위로 다시 섞어 {0}가지 시나리오를 만들었습니다. 같은 전략이라도 시장 흐름의 순서가 달랐다면 결과가 어떻게 달라졌을지 본 것입니다.", iterations)
  );

  items.push(
    t("시나리오의 절반은 연평균 수익률(CAGR)이 {0} 이상, 절반은 그 이하로 끝났습니다.", ratioPct(result.cagr.median))
  );
  items.push(
    t("운이 나쁜 편에 속하는 시나리오(하위 5%)의 연평균 수익률은 {0} 이하였습니다.", ratioPct(result.cagr.p05))
  );
  items.push(
    t("전체 시나리오 중 {0}는 수익으로 끝났고, {1}는 손실로 끝났습니다.", ratioPct(result.probPositiveCagr), ratioPct(1 - result.probPositiveCagr))
  );

  let mddSentence = t("계좌가 고점 대비 30% 넘게 하락한 시나리오는 {0}였고, 낙폭이 큰 편(상위 5%)의 시나리오에서는 고점 대비 {1} 이상 하락했습니다.", ratioPct(result.probMddOver30pct), ratioPct(result.mdd.p95));
  if (result.mode === "trades") {
    mddSentence += t(" (거래 재표본 방식에서는 거래 도중의 낙폭은 반영되지 않습니다.)");
  }
  items.push(mddSentence);

  if (result.observed) {
    const deeperPct = Math.round((1 - result.observed.mddPct) * 100);
    items.push(
      t("재표본하지 않은 원래 순서의 최대 낙폭은 {0}였고, 시나리오 중 {1}%가 이보다 더 깊은 낙폭을 겪었습니다. 낙폭은 수익률이 이어진 순서에 따라 달라지므로, 이 비율이 클수록 원래 순서가 낙폭 면에서 유리한 편이었다는 뜻입니다.", ratioPct(result.observed.mdd), deeperPct)
    );
  }

  if (result.mode === "trades" && result.tradeCosts !== "net") {
    items.push(
      t("이 거래 재표본은 체결가 차액(수수료·거래세 차감 전)으로 계산되어, 비용을 반영한 백테스트 결과보다 수익률이 다소 높게 나올 수 있습니다.")
    );
  }

  if (result.underwater) {
    const unit = result.mode === "trades" ? t("거래") : t("거래일");
    items.push(
      t("한 번 손실을 본 뒤 다시 고점을 회복하기까지 가장 오래 걸린 구간은, 시나리오 중앙값으로 약 {0}{1}, 회복이 더딘 편(상위 5%)에서는 약 {2}{3}였습니다.", Math.round(result.underwater.median), unit, Math.round(result.underwater.p95), unit)
    );
  }

  if (result.mode === "returns" && result.blockSize !== undefined && result.blockSize <= 1) {
    items.push(
      t("이 방식(일별 독립 재표본)은 각 날짜를 서로 무관하게 뽑기 때문에, 며칠씩 이어지는 연속된 시장 흐름(자기상관·변동성 군집·추세)은 반영되지 않습니다. 연속성을 함께 보려면 N일 블록이나 가변 블록 방식을 사용하세요.")
    );
  }

  if (result.sufficiency?.low) {
    items.push(
      t("재표본에 쓰인 독립 단위가 약 {0}개로 많지 않아, 이 분포는 참고용으로 보는 것이 적절합니다. 더 긴 기간이나 더 많은 거래가 쌓일수록 추정이 안정됩니다.", Math.round(result.sufficiency.effectiveSamples))
    );
  }

  return items;
}

export default function ResultPlainSummary({ items }: { items: string[] }) {
  if (items.length === 0) return null;

  return (
    <div data-testid="result-plain-summary">
      <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gray-500">{t("쉽게 이해하기")}</p>
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
