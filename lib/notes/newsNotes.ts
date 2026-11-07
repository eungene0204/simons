// 연구노트 — 뉴스 전략 기록. 뉴스 기사(주로 연합뉴스)에서 떠올린 규칙 하나를 널스탁에 문장으로 입력해 과거 데이터에 적용한 결과다.
//
// 원본은 `newsNotes.data.json` — 뉴스 전략 테스트 산출물(~/nullstock-news)에서
// `.claude/skills/news-strategy-test/scripts/build_news_notes.py`가 숫자를 다시 계산하지 않고 옮겨 만든다(사진은 public/notes/news).
// 표현은 규제 안전 원칙을 따른다(CLAUDE.md) — 기사와 결과의 인과, 규칙의 우열, 전망을 말하지 않고 관측된 값만 기록한다.
// 종목명은 결과 서술에 싣지 않는다(입력 문장·기사 제목은 원문 그대로). 순수 데이터 모듈이다(react·next 의존 없음).

import type { GuideArticle, GuideFaq, GuideImage, GuideSection } from "@/lib/guide/articles";
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
  const footnote = `${period}, 신호 다음 거래일 시가 체결${n.cost ? `, ${n.cost}` : ""}. 널스탁 백테스트 엔진 v${n.engine}으로 ${n.date}에 계산했습니다.`;

  const sections: GuideSection[] = [
    {
      heading: "출발한 기사",
      paragraphs: [
        `${dayLabel(n.date)} 기사를 보고 떠올린 규칙 하나를 과거 데이터에 적용한 기록입니다. 기사에서 옮긴 생각은 이렇습니다: ${n.why}.`,
        "이 노트는 기사 내용과 결과 사이의 관계를 말하지 않습니다. 기사는 규칙을 떠올린 계기일 뿐이고, 아래 숫자는 같은 규칙이 과거 구간에서 낸 값입니다.",
      ],
      source: { label: REGULATED_WORDING.test(n.news.title) ? "기사 원문 보기" : n.news.title, href: n.news.link },
    },
    {
      heading: "입력한 문장과 해석된 조건",
      paragraphs: [
        "널스탁에 아래 문장을 그대로 입력했습니다.",
        `“${n.prompt}”`,
        ...(n.answered.length > 0 ? [`문장에 없던 설정은 화면의 선택지로 정했습니다: ${n.answered.join(" · ")}.`] : []),
      ],
      bullets: n.card.map(([label, value]) => `${label}: ${value}`),
    },
    {
      heading: "결과",
      paragraphs: [
        `${period} 구간에서 관측된 값입니다. 전략과 벤치마크는 구성과 규칙이 다르므로 표의 차이는 우열을 뜻하지 않습니다.`,
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
      heading: "결과 해석",
      paragraphs: ["결과 숫자가 어떻게 나왔는지 로그와 지표의 값으로 풀었습니다. 평가가 아니라 산술입니다."],
      bullets: n.interpretation,
      images: images(n, "dist"),
    },
    {
      heading: "읽을 때 주의할 점",
      paragraphs: [
        "이 기록은 한 가지 유니버스·기간·설정 조합의 과거 시뮬레이션 결과입니다. 다른 기간이나 값에서는 다른 결과가 나올 수 있고, 기사에 나온 사건이 앞으로의 가격에 어떤 영향을 줄지와는 관계가 없습니다.",
      ],
    },
  ];

  const faq: GuideFaq[] = [
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
    title: `뉴스 전략 백테스트 — ${n.name} (${dayLabel(n.date)} 기사)`,
    description: `${dayLabel(n.date)} 기사에서 출발해 “${n.name}” 규칙을 ${period} 과거 데이터에 적용한 기록입니다. 입력 문장, 해석된 조건, 결과 수치와 결과 화면 사진을 담았습니다.`,
    summary: `${period} 구간에 “${n.name}” 규칙을 적용했더니 투자 수익률은 ${m.ret}, CAGR은 ${m.cagr}, 최대 낙폭은 ${m.mdd}, 승률은 ${m.win}(${m.trades})였고 같은 기간 벤치마크(${m.benchName})는 ${m.bench}였습니다.`,
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

/** "이 전략 그대로 열기" 링크에 넣을 입력 문장 — DB 노트에는 이 필드가 없으므로 원본에서 slug로 찾는다. 뉴스 글이 아니면 undefined. */
export function newsNoteOpenPrompt(slug: string): string | undefined {
  return NEWS.find((n) => n.slug === slug)?.prompt;
}
