"use client";

import { useEffect, useMemo, useState } from "react";

type ExampleCategory = "가치투자" | "기술분석" | "모멘텀" | "복합전략" | "AI 전략";
type ExampleLevel = "beginner" | "intermediate" | "expert";

interface Example {
  level: ExampleLevel;
  category: ExampleCategory;
  title: string;
  prompt: string;
}

const DEFAULT_VISIBLE_COUNT = 6;

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
    level: "beginner",
    category: "기술분석",
    title: "박스권 상단 돌파 따라가기",
    prompt: "복잡한 지표는 아직 어려워서 최근 한 달 동안 가격이 갇혀 있던 박스권을 위로 돌파하는 종목만 사고 싶어요. KOSPI 종목 중 20일 고점을 넘기는 날 매수하고 다시 박스 안으로 내려오면 매도해 주세요. 최대 8종목, 손절은 -7%로 부탁드립니다.",
  },
  {
    level: "beginner",
    category: "모멘텀",
    title: "최근 수익률 좋은 종목만 담기",
    prompt: "최근 3개월 동안 꾸준히 오른 종목을 따라가는 전략을 써보고 싶어요. KOSDAQ에서 최근 60거래일 수익률이 높은 종목 상위권만 골라서 6종목 정도 나눠 사고, 한 달에 한 번씩 다시 순위를 확인해 주세요. 손절은 -9%로 해주세요.",
  },
  {
    level: "beginner",
    category: "복합전략",
    title: "배당주 + 눌림목 진입",
    prompt: "배당도 어느 정도 주는 안정적인 종목을 사고 싶은데 너무 비싸게 사고 싶지는 않아요. KOSPI에서 배당수익률이 높은 종목 중 20일 이동평균선 근처로 눌린 종목만 매수하게 해주세요. 종목 수는 8개 정도, 손절은 -8%, 보유 기간은 3개월 정도로 설정해 주세요.",
  },
  {
    level: "beginner",
    category: "AI 전략",
    title: "AI 추천주 주간 점검",
    prompt: "AI가 좋다고 보는 종목을 너무 자주 바꾸지 않고 주간 단위로 따라가고 싶어요. KOSPI에서 AI가 상승 후보로 분류한 종목 중 상위 5개만 매수하고, 매주 한 번씩 다시 점검해서 순위가 밀리면 교체해 주세요. 손절은 -6%로 부탁드립니다.",
  },
  {
    level: "beginner",
    category: "가치투자",
    title: "저PER 현금 많은 기업 고르기",
    prompt: "싼 종목 중에서도 현금이 충분한 회사를 골라서 비교적 편하게 보유하고 싶습니다. KOSPI 종목 중 PER이 낮고 부채비율이 낮은 기업만 남긴 뒤 8종목 정도 동일하게 투자해 주세요. 너무 큰 손실만 막고 싶어서 손절은 -10%, 점검은 두 달에 한 번이면 좋겠습니다.",
  },
  {
    level: "beginner",
    category: "기술분석",
    title: "20일선 위 종목만 보유",
    prompt: "추세가 완전히 꺾인 종목은 피하고 싶어서 20일 이동평균선 위에 있는 종목만 담고 싶어요. KOSDAQ에서 종가가 20일선 위에 있고 최근 거래량도 너무 적지 않은 종목을 7개 정도 사서, 20일선 아래로 내려오면 정리해 주세요. 손절은 -8%로 설정해 주세요.",
  },
  {
    level: "beginner",
    category: "모멘텀",
    title: "거래대금 붙은 상승주만 추종",
    prompt: "갑자기 움직이는 종목 중에서도 실제로 돈이 많이 들어오는 종목만 따라가고 싶어요. KOSPI에서 최근 거래대금이 크게 늘고 주가가 5일 연속 강한 종목만 매수해 주세요. 최대 6종목, 15거래일 정도 보유하고 손절은 -9%로 부탁드립니다.",
  },
  {
    level: "beginner",
    category: "복합전략",
    title: "실적 괜찮은 종목의 단순 추세 추종",
    prompt: "아예 테마주보다는 실적이 나오는 종목 중에 차트도 괜찮은 종목을 사고 싶어요. KOSPI에서 ROE가 양호한 기업 중 5일선이 20일선 위에 있는 종목만 매수하고, 추세가 꺾이면 매도해 주세요. 최대 8종목, 손절 -8%, 익절 +15%로 부탁드립니다.",
  },
  {
    level: "beginner",
    category: "AI 전략",
    title: "AI + 거래량 확인 입문형",
    prompt: "AI 추천만 그대로 따르기보다는 시장 관심이 붙은 종목만 들어가고 싶어요. KOSDAQ에서 AI가 상승으로 보는 종목 중 거래량이 최근 평균보다 많은 경우만 진입하게 해주세요. 종목은 5개만 보유하고 AI가 약세로 바뀌면 매도, 손절은 -7%로 설정해 주세요.",
  },
  {
    level: "beginner",
    category: "가치투자",
    title: "낮은 부채비율 우량주 보유",
    prompt: "안정적인 회사에 분산 투자하고 싶어서 빚이 적은 회사 위주로 골라주세요. KOSPI에서 부채비율이 낮고 ROE가 너무 나쁘지 않은 종목을 10개 정도 선정해서 3개월 이상 보유하는 전략으로 만들어 주세요. 손절은 -10%로만 넣어 주세요.",
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
    level: "intermediate",
    category: "가치투자",
    title: "현금흐름 + 저평가 조합",
    prompt: "KOSPI 종목 중 PBR 1.3배 이하이면서 영업활동현금흐름이 최근 분기 기준 흑자인 기업만 보고 싶습니다. 너무 오래 묶이기만 하는 종목은 피하고 싶어서 최근 60일 수익률이 시장보다 너무 약한 종목은 제외해 주세요. 최대 10종목, 분기 리밸런싱, 손절 -11%로 구성해 주세요.",
  },
  {
    level: "intermediate",
    category: "기술분석",
    title: "볼린저 중심선 재돌파 스윙",
    prompt: "KOSDAQ 종목 중 볼린저밴드 중심선 아래로 눌렸다가 다시 중심선을 회복하는 시점만 매수하고 싶습니다. 과열 돌파보다 눌림 후 재상승을 노리는 전략입니다. 상단 밴드 도달 시 절반 익절, 중심선 재이탈 시 전량 매도, 최대 9종목, 손절 -8%로 설정해 주세요.",
  },
  {
    level: "intermediate",
    category: "모멘텀",
    title: "상대강도 상위주 월간 교체",
    prompt: "KOSPI200 안에서 최근 3개월 상대강도가 높은 종목만 담고 싶습니다. 다만 거래대금이 너무 낮은 종목은 제외하고, 매월 한 번씩 순위를 다시 매겨 상위 10종목만 유지해 주세요. 개별 손절 -9%, 포트폴리오 전체 최대 보유 종목 수는 10개로 해주세요.",
  },
  {
    level: "intermediate",
    category: "복합전략",
    title: "퀄리티 필터 후 추세 진입",
    prompt: "KOSPI에서 ROE 12% 이상, 부채비율 120% 이하 종목을 먼저 고른 뒤 20일 EMA가 60일 EMA 위에 있는 종목만 담고 싶습니다. 재무가 괜찮은 종목 중 추세가 살아 있는 경우만 매수하는 전략입니다. 월간 리밸런싱, 최대 12종목, 손절 -10%, 익절 +18%로 부탁드립니다.",
  },
  {
    level: "intermediate",
    category: "AI 전략",
    title: "AI 예측 + 변동성 필터",
    prompt: "AI가 상승으로 보는 종목 중에서도 하루 변동성이 너무 큰 종목은 제외하고 싶습니다. KOSDAQ 종목에서 최근 20일 변동성이 과도하지 않은 종목만 남긴 뒤 AI 매수 신호가 유지되는 동안 보유하게 해주세요. 최대 8종목, 주간 리밸런싱, 손절 -8%로 설정해 주세요.",
  },
  {
    level: "intermediate",
    category: "가치투자",
    title: "배당 + 저PBR 월간 점검",
    prompt: "KOSPI에서 PBR 1배 이하이면서 최근 배당 이력이 꾸준한 종목을 중심으로 포트폴리오를 만들고 싶습니다. 거래가 너무 없는 종목은 제외하고 매월 조건을 다시 점검해 주세요. 최대 12종목, 동일 비중, 손절 -12%로 운영하고 싶습니다.",
  },
  {
    level: "intermediate",
    category: "기술분석",
    title: "이격도 과열 회피형 추세 추종",
    prompt: "KOSPI 종목 중 20일선 위에 있으면서도 주가가 20일선에서 너무 멀리 벌어지지 않은 종목만 진입하고 싶습니다. 과열 구간 추격은 피하되 추세는 유지되는 종목을 찾는 목적입니다. 20일선 이탈 시 매도, 최대 10종목, 손절 -7%, 익절 +16% 조건으로 부탁드립니다.",
  },
  {
    level: "intermediate",
    category: "모멘텀",
    title: "신고가 후 눌림목 재진입",
    prompt: "KOSDAQ에서 60일 신고가를 만든 뒤 5거래일 안에 크게 무너지지 않고 다시 거래량이 붙는 종목만 매수하고 싶습니다. 강한 종목의 2차 진입 구간을 노리는 전략입니다. 보유는 최대 15거래일, 동시 보유 8종목, 손절 -8%로 설정해 주세요.",
  },
  {
    level: "intermediate",
    category: "복합전략",
    title: "가치 + 모멘텀 혼합 리밸런싱",
    prompt: "KOSPI 종목 중 PER과 PBR이 낮은 편이면서 최근 60거래일 수익률도 양호한 종목을 함께 보고 싶습니다. 너무 단순한 저평가 함정은 피하고 싶은 의도입니다. 월 1회 리밸런싱으로 상위 10종목을 유지하고, 손절 -10%, 익절 +20%를 적용해 주세요.",
  },
  {
    level: "intermediate",
    category: "AI 전략",
    title: "AI + 이동평균 추세 유지",
    prompt: "AI 상승 예측이 나온 종목 중 20일 EMA가 60일 EMA 위에 있는 경우만 매수해 주세요. AI 신호만으로 진입하지 않고 기본 추세가 유지되는 종목만 담고 싶습니다. AI 하락 전환 또는 20일 EMA 이탈 시 청산, 최대 10종목, 손절 -9%로 부탁드립니다.",
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
    prompt: "KOSDAQ 종목 중 ADX가 25 이상으로 올라온 것이 확인된 후 5일 EMA가 20일 EMA를 상향 돌파하는 시점에만 매수해 주세요. 추세 강도가 실제로 확인된 구간만 거래하고 싶고, 진입 후에는 5일 EMA가 다시 20일 EMA 아래로 내려오면 청산하는 식으로 운용하겠습니다. 동시 보유는 최대 8종목, 보유 기간 상한은 30거래일, 손절 -6% 조건을 넣어 주세요.",
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
    prompt: "AI 상승 예측 신호를 메인 알파로 쓰되 노이즈를 줄이기 위해 기술 조건을 추가하고 싶습니다. KOSPI 종목 중 AI가 상승으로 분류한 후보 가운데 5일 EMA가 20일 EMA를 상향 돌파한 경우에만 진입해 주세요. 청산은 AI 하락 전환 또는 EMA 데드크로스 중 먼저 도달하는 조건으로 하고, 포트폴리오는 최대 10종목, 손절은 -8%, 익절 +18%, 월간 리밸런싱으로 부탁드립니다.",
  },
  {
    level: "expert",
    category: "기술분석",
    title: "볼린저밴드 상단 돌파 + 거래량 확인",
    prompt: "KOSPI200 종목 중 볼린저밴드 상단을 돌파하면서 거래량도 평소보다 급증한 종목만 진입 대상으로 설정해 주세요. 단순 상단 터치가 아닌 거래량으로 확인된 돌파만 노리려는 의도이며, 진입 후에는 볼린저밴드 하단에 닿으면 청산하겠습니다. 동시 보유 10종목 제한, 개별 손절 -6%, 익절 +20% 조건을 적용해 주세요.",
  },
  {
    level: "expert",
    category: "AI 전략",
    title: "AI 신호 기반 월간 로테이션",
    prompt: "KOSPI와 KOSDAQ 전체 유니버스에서 일평균 거래대금 50억 원 이상인 종목만 남긴 뒤, AI 모델이 상승 예측한 종목에 매수 진입해 주세요. AI가 하락으로 전환하면 즉시 청산하고, 매월 리밸런싱으로 포트폴리오를 재정비합니다. 최대 15종목 동일 비중으로 운용하고 종목별 손절은 -8%로 제한해 주세요.",
  },
  {
    level: "expert",
    category: "가치투자",
    title: "퀄리티 밸류 저변동 포트폴리오",
    prompt: "KOSPI 200 유니버스에서 PBR 1.4배 이하, ROE 12% 이상, 부채비율 100% 이하 조건을 만족하는 종목만 1차 선별해 주세요. 이후 최근 60거래일 변동성이 시장 평균보다 과도하게 높지 않은 종목만 남겨 15종목 동일가중 포트폴리오를 구성하고 분기 리밸런싱을 적용해 주세요. 종목별 손절 -10%, 포트폴리오 최대 낙폭 관리 목적의 현금 비중 10% 유지 조건도 반영해 주세요.",
  },
  {
    level: "expert",
    category: "기술분석",
    title: "다중 시간축 EMA 정렬 추세 전략",
    prompt: "KOSDAQ 유니버스에서 5일, 20일, 60일 EMA가 순차적으로 정배열된 종목만 매수 후보로 보겠습니다. 단기 눌림 후 재상승 구간만 진입하기 위해 종가가 5일 EMA를 회복한 시점에만 진입하고, 20일 EMA 이탈 또는 25거래일 경과 시 청산해 주세요. 동시 보유 8종목, 손절 -6%, 익절 +21% 조건으로 설정해 주세요.",
  },
  {
    level: "expert",
    category: "모멘텀",
    title: "상대강도 + 유동성 가중 로테이션",
    prompt: "KOSPI와 KOSDAQ 전체 종목 중 최근 120거래일 상대강도가 높은 상위 15% 종목을 추린 뒤, 일평균 거래대금 70억 원 이상인 종목만 남겨 주세요. 그 안에서 20일 신고가 경신 종목만 편입하고 월간 리밸런싱으로 최대 12종목 동일가중 포트폴리오를 유지하겠습니다. 손절 -7%, 보유 기간 상한 40거래일을 추가해 주세요.",
  },
  {
    level: "expert",
    category: "복합전략",
    title: "섹터 중립 퀄리티 모멘텀",
    prompt: "KOSPI 200을 섹터별로 나눈 뒤 각 섹터에서 ROE 14% 이상, 부채비율 80% 이하, 최근 60거래일 상대강도 상위 종목만 선별해 주세요. 특정 섹터 쏠림을 줄이기 위해 섹터당 최대 2종목만 편입하고 전체 포트폴리오는 10종목으로 제한하겠습니다. 월 1회 리밸런싱, 손절 -8%, 익절 +20%로 구성해 주세요.",
  },
  {
    level: "expert",
    category: "AI 전략",
    title: "AI 확률 점수 기반 랭킹 포트폴리오",
    prompt: "AI 모델이 산출하는 상승 확률 점수를 알파로 사용하되, KOSPI 유니버스 중 일평균 거래대금 100억 원 이상 종목만 대상으로 해주세요. 매주 상위 점수 10종목만 동일 비중으로 보유하고, 점수가 하위 30%로 밀리면 교체하는 랭킹 전략으로 구성해 주세요. 개별 손절 -7%, 포트폴리오 현금 5% 유지 조건을 반영해 주세요.",
  },
  {
    level: "expert",
    category: "가치투자",
    title: "현금흐름 개선 기업 집중형",
    prompt: "KOSPI 중형주 유니버스에서 PBR 1.2배 이하, ROE 10% 이상 조건을 만족하면서 최근 4개 분기 영업활동현금흐름이 개선되는 기업을 선별해 주세요. 동시에 거래대금 하위 종목은 제외하고 10종목 집중 포트폴리오를 구성하되 분기 리밸런싱과 손절 -11% 규칙을 적용해 주세요. 익절은 고정값보다 밸류에이션 정상화 시점 기준으로 판단하는 전략 형태로 정리해 주세요.",
  },
  {
    level: "expert",
    category: "기술분석",
    title: "볼륨 프로파일 돌파 확인 전략",
    prompt: "KOSDAQ 종목 중 최근 3개월 거래량 집중 구간을 상향 이탈하는 종목만 매수 대상으로 보겠습니다. 단순 돌파가 아니라 당일 거래대금이 최근 20일 평균의 2배 이상인 경우만 유효 신호로 취급하고, 돌파 실패로 종가가 재진입하면 즉시 청산해 주세요. 최대 7종목, 손절 -5.5%, 익절 +18%로 설정해 주세요.",
  },
  {
    level: "expert",
    category: "모멘텀",
    title: "ADX + 상대강도 결합 스윙",
    prompt: "KOSPI200 종목 중 ADX가 23 이상이고 최근 60거래일 상대강도가 상위 20%에 속한 종목만 거래하고 싶습니다. 진입은 10일 고가 돌파 시점으로 하고, 청산은 ADX 20 하향 이탈 또는 10일 저가 이탈 중 먼저 발생하는 조건으로 해주세요. 최대 10종목, 손절 -6.5%, 보유기간 상한 25거래일을 적용해 주세요.",
  },
  {
    level: "expert",
    category: "복합전략",
    title: "저평가 성장주 추세 지속 전략",
    prompt: "KOSDAQ 중 시가총액 2000억 원 이상 종목에서 매출 성장률이 양호하고 PBR이 과도하게 높지 않은 기업만 먼저 고르고 싶습니다. 이후 20일 EMA가 60일 EMA 위에 있고 최근 거래대금이 30일 평균보다 높은 경우만 진입하는 방식으로 설계해 주세요. 주간 리밸런싱, 최대 9종목, 손절 -7%, 익절 +24% 조건으로 부탁드립니다.",
  },
  {
    level: "expert",
    category: "AI 전략",
    title: "AI + 팩터 필터 멀티알파 전략",
    prompt: "AI 상승 예측 신호를 기본으로 하되, KOSPI/KOSDAQ 공통 유니버스에서 ROE 12% 이상, 최근 60거래일 상대강도 상위 30%, 일평균 거래대금 50억 원 이상 조건을 동시에 만족하는 종목만 편입해 주세요. 매주 점수를 재산출해 상위 12종목 동일 비중 포트폴리오를 유지하고, AI 하락 전환 또는 손절 -8% 도달 시 청산하도록 구성해 주세요.",
  },
  {
    level: "expert",
    category: "가치투자",
    title: "밸류 트랩 회피형 분산 보유",
    prompt: "KOSPI 전체 종목 중 PER과 PBR이 낮지만 최근 4분기 연속 적자인 기업은 제외하고, ROE가 플러스이며 거래대금이 충분한 종목만 선별해 주세요. 업종 분산을 위해 동일 업종 최대 2종목 제한을 두고 총 14종목 포트폴리오를 구성하겠습니다. 월간 리밸런싱, 개별 손절 -10%, 시장 급락 구간에서는 신규 진입 보류 조건도 넣어 주세요.",
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
  const [showAllExamples, setShowAllExamples] = useState(false);

  const levelExamples = useMemo(
    () => EXAMPLES.filter((example) => example.level === activeLevel),
    [activeLevel]
  );
  const visibleExamples = useMemo(
    () => (showAllExamples ? levelExamples : levelExamples.slice(0, DEFAULT_VISIBLE_COUNT)),
    [levelExamples, showAllExamples]
  );

  useEffect(() => {
    setShowAllExamples(false);
  }, [activeLevel]);

  const hiddenExampleCount = Math.max(levelExamples.length - DEFAULT_VISIBLE_COUNT, 0);

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

      {hiddenExampleCount > 0 && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setShowAllExamples((prev) => !prev)}
            className="rounded-2xl border border-white/[0.08] bg-white/[0.02] px-4 py-2 text-xs font-black text-gray-300 transition-colors duration-200 hover:border-white/[0.14] hover:text-white"
          >
            {showAllExamples ? "예시 접기" : `${hiddenExampleCount}개 예시 더 보기`}
          </button>
        </div>
      )}
    </div>
  );
}
