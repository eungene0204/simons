// 연구노트 — 유명 매매기법 10개의 KOSPI·KOSDAQ 최근 3년 백테스트 기록, 계열별 모음(허브) 5편, 종합 1편
// (AEO 설계서 3~6단계, 2026-11-04~05).
//
// 숫자는 손으로 옮기지 않는다 — `classicResults.ts`(scripts/research_classic_to_ts.py가 엔진 결과 JSON에서 생성)만 읽는다.
// 규칙은 실행 전에 `scripts/research_classic_techniques.py`에 고정했고, 앱과 같은 경로(해석된 전략 → 엔진 요청)로 계산했다.
// 모음·종합 글의 요약과 표도 같은 결과에서 만든다. 사람이 쓴 문장은 기록마다의 '결과 해석'과 대조 설명뿐이다.
// 표현은 규제 안전 원칙을 따른다(CLAUDE.md) — 관측된 값만 기록하고 기법의 성립 여부·우열·전망을 말하지 않는다.
// 종목명은 싣지 않는다(엔진 가격 보정 결함 1건의 대조 근거로 종목 코드만 적는다). 순수 데이터 모듈이다(react·next 의존 없음).

import type { GuideArticle, GuideFaq, GuideSection } from "@/lib/guide/articles";
import type { BacktestDataset } from "@/lib/guide/jsonLd";
import { CLASSIC_RESULTS } from "./classicResults";

type Market = "KOSPI" | "KOSDAQ";
type RuleKey = keyof (typeof CLASSIC_RESULTS)["KOSPI"];
type Family = "moving-average" | "oscillator" | "volatility" | "momentum" | "value";

type Result = {
  start: string;
  end: string;
  tradingDays: string;
  endValue: string;
  ret: string;
  cagr: string;
  mdd: string;
  sharpe: string;
  win: string;
  pf: string;
  trades: string;
  hold: string;
  benchLabel: string;
  benchRet: string;
  benchCagr: string;
  below: boolean;
  yearly: readonly (readonly string[])[];
  exits: readonly (readonly string[])[];
  strategyId: string;
  engineVersion: string;
  computedOn: string;
  dataNotes: readonly string[];
  lookupFailures: number;
  startRuns?: readonly (readonly string[])[];
  retRange?: readonly string[];
};

const RESULTS = CLASSIC_RESULTS as unknown as Record<Market, Record<RuleKey, Result>>;
const MARKETS: Market[] = ["KOSPI", "KOSDAQ"];

type Technique = {
  key: RuleKey;
  /** slug 뒷부분 — 기록 slug는 `{시장}-3y-{base}`. */
  base: string;
  family: Family;
  /** 제목·요약에 쓰는 기법 이름. */
  name: string;
  /** 표·모음 글에 쓰는 짧은 이름. */
  short: string;
  /** 요약 괄호 안의 한 줄 규칙. */
  rule: string;
  intro: string[];
  conditions: string[];
  /** 엔진에 넘긴 진입·청산(또는 순위) 조건 — 시장과 무관한 부분. */
  engine: [string, string][];
  /** 체결 방식 설명(기본: 다음 거래일 시가). */
  fill?: string;
  caveats?: string[];
  /** 기법과 이어지는 속설 검증·가이드 글. */
  related: string[];
};

type Report = {
  market: Market;
  key: RuleKey;
  commentary: string[];
  /** 독립 대조 설명(없으면 시장 공통 신호 대조 문장). */
  check?: string;
  caveats?: string[];
};

const PERIOD_LABEL = "최근 3년";
const DEFAULT_FILL = "신호가 나온 다음 거래일 시가에 체결합니다.";
const COST_SETUP =
  "수수료 매수·매도 각 0.015%, 슬리피지 0.05%, 매도 증권거래세는 시행일 기준 법정 세율(0.20%→0.15%)을 반영했습니다. 배당은 배당소득세 15.4%를 뺀 금액을 재투자합니다.";
const TIEBREAK_NOTE =
  "매수 신호가 빈 자리보다 많은 날에는 엔진 기본 규칙에 따라 최근 60거래일 수익률이 높은 종목부터 담습니다. 넓은 유니버스에서는 이미 크게 오른 종목이 먼저 선택되는 구조라 결과에 큰 영향을 줍니다.";
const VB_PRIORITY_NOTE =
  "돌파한 종목이 빈 자리보다 많은 날에는 엔진 기본 규칙에 따라 최근 60거래일 수익률이 높은 종목부터 담습니다. 장중에 어느 종목이 먼저 돌파했는지는 일봉으로 알 수 없어서 실제 매매 순서와 다를 수 있습니다.";

const BENCH_SHORT: Record<Market, string> = { KOSPI: "KODEX 코스피", KOSDAQ: "KODEX KOSDAQ 150" };

function universeNote(market: Market): string {
  return `${market} 상장 보통주 중 그날 상장돼 있던 종목(상장폐지 종목 포함)이 대상이고, 거래대금이 부족한 종목은 엔진의 유동성 기준에서 빠집니다.`;
}

function slugOf(market: Market, t: Technique): string {
  return `${market.toLowerCase()}-3y-${t.base}`;
}

function technique(key: RuleKey): Technique {
  return TECHNIQUES.find((t) => t.key === key)!;
}

function footnote(market: Market, t: Technique, r: Result): string {
  const fill = t.fill ? "돌파가 매수·다음 거래일 시가 매도" : "다음 거래일 시가 체결";
  return `${market}, ${r.start}~${r.end}, ${fill}, 수수료 0.015%·슬리피지 0.05%. 널스탁 백테스트 엔진 v${r.engineVersion}으로 ${r.computedOn}에 계산했습니다.`;
}

function dataset(market: Market, t: Technique, r: Result): BacktestDataset {
  const fill = t.fill ? "돌파가 매수·다음 거래일 시가 매도" : "다음 거래일 시가 체결";
  return {
    name: `${t.name} ${market} ${r.start}~${r.end} 백테스트 결과`,
    description: `${market} 일별 가격 기반, 수수료 0.015%·슬리피지 0.05%·시행일 기준 증권거래세 반영, ${fill}. 널스탁 백테스트 엔진 v${r.engineVersion}으로 ${r.computedOn}에 계산했습니다.`,
    temporalCoverage: `${r.start}/${r.end}`,
    variableMeasured: ["투자 수익률", "CAGR", "최대 낙폭(MDD)", "샤프 비율", "승률", "거래 수", "연도별 수익률", "같은 기간 벤치마크 수익률"],
  };
}

function summary(market: Market, t: Technique, r: Result): string {
  return (
    `${PERIOD_LABEL}(${r.start}~${r.end}) 동안 ${market} 종목에 ${t.name}(${t.rule})을 적용해 백테스트한 결과, ` +
    `투자 수익률은 ${r.ret}, 연평균 수익률(CAGR)은 ${r.cagr}로 같은 기간 ${BENCH_SHORT[market]} 보유(CAGR ${r.benchCagr})보다 ${r.below ? "낮았" : "높았"}습니다. ` +
    `최대낙폭(MDD)은 ${r.mdd}, 승률은 ${r.win}, 총 거래는 ${r.trades}였습니다. ` +
    (r.retRange ? `시작일만 하루씩 바꿔 다섯 번 계산하면 투자 수익률은 ${r.retRange[0]}~${r.retRange[1]}였습니다. ` : "") +
    `수수료 0.015%와 슬리피지 0.05%를 반영한 과거 데이터 기준 결과입니다.`
  );
}

/** 재무 값 필터가 있는 규칙의 데이터 커버리지 — 엔진 결과 경고와 외부 조회 실패 수에서 만든다. */
function dataCaveats(r: Result): string[] {
  const out: string[] = [];
  if (r.dataNotes.length) {
    out.push(`재무 값이 없는 종목은 해당 조건에서 빠졌습니다. 엔진이 결과와 함께 보고한 내용: ${r.dataNotes.join(" ")}`);
  }
  if (r.lookupFailures > 0) {
    out.push(
      `계산 중 외부 재무 데이터 조회가 실패해 조건에서 빠진 종목이 ${r.lookupFailures}개 있었습니다. 다시 계산하면 이 종목들이 포함되는지에 따라 결과가 조금 달라질 수 있습니다.`,
    );
  }
  return out;
}

function engineRows(market: Market, t: Technique): [string, string][] {
  return [
    ["유니버스", `${market.toLowerCase()} (시점별 구성·상장폐지 포함)`],
    ["기간", "2023-11-03 ~ 2026-11-03"],
    ...t.engine,
    ["체결·비용", "next_open · fee_rate 0.00015 · slippage_rate 0.0005"],
  ];
}

// 2026-11-08 사용자 지시: 질문의 표현을 글마다 다르게. 모두 과거형이고 60자 안에 든다(notes.test).
const REPORT_TITLE_PATTERNS: ((name: string, market: string) => string)[] = [
  (name, market) => `${name}, ${market} 백테스트하면 수익이 났을까?`,
  (name, market) => `${name}, ${market} 수익률은 얼마였을까?`,
  (name, market) => `${name}의 최대 낙폭은 얼마나 컸을까? ${market} 백테스트`,
  (name, market) => `${name}을 ${market} 데이터로 시험한 결과는 어땠을까?`,
  (name, market) => `${name}의 승률은 몇 퍼센트였을까? ${market} 백테스트`,
  (name, market) => `${market} 백테스트, ${name}은 벤치마크와 얼마나 달랐을까?`,
  (name, market) => `${name}의 매매 횟수와 손익은 어땠을까? ${market} 백테스트`,
];

function buildReport(rep: Report, index: number): GuideArticle {
  const t = technique(rep.key);
  const r = RESULTS[rep.market][rep.key];
  const m = rep.market;
  const bench = BENCH_SHORT[m];
  const note = footnote(m, t, r);
  const sections: GuideSection[] = [
    { heading: "검증한 기법", paragraphs: t.intro },
    {
      heading: "규칙과 설정",
      paragraphs: [
        "결과를 보기 전에 아래 규칙을 정해 두고 한 번에 계산했습니다. 같은 이름의 기법이라도 기간·청산 규칙·종목 수를 다르게 정하면 결과가 달라집니다.",
      ],
      bullets: [
        ...t.conditions,
        universeNote(m),
        `시작 자금 1,000만 원, ${t.fill ?? DEFAULT_FILL}`,
        COST_SETUP,
        "손절·익절·트레일링 스톱은 쓰지 않았습니다.",
      ],
    },
    {
      heading: "핵심 지표",
      paragraphs: [
        `${r.start}~${r.end}(${r.tradingDays}) 구간의 값입니다. 벤치마크는 같은 기간 ${bench}를 사서 보유한 결과입니다. 전략과 벤치마크는 보유 종목 구성과 규칙이 다르므로 표의 차이는 우열을 뜻하지 않습니다.`,
      ],
      table: {
        caption: `${t.name} — ${m} ${PERIOD_LABEL} 백테스트 결과`,
        headers: ["지표", "전략", `${bench} 보유`],
        rows: [
          ["투자 수익률", r.ret, r.benchRet],
          ["CAGR", r.cagr, r.benchCagr],
          ["최대 낙폭(MDD)", r.mdd, "—"],
          ["샤프 비율", r.sharpe, "—"],
          ["승률", r.win, "—"],
          ["손익비", r.pf, "—"],
          ["거래 수", r.trades, "—"],
          ["평균 보유", r.hold, "—"],
          ["끝 자산(시작 1,000만 원)", r.endValue, "—"],
        ],
        footnote: note,
      },
    },
    {
      heading: "연도별 수익률",
      paragraphs: [
        `해마다 연말 자산을 직전 연말(첫해는 시작 자금)과 비교한 값입니다. ${r.start.slice(0, 4)}년과 ${r.end.slice(0, 4)}년은 구간에 포함된 기간만의 수익률입니다.`,
      ],
      table: {
        caption: `${t.name} — ${m} 연도별 수익률`,
        headers: ["연도", "전략", `${bench} 보유`],
        rows: r.yearly.map((row) => [...row]),
        footnote: note,
      },
    },
  ];

  if (r.startRuns && r.retRange) {
    sections.push({
      heading: "시작일을 하루씩 바꿔 본 결과",
      paragraphs: [
        `종료일은 그대로 두고 시작일만 하루씩 옮겨 같은 규칙을 다시 계산했습니다. 투자 수익률은 ${r.retRange[0]}에서 ${r.retRange[1]} 사이였습니다. 보유 종목 수가 정해져 있고 대상 종목이 많은 규칙은 첫날 어떤 종목을 샀는지에 따라 이후 매매가 통째로 달라질 수 있어서, 한 번의 계산값만으로 읽지 않도록 함께 싣습니다.`,
      ],
      table: {
        caption: `${t.name} — ${m} 시작일별 결과(종료일 ${r.end} 고정)`,
        headers: ["시작일", "투자 수익률", "CAGR"],
        rows: r.startRuns.map((row) => [...row]),
        footnote: note,
      },
    });
  }

  sections.push(
    {
      heading: "청산 내역",
      paragraphs: ["거래가 끝난 이유별 건수입니다. 기간 종료 정산은 마지막 날 보유 중이던 종목을 그날 가격으로 평가해 닫은 것입니다."],
      table: { caption: `${t.name} — ${m} 청산 사유별 건수`, headers: ["청산 사유", "건수"], rows: r.exits.map((row) => [...row]), footnote: note },
    },
    {
      heading: "엔진에 넘긴 조건",
      paragraphs: [
        `같은 결과를 다시 계산할 수 있도록 엔진 조건을 그대로 적습니다. 전략 식별값은 ${r.strategyId.slice(0, 16)}입니다. 데이터 출처와 비용·체결 가정은 백테스트 방법론 페이지에 정리했습니다.`,
      ],
      table: { caption: `${t.name} — ${m} 엔진 조건`, headers: ["항목", "값"], rows: engineRows(m, t), footnote: note },
    },
    {
      heading: "직접 다시 계산해 대조한 것",
      paragraphs: [
        "엔진 결과를 그대로 믿지 않고, 가격·재무 데이터 원본에서 신호와 선택 종목을 독립적으로 다시 계산해 대조했습니다.",
      ],
      bullets: rep.check ? [rep.check, PRICE_CHECK[m]] : [SIGNAL_CHECK[m], PRICE_CHECK[m]],
    },
    { heading: "결과 해석", paragraphs: rep.commentary },
    {
      heading: "읽을 때 주의할 점",
      paragraphs: [
        "이 기록은 한 유니버스·한 기간·한 가지 파라미터 조합의 과거 시뮬레이션 결과입니다. 3년은 시장 국면 한두 개를 담는 짧은 구간이라, 다른 기간이나 값에서는 다른 결과가 나올 수 있습니다. 미래 수익은 보장되지 않습니다.",
        ...(t.caveats ?? []),
        ...(rep.caveats ?? []),
        ...dataCaveats(r),
      ],
    },
  );

  const faq: GuideFaq[] = [
    {
      question: `${t.name}은 ${m}에서 효과가 있었나요?`,
      answer: `이 기록의 설정에서는 ${r.start}~${r.end} 동안 투자 수익률 ${r.ret}, CAGR ${r.cagr}, 최대 낙폭 ${r.mdd}였고 같은 기간 ${bench} 보유는 ${r.benchRet}였습니다. 한 기간·한 설정의 과거 값이며 기법 전체의 효과를 판정하지 않습니다.`,
    },
    {
      question: "같은 기법인데 다른 곳의 백테스트 결과와 숫자가 다른 이유는 무엇인가요?",
      answer:
        "기간, 대상 종목, 보유 종목 수, 청산 규칙, 수수료·슬리피지 가정, 상장폐지 종목 포함 여부가 다르면 결과가 달라집니다. 이 기록의 가정은 본문 '규칙과 설정'과 백테스트 방법론 페이지에 모두 적었습니다.",
    },
    {
      question: "표의 벤치마크와의 차이는 무엇을 뜻하나요?",
      answer: `같은 기간 ${bench}를 보유한 결과(${r.benchRet})와 전략 결과(${r.ret})를 표시값 그대로 비교하는 용도입니다. 전략은 조건에 맞는 일부 종목만 보유하고 ETF는 지수 전체를 보유하므로 구성과 규칙이 달라 우열을 가리는 값은 아닙니다.`,
    },
  ];

  const other = MARKETS.find((x) => x !== m)!;
  return {
    slug: slugOf(m, t),
    title: REPORT_TITLE_PATTERNS[index % REPORT_TITLE_PATTERNS.length](t.name, `${m} ${PERIOD_LABEL}`),
    description: `${t.short} 전략을 ${m} ${r.start}~${r.end}에 적용한 백테스트: 투자 수익률 ${r.ret}, CAGR ${r.cagr}, MDD ${r.mdd}, 거래 ${r.trades}. 같은 기간 ${bench} 보유 ${r.benchRet}.`,
    summary: summary(m, t, r),
    published: REPORT_PUBLISHED[`${m}:${rep.key}`] ?? "2026-11-05",
    updated: "2026-11-05",
    sections,
    related: [hubSlug(t.family), slugOf(other, t), ...t.related],
    faq,
  };
}

// 첫 공개일 — 2026-11-04에 먼저 올린 KOSPI 9편. 나머지는 2026-11-05.
const REPORT_PUBLISHED: Partial<Record<string, string>> = Object.fromEntries(
  (
    [
      "golden_cross_5_20",
      "ma_alignment_5_20_60",
      "rsi_30_70",
      "macd_signal_cross",
      "bollinger_lower",
      "high_52w_hold_3m",
      "dual_momentum_12m",
      "low_per_pbr_20",
      "magic_formula_20",
    ] as RuleKey[]
  ).map((key) => [`KOSPI:${key}`, "2026-11-04"]),
);

const SIGNAL_CHECK: Record<Market, string> = {
  KOSPI:
    "매수 기록(매도 신호가 있는 규칙은 매도 신호 기록도)에서 무작위로 30건씩 골라 가격 데이터로 지표를 다시 계산해, 체결일 전 거래일에 규칙의 조건이 성립했는지 확인했습니다. 표본 전부가 규칙대로였습니다.",
  KOSDAQ:
    "매수 기록(매도 신호가 있는 규칙은 매도 신호 기록도)에서 무작위로 30건씩 골라 가격 데이터로 지표를 다시 계산해, 체결일 전 거래일에 규칙의 조건이 성립했는지 확인했습니다. 여섯 기법의 표본 330건 중 329건이 규칙대로였고, 나머지 1건은 상장 1년이 안 된 종목이 상장 이후 최고가를 넘은 날을 52주 신고가로 본 경우였습니다(엔진 기본 동작).",
};
const PRICE_CHECK: Record<Market, string> = {
  KOSPI:
    "거래마다 엔진의 체결 수익률을 원본 시가로 다시 계산한 수익률과 비교했습니다. 대부분 1%p 안에서 같았습니다. 오래 보유한 거래의 작은 차이는 세후 배당 재투자분이었고(예: 배당 1회가 있었던 거래에서 원본 25.35%에 세후 배당을 더하면 엔진 값 30.39%와 일치), 크게 다른 몇 건은 거래정지 뒤 주식 분할·병합으로 가격 단위가 정확히 5배 바뀐 종목을 엔진이 같은 비율로 보정한 경우였습니다.",
  KOSDAQ:
    "거래마다 엔진의 체결 수익률을 원본 시가로 다시 계산한 수익률과 비교했습니다. 대부분 1%p 안에서 같았습니다. 차이가 난 거래는 세후 배당 재투자분, 주식 병합(예: 10주를 1주로)으로 가격 단위가 바뀐 종목을 엔진이 같은 비율로 보정한 경우였습니다.",
};

const VB_CHECK: Record<Market, string> = {
  KOSPI:
    "매수·매도 기록 500쌍을 무작위로 골라 원본 가격으로 돌파가(시가 + 전일 고저폭 × 0.5)를 다시 계산했습니다. 498쌍이 '그날 고가가 돌파가에 닿았고, 돌파가에 사서 다음 거래일 시가에 판' 기록과 일치했습니다(그중 234쌍은 배당·분할 보정으로 매수가·매도가가 같은 비율로 달라져 수익률은 같은 경우). 나머지 2쌍은 12월 말에 산 거래로, 매수일과 매도일 사이 가격 보정 비율이 달라 대조 기준(0.2%)을 벗어났습니다.",
  KOSDAQ:
    "매수·매도 기록 500쌍을 무작위로 골라 원본 가격으로 돌파가(시가 + 전일 고저폭 × 0.5)를 다시 계산했습니다. 495쌍이 '그날 고가가 돌파가에 닿았고, 돌파가에 사서 다음 거래일 시가에 판' 기록과 일치했습니다(그중 129쌍은 배당·분할 보정으로 매수가·매도가가 같은 비율로 달라져 수익률은 같은 경우). 나머지 5쌍은 매수 다음 날이 거래정지(거래량 0)여서 그다음 거래일 시가에 판 경우였습니다.",
};

const RANKING_CHECK: Record<Market, Partial<Record<RuleKey, string>>> = {
  KOSPI: {
    dual_momentum_12m:
      "리밸런싱일 여섯 번을 골라 KOSPI 전 종목의 전일 기준 12개월 수익률을 다시 계산했습니다. 매수한 종목은 모두 수익률이 0% 초과인 종목 가운데 상위권(가장 낮은 순위 11위)이었습니다. 10위를 넘는 순위는 거래대금이 부족한 종목이 유동성 기준에서 빠져 다음 순위가 채운 경우입니다.",
    low_per_pbr_20:
      "리밸런싱일 여섯 번을 골라 PER·PBR이 모두 양수인 KOSPI 종목의 전일 기준 순위를 다시 계산했습니다. 매수한 종목은 모두 두 순위 평균의 상위권(가장 낮은 순위 21위)이었고, 20위를 넘는 순위는 유동성 기준에서 빠진 종목을 다음 순위가 채운 경우입니다.",
    magic_formula_20:
      "리밸런싱일 다섯 번을 골라 EV/EBIT이 양수인 KOSPI 종목의 전일 기준 ROIC 순위·EV/EBIT 순위를 다시 계산했습니다. 매수한 종목은 모두 두 순위 평균의 상위 20위 안이었습니다.",
  },
  KOSDAQ: {
    dual_momentum_12m:
      "리밸런싱일 여섯 번을 골라 KOSDAQ 전 종목의 전일 기준 12개월 수익률을 다시 계산했습니다. 매수한 종목은 모두 수익률이 0% 초과인 종목 가운데 상위 10위 안이었습니다.",
    low_per_pbr_20:
      "리밸런싱일 여섯 번을 골라 PER·PBR이 모두 양수인 KOSDAQ 종목의 전일 기준 순위를 다시 계산했습니다. 매수한 종목은 모두 두 순위 평균의 상위권(가장 낮은 순위 22위)이었고, 20위를 넘는 순위는 유동성 기준에서 빠진 종목을 다음 순위가 채운 경우입니다.",
    magic_formula_20:
      "리밸런싱일 다섯 번을 골라 EV/EBIT이 양수인 KOSDAQ 종목의 전일 기준 ROIC 순위·EV/EBIT 순위를 다시 계산했습니다. 매수한 종목은 모두 두 순위 평균의 상위권(가장 낮은 순위 21위)이었고, 20위를 넘는 순위는 유동성 기준에서 빠진 종목을 다음 순위가 채운 경우입니다.",
  },
};

const GUIDE_READ = "how-to-read-backtest-results";
const GUIDE_PIT = "backtest-pitfalls";
const GUIDE_COST = "backtest-trading-costs";
const GUIDE_REBAL = "backtest-rebalancing";

const TECH = (entry: string, exit: string): [string, string][] => [
  ["진입", entry],
  ["청산", exit],
  ["보유", "최대 10종목, 종목당 자본의 10%"],
];
const RANK = (filters: string, ranking: string, holding: string, rebal: string): [string, string][] => [
  ["후보 필터", filters],
  ["순위", ranking],
  ["보유", holding],
  ["리밸런싱", rebal],
];

const NEW_LISTING_HIGH =
  "상장 1년이 안 된 종목은 상장 이후 최고가를 넘은 날을 신고가로 봤습니다(엔진 기본 동작 — 직전 252거래일이 다 차지 않아도 있는 기간의 최고가와 비교합니다).";
const DISCLOSURE_LAG = "재무 값은 공시가 공개된 날부터 씁니다(공개일을 모르면 결산일 90일 뒤부터).";

const TECHNIQUES: Technique[] = [
  {
    key: "golden_cross_5_20",
    base: "golden-cross-5-20",
    family: "moving-average",
    name: "골든크로스(5일·20일 이동평균) 전략",
    short: "골든크로스(5·20)",
    rule: "5일선이 20일선을 위로 넘으면 매수, 아래로 넘으면 매도",
    intro: [
      "골든크로스는 짧은 기간 이동평균선이 긴 기간 이동평균선을 아래에서 위로 넘는 것을 말합니다. 반대로 위에서 아래로 넘는 것을 데드크로스라고 합니다. 5일선과 20일선 조합은 개인 투자자에게 가장 널리 알려진 형태입니다.",
    ],
    conditions: ["매수: 종가 기준 5일 이동평균이 20일 이동평균을 위로 넘은 날(골든크로스)", "매도: 5일 이동평균이 20일 이동평균을 아래로 넘은 날(데드크로스)", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH("ma_crossover(shortMA=5, longMA=20, 골든크로스)", "ma_crossover(shortMA=5, longMA=20, 데드크로스)"),
    related: ["cost-sensitivity-ma-crossover", "myth-09-ma-5-20-cross", GUIDE_READ],
  },
  {
    key: "ma_alignment_5_20_60",
    base: "ma-alignment-5-20-60",
    family: "moving-average",
    name: "이동평균 정배열(5·20·60일) 전략",
    short: "정배열(5·20·60)",
    rule: "5일선>20일선>60일선 정배열일 때 매수, 5일선이 20일선 아래로 내려가면 매도",
    intro: [
      "정배열은 짧은 이동평균선이 위에, 긴 이동평균선이 아래에 차례로 놓인 상태를 말합니다. 가격이 최근으로 올수록 높아졌다는 뜻이라 상승 추세의 모양으로 흔히 설명됩니다. 여기서는 5일·20일·60일 세 선의 정배열을 썼습니다.",
    ],
    conditions: ["매수: 5일 이동평균 ≥ 20일 이동평균, 20일 이동평균 ≥ 60일 이동평균이 함께 성립하는 날(교차한 날만이 아니라 정배열인 동안 계속 후보)", "매도: 5일 이동평균이 20일 이동평균을 아래로 넘은 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH("ma_crossover(5, 20, mode=above) AND ma_crossover(20, 60, mode=above)", "ma_crossover(shortMA=5, longMA=20, 데드크로스)"),
    related: ["myth-12-above-ma60", GUIDE_READ],
  },
  {
    key: "rsi_30_70",
    base: "rsi-30-70",
    family: "oscillator",
    name: "RSI 30 이하 매수·70 이상 매도 전략",
    short: "RSI 30/70",
    rule: "14일 RSI가 30 이하이면 매수, 70 이상이면 매도",
    intro: [
      "RSI(상대강도지수)는 일정 기간 오른 폭과 내린 폭을 비교해 0~100 사이 값으로 나타낸 지표입니다. 흔히 30 이하를 과매도, 70 이상을 과매수 구간이라고 부르며, 과매도에서 사서 과매수에서 파는 규칙이 널리 알려져 있습니다.",
    ],
    conditions: ["매수: 14일 RSI가 30 이하인 날", "매도: 14일 RSI가 70 이상인 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH("rsi(period=14, <= 30)", "rsi(period=14, >= 70)"),
    related: ["myth-04-rsi-oversold", GUIDE_READ],
  },
  {
    key: "macd_signal_cross",
    base: "macd-signal-cross",
    family: "oscillator",
    name: "MACD 시그널 교차 전략",
    short: "MACD 교차",
    rule: "MACD선이 시그널선을 위로 넘으면 매수, 아래로 넘으면 매도",
    intro: [
      "MACD는 12일 지수이동평균에서 26일 지수이동평균을 뺀 값이고, 시그널선은 MACD의 9일 지수이동평균입니다. MACD선이 시그널선을 위로 넘는 것을 매수 신호로, 아래로 넘는 것을 매도 신호로 쓰는 방법이 가장 흔합니다.",
    ],
    conditions: ["매수: MACD(12, 26)가 시그널선(9)을 위로 넘은 날", "매도: MACD가 시그널선을 아래로 넘은 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH("macd(12, 26, 9, mode=crossover, 상향)", "macd(12, 26, 9, mode=crossover, 하향)"),
    related: ["myth-05-macd-golden-cross", GUIDE_COST],
  },
  {
    key: "volatility_breakout_k05",
    base: "volatility-breakout-k05",
    family: "volatility",
    name: "변동성 돌파(k=0.5) 전략",
    short: "변동성 돌파(k=0.5)",
    rule: "그날 고가가 시가 + 전일 고저폭 × 0.5를 넘으면 그 가격에 매수, 다음 거래일 시가에 매도",
    intro: [
      "변동성 돌파는 래리 윌리엄스가 소개한 단기 매매 규칙입니다. 전날 고가와 저가의 차이(고저폭)에 k를 곱한 만큼 오늘 시가보다 오르면 그 순간 사고, 다음 날 시가에 팝니다. 국내에서는 k=0.5가 가장 널리 알려져 있습니다.",
      "장중에 돌파 가격으로 사야 해서 '다음 날 시가 체결'만으로는 계산할 수 없습니다. 널스탁 엔진 v16.46의 변동성 돌파 체결(그날 고가가 돌파가에 닿으면 돌파가에 체결)로 계산했습니다.",
    ],
    conditions: [
      "매수: 그날 고가가 '시가 + 전일 (고가 − 저가) × 0.5'(돌파가)에 닿으면 돌파가에 매수합니다(시가가 이미 넘었으면 시가). 다른 매수 조건은 없고 거래 가능한 모든 종목이 후보입니다.",
      "매도: 매수 다음 거래일 시가(그날 거래정지면 그다음 거래일 시가)",
      "최대 10종목, 종목당 자본의 10%",
      VB_PRIORITY_NOTE,
    ],
    engine: TECH("없음 — 거래 가능한 모든 종목이 후보", "volatility_breakout_k=0.5 (돌파가 매수 · 다음 거래일 시가 매도)"),
    fill: "매수는 돌파가, 매도는 다음 거래일 시가에 체결합니다.",
    caveats: [
      "돌파가에 정확히 체결된다고 가정했습니다. 실제로는 돌파 순간 호가가 비어 더 높은 가격에 체결되거나, 상한가에 묶여 체결되지 않을 수 있습니다(시가·고가·저가·종가가 모두 같은 상한가 봉에서도 체결된 것으로 계산됩니다).",
      "같은 날 판 종목은 그날 다시 사지 않습니다(일봉 엔진의 한계). 전날 거래정지였던 종목은 고저폭을 알 수 없어 사지 않습니다.",
      "k를 시장 상황에 맞춰 바꾸거나 이동평균 필터를 함께 쓰는 변형도 많지만, 여기서는 k=0.5 하나와 필터 없이 계산했습니다.",
    ],
    related: ["myth-01-breakout-chasing", GUIDE_COST],
  },
  {
    key: "bollinger_lower",
    base: "bollinger-lower",
    family: "volatility",
    name: "볼린저밴드 하단 매수 전략",
    short: "볼린저밴드 하단",
    rule: "종가가 볼린저밴드 하단 이하이면 매수, 상단 이상이면 매도",
    intro: [
      "볼린저밴드는 20일 이동평균을 중심으로 위아래에 표준편차의 2배만큼 띄운 띠입니다. 가격이 하단 밖으로 나가면 평소보다 많이 내려간 것으로 보고 사는 규칙이 널리 알려져 있습니다.",
    ],
    conditions: ["매수: 종가가 볼린저밴드(20일, 표준편차 2배) 하단 이하인 날", "매도: 종가가 상단 이상인 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH("bollinger_bands(20, 2, 종가 ≤ 하단)", "bollinger_bands(20, 2, 종가 ≥ 상단)"),
    related: ["myth-08-bollinger-lower", GUIDE_READ],
  },
  {
    key: "high_52w_hold_3m",
    base: "52-week-high",
    family: "momentum",
    name: "52주 신고가 매수 전략",
    short: "52주 신고가",
    rule: "고가가 직전 252거래일 최고가를 넘으면 매수, 63거래일 보유 후 매도",
    intro: [
      "52주 신고가 매수는 주가가 지난 1년 중 가장 높은 가격을 넘어설 때 사는 모멘텀 계열 규칙입니다. 여기서는 1년을 252거래일로, 보유 기간을 약 3개월(63거래일)로 정했습니다.",
    ],
    conditions: ["매수: 그날 고가가 직전 252거래일의 최고가를 넘은 날", "매도: 매수 후 63거래일이 지나면(매도 신호 없음)", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH("breakout(lookbackPeriod=252, 고가 기준 상향)", "max_holding_days=63"),
    caveats: [NEW_LISTING_HIGH],
    related: ["myth-15-52week-low", GUIDE_PIT],
  },
  {
    key: "dual_momentum_12m",
    base: "dual-momentum-12m",
    family: "momentum",
    name: "듀얼 모멘텀(12개월) 전략",
    short: "듀얼 모멘텀(12개월)",
    rule: "매달 12개월 수익률 상위 10종목 중 수익률이 0% 초과인 종목 보유",
    intro: [
      "듀얼 모멘텀은 다른 자산보다 많이 오른 것을 고르는 상대 모멘텀과, 스스로 올랐는지 보는 절대 모멘텀을 함께 쓰는 방법입니다. 원래는 주식·채권 같은 자산군 사이에서 쓰지만, 여기서는 개별 종목에 적용했습니다.",
    ],
    conditions: ["매달 첫 거래일에 최근 252거래일 수익률 순위 상위 10종목을 고릅니다(상대 모멘텀).", "그중 수익률이 0% 이하인 종목은 고르지 않고 그 자리는 현금으로 둡니다(절대 모멘텀).", "종목당 자본의 10%"],
    engine: RANK("없음", "return(lookback=252일) 상위 · absolute_momentum_threshold_pct=0", "10종목, 종목당 10%", "monthly(매달 첫 거래일)"),
    caveats: ["절대 모멘텀의 기준을 무위험 금리가 아니라 0%로 단순화했습니다. 원래 방법과 다릅니다."],
    related: ["rebalancing-period-momentum-ranking", GUIDE_REBAL],
  },
  {
    key: "low_per_pbr_20",
    base: "low-per-pbr-20",
    family: "value",
    name: "저PER·저PBR 20종목 전략",
    short: "저PER·저PBR 20",
    rule: "분기마다 PER·PBR 순위 평균 상위 20종목 보유",
    intro: [
      "PER(주가수익비율)과 PBR(주가순자산비율)이 낮은 종목은 이익이나 자산에 비해 주가가 낮다고 보고 사는 가치 투자 규칙입니다. 두 지표의 순위를 합쳐 고르는 방식이 흔히 쓰입니다.",
    ],
    conditions: ["후보: PER과 PBR이 모두 0보다 큰 종목(적자·자본잠식 종목 제외)", "분기 첫 거래일에 PER 낮은 순위와 PBR 낮은 순위를 평균해 상위 20종목을 고릅니다.", "종목당 자본의 5%"],
    engine: RANK("per > 0 AND pbr > 0", "composite(per 낮은 순, pbr 낮은 순, 동일 가중)", "20종목, 종목당 5%", "quarterly(분기 첫 거래일)"),
    caveats: [DISCLOSURE_LAG],
    related: ["myth-02-low-per", GUIDE_REBAL],
  },
  {
    key: "magic_formula_20",
    base: "magic-formula-20",
    family: "value",
    name: "마법공식(ROIC·EV/EBIT) 전략",
    short: "마법공식",
    rule: "분기마다 ROIC 높은 순위·EV/EBIT 낮은 순위 평균 상위 20종목 보유",
    intro: [
      "마법공식은 조엘 그린블라트가 소개한 방법으로, 자본 대비 이익을 잘 내는 회사(높은 ROIC)를 이익 대비 싼 가격(낮은 EV/EBIT)에 사는 규칙입니다. 두 순위를 합쳐 상위 종목을 고릅니다.",
    ],
    conditions: ["후보: EV/EBIT이 0보다 큰 종목(영업이익 적자 제외)", "분기 첫 거래일에 ROIC 높은 순위와 EV/EBIT 낮은 순위를 평균해 상위 20종목을 고릅니다.", "종목당 자본의 5%"],
    engine: RANK("ev_ebit > 0", "composite(roic 높은 순, ev_ebit 낮은 순, 동일 가중)", "20종목, 종목당 5%", "quarterly(분기 첫 거래일)"),
    caveats: [
      "원래 방법은 1년마다 교체하고 금융·유틸리티 업종을 빼지만, 여기서는 분기마다 교체했고 업종을 빼지 않았습니다.",
      DISCLOSURE_LAG,
    ],
    related: ["myth-06-quality-hold", GUIDE_REBAL],
  },
];

const REPORTS: Report[] = [
  // ── KOSPI ──
  {
    market: "KOSPI",
    key: "golden_cross_5_20",
    commentary: [
      "거래는 508회, 평균 보유 기간은 14일로 매매가 잦았고 승률 26.8%, 손익비 0.78이었습니다. 연도별로는 2024년 −21.0%, 2025년 −32.5%였는데, 2025년은 같은 기간 KODEX 코스피 보유가 +82.7%였던 해입니다.",
      "손실이 가장 컸던 거래 10건 중 8건은 매수 전 5거래일 안에 상한가(+30%)가 있었던 종목이었습니다. 신호가 빈 자리보다 많은 날 최근 60거래일 수익률이 높은 종목부터 담는 엔진 기본 규칙 때문에, 이미 크게 오른 종목이 먼저 선택되는 구조였습니다. 시작일에 따라 결과가 −72.77%까지 벌어졌다는 점도 함께 읽어야 합니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "ma_alignment_5_20_60",
    commentary: [
      "거래는 460회, 평균 보유 기간은 14일, 승률 24.8%, 손익비 0.59였습니다. 2024년 한 해에 −61.9%를 기록했고, KODEX 코스피 보유가 +82.7%였던 2025년에도 +4.5%였습니다.",
      "정배열인 동안 계속 매수 후보가 되므로 후보가 매우 많았고, 그중 최근 60거래일 수익률이 높은 종목부터 담는 엔진 기본 규칙이 적용됐습니다. 시작일을 바꿔도 −74.47%~−76.45%로 결과가 거의 같아, 한 번의 계산값이 우연에 크게 좌우된 경우는 아니었습니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "rsi_30_70",
    commentary: [
      "거래는 67회, 평균 보유 기간은 108일로 다른 기술적 규칙보다 훨씬 길었습니다. RSI가 70까지 올라야 팔기 때문에 매수 후 오래 기다린 거래가 많았고, 마지막 날까지 보유 중이던 종목이 9개였습니다. 승률은 62.7%, 손익비는 1.36이었습니다.",
      "이 기록에서 가장 크게 읽어야 할 것은 시작일 민감도입니다. 2023-11-03에 시작하면 +21.89%였지만 하루씩 늦춘 나머지 네 번은 −2.21%~−9.34%로 모두 손실이었습니다. 거래 수가 적고 보유가 길어서, 처음 산 종목이 달라지면 이후 결과가 크게 달라지는 구조입니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "macd_signal_cross",
    commentary: [
      "거래는 798회, 평균 보유 기간은 9일, 승률 28.1%, 손익비 0.79였습니다. 연도별로는 2025년 −27.2%, 2026년 −51.1%였습니다.",
      "보유가 짧고 매매가 잦아 거래 비용이 반복해서 쌓이는 구조입니다. 시작일을 바꿔도 −65.15%~−68.86%로 결과가 비슷했습니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "volatility_breakout_k05",
    check: VB_CHECK.KOSPI,
    commentary: [
      "거래는 6,139회로 거의 매 거래일 10종목을 사고팔았고, 평균 보유 기간은 1일이었습니다. 승률 41.0%, 손익비 0.83으로 이긴 거래의 이익 합계가 진 거래의 손실 합계보다 작았습니다. 연도별로는 2024년 −56.5%, 2025년 −31.8%, 2026년 −47.9%로 매해 손실이었고, 같은 기간 KODEX 코스피 보유는 −5.7%, +82.7%, +35.0%였습니다.",
      "한 번 사고팔 때마다 수수료(0.015%×2)·슬리피지(0.05%×2)·거래세(0.15~0.20%)를 합쳐 약 0.3%가 들고, 이 비용이 6,139번 반복됐습니다. 돌파한 종목이 빈 자리보다 많았던 날이 728거래일로 거의 매일이었고, 그날은 최근 60거래일 수익률이 높은 종목부터 담았습니다. 시작일을 바꿔도 결과가 거의 같았습니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "bollinger_lower",
    commentary: [
      "거래는 149회, 평균 보유 기간은 49일, 승률 51.0%, 손익비 0.85였습니다. 이긴 거래와 진 거래의 수는 비슷했지만 진 거래의 손실 합계가 더 컸습니다. 연도별로는 2023년(11~12월) +9.6%, 2025년 +9.4%, 2024년 −9.8%, 2026년 −20.1%였습니다.",
      "시작일에 따라 −13.54%~−23.04%로 바뀌었고, 2023-11-03에 시작한 경우가 다섯 번 중 손실이 가장 작았습니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "high_52w_hold_3m",
    commentary: [
      "거래는 118회, 평균 보유 기간은 60일, 승률 33.1%, 손익비 0.87이었습니다. 연도별 편차가 커서 2024년 −29.4%, 2025년 +45.2%, 2026년 −18.9%였습니다.",
      "시작일에 따라 −20.79%~−43.21%로 결과가 크게 갈렸습니다. 2023-11-03에 시작한 경우가 다섯 번 중 손실이 가장 작았고, 나머지 넷 중 셋은 −42%~−43% 수준이었습니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "dual_momentum_12m",
    check: RANKING_CHECK.KOSPI.dual_momentum_12m,
    commentary: [
      "투자 수익률은 +90.13%였지만 최대 낙폭도 −58.90%로 컸습니다. 리밸런싱은 매달 이뤄졌고 평균 보유 기간은 66일, 승률 61.2%, 손익비 1.34였습니다. 연도별로는 2024년 +18.9%(KODEX 코스피 보유 −5.7%), 2025년 +51.1%(같은 기간 +82.7%), 2026년 +3.3%(같은 기간 +35.0%)였습니다.",
      "시작일을 바꾸면 +65.41%~+90.13%였고, 다섯 번 모두 이익이었지만 같은 기간 KODEX 코스피 보유(+164.90%)보다는 낮았습니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "low_per_pbr_20",
    check: RANKING_CHECK.KOSPI.low_per_pbr_20,
    commentary: [
      "투자 수익률 +31.18%, 최대 낙폭 −27.64%였고, 분기마다 교체해 거래는 84회, 평균 보유 기간은 170일이었습니다. 승률 58.3%, 손익비 1.96이었습니다. 수익의 대부분은 2025년(+41.2%)에 났고 2024년은 −0.6%, 2026년은 −7.8%였습니다.",
      "시작일을 바꿔도 +29.24%~+31.18%로 결과가 거의 같았습니다. 순위로 종목을 고르는 규칙이라 시작일이 하루 달라도 고르는 종목이 크게 바뀌지 않았기 때문입니다.",
    ],
  },
  {
    market: "KOSPI",
    key: "magic_formula_20",
    check: RANKING_CHECK.KOSPI.magic_formula_20,
    commentary: [
      "투자 수익률 +51.05%, 최대 낙폭 −33.28%였고, 거래는 57회, 평균 보유 기간은 254일이었습니다. 순위 상위에 계속 남은 종목은 교체하지 않아 보유가 길었습니다. 승률 52.6%, 손익비 2.57이었습니다.",
      "연도별로는 2024년 −15.1%, 2025년 +32.7%, 2026년 +25.3%였습니다. 시작일을 바꿔도 +48.35%~+51.05%로 결과가 안정적이었습니다.",
    ],
  },
  // ── KOSDAQ ──
  {
    market: "KOSDAQ",
    key: "golden_cross_5_20",
    commentary: [
      "거래는 534회, 평균 보유 기간은 13일, 승률 24.5%, 손익비 0.50이었습니다. 연도별로는 2024년 −61.7%, 2025년 −44.9%, 2026년 −52.2%로 매해 손실이었고, 같은 기간 KODEX KOSDAQ 150 보유는 −18.9%, +37.8%, −24.9%였습니다.",
      "같은 규칙을 KOSPI에 적용한 기록은 −53.43%였습니다. 두 시장 모두 신호가 빈 자리보다 많은 날 최근 60거래일 수익률이 높은 종목부터 담는 엔진 기본 규칙이 적용됐습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "ma_alignment_5_20_60",
    commentary: [
      "거래는 508회, 평균 보유 기간은 14일, 승률 26.6%, 손익비 0.63이었습니다. 연도별로는 2024년 −54.7%, 2025년 −43.5%, 2026년 −54.4%였습니다.",
      "정배열인 동안 계속 매수 후보가 되므로 후보가 매우 많았고, 그중 최근 60거래일 수익률이 높은 종목부터 담는 엔진 기본 규칙이 적용됐습니다. 같은 규칙을 KOSPI에 적용한 기록은 −76.45%였습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "rsi_30_70",
    commentary: [
      "거래는 64회, 평균 보유 기간은 114일로 길었고, 마지막 날까지 보유 중이던 종목이 10개였습니다. 승률 53.1%, 손익비 0.92였습니다.",
      "연도별로는 2023년(11~12월) +6.4%, 2024년 −16.5%, 2025년 +30.1%, 2026년 −19.9%로, 해마다 같은 기간 KODEX KOSDAQ 150 보유(+15.5%, −18.9%, +37.8%, −24.9%)와 같은 방향이었습니다. 시작일에 따라 결과가 달라지는 폭도 함께 읽어야 합니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "macd_signal_cross",
    commentary: [
      "거래는 886회, 평균 보유 기간은 8일, 승률 25.4%, 손익비 0.62였습니다. 연도별로는 2024년 −59.8%, 2025년 −44.2%, 2026년 −50.0%였습니다.",
      "보유가 짧고 매매가 잦아 거래 비용이 반복해서 쌓이는 구조입니다. 보유 중 상장폐지돼 정리 가격으로 정산된 거래가 1건 있었습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "volatility_breakout_k05",
    check: VB_CHECK.KOSDAQ,
    commentary: [
      "거래는 6,890회, 평균 보유 기간은 1일, 승률 40.6%, 손익비 0.83이었습니다. 연도별로는 2024년 −70.2%, 2025년 −67.5%, 2026년 −47.3%로 매해 손실이었고, 같은 기간 KODEX KOSDAQ 150 보유는 −18.9%, +37.8%, −24.9%였습니다.",
      "한 번 사고팔 때마다 수수료·슬리피지·거래세를 합쳐 약 0.3%가 들고, 이 비용이 6,890번 반복됐습니다. 돌파한 종목이 빈 자리보다 많았던 날이 728거래일로 거의 매일이었습니다. 같은 규칙을 KOSPI에 적용한 기록은 −86.69%였고, 두 시장 모두 시작일을 바꿔도 결과가 거의 같았습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "bollinger_lower",
    commentary: [
      "거래는 129회, 평균 보유 기간은 56일, 승률 48.8%, 손익비 0.81이었습니다. 연도별로는 2023년(11~12월) +5.4%, 2024년 −6.5%, 2025년 −12.1%, 2026년 −21.0%였습니다.",
      "2025년은 같은 기간 KODEX KOSDAQ 150 보유가 +37.8%였던 해였고, 2024년과 2026년에는 이 기록의 손실이 ETF 보유(−18.9%, −24.9%)보다 작았습니다.",
    ],
    caveats: [
      "보유 중 상장폐지된 거래가 1건(종목 코드 227100) 있습니다. 오랜 거래정지 뒤 정리매매 첫날(2026-06-22) 시가 42원(직전 거래가 612원)에 팔려 이 거래의 수익률은 −93.94%였습니다.",
      "2026-11-05에 고친 기록입니다. 처음 게시한 계산(엔진 v16.45.1)은 엔진의 가격 보정이 이 정리매매 첫날 가격을 잘못된 가격으로 보고 앞뒤 평균으로 바꿔, 이 거래가 −54.12%, 전체 투자 수익률이 −27.86%로 기록됐습니다. 엔진 v16.47에서 정리매매 기간의 가격은 보정하지 않도록 고친 뒤 다시 계산했습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "high_52w_hold_3m",
    commentary: [
      "거래는 119회, 평균 보유 기간은 60일, 승률 37.8%, 손익비 0.76이었습니다. 연도별로는 2024년 −39.8%, 2025년 +16.4%, 2026년 −11.5%였습니다.",
      "같은 규칙을 KOSPI에 적용한 기록은 −20.79%였고, 두 시장 모두 시작일에 따라 결과가 크게 갈렸습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "dual_momentum_12m",
    check: RANKING_CHECK.KOSDAQ.dual_momentum_12m,
    commentary: [
      "투자 수익률은 +18.07%였지만 최대 낙폭은 −68.82%였습니다. 평균 보유 기간은 57일, 승률 61.1%, 손익비 1.08이었습니다.",
      "연도별 편차가 매우 커서 2025년 한 해에 +98.9%(같은 기간 KODEX KOSDAQ 150 보유 +37.8%)였고, 2024년은 −16.8%, 2026년은 −25.3%였습니다. 수익의 대부분이 한 해에서 나왔습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "low_per_pbr_20",
    check: RANKING_CHECK.KOSDAQ.low_per_pbr_20,
    commentary: [
      "투자 수익률 +30.63%, 최대 낙폭 −30.23%였고, 거래는 94회, 평균 보유 기간은 155일이었습니다. 승률 50.0%, 손익비 1.62였습니다.",
      "연도별로는 2024년 −14.6%, 2025년 +37.2%, 2026년 +2.9%였고, 2026년은 같은 기간 KODEX KOSDAQ 150 보유가 −24.9%였던 해입니다. 순위로 종목을 고르는 규칙이라 시작일을 바꿔도 결과 차이가 작았습니다.",
    ],
  },
  {
    market: "KOSDAQ",
    key: "magic_formula_20",
    check: RANKING_CHECK.KOSDAQ.magic_formula_20,
    commentary: [
      "투자 수익률 +2.20%, 최대 낙폭 −34.56%였고, 거래는 64회, 평균 보유 기간은 228일이었습니다. 승률 39.1%, 손익비 1.04였습니다.",
      "연도별로는 2023년(11~12월) +13.4%, 2024년 −15.0%, 2025년 +24.7%, 2026년 −15.0%였습니다. 같은 규칙을 KOSPI에 적용한 기록은 +51.05%였습니다. KOSDAQ은 EV/EBIT 값이 있는 기간이 짧아 후보가 적었다는 점(아래 주의할 점)도 함께 읽어야 합니다.",
    ],
  },
];

// ── 계열별 모음(허브) ─────────────────────────────────────────────────────────

type Hub = { family: Family; label: string; intro: string };

const HUBS: Hub[] = [
  {
    family: "moving-average",
    label: "이동평균선",
    intro: "이동평균선 기법은 일정 기간 종가의 평균선을 기준으로 추세의 방향을 읽는 규칙입니다. 짧은 선과 긴 선이 교차하거나 차례로 놓인 모양을 매매 신호로 씁니다.",
  },
  {
    family: "oscillator",
    label: "오실레이터(RSI·MACD)",
    intro: "오실레이터는 가격의 오르내림을 일정 범위의 값이나 두 선의 차이로 바꿔, 과하게 오르거나 내린 구간과 추세가 바뀌는 지점을 읽는 지표입니다.",
  },
  {
    family: "volatility",
    label: "변동성(변동성 돌파·볼린저밴드)",
    intro: "변동성 기법은 가격이 평소 움직이는 폭을 기준으로 삼습니다. 그 폭을 넘어 오르면 사거나(변동성 돌파), 폭의 아래쪽 끝까지 내려오면 사는(볼린저밴드 하단) 규칙이 대표적입니다.",
  },
  {
    family: "momentum",
    label: "모멘텀(52주 신고가·듀얼 모멘텀)",
    intro: "모멘텀 기법은 최근 많이 오른 종목이 한동안 더 오른다는 관찰에서 나온 규칙입니다. 신고가를 넘는 순간을 보거나, 일정 기간 수익률 순위로 종목을 고릅니다.",
  },
  {
    family: "value",
    label: "가치(저PER·저PBR·마법공식)",
    intro: "가치 기법은 이익·자산에 비해 주가가 낮은 종목을 재무 지표 순위로 골라 정기적으로 교체하는 규칙입니다.",
  },
];

function hubSlug(family: Family): string {
  return `techniques-${family}-3y`;
}

function familyMembers(family: Family): Technique[] {
  return TECHNIQUES.filter((t) => t.family === family);
}

function resultRow(m: Market, t: Technique): string[] {
  const r = RESULTS[m][t.key];
  return [t.short, m, r.ret, r.cagr, r.mdd, r.trades, r.retRange ? `${r.retRange[0]} ~ ${r.retRange[1]}` : "—"];
}

const RESULT_HEADERS = ["기법", "시장", "투자 수익률", "CAGR", "MDD", "거래 수", "시작일 5번 범위"];

function anyResult(): Result {
  return RESULTS.KOSPI.golden_cross_5_20;
}

/** 모음 글의 계산 정보 — 기록들의 엔진 버전·계산일을 모두 적는다. */
function collectionStamp(): string {
  const all = MARKETS.flatMap((m) => Object.values(RESULTS[m]));
  const versions = Array.from(new Set(all.map((r) => r.engineVersion))).sort();
  const dates = Array.from(new Set(all.map((r) => r.computedOn))).sort();
  return `널스탁 백테스트 엔진 ${versions.map((v) => `v${v}`).join("·")}으로 ${dates.join("·")}에 계산했습니다.`;
}

function collectionFootnote(): string {
  const r = anyResult();
  return `${r.start}~${r.end}, 수수료 0.015%·슬리피지 0.05%. 시작일 5번 범위는 종료일을 고정하고 시작일만 하루씩 옮겨 다시 계산한 투자 수익률의 최소~최대입니다. ${collectionStamp()}`;
}

function benchTable(): GuideSection {
  const r = anyResult();
  return {
    heading: "같은 기간 시장 ETF 보유",
    paragraphs: ["기록마다 같은 기간 해당 시장 ETF를 사서 보유한 결과를 벤치마크로 함께 실었습니다."],
    table: {
      caption: `시장 ETF 보유 결과(${r.start}~${r.end})`,
      headers: ["시장", "벤치마크", "투자 수익률", "CAGR"],
      rows: MARKETS.map((m) => {
        const b = RESULTS[m].golden_cross_5_20;
        return [m, BENCH_SHORT[m], b.benchRet, b.benchCagr];
      }),
      footnote: `배당을 세후 재투자한 값입니다. ${collectionStamp()}`,
    },
  };
}

const COLLECTION_SETUP = [
  "기간 2023-11-03~2026-11-03(최근 3년), 시작 자금 1,000만 원",
  "시장마다 그날 상장돼 있던 보통주 전체(상장폐지 종목 포함)가 대상이고, 거래대금이 부족한 종목은 엔진의 유동성 기준에서 빠집니다.",
  COST_SETUP,
  "체결은 다음 거래일 시가입니다(변동성 돌파만 돌파가 매수·다음 거래일 시가 매도).",
  "손절·익절·트레일링 스톱은 쓰지 않았습니다. 규칙은 결과를 보기 전에 정해 두고 한 번에 계산했습니다.",
];

function buildHub(hub: Hub): GuideArticle {
  const members = familyMembers(hub.family);
  const r = anyResult();
  const names = members.map((t) => t.short).join("·");
  const perMarket = MARKETS.map(
    (m) => `${m}에서 ${members.map((t) => `${t.short} ${RESULTS[m][t.key].ret}`).join(", ")}`,
  ).join(", ");
  const benches = MARKETS.map((m) => `${BENCH_SHORT[m]} ${RESULTS[m].golden_cross_5_20.benchRet}`).join(", ");
  return {
    slug: hubSlug(hub.family),
    title: `${hub.label} 매매기법 백테스트 모음: KOSPI·KOSDAQ ${PERIOD_LABEL}`,
    description: `${names} 전략을 KOSPI·KOSDAQ ${r.start}~${r.end} 데이터로 백테스트한 기록 ${members.length * 2}편의 투자 수익률·CAGR·MDD·거래 수를 한 표로 모았습니다.`,
    summary:
      `${names} 전략을 KOSPI와 KOSDAQ의 ${r.start}~${r.end} 데이터로 백테스트한 기록 ${members.length * 2}편을 모았습니다. ` +
      `투자 수익률은 ${perMarket}였고, 같은 기간 ${benches}였습니다. ` +
      `과거 데이터 기준 결과입니다.`,
    published: "2026-11-05",
    updated: "2026-11-05",
    sections: [
      { heading: "이 묶음의 기법", paragraphs: [hub.intro], bullets: members.map((t) => `${t.short}: ${t.rule}`) },
      {
        heading: "결과 한눈에 보기",
        paragraphs: [
          "기법마다 규칙과 보유 종목 수가 다르고, 시장 ETF는 지수 전체를 보유합니다. 표는 각 설정의 과거 결과를 나란히 놓은 것이며 기법 사이의 우열을 뜻하지 않습니다. 기록마다의 연도별 수익률·청산 내역·대조 결과는 아래 링크의 개별 기록에 있습니다.",
        ],
        table: {
          caption: `${hub.label} 기법 — KOSPI·KOSDAQ ${PERIOD_LABEL} 백테스트 결과`,
          headers: RESULT_HEADERS,
          rows: members.flatMap((t) => MARKETS.map((m) => resultRow(m, t))),
          footnote: collectionFootnote(),
        },
      },
      benchTable(),
      { heading: "공통 설정", paragraphs: ["모든 기록에 같은 조건을 썼습니다."], bullets: COLLECTION_SETUP },
      {
        heading: "읽을 때 주의할 점",
        paragraphs: [
          "모든 숫자는 한 기간·한 가지 파라미터 조합의 과거 시뮬레이션 결과입니다. 3년은 시장 국면 한두 개를 담는 짧은 구간이라 다른 기간이나 값에서는 다른 결과가 나올 수 있습니다. 미래 수익은 보장되지 않습니다.",
          "기록마다 주의할 점(재무 데이터 커버리지, 엔진 가격 보정, 체결 가정 등)이 따로 있으니 개별 기록을 함께 읽어 주세요.",
        ],
      },
    ],
    related: members.flatMap((t) => MARKETS.map((m) => slugOf(m, t))),
    faq: [
      {
        question: `${hub.label} 기법 백테스트는 어떤 조건으로 계산했나요?`,
        answer: `KOSPI·KOSDAQ의 ${r.start}~${r.end} 데이터, 시작 자금 1,000만 원, 수수료 0.015%·슬리피지 0.05%·시행일 기준 증권거래세를 반영했고 상장폐지 종목도 포함했습니다. 규칙과 엔진 조건은 개별 기록에 모두 적었습니다.`,
      },
      {
        question: "같은 기법인데 KOSPI와 KOSDAQ 결과가 다른 이유는 무엇인가요?",
        answer:
          "대상 종목과 같은 기간 시장 흐름이 다르기 때문입니다. 같은 규칙이라도 고르는 종목이 달라지고, 벤치마크도 KODEX 코스피와 KODEX KOSDAQ 150으로 다릅니다. 두 결과는 각 시장의 과거 값이며 어느 시장이 기법에 맞는지를 판정하지 않습니다.",
      },
    ],
  };
}

// ── 종합 ─────────────────────────────────────────────────────────────────────

export const CLASSIC_SUMMARY_SLUG = "famous-techniques-3y-kospi-kosdaq";

/** 생성된 표시값("+12.34%", "−5.67%")을 숫자로 — 우리가 만든 형식의 정규화일 뿐이다. */
function pctValue(text: string): number {
  return Number(text.replace("−", "-").replace(/[+%,]/g, ""));
}

function buildSummary(): GuideArticle {
  const r = anyResult();
  const rows = TECHNIQUES.flatMap((t) => MARKETS.map((m) => ({ m, t, r: RESULTS[m][t.key] })));
  const positive = rows.filter((x) => pctValue(x.r.ret) > 0).length;
  const aboveBench = rows.filter((x) => !x.r.below).length;
  const heavy = rows.filter((x) => Number(x.r.trades.replace(/[^0-9]/g, "")) >= 500);
  const heavyNegative = heavy.filter((x) => pctValue(x.r.ret) < 0).length;
  const benches = MARKETS.map((m) => `${BENCH_SHORT[m]} CAGR ${RESULTS[m].golden_cross_5_20.benchCagr}`).join(", ");
  const n = rows.length;
  return {
    slug: CLASSIC_SUMMARY_SLUG,
    title: `유명 매매기법 10개, KOSPI·KOSDAQ ${PERIOD_LABEL} 백테스트 결과 모음`,
    description: `골든크로스·RSI·MACD·변동성 돌파·마법공식 등 매매기법 10개를 KOSPI·KOSDAQ ${r.start}~${r.end}에 백테스트한 결과 ${n}개를 한 표로 모았습니다.`,
    summary:
      `널리 알려진 매매기법 10개를 KOSPI와 KOSDAQ의 ${r.start}~${r.end} 데이터로 각각 백테스트했습니다. ` +
      `${n}번의 계산 중 투자 수익률이 플러스였던 것은 ${positive}번이었고, CAGR이 같은 기간 시장 ETF 보유(${benches})보다 높았던 것은 ${aboveBench}번이었습니다. ` +
      `수수료 0.015%와 슬리피지 0.05%를 반영한 과거 데이터 기준 결과입니다.`,
    published: "2026-11-05",
    updated: "2026-11-05",
    sections: [
      {
        heading: "계산한 기법",
        paragraphs: ["유튜브·커뮤니티에서 자주 언급되는 기법을 계열별로 둘씩 골랐습니다. 규칙은 결과를 보기 전에 정해 두었습니다."],
        bullets: TECHNIQUES.map((t) => `${t.short}: ${t.rule}`),
      },
      {
        heading: "결과 표",
        paragraphs: [
          "계열 순서대로 놓았습니다. 기법마다 규칙과 보유 종목 수가 달라 표는 각 설정의 과거 결과를 나란히 놓은 것이며, 기법 사이의 우열을 뜻하지 않습니다.",
        ],
        table: {
          caption: `유명 매매기법 10개 — KOSPI·KOSDAQ ${PERIOD_LABEL} 백테스트 결과`,
          headers: RESULT_HEADERS,
          rows: rows.map(({ m, t }) => resultRow(m, t)),
          footnote: collectionFootnote(),
        },
      },
      benchTable(),
      {
        heading: "숫자에서 관측된 것",
        paragraphs: ["아래는 표의 값을 그대로 센 것입니다. 원인이나 앞으로의 결과를 판정하지 않습니다."],
        bullets: [
          `투자 수익률이 플러스였던 계산은 ${n}개 중 ${positive}개였습니다.`,
          `CAGR이 같은 기간 시장 ETF 보유보다 높았던 계산은 ${n}개 중 ${aboveBench}개였습니다.`,
          `거래가 500회 이상이었던 계산은 ${heavy.length}개(${heavy.map((x) => `${x.t.short} ${x.m}`).join(", ")})였고, ${heavyNegative === heavy.length ? "모두 투자 수익률이 마이너스였습니다" : `그중 투자 수익률이 마이너스였던 것은 ${heavyNegative}개였습니다`}. 한 번 사고팔 때 수수료·슬리피지·거래세로 약 0.3%가 듭니다.`,
          "시작일만 하루씩 바꿔도 투자 수익률이 크게 달라진 기록이 있습니다. 표의 '시작일 5번 범위'를 함께 읽어 주세요.",
        ],
      },
      { heading: "공통 설정", paragraphs: ["모든 기록에 같은 조건을 썼습니다."], bullets: COLLECTION_SETUP },
      {
        heading: "읽을 때 주의할 점",
        paragraphs: [
          "모든 숫자는 한 기간·한 가지 파라미터 조합의 과거 시뮬레이션 결과입니다. 3년은 시장 국면 한두 개를 담는 짧은 구간이라 다른 기간이나 값에서는 다른 결과가 나올 수 있습니다. 미래 수익은 보장되지 않습니다.",
          "기록마다 주의할 점(재무 데이터 커버리지, 엔진 가격 보정, 체결 가정 등)이 따로 있습니다. 계열별 모음과 개별 기록에서 확인할 수 있습니다.",
        ],
      },
    ],
    related: HUBS.map((h) => hubSlug(h.family)),
    faq: [
      {
        question: "유명 매매기법들은 백테스트에서 수익이 났나요?",
        answer: `이 모음의 설정에서는 ${n}번의 계산 중 ${positive}번이 플러스 수익률이었고, CAGR이 같은 기간 시장 ETF 보유보다 높았던 것은 ${aboveBench}번이었습니다. 한 기간·한 설정의 과거 값이며 기법 전체의 효과를 판정하지 않습니다.`,
      },
      {
        question: "결과를 직접 다시 계산해 볼 수 있나요?",
        answer:
          "개별 기록마다 엔진에 넘긴 조건과 전략 식별값, 가정을 모두 적었습니다. 데이터 출처와 비용·체결 가정은 백테스트 방법론 페이지에 정리했습니다.",
      },
      {
        question: "왜 최근 3년만 계산했나요?",
        answer:
          "최근 시장에서 같은 규칙이 어떤 값을 냈는지 보기 위해 기간을 3년으로 정했습니다. 3년은 짧은 구간이라 시작일을 하루씩 바꿔 다시 계산한 범위를 함께 실었습니다.",
      },
    ],
  };
}

// 같은 게시일 안에서는 시드 순서가 목록 순서다 — 종합, 계열별 모음, 개별 기록 순으로 둔다.
export const CLASSIC_NOTES: GuideArticle[] = [buildSummary(), ...HUBS.map(buildHub), ...REPORTS.map(buildReport)];

/** 결과 JSON의 시장·규칙 이름 → 기록 slug — 원본 결과를 ResearchNoteResult에 올릴 때 쓴다. */
export function classicNoteSlug(market: string, rule: string): string | undefined {
  const t = TECHNIQUES.find((item) => item.key === rule);
  return t && MARKETS.includes(market as Market) ? slugOf(market as Market, t) : undefined;
}

/** 유명 기법 기록이 근거로 삼은 결과 데이터(Dataset 구조화 데이터). 개별 기록이 아니면 undefined. */
export function classicNoteDataset(slug: string): BacktestDataset | undefined {
  for (const rep of REPORTS) {
    const t = technique(rep.key);
    if (slugOf(rep.market, t) === slug) return dataset(rep.market, t, RESULTS[rep.market][rep.key]);
  }
  return undefined;
}
