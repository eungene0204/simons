// 연구노트 — 뉴스 전략 기록. 뉴스 기사(주로 연합뉴스)에서 떠올린 규칙 하나를 널스탁에 문장으로 입력해 과거 데이터에 적용한 결과다.
//
// 원본은 `newsNotes.data.json` — 뉴스 전략 테스트 산출물(~/nullstock-news)에서
// `.claude/skills/news-strategy-test/scripts/build_news_notes.py`가 숫자를 다시 계산하지 않고 옮겨 만든다(사진은 public/notes/news).
// 표현은 규제 안전 원칙을 따른다(CLAUDE.md) — 기사와 결과의 인과, 규칙의 우열, 전망을 말하지 않고 관측된 값만 기록한다.
// 종목명은 결과 서술에 싣지 않는다(입력 문장·기사 제목은 원문 그대로). 순수 데이터 모듈이다(react·next 의존 없음).
//
// 글 구성은 AI 답변 엔진이 인용하기 좋은 순서다(2026-11-08): 제목은 사람이 묻는 말(규칙 이름 + 백테스트 결과 + 연도),
// 요약·첫 절에 결과 수치, 그다음 규칙·해석·기사·계산 기준. 문장·FAQ는 앞뒤 없이 잘려도 뜻이 통하도록 규칙 이름·구간·수치를 자체로 갖는다.
// 숫자 없는 공통 문구를 늘리지 않는다 — 같은 틀의 글이 대량으로 쌓이므로 글마다 다른 것은 계산 결과뿐이어야 한다.

import type { GuideArticle, GuideFaq, GuideImage, GuideSection } from "@/lib/guide/articles";
import type { BacktestDataset } from "@/lib/guide/jsonLd";
import NEWS_DATA from "./newsNotes.data.json";

type Row = [string, string];

type Photo = { key: "overview" | "dist"; src: string; caption: string; width: number; height: number };

type NewsStrategy = {
  slug: string;
  /** 계산일 = 기사 날짜(YYYY-MM-DD). */
  date: string;
  engine: string;
  news: { title: string; link: string; published: string };
  /** 기사에서 규칙을 떠올린 이유 한 줄. */
  why: string;
  name: string;
  /** 입력 문장(원문). 열기 링크가 이 문장을 쓴다. */
  prompt: string;
  /** 해석 카드의 (칸 이름, 값). */
  card: string[][];
  /** 문장에 없어 화면의 선택지로 정한 값. */
  answered: string[];
  period: string[] | null;
  cost: string | null;
  metrics: {
    ret: string;
    profit: string;
    cagr: string;
    mdd: string;
    sharpe: string;
    trades: string;
    win: string;
    pf: string;
    avgWin: string | null;
    avgLoss: string | null;
    hold: string | null;
    benchName: string;
    bench: string;
  };
  interpretation: string[];
  photos: Photo[];
};

const NEWS = NEWS_DATA as NewsStrategy[];

const GUIDE_READ = "how-to-read-backtest-results";

/** 기사 제목에 추천·전망·보장류 표현이 있으면 출처 링크 글자로 옮기지 않는다 — 제3자 문구라도 우리 화면에 실린다(2026-11-07).
 *  `notes.test.ts`의 규제 표현 검사와 같은 낱말이다(그 검사가 출처 칸도 본다). */
const REGULATED_WORDING = /추천|유망|권장|전망|보장|고수익|적합|우수|유리/;

function dayLabel(date: string): string {
  const [, month, day] = date.split("-");
  return `${Number(month)}월 ${Number(day)}일`;
}

function periodLabel(n: NewsStrategy): string {
  return n.period ? `${n.period[0]}~${n.period[1]}` : "최근 5년";
}

function yearsLabel(n: NewsStrategy): string {
  return n.period ? `${n.period[0].slice(0, 4)}~${n.period[1].slice(0, 4)}년` : "최근 5년";
}

/** 전략 수익률과 벤치마크의 표시값 차이(%p) — 해석 절의 '벤치마크 비교'와 같은 산술이다. */
function benchmarkGap(n: NewsStrategy): string {
  const percent = (value: string) => Number(value.replace("−", "-").replace(/[+%,]/g, ""));
  const gap = percent(n.metrics.ret) - percent(n.metrics.bench);
  return `${gap < 0 ? "−" : "+"}${Math.abs(gap).toFixed(2)}%p`;
}

/** FAQ '매수·매도 조건' 답에 싣는 해석 카드 칸 — 자금·기간처럼 규칙이 아닌 칸은 뺀다. */
const RULE_LABELS = new Set(["유니버스", "대상 종목", "투자 대상", "업종", "매수 조건", "매도 조건", "최대 보유", "리밸런싱"]);

function resultRows(n: NewsStrategy): Row[] {
  const m = n.metrics;
  const rows: Row[] = [
    ["기간", periodLabel(n)],
    ["투자 수익률", m.ret],
    ["총 수익", m.profit],
    ["CAGR", m.cagr],
    ["최대 낙폭", m.mdd],
    ["샤프 / 소티노", m.sharpe],
    ["거래 수", m.trades],
    ["승률", m.win],
    ["손익비", m.pf],
  ];
  if (m.avgWin) rows.push(["평균 수익 거래", m.avgWin]);
  if (m.avgLoss) rows.push(["평균 손실 거래", m.avgLoss]);
  if (m.hold) rows.push(["평균 보유", m.hold]);
  rows.push(["같은 기간 벤치마크", `${m.benchName} ${m.bench}`]);
  return rows;
}

function images(n: NewsStrategy, key: Photo["key"]): GuideImage[] {
  return n.photos
    .filter((photo) => photo.key === key)
    .map((photo) => ({
      src: photo.src,
      alt: `${n.name} 백테스트 결과 화면 — ${photo.caption}`,
      caption: photo.caption,
      width: photo.width,
      height: photo.height,
    }));
}

function buildNote(n: NewsStrategy, related: string[]): GuideArticle {
  const m = n.metrics;
  const period = periodLabel(n);
  const costClause = n.cost ? `${n.cost}를 매 거래에 반영` : "거래 비용을 반영";
  const footnote = `${period}, 신호 다음 거래일 시가 체결${n.cost ? `, ${n.cost}` : ""}. 널스탁 백테스트 엔진 v${n.engine}으로 ${n.date}에 계산했습니다.`;

  const sections: GuideSection[] = [
    {
      heading: `${n.name} 백테스트 결과`,
      paragraphs: [
        `“${n.name}” 규칙의 ${period} 투자 수익률은 ${m.ret}(총 수익 ${m.profit})이고, 같은 기간 ${m.benchName}의 수익률 ${m.bench}와 ${benchmarkGap(n)} 차이가 났습니다. 전략과 벤치마크는 구성과 규칙이 다르므로 이 차이는 우열을 뜻하지 않습니다.`,
      ],
      table: {
        caption: `${n.name} — 백테스트 결과`,
        headers: ["지표", "값"],
        rows: resultRows(n),
        footnote,
      },
      images: images(n, "overview"),
    },
    {
      heading: "전략 규칙과 설정값",
      paragraphs: [
        "널스탁에 아래 문장을 그대로 입력했습니다.",
        `“${n.prompt}”`,
        ...(n.answered.length > 0 ? [`문장에 없던 설정은 화면의 선택지로 정했습니다: ${n.answered.join(" · ")}.`] : []),
      ],
      bullets: n.card.map(([label, value]) => `${label}: ${value}`),
    },
    {
      heading: "결과 해석",
      paragraphs: [`“${n.name}” 규칙의 ${period} 결과를 백테스트 로그와 지표의 값으로 풀었습니다. 평가가 아니라 산술입니다.`],
      bullets: n.interpretation,
      images: images(n, "dist"),
    },
    {
      heading: "이 규칙을 떠올린 기사",
      paragraphs: [
        `${dayLabel(n.date)} 기사를 보고 떠올린 규칙 하나를 과거 데이터에 적용한 기록입니다. 기사에서 옮긴 생각은 이렇습니다: ${n.why}.`,
        "이 노트는 기사 내용과 결과 사이의 관계를 말하지 않습니다. 기사는 규칙을 떠올린 계기일 뿐이고, 위 숫자는 같은 규칙이 과거 구간에서 낸 값입니다.",
      ],
      source: { label: REGULATED_WORDING.test(n.news.title) ? "기사 원문 보기" : n.news.title, href: n.news.link },
    },
    {
      heading: "계산 기준과 한계",
      paragraphs: [
        `“${n.name}” 결과는 널스탁 백테스트 엔진 v${n.engine}으로 ${n.date}에 직접 계산한 값입니다. 매매는 신호 다음 거래일 시가에 체결한다고 가정했고 ${costClause}했습니다.`,
        "이 기록은 한 가지 유니버스·기간·설정 조합의 과거 시뮬레이션 결과입니다. 다른 기간이나 값에서는 다른 결과가 나올 수 있고, 기사에 나온 사건이 앞으로의 가격에 어떤 영향을 줄지와는 관계가 없습니다.",
      ],
    },
  ];

  const rules = n.card.filter(([label]) => RULE_LABELS.has(label)).map(([label, value]) => `${label} ${value}`);
  const faq: GuideFaq[] = [
    {
      question: `${n.name} 백테스트 수익률은 얼마인가요?`,
      answer: `${period} 구간의 투자 수익률은 ${m.ret}, CAGR은 ${m.cagr}였습니다. 같은 기간 ${m.benchName}의 수익률은 ${m.bench}였습니다. 신호 다음 거래일 시가 체결과 거래 비용을 반영한 과거 시뮬레이션 값입니다.`,
    },
    {
      question: `${n.name} 백테스트의 최대 낙폭과 승률은 얼마인가요?`,
      answer: `${period} 과거 데이터 백테스트에서 최대 낙폭은 ${m.mdd}, 승률은 ${m.win}, 거래 수는 ${m.trades}, 손익비는 ${m.pf}였습니다.`,
    },
    {
      question: `${n.name} 규칙의 매수·매도 조건은 무엇인가요?`,
      answer: `널스탁이 입력 문장을 해석한 조건은 ${rules.join(", ")}입니다.`,
    },
    {
      question: "이 결과가 기사 내용 때문에 나온 것인가요?",
      answer:
        "아닙니다. 기사는 규칙을 떠올린 계기일 뿐이고, 결과는 기사보다 앞선 과거 데이터에 규칙을 적용해 계산한 값입니다. 기사와 결과 사이의 인과는 확인하지 않았습니다.",
    },
    {
      question: "표의 벤치마크와의 차이는 무엇을 뜻하나요?",
      answer: `같은 기간 지수 ETF의 수익률(${m.bench})과 전략 수익률(${m.ret})을 표시값 그대로 비교하는 용도입니다. 전략은 조건에 맞는 종목만 보유하고 ETF는 지수 전체를 보유하므로 구성과 규칙이 달라 우열을 가리는 값은 아닙니다.`,
    },
  ];

  return {
    slug: n.slug,
    title: `${n.name} 백테스트 결과 (${yearsLabel(n)})`,
    description: `“${n.name}” 규칙을 ${period} 한국 주식 과거 데이터로 백테스트한 투자 수익률은 ${m.ret}, 최대 낙폭은 ${m.mdd}였습니다. 기사에서 출발한 뉴스 전략의 입력 문장, 조건, 비용 가정과 결과 표를 기록했습니다.`,
    summary: `널스탁 백테스트 기준, ${period} 구간에 “${n.name}” 규칙을 적용한 투자 수익률은 ${m.ret}, CAGR은 ${m.cagr}, 최대 낙폭은 ${m.mdd}, 승률은 ${m.win}(거래 ${m.trades})였습니다. 같은 기간 벤치마크 ${m.benchName}의 수익률은 ${m.bench}였습니다.`,
    published: n.date,
    updated: n.date,
    sections,
    related,
    faq,
  };
}

/** 같은 날 다른 뉴스 전략 두 편과 결과 읽는 법 가이드를 함께 읽을 글로 건다. */
function relatedOf(n: NewsStrategy): string[] {
  const sameDay = NEWS.filter((other) => other.date === n.date && other.slug !== n.slug).slice(0, 2);
  return [...sameDay.map((other) => other.slug), GUIDE_READ];
}

export const NEWS_NOTES: GuideArticle[] = NEWS.map((n) => buildNote(n, relatedOf(n)));

/** Article의 isBasedOn으로 잇는 결과 데이터 — DB 노트에는 이 필드가 없으므로 원본에서 slug로 찾는다. 뉴스 글이 아니면 undefined. */
export function newsNoteDataset(slug: string): BacktestDataset | undefined {
  const n = NEWS.find((item) => item.slug === slug);
  if (!n) return undefined;
  return {
    name: `${n.name} ${periodLabel(n)} 백테스트 결과`,
    description: `한국 주식 일별 가격 기반, 신호 다음 거래일 시가 체결${n.cost ? `, ${n.cost}` : ""}. 널스탁 백테스트 엔진 v${n.engine}으로 ${n.date}에 계산했습니다.`,
    ...(n.period ? { temporalCoverage: `${n.period[0]}/${n.period[1]}` } : {}),
    variableMeasured: ["투자 수익률", "CAGR", "최대 낙폭(MDD)", "승률", "거래 수", "같은 기간 벤치마크 수익률"],
  };
}

/** "이 전략 그대로 열기" 링크에 넣을 입력 문장 — DB 노트에는 이 필드가 없으므로 원본에서 slug로 찾는다. 뉴스 글이 아니면 undefined. */
export function newsNoteOpenPrompt(slug: string): string | undefined {
  return NEWS.find((n) => n.slug === slug)?.prompt;
}
