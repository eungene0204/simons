"use client";

import { useMemo, useState } from "react";

type ExampleCategory = "가치투자" | "기술분석" | "모멘텀" | "복합전략" | "AI 전략";
type ExampleLevel = "beginner" | "intermediate" | "expert";

interface Example {
  level: ExampleLevel;
  category: ExampleCategory;
  title: string;
  prompt: string;
}

const EXAMPLES: Example[] = [
  {
    level: "beginner",
    category: "가치투자",
    title: "저PBR 대형주 장기보유",
    prompt: "주식은 아직 초보라서 너무 복잡한 조건 말고 이해하기 쉬운 전략으로 하고 싶어요. KOSPI 대형주 중에서 PBR이 1배 이하인 종목만 골라서 8종목 정도 나눠 사고, 한 번 사면 최소 6개월은 들고 가고 싶습니다. 큰 손실은 무서우니 -12% 손절만 넣어 주세요.",
  },
  {
    level: "beginner",
    category: "기술분석",
    title: "이평선 골든크로스 따라가기",
    prompt: "차트를 보니까 단기 이동평균선이 장기 이동평균선을 위로 뚫을 때 많이들 들어간다고 하더라고요. KOSPI 종목 중 골든크로스가 나오면 매수하고, 반대로 데드크로스가 나오면 매도하는 식으로 간단하게 만들어 주세요. 종목은 최대 10개, 손절은 -8%로 부탁드립니다.",
  },
  {
    level: "beginner",
    category: "모멘텀",
    title: "신고가 돌파주 짧게 보유",
    prompt: "뉴스에 자주 나오는 강한 종목을 짧게 타보는 전략을 써보고 싶어요. KOSDAQ에서 52주 신고가를 새로 만들고 거래량도 평소보다 확 늘어난 종목이 나오면 들어가고, 너무 오래 끌지는 말고 20일 정도 지나면 정리해 주세요. 최대 6종목, 손절은 -10%로 해주세요.",
  },
  {
    level: "beginner",
    category: "복합전략",
    title: "저평가 + RSI 과매도 반등",
    prompt: "완전 단타보다는 어느 정도 싼 종목을 조금 더 안전하게 사고 싶습니다. KOSPI에서 PER 10 이하인 종목 중 RSI가 30 아래로 내려갔다가 다시 올라오는 종목만 매수하게 해주세요. 종목 수는 8개 정도로 제한하고, 수익이 15% 나면 팔고 손절은 -8%면 좋겠습니다.",
  },
  {
    level: "beginner",
    category: "AI 전략",
    title: "AI가 고른 상승 후보 따라가기",
    prompt: "아직 직접 종목을 고를 자신은 없어서 우리 AI 모델이 단기 상승 가능성이 높다고 판단하는 종목만 따라가 보고 싶어요. KOSPI 종목 중 AI가 매수 후보로 보는 종목을 5개 정도만 골라서 사고, AI가 하락으로 바뀌면 바로 팔아 주세요. 너무 큰 손실은 싫어서 손절은 -7%로 부탁드립니다.",
  },
  {
    level: "beginner",
    category: "가치투자",
    title: "우량주 천천히 모으기",
    prompt: "너무 급하게 사고파는 건 자신이 없어서 실적이 괜찮은 큰 회사들 위주로 천천히 투자하고 싶어요. KOSPI에서 ROE 10% 이상이고 부채비율이 100% 이하인 종목만 골라서 10종목 정도 나눠 사고, 3개월마다 다시 점검해 주세요. 손절은 -10% 정도로만 넣어 주세요.",
  },
  {
    level: "intermediate",
    category: "가치투자",
    title: "저PBR 우량주 분기 점검",
    prompt: "KOSPI 종목 중 PBR이 1.5배 이하이고 ROE가 8% 이상인 기업만 골라서 12종목 정도로 포트폴리오를 만들고 싶습니다. 너무 잦은 매매는 피하고 싶으니 분기마다 조건을 다시 확인해서 리밸런싱해 주세요. 손절은 -12%로 설정해 주세요.",
  },
  {
    level: "intermediate",
    category: "기술분석",
    title: "MACD + RSI 확인 매매",
    prompt: "KOSDAQ 종목 중 MACD 골든크로스가 발생하고 RSI가 50 이상으로 올라온 경우만 진입하고 싶습니다. 단순 반등보다 추세가 실제로 붙는 종목만 고르려는 의도입니다. MACD 데드크로스가 나오거나 RSI가 다시 45 아래로 밀리면 정리하고, 최대 10종목, 손절 -9%, 익절 +18%로 부탁드립니다.",
  },
  {
    level: "intermediate",
    category: "복합전략",
    title: "저평가 업종 내 거래대금 필터",
    prompt: "KOSPI에서 PBR 1.2배 이하이면서 최근 20일 평균 거래대금이 30억 원 이상인 종목만 대상으로 보고 싶습니다. 너무 거래가 없는 종목은 제외하고 싶고, 그 안에서 20일 신고가 돌파가 나오면 진입하는 방식으로 구성해 주세요. 최대 12종목, 월간 리밸런싱, 손절 -10%, 익절 +20% 조건으로 백테스트할 수 있게 해주세요.",
  },
  {
    level: "intermediate",
    category: "AI 전략",
    title: "AI 예측 + 재무 건전성 필터",
    prompt: "AI 예측을 그대로 믿기보다는 기본 재무 필터를 같이 걸고 싶습니다. KOSPI 종목 중 ROE 10% 이상, 부채비율 150% 이하인 기업만 남긴 뒤 AI가 상승 확률이 높다고 보는 종목에만 들어가 주세요. AI가 하락으로 바뀌면 바로 매도하고, 종목 수는 10개, 손절은 -10%로 운영하고 싶습니다.",
  },
  {
    level: "intermediate",
    category: "모멘텀",
    title: "거래량 급증 + EMA 추세 확인",
    prompt: "KOSPI 종목 중 최근 거래량이 평소보다 2배 이상 늘어난 날만 관심 대상으로 보고 싶습니다. 그중 5일 EMA가 20일 EMA 위에 있는 종목만 매수해서 추세가 살아 있는 종목만 담고 싶고, 5일 EMA가 다시 20일 EMA 아래로 내려오면 정리해 주세요. 최대 10종목, 손절 -8%, 익절 +15%로 부탁드립니다.",
  },
  {
    level: "intermediate",
    category: "AI 전략",
    title: "AI + 돌파매매 확인",
    prompt: "우리 AI 모델이 상승 가능성이 높다고 보는 종목 중에서도 너무 이른 진입은 피하고 싶습니다. KOSDAQ에서 AI 매수 신호가 나온 후보 가운데 20일 신고가를 돌파한 종목만 진입하게 해주세요. AI가 하락으로 바뀌거나 돌파 후 10거래일 안에 힘을 못 쓰면 정리하고, 최대 8종목, 손절은 -9%로 운영하고 싶습니다.",
  },
  {
    level: "expert",
    category: "복합전략",
    title: "중형주 퀄리티-밸류-모멘텀 결합",
    prompt: "KOSPI와 KOSDAQ 합산 유니버스에서 시가총액 3000억 원 이상 3조 원 이하 중형주만 대상으로 보겠습니다. 최근 분기 기준 ROE 15% 이상, 부채비율 80% 이하, PBR 1.5배 이하로 1차 스크리닝한 뒤, 60일 신고가 돌파와 20일 평균 거래대금 50억 원 이상이 동시에 확인될 때만 진입해 주세요. 포트폴리오는 최대 12종목 동일가중, 월 1회 리밸런싱, 개별 종목 손절 -7%, 익절 +22% 조건으로 설정해 주세요.",
  },
  {
    level: "expert",
    category: "모멘텀",
    title: "ADX 추세 강도 기반 스윙",
    prompt: "KOSDAQ 150 구성 종목 중 ADX가 25 이상으로 올라오고 +DI가 -DI를 상향 돌파하는 시점만 매수 대상으로 잡아 주세요. 추세 강도가 실제로 확인된 구간만 거래하고 싶고, 진입 후에는 10일 EMA를 종가 기준으로 이탈하면 청산하는 식으로 운용하겠습니다. 동시 보유는 최대 8종목, 보유 기간 상한은 30거래일, 손절 -6% 조건을 넣어 주세요.",
  },
  {
    level: "expert",
    category: "가치투자",
    title: "현금흐름 중심 저평가 포트폴리오",
    prompt: "KOSPI 200 종목 중 PER 15배 이하, PBR 1.3배 이하, ROE 14% 이상 조건을 만족하는 기업을 먼저 선별하고 싶습니다. 여기에 최근 4개 분기 기준으로 수익성이 안정적이라고 볼 수 있는 종목만 담는다는 가정으로 분기 리밸런싱 전략을 구성해 주세요. 20종목 동일 비중으로 편입하고, 시장 급락 구간 대응을 위해 종목별 손절은 -12%로 제한하겠습니다.",
  },
  {
    level: "expert",
    category: "AI 전략",
    title: "AI 예측과 기술 신호 이중 확인",
    prompt: "AI 상승 예측 신호를 메인 알파로 쓰되 노이즈를 줄이기 위해 기술 조건을 추가하고 싶습니다. KOSPI 종목 중 AI가 상승으로 분류한 후보 가운데 5일 EMA가 20일 EMA를 상향 돌파했고 RSI가 55 이상인 경우에만 진입해 주세요. 청산은 AI 하락 전환, EMA 데드크로스, 또는 +18% 익절 중 먼저 도달하는 조건으로 하고, 포트폴리오는 최대 10종목, 손절은 -8%, 주간 리밸런싱으로 부탁드립니다.",
  },
  {
    level: "expert",
    category: "기술분석",
    title: "볼린저 수축 후 확장 돌파",
    prompt: "KOSPI 200 종목 중 최근 20일 기준 볼린저밴드 폭이 과거 대비 충분히 축소된 뒤 상단 돌파가 나오는 케이스만 진입 대상으로 설정해 주세요. 변동성 수축 이후 확장 국면만 노리려는 의도이며, 진입 후에는 종가가 20일선 아래로 이탈하면 청산하겠습니다. 동시 보유 10종목 제한, 개별 손절 -6%, 익절 +20% 조건을 적용해 주세요.",
  },
  {
    level: "expert",
    category: "AI 전략",
    title: "AI 스코어 기반 주간 로테이션",
    prompt: "우리 AI 모델의 예측 점수를 랭킹 신호처럼 활용하는 전략을 만들고 싶습니다. KOSPI와 KOSDAQ 전체 유니버스에서 유동성 하위 종목은 제외하고, 매주 AI 상승 점수가 높은 상위 15종목만 동일 비중으로 편입해 주세요. 다음 주 리밸런싱 때 점수가 밀린 종목은 교체하고, 종목별 손절은 -8%로 제한해 주세요.",
  },
];

const CATEGORY_STYLE: Record<ExampleCategory, { label: string; color: string; bg: string; border: string }> = {
  가치투자: { label: "가치투자", color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  기술분석: { label: "기술분석", color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/20" },
  모멘텀: { label: "모멘텀", color: "text-violet-400", bg: "bg-violet-500/10", border: "border-violet-500/20" },
  복합전략: { label: "복합전략", color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/20" },
  "AI 전략": { label: "AI 전략", color: "text-pink-400", bg: "bg-pink-500/10", border: "border-pink-500/20" },
};

const LEVEL_META: Record<ExampleLevel, { label: string; description: string }> = {
  beginner: {
    label: "초보자 예시",
    description: "용어를 많이 쓰지 않고, 손실이 무섭거나 오래 들고 가고 싶다는 식으로 입력하는 패턴입니다.",
  },
  intermediate: {
    label: "중급자 예시",
    description: "재무 필터와 기술 지표를 함께 쓰고, 리밸런싱과 유동성 조건까지 직접 넣는 수준입니다.",
  },
  expert: {
    label: "전문가 예시",
    description: "유니버스, 팩터 정의, 유동성, 리스크 관리 규칙까지 명시하는 실제 운용자 스타일입니다.",
  },
};

export function StrategyExampleTabs({ onSelectExample }: { onSelectExample: (prompt: string) => void }) {
  const [activeLevel, setActiveLevel] = useState<ExampleLevel>("beginner");

  const visibleExamples = useMemo(
    () => EXAMPLES.filter((example) => example.level === activeLevel),
    [activeLevel]
  );

  return (
    <div className="w-full space-y-3">
      <div className="space-y-2 text-center">
        <div className="mx-auto inline-flex w-full max-w-2xl rounded-2xl border border-white/[0.06] bg-white/[0.02] p-1">
          {(Object.keys(LEVEL_META) as ExampleLevel[]).map((level) => {
            const isActive = level === activeLevel;
            return (
              <button
                key={level}
                type="button"
                onClick={() => setActiveLevel(level)}
                className={`flex-1 rounded-xl px-3 py-2.5 text-xs font-black transition-all duration-200 ${
                  isActive
                    ? "bg-[var(--main-blue)] text-white shadow-[0_8px_30px_rgba(59,130,246,0.28)]"
                    : "text-gray-400 hover:bg-white/[0.04] hover:text-white"
                }`}
              >
                {LEVEL_META[level].label}
              </button>
            );
          })}
        </div>
        <p className="text-xs font-bold text-gray-500 leading-relaxed max-w-2xl mx-auto">
          {LEVEL_META[activeLevel].description}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {visibleExamples.map((example) => {
          const style = CATEGORY_STYLE[example.category];
          return (
            <button
              key={example.title}
              type="button"
              onClick={() => onSelectExample(example.prompt)}
              className="group text-left rounded-2xl border border-white/[0.05] hover:border-white/[0.12] bg-white/[0.02] hover:bg-white/[0.04] px-4 py-4 transition-all duration-200 space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className={`inline-flex items-center text-[10px] font-black px-2 py-1 rounded-md ${style.bg} ${style.border} border ${style.color}`}>
                  {style.label}
                </span>
                <span className="text-[10px] font-black uppercase tracking-widest text-gray-600">입력 예시</span>
              </div>
              <p className="text-sm font-black text-white/85 group-hover:text-white leading-snug">{example.title}</p>
              <p className="text-xs font-bold text-gray-400 group-hover:text-gray-300 leading-relaxed line-clamp-5">
                {example.prompt}
              </p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
