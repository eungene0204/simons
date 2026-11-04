// 연구노트 — 유명 매매기법 KOSPI 최근 3년 백테스트 기록(AEO 설계서 3단계, 2026-11-04).
//
// 숫자는 손으로 옮기지 않는다 — `classicResults.ts`(scripts/research_classic_to_ts.py가 엔진 결과 JSON에서 생성)만 읽는다.
// 규칙은 실행 전에 `scripts/research_classic_techniques.py`에 고정했고, 앱과 같은 경로(해석된 전략 → 엔진 요청)로 계산했다.
// 표현은 규제 안전 원칙을 따른다(CLAUDE.md) — 관측된 값만 기록하고 기법의 성립 여부·우열·전망을 말하지 않는다.
// 종목명·종목 코드는 싣지 않는다. 순수 데이터 모듈이다(react·next 의존 없음).

import type { GuideArticle, GuideFaq, GuideSection } from "@/lib/guide/articles";
import type { BacktestDataset } from "@/lib/guide/jsonLd";
import { CLASSIC_ENGINE_VERSION, CLASSIC_RESULTS } from "./classicResults";

type RuleKey = keyof typeof CLASSIC_RESULTS;
type Result = (typeof CLASSIC_RESULTS)[RuleKey];

type Classic = {
  key: RuleKey;
  slug: string;
  /** 제목·요약에 쓰는 기법 이름. */
  name: string;
  /** 요약 괄호 안의 한 줄 규칙. */
  rule: string;
  /** 기법이 무엇인지. */
  intro: string[];
  /** 규칙을 사람 말로. */
  conditions: string[];
  /** 엔진에 넘긴 조건(재현용) — [항목, 값]. */
  engine: [string, string][];
  /** 결과 해석(관측 사실만, 전망 없음). */
  commentary: string[];
  caveats?: string[];
  related: string[];
};

const PERIOD_LABEL = "최근 3년";
const UNIVERSE_NOTE =
  "KOSPI 상장 보통주 중 그날 상장돼 있던 종목(상장폐지 종목 포함)이 대상이고, 거래대금이 부족한 종목은 엔진의 유동성 기준에서 빠집니다.";
const COMMON_SETUP = [
  "시작 자금 1,000만 원, 신호가 나온 다음 거래일 시가에 체결합니다.",
  "수수료 매수·매도 각 0.015%, 슬리피지 0.05%, 매도 증권거래세는 시행일 기준 법정 세율(0.20%→0.15%)을 반영했습니다. 배당은 배당소득세 15.4%를 뺀 금액을 재투자합니다.",
  "손절·익절·트레일링 스톱은 쓰지 않았습니다.",
];
const TIEBREAK_NOTE =
  "매수 신호가 빈 자리보다 많은 날에는 엔진 기본 규칙에 따라 최근 60거래일 수익률이 높은 종목부터 담습니다. 넓은 유니버스에서는 이미 크게 오른 종목이 먼저 선택되는 구조라 결과에 큰 영향을 줍니다.";

function dataset(c: Classic, r: Result): BacktestDataset {
  return {
    name: `${c.name} KOSPI ${r.start}~${r.end} 백테스트 결과`,
    description: `KOSPI 일별 가격 기반, 수수료 0.015%·슬리피지 0.05%·시행일 기준 증권거래세 반영, 다음 거래일 시가 체결. 널스탁 백테스트 엔진 v${CLASSIC_ENGINE_VERSION}으로 2026-11-04에 계산했습니다.`,
    temporalCoverage: `${r.start}/${r.end}`,
    variableMeasured: ["투자 수익률", "CAGR", "최대 낙폭(MDD)", "샤프 비율", "승률", "거래 수", "연도별 수익률", "같은 기간 벤치마크 수익률"],
  };
}

function summary(c: Classic, r: Result): string {
  return (
    `${PERIOD_LABEL}(${r.start}~${r.end}) 동안 KOSPI 종목에 ${c.name}(${c.rule})을 적용해 백테스트한 결과, ` +
    `투자 수익률은 ${r.ret}, 연평균 수익률(CAGR)은 ${r.cagr}로 같은 기간 KODEX 코스피 보유(CAGR ${r.benchCagr})보다 ${r.below ? "낮았" : "높았"}습니다. ` +
    `최대낙폭(MDD)은 ${r.mdd}, 승률은 ${r.win}, 총 거래는 ${r.trades}였습니다. ` +
    ("retRange" in r ? `시작일만 하루씩 바꿔 다섯 번 계산하면 투자 수익률은 ${r.retRange[0]}~${r.retRange[1]}였습니다. ` : "") +
    `수수료 0.015%와 슬리피지 0.05%를 반영한 과거 데이터 기준 결과이며, 미래 수익을 보장하지 않습니다.`
  );
}

function buildNote(c: Classic): GuideArticle {
  const r = CLASSIC_RESULTS[c.key];
  const footnote = `KOSPI, ${r.start}~${r.end}, 다음 거래일 시가 체결, 수수료 0.015%·슬리피지 0.05%. 널스탁 백테스트 엔진 v${CLASSIC_ENGINE_VERSION}으로 2026-11-04에 계산했습니다.`;
  const startRuns = "startRuns" in r ? r.startRuns : undefined;
  const sections: GuideSection[] = [
    { heading: "검증한 기법", paragraphs: c.intro },
    {
      heading: "규칙과 설정",
      paragraphs: [
        "결과를 보기 전에 아래 규칙을 정해 두고 한 번에 계산했습니다. 같은 이름의 기법이라도 기간·청산 규칙·종목 수를 다르게 정하면 결과가 달라집니다.",
      ],
      bullets: [...c.conditions, UNIVERSE_NOTE, ...COMMON_SETUP],
    },
    {
      heading: "핵심 지표",
      paragraphs: [
        `${r.start}~${r.end}(${r.tradingDays}) 구간의 값입니다. 벤치마크는 같은 기간 KODEX 코스피를 사서 보유한 결과입니다. 전략과 벤치마크는 보유 종목 구성과 규칙이 다르므로 표의 차이는 우열을 뜻하지 않습니다.`,
      ],
      table: {
        caption: `${c.name} — KOSPI ${PERIOD_LABEL} 백테스트 결과`,
        headers: ["지표", "전략", "KODEX 코스피 보유"],
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
        footnote,
      },
    },
    {
      heading: "연도별 수익률",
      paragraphs: [
        `해마다 연말 자산을 직전 연말(첫해는 시작 자금)과 비교한 값입니다. ${r.start.slice(0, 4)}년과 ${r.end.slice(0, 4)}년은 구간에 포함된 기간만의 수익률입니다.`,
      ],
      table: {
        caption: `${c.name} — 연도별 수익률`,
        headers: ["연도", "전략", "KODEX 코스피 보유"],
        rows: r.yearly.map((row) => [...row]),
        footnote,
      },
    },
  ];

  if (startRuns) {
    sections.push({
      heading: "시작일을 하루씩 바꿔 본 결과",
      paragraphs: [
        `종료일은 그대로 두고 시작일만 하루씩 옮겨 같은 규칙을 다시 계산했습니다. 투자 수익률은 ${r.retRange[0]}에서 ${r.retRange[1]} 사이였습니다. 보유 종목 수가 정해져 있고 대상 종목이 많은 규칙은 첫날 어떤 종목을 샀는지에 따라 이후 매매가 통째로 달라질 수 있어서, 한 번의 계산값만으로 읽지 않도록 함께 싣습니다.`,
      ],
      table: {
        caption: `${c.name} — 시작일별 결과(종료일 ${r.end} 고정)`,
        headers: ["시작일", "투자 수익률", "CAGR"],
        rows: startRuns.map((row) => [...row]),
        footnote,
      },
    });
  }

  sections.push(
    {
      heading: "청산 내역",
      paragraphs: ["거래가 끝난 이유별 건수입니다. 기간 종료 정산은 마지막 날 보유 중이던 종목을 그날 가격으로 평가해 닫은 것입니다."],
      table: { caption: `${c.name} — 청산 사유별 건수`, headers: ["청산 사유", "건수"], rows: r.exits.map((row) => [...row]), footnote },
    },
    {
      heading: "엔진에 넘긴 조건",
      paragraphs: [
        `같은 결과를 다시 계산할 수 있도록 엔진 조건을 그대로 적습니다. 전략 식별값은 ${r.strategyId.slice(0, 16)}입니다. 데이터 출처와 비용·체결 가정은 백테스트 방법론 페이지에 정리했습니다.`,
      ],
      table: { caption: `${c.name} — 엔진 조건`, headers: ["항목", "값"], rows: c.engine, footnote },
    },
    {
      heading: "직접 다시 계산해 대조한 것",
      paragraphs: [
        "엔진 결과를 그대로 믿지 않고, 가격·재무 데이터 원본에서 신호와 선택 종목을 독립적으로 다시 계산해 대조했습니다.",
      ],
      bullets: [c.key in RANKING_CHECK ? RANKING_CHECK[c.key]! : SIGNAL_CHECK, PRICE_CHECK],
    },
    { heading: "결과 해석", paragraphs: c.commentary },
    {
      heading: "읽을 때 주의할 점",
      paragraphs: [
        "이 기록은 한 유니버스·한 기간·한 가지 파라미터 조합의 과거 시뮬레이션 결과입니다. 3년은 시장 국면 한두 개를 담는 짧은 구간이라, 다른 기간이나 값에서는 다른 결과가 나올 수 있습니다. 미래 수익은 보장되지 않습니다.",
        ...(c.caveats ?? []),
      ],
    },
  );

  const faq: GuideFaq[] = [
    {
      question: `${c.name}은 KOSPI에서 효과가 있었나요?`,
      answer: `이 기록의 설정에서는 ${r.start}~${r.end} 동안 투자 수익률 ${r.ret}, CAGR ${r.cagr}, 최대 낙폭 ${r.mdd}였고 같은 기간 KODEX 코스피 보유는 ${r.benchRet}였습니다. 한 기간·한 설정의 과거 값이며 기법 전체의 효과를 판정하지 않고, 미래 수익을 보장하지 않습니다.`,
    },
    {
      question: "같은 기법인데 다른 곳의 백테스트 결과와 숫자가 다른 이유는 무엇인가요?",
      answer:
        "기간, 대상 종목, 보유 종목 수, 청산 규칙, 수수료·슬리피지 가정, 상장폐지 종목 포함 여부가 다르면 결과가 달라집니다. 이 기록의 가정은 본문 '규칙과 설정'과 백테스트 방법론 페이지에 모두 적었습니다.",
    },
    {
      question: "표의 벤치마크와의 차이는 무엇을 뜻하나요?",
      answer: `같은 기간 KODEX 코스피를 보유한 결과(${r.benchRet})와 전략 결과(${r.ret})를 표시값 그대로 비교하는 용도입니다. 전략은 조건에 맞는 일부 종목만 보유하고 ETF는 지수 전체를 보유하므로 구성과 규칙이 달라 우열을 가리는 값은 아닙니다.`,
    },
  ];

  return {
    slug: c.slug,
    title: `${c.name}, KOSPI ${PERIOD_LABEL} 백테스트하면 수익이 났을까?`,
    description: `${c.name}을 KOSPI ${r.start}~${r.end}에 적용한 백테스트 결과: 투자 수익률 ${r.ret}, CAGR ${r.cagr}, MDD ${r.mdd}, 거래 ${r.trades}. 같은 기간 KODEX 코스피 보유 ${r.benchRet}.`,
    summary: summary(c, r),
    published: "2026-11-04",
    updated: "2026-11-04",
    sections,
    related: c.related,
    faq,
  };
}

const SIGNAL_CHECK =
  "매수 기록(매도 신호가 있는 규칙은 매도 신호 기록도)에서 무작위로 30건씩 골라 가격 데이터로 지표를 다시 계산해, 체결일 전 거래일에 규칙의 조건이 성립했는지 확인했습니다. 표본 전부가 규칙대로였습니다.";
const PRICE_CHECK =
  "거래마다 엔진의 체결 수익률을 원본 시가로 다시 계산한 수익률과 비교했습니다. 대부분 1%p 안에서 같았습니다. 오래 보유한 거래의 작은 차이는 세후 배당 재투자분이었고(예: 배당 1회가 있었던 거래에서 원본 25.35%에 세후 배당을 더하면 엔진 값 30.39%와 일치), 크게 다른 몇 건은 거래정지 뒤 주식 분할·병합으로 가격 단위가 정확히 5배 바뀐 종목을 엔진이 같은 비율로 보정한 경우였습니다.";
const RANKING_CHECK: Partial<Record<RuleKey, string>> = {
  dual_momentum_12m:
    "리밸런싱일 여섯 번을 골라 KOSPI 전 종목의 전일 기준 12개월 수익률을 다시 계산했습니다. 매수한 종목은 모두 수익률이 0% 초과인 종목 가운데 상위권(가장 낮은 순위 11위)이었습니다. 10위를 넘는 순위는 거래대금이 부족한 종목이 유동성 기준에서 빠져 다음 순위가 채운 경우입니다.",
  low_per_pbr_20:
    "리밸런싱일 여섯 번을 골라 PER·PBR이 모두 양수인 KOSPI 종목의 전일 기준 순위를 다시 계산했습니다. 매수한 종목은 모두 두 순위 평균의 상위권(가장 낮은 순위 21위)이었고, 20위를 넘는 순위는 유동성 기준에서 빠진 종목을 다음 순위가 채운 경우입니다.",
  magic_formula_20:
    "리밸런싱일 다섯 번을 골라 EV/EBIT이 양수인 KOSPI 종목의 전일 기준 ROIC 순위·EV/EBIT 순위를 다시 계산했습니다. 매수한 종목은 모두 두 순위 평균의 상위 20위 안이었습니다.",
};

const GUIDE_READ = "how-to-read-backtest-results";
const GUIDE_PIT = "backtest-pitfalls";
const GUIDE_COST = "backtest-trading-costs";
const GUIDE_REBAL = "backtest-rebalancing";

const TECH_ENGINE = (entry: string, exit: string): [string, string][] => [
  ["유니버스", "kospi (시점별 구성·상장폐지 포함)"],
  ["기간", "2023-11-03 ~ 2026-11-03"],
  ["진입", entry],
  ["청산", exit],
  ["보유", "최대 10종목, 종목당 자본의 10%"],
  ["체결·비용", "next_open · fee_rate 0.00015 · slippage_rate 0.0005"],
];
const RANK_ENGINE = (filters: string, ranking: string, holding: string, rebal: string): [string, string][] => [
  ["유니버스", "kospi (시점별 구성·상장폐지 포함)"],
  ["기간", "2023-11-03 ~ 2026-11-03"],
  ["후보 필터", filters],
  ["순위", ranking],
  ["보유", holding],
  ["리밸런싱", rebal],
  ["체결·비용", "next_open · fee_rate 0.00015 · slippage_rate 0.0005"],
];

const CLASSICS: Classic[] = [
  {
    key: "golden_cross_5_20",
    slug: "kospi-3y-golden-cross-5-20",
    name: "골든크로스(5일·20일 이동평균) 전략",
    rule: "5일선이 20일선을 위로 넘으면 매수, 아래로 넘으면 매도",
    intro: [
      "골든크로스는 짧은 기간 이동평균선이 긴 기간 이동평균선을 아래에서 위로 넘는 것을 말합니다. 반대로 위에서 아래로 넘는 것을 데드크로스라고 합니다. 5일선과 20일선 조합은 개인 투자자에게 가장 널리 알려진 형태입니다.",
    ],
    conditions: ["매수: 종가 기준 5일 이동평균이 20일 이동평균을 위로 넘은 날(골든크로스)", "매도: 5일 이동평균이 20일 이동평균을 아래로 넘은 날(데드크로스)", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH_ENGINE("ma_crossover(shortMA=5, longMA=20, 골든크로스)", "ma_crossover(shortMA=5, longMA=20, 데드크로스)"),
    commentary: [
      "거래는 508회, 평균 보유 기간은 14일로 매매가 잦았고 승률 26.8%, 손익비 0.78이었습니다. 연도별로는 2024년 −21.0%, 2025년 −32.5%였는데, 2025년은 같은 기간 KODEX 코스피 보유가 +82.7%였던 해입니다.",
      "손실이 가장 컸던 거래 10건 중 8건은 매수 전 5거래일 안에 상한가(+30%)가 있었던 종목이었습니다. 신호가 빈 자리보다 많은 날 최근 60거래일 수익률이 높은 종목부터 담는 엔진 기본 규칙 때문에, 이미 크게 오른 종목이 먼저 선택되는 구조였습니다. 시작일에 따라 결과가 −72.77%까지 벌어졌다는 점도 함께 읽어야 합니다.",
    ],
    related: ["kospi-3y-ma-alignment-5-20-60", "cost-sensitivity-ma-crossover", "myth-09-ma-5-20-cross", GUIDE_READ],
  },
  {
    key: "ma_alignment_5_20_60",
    slug: "kospi-3y-ma-alignment-5-20-60",
    name: "이동평균 정배열(5·20·60일) 전략",
    rule: "5일선>20일선>60일선 정배열일 때 매수, 5일선이 20일선 아래로 내려가면 매도",
    intro: [
      "정배열은 짧은 이동평균선이 위에, 긴 이동평균선이 아래에 차례로 놓인 상태를 말합니다. 가격이 최근으로 올수록 높아졌다는 뜻이라 상승 추세의 모양으로 흔히 설명됩니다. 여기서는 5일·20일·60일 세 선의 정배열을 썼습니다.",
    ],
    conditions: ["매수: 5일 이동평균 ≥ 20일 이동평균, 20일 이동평균 ≥ 60일 이동평균이 함께 성립하는 날(교차한 날만이 아니라 정배열인 동안 계속 후보)", "매도: 5일 이동평균이 20일 이동평균을 아래로 넘은 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH_ENGINE("ma_crossover(5, 20, mode=above) AND ma_crossover(20, 60, mode=above)", "ma_crossover(shortMA=5, longMA=20, 데드크로스)"),
    commentary: [
      "거래는 460회, 평균 보유 기간은 14일, 승률 24.8%, 손익비 0.59였습니다. 2024년 한 해에 −61.9%를 기록했고, KODEX 코스피 보유가 +82.7%였던 2025년에도 +4.5%였습니다.",
      "정배열인 동안 계속 매수 후보가 되므로 후보가 매우 많았고, 그중 최근 60거래일 수익률이 높은 종목부터 담는 엔진 기본 규칙이 적용됐습니다. 시작일을 바꿔도 −74.47%~−76.45%로 결과가 거의 같아, 한 번의 계산값이 우연에 크게 좌우된 경우는 아니었습니다.",
    ],
    related: ["kospi-3y-golden-cross-5-20", "myth-12-above-ma60", GUIDE_READ],
  },
  {
    key: "rsi_30_70",
    slug: "kospi-3y-rsi-30-70",
    name: "RSI 30 이하 매수·70 이상 매도 전략",
    rule: "14일 RSI가 30 이하이면 매수, 70 이상이면 매도",
    intro: [
      "RSI(상대강도지수)는 일정 기간 오른 폭과 내린 폭을 비교해 0~100 사이 값으로 나타낸 지표입니다. 흔히 30 이하를 과매도, 70 이상을 과매수 구간이라고 부르며, 과매도에서 사서 과매수에서 파는 규칙이 널리 알려져 있습니다.",
    ],
    conditions: ["매수: 14일 RSI가 30 이하인 날", "매도: 14일 RSI가 70 이상인 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH_ENGINE("rsi(period=14, <= 30)", "rsi(period=14, >= 70)"),
    commentary: [
      "거래는 67회, 평균 보유 기간은 108일로 다른 기술적 규칙보다 훨씬 길었습니다. RSI가 70까지 올라야 팔기 때문에 매수 후 오래 기다린 거래가 많았고, 마지막 날까지 보유 중이던 종목이 9개였습니다. 승률은 62.7%, 손익비는 1.36이었습니다.",
      "이 기록에서 가장 크게 읽어야 할 것은 시작일 민감도입니다. 2023-11-03에 시작하면 +21.89%였지만 하루씩 늦춘 나머지 네 번은 −2.21%~−9.34%로 모두 손실이었습니다. 거래 수가 적고 보유가 길어서, 처음 산 종목이 달라지면 이후 결과가 크게 달라지는 구조입니다.",
    ],
    related: ["myth-04-rsi-oversold", "kospi-3y-bollinger-lower", GUIDE_READ],
  },
  {
    key: "macd_signal_cross",
    slug: "kospi-3y-macd-signal-cross",
    name: "MACD 시그널 교차 전략",
    rule: "MACD선이 시그널선을 위로 넘으면 매수, 아래로 넘으면 매도",
    intro: [
      "MACD는 12일 지수이동평균에서 26일 지수이동평균을 뺀 값이고, 시그널선은 MACD의 9일 지수이동평균입니다. MACD선이 시그널선을 위로 넘는 것을 매수 신호로, 아래로 넘는 것을 매도 신호로 쓰는 방법이 가장 흔합니다.",
    ],
    conditions: ["매수: MACD(12, 26)가 시그널선(9)을 위로 넘은 날", "매도: MACD가 시그널선을 아래로 넘은 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH_ENGINE("macd(12, 26, 9, mode=crossover, 상향)", "macd(12, 26, 9, mode=crossover, 하향)"),
    commentary: [
      "거래는 798회로 아홉 기법 중 가장 많았고, 평균 보유 기간은 9일, 승률 28.1%, 손익비 0.79였습니다. 연도별로는 2025년 −27.2%, 2026년 −51.1%였습니다.",
      "보유가 짧고 매매가 잦아 거래 비용이 반복해서 쌓이는 구조입니다. 시작일을 바꿔도 −65.15%~−68.86%로 결과가 비슷했습니다.",
    ],
    related: ["myth-05-macd-golden-cross", "kospi-3y-golden-cross-5-20", GUIDE_COST],
  },
  {
    key: "bollinger_lower",
    slug: "kospi-3y-bollinger-lower",
    name: "볼린저밴드 하단 매수 전략",
    rule: "종가가 볼린저밴드 하단 이하이면 매수, 상단 이상이면 매도",
    intro: [
      "볼린저밴드는 20일 이동평균을 중심으로 위아래에 표준편차의 2배만큼 띄운 띠입니다. 가격이 하단 밖으로 나가면 평소보다 많이 내려간 것으로 보고 사는 규칙이 널리 알려져 있습니다.",
    ],
    conditions: ["매수: 종가가 볼린저밴드(20일, 표준편차 2배) 하단 이하인 날", "매도: 종가가 상단 이상인 날", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH_ENGINE("bollinger_bands(20, 2, 종가 ≤ 하단)", "bollinger_bands(20, 2, 종가 ≥ 상단)"),
    commentary: [
      "거래는 149회, 평균 보유 기간은 49일, 승률 51.0%, 손익비 0.85였습니다. 이긴 거래와 진 거래의 수는 비슷했지만 진 거래의 손실 합계가 더 컸습니다. 연도별로는 2023년(11~12월) +9.6%, 2025년 +9.4%, 2024년 −9.8%, 2026년 −20.1%였습니다.",
      "시작일에 따라 −13.54%~−23.04%로 바뀌었고, 2023-11-03에 시작한 경우가 다섯 번 중 손실이 가장 작았습니다.",
    ],
    related: ["myth-08-bollinger-lower", "kospi-3y-rsi-30-70", GUIDE_READ],
  },
  {
    key: "high_52w_hold_3m",
    slug: "kospi-3y-52-week-high",
    name: "52주 신고가 매수 전략",
    rule: "고가가 직전 252거래일 최고가를 넘으면 매수, 63거래일 보유 후 매도",
    intro: [
      "52주 신고가 매수는 주가가 지난 1년 중 가장 높은 가격을 넘어설 때 사는 모멘텀 계열 규칙입니다. 여기서는 1년을 252거래일로, 보유 기간을 약 3개월(63거래일)로 정했습니다.",
    ],
    conditions: ["매수: 그날 고가가 직전 252거래일의 최고가를 넘은 날", "매도: 매수 후 63거래일이 지나면(매도 신호 없음)", "최대 10종목, 종목당 자본의 10%", TIEBREAK_NOTE],
    engine: TECH_ENGINE("breakout(lookbackPeriod=252, 고가 기준 상향)", "max_holding_days=63"),
    commentary: [
      "거래는 118회, 평균 보유 기간은 60일, 승률 33.1%, 손익비 0.87이었습니다. 연도별 편차가 커서 2024년 −29.4%, 2025년 +45.2%, 2026년 −18.9%였습니다.",
      "시작일에 따라 −20.79%~−43.21%로 결과가 크게 갈렸습니다. 2023-11-03에 시작한 경우가 다섯 번 중 손실이 가장 작았고, 나머지 넷 중 셋은 −42%~−43% 수준이었습니다.",
    ],
    related: ["myth-15-52week-low", "kospi-3y-dual-momentum-12m", GUIDE_PIT],
  },
  {
    key: "dual_momentum_12m",
    slug: "kospi-3y-dual-momentum-12m",
    name: "듀얼 모멘텀(12개월) 전략",
    rule: "매달 12개월 수익률 상위 10종목 중 수익률이 0% 초과인 종목 보유",
    intro: [
      "듀얼 모멘텀은 다른 자산보다 많이 오른 것을 고르는 상대 모멘텀과, 스스로 올랐는지 보는 절대 모멘텀을 함께 쓰는 방법입니다. 원래는 주식·채권 같은 자산군 사이에서 쓰지만, 여기서는 KOSPI 개별 종목에 적용했습니다.",
    ],
    conditions: ["매달 첫 거래일에 최근 252거래일 수익률 순위 상위 10종목을 고릅니다(상대 모멘텀).", "그중 수익률이 0% 이하인 종목은 고르지 않고 그 자리는 현금으로 둡니다(절대 모멘텀).", "종목당 자본의 10%"],
    engine: RANK_ENGINE("없음", "return(lookback=252일) 상위 · absolute_momentum_threshold_pct=0", "10종목, 종목당 10%", "monthly(매달 첫 거래일)"),
    commentary: [
      "투자 수익률은 +90.13%였지만 최대 낙폭도 −58.90%로 컸습니다. 리밸런싱은 매달 이뤄졌고 평균 보유 기간은 66일, 승률 61.2%, 손익비 1.34였습니다. 연도별로는 2024년 +18.9%(KODEX 코스피 보유 −5.7%), 2025년 +51.1%(같은 기간 +82.7%), 2026년 +3.3%(같은 기간 +35.0%)였습니다.",
      "시작일을 바꾸면 +65.41%~+90.13%였고, 다섯 번 모두 이익이었지만 같은 기간 KODEX 코스피 보유(+164.90%)보다는 낮았습니다.",
    ],
    caveats: ["절대 모멘텀의 기준을 무위험 금리가 아니라 0%로 단순화했습니다. 원래 방법과 다릅니다."],
    related: ["rebalancing-period-momentum-ranking", "kospi-3y-52-week-high", GUIDE_REBAL],
  },
  {
    key: "low_per_pbr_20",
    slug: "kospi-3y-low-per-pbr-20",
    name: "저PER·저PBR 20종목 전략",
    rule: "분기마다 PER·PBR 순위 평균 상위 20종목 보유",
    intro: [
      "PER(주가수익비율)과 PBR(주가순자산비율)이 낮은 종목은 이익이나 자산에 비해 주가가 낮다고 보고 사는 가치 투자 규칙입니다. 두 지표의 순위를 합쳐 고르는 방식이 흔히 쓰입니다.",
    ],
    conditions: ["후보: PER과 PBR이 모두 0보다 큰 종목(적자·자본잠식 종목 제외)", "분기 첫 거래일에 PER 낮은 순위와 PBR 낮은 순위를 평균해 상위 20종목을 고릅니다.", "종목당 자본의 5%"],
    engine: RANK_ENGINE("per > 0 AND pbr > 0", "composite(per 낮은 순, pbr 낮은 순, 동일 가중)", "20종목, 종목당 5%", "quarterly(분기 첫 거래일)"),
    commentary: [
      "투자 수익률 +31.18%, 최대 낙폭 −27.64%였고, 분기마다 교체해 거래는 84회, 평균 보유 기간은 170일이었습니다. 승률 58.3%, 손익비 1.96이었습니다. 수익의 대부분은 2025년(+41.2%)에 났고 2024년은 −0.6%, 2026년은 −7.8%였습니다.",
      "시작일을 바꿔도 +29.24%~+31.18%로 결과가 거의 같았습니다. 순위로 종목을 고르는 규칙이라 시작일이 하루 달라도 고르는 종목이 크게 바뀌지 않았기 때문입니다.",
    ],
    caveats: ["재무 값은 공시가 공개된 날부터 씁니다(공개일을 모르면 결산일 90일 뒤부터)."],
    related: ["myth-02-low-per", "kospi-3y-magic-formula-20", GUIDE_REBAL],
  },
  {
    key: "magic_formula_20",
    slug: "kospi-3y-magic-formula-20",
    name: "마법공식(ROIC·EV/EBIT) 전략",
    rule: "분기마다 ROIC 높은 순위·EV/EBIT 낮은 순위 평균 상위 20종목 보유",
    intro: [
      "마법공식은 조엘 그린블라트가 소개한 방법으로, 자본 대비 이익을 잘 내는 회사(높은 ROIC)를 이익 대비 싼 가격(낮은 EV/EBIT)에 사는 규칙입니다. 두 순위를 합쳐 상위 종목을 고릅니다.",
    ],
    conditions: ["후보: EV/EBIT이 0보다 큰 종목(영업이익 적자 제외)", "분기 첫 거래일에 ROIC 높은 순위와 EV/EBIT 낮은 순위를 평균해 상위 20종목을 고릅니다.", "종목당 자본의 5%"],
    engine: RANK_ENGINE("ev_ebit > 0", "composite(roic 높은 순, ev_ebit 낮은 순, 동일 가중)", "20종목, 종목당 5%", "quarterly(분기 첫 거래일)"),
    commentary: [
      "투자 수익률 +51.05%, 최대 낙폭 −33.28%였고, 거래는 57회, 평균 보유 기간은 254일이었습니다. 순위 상위에 계속 남은 종목은 교체하지 않아 보유가 길었습니다. 승률 52.6%, 손익비 2.57이었습니다.",
      "연도별로는 2024년 −15.1%, 2025년 +32.7%, 2026년 +25.3%였습니다. 시작일을 바꿔도 +48.35%~+51.05%로 결과가 안정적이었습니다.",
    ],
    caveats: [
      "원래 방법은 1년마다 교체하고 금융·유틸리티 업종을 빼지만, 여기서는 분기마다 교체했고 업종을 빼지 않았습니다.",
      "재무 값은 공시가 공개된 날부터 씁니다(공개일을 모르면 결산일 90일 뒤부터).",
    ],
    related: ["kospi-3y-low-per-pbr-20", "myth-06-quality-hold", GUIDE_REBAL],
  },
];

export const CLASSIC_NOTES: GuideArticle[] = CLASSICS.map(buildNote);

/** 결과 JSON의 규칙 이름 → 노트 slug — 원본 결과를 ResearchNoteResult에 올릴 때 쓴다. */
export const CLASSIC_SLUG_BY_RULE = Object.fromEntries(CLASSICS.map((c) => [c.key, c.slug])) as Record<RuleKey, string>;

/** 유명 기법 노트가 근거로 삼은 결과 데이터(Dataset 구조화 데이터). 이 묶음의 글이 아니면 undefined. */
export function classicNoteDataset(slug: string): BacktestDataset | undefined {
  const c = CLASSICS.find((item) => item.slug === slug);
  return c ? dataset(c, CLASSIC_RESULTS[c.key]) : undefined;
}
