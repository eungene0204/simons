'use client'

import { useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// Agent 설계 구조 시각화 탭.
// 코드에서 자동 추출하지 않는 정적 스냅샷이다 — 파이프라인 구조가 바뀌면 이 데이터를
// 함께 갱신할 것. 노드 이름은 내부 변수/모듈명이 아니라 운영자가 읽는 친화 명칭을 쓴다.
// ─────────────────────────────────────────────────────────────────────────────

type NodeKind = 'input' | 'llm' | 'auto' | 'data' | 'guard' | 'ask' | 'output'

interface FlowNode {
  kind: NodeKind
  title: string
  desc?: string
  items?: string[]
}

interface FlowBranch {
  branches: { label: string; nodes: FlowNode[] }[]
}

type FlowStep = FlowNode | FlowBranch

interface AgentSpec {
  id: string
  name: string
  tagline: string
  summary: string
  flow: FlowStep[]
  notes?: string[]
  location: string
}

const KIND_META: Record<NodeKind, { label: string; badge: string; border: string }> = {
  input: { label: '입력', badge: 'bg-gray-500/20 text-gray-300', border: 'border-gray-500/40' },
  llm: { label: 'AI 판단', badge: 'bg-purple-500/20 text-purple-300', border: 'border-purple-500/40' },
  auto: { label: '자동 규칙', badge: 'bg-sky-500/20 text-sky-300', border: 'border-sky-500/40' },
  data: { label: '지식·데이터', badge: 'bg-emerald-500/20 text-emerald-300', border: 'border-emerald-500/40' },
  guard: { label: '안전장치', badge: 'bg-rose-500/20 text-rose-300', border: 'border-rose-500/40' },
  ask: { label: '사용자 확인', badge: 'bg-amber-500/20 text-amber-300', border: 'border-amber-500/40' },
  output: { label: '결과물', badge: 'bg-white/15 text-white', border: 'border-white/30' },
}

const AGENTS: AgentSpec[] = [
  {
    id: 'interpreter',
    name: '전략 해석기',
    tagline: '자연어 → 전략 변환',
    summary:
      '사용자가 한국어로 쓴 전략("골든크로스에 사고 손절 5%")을 백테스트 엔진이 실행할 수 있는 구조화된 전략으로 바꾸는 핵심 파이프라인. 의미 해석은 AI만 하고, 형식 검증과 컴파일은 전부 자동 규칙이 담당한다.',
    flow: [
      { kind: 'input', title: '사용자 자연어 입력', desc: '"반도체 대형주를 골든크로스에 매수, 손절 5%"' },
      {
        kind: 'guard',
        title: '규제 안전 게이트',
        desc: '종목 추천·시장 전망·맞춤 조언 요청은 해석 전에 차단하고 안내로 응답',
      },
      {
        kind: 'llm',
        title: '대화 플래너 — 투자 범위 먼저 판별',
        desc: '어떤 종목 집단(시장·업종·테마·개별 종목)을 대상으로 하는지 도구를 호출해 먼저 확정 (아래 "대화 플래너" 탭 참고)',
      },
      {
        kind: 'llm',
        title: 'AI 의미 해석',
        desc: '동의어·정성 표현·오타·문맥을 이해해 조건·지표·수치를 뽑아 구조화된 전략 초안(JSON)으로 출력',
      },
      {
        kind: 'auto',
        title: '표기 정리 + 형식 검사',
        desc: 'AI 출력의 껍데기 제거·값 표기 통일 후 필수 항목과 타입을 검사 — 원문을 재해석하지 않음',
        items: [
          '손절·익절이 리스크 관리 칸과 매도 조건에 중복 표현되면 정본 자리(리스크 관리)에 한 번만 남긴다 — 손절도 의미상 청산 규칙이라 AI가 두 곳에 쓰는 일이 있다 (2026-08-05)',
        ],
      },
      {
        kind: 'auto',
        title: '지원 여부·완결성 검사',
        items: [
          '지표가 엔진에서 지원되는지',
          '청산 조건에 올 수 있는 지표인지 (기술적 신호만 가능 — 위반 조건은 전략 전체를 버리지 않고 그 조건만 제외 후 안내, 2026-08-05)',
          '단, 매수 조건에 이미 있는 지표를 원문 근거 없이 청산에 복제한 것(AI 미러 드리프트)은 안내 없이 정리 — 매수에 정상 반영된 지표가 "반영 못했다"로 읽히는 혼란 방지 (2026-08-05)',
          '값 범위·단위가 올바른지',
          '조건끼리 충돌하지 않는지',
          '진입·청산 등 필수 조건이 다 있는지',
          '말한 조건이 빠짐없이 반영됐는지 (누락 검사)',
        ],
      },
      {
        kind: 'guard',
        title: '설정값 범위 게이트',
        desc: '범위를 벗어난 설정값을 조용히 깎아 맞추지 않는다 — 사용자가 말한 적 없는 금액을 우리가 확정하는 셈이기 때문',
        items: [
          '하한 미만(초기 자금 100만원 등) — 하한으로 보정하고 보정 사실을 알린다',
          '상한 초과(초기 자금 100억원) — 값을 버리고 "사용자가 말했다"는 기록까지 떼어내 다시 묻는다',
          '시장이 소화할 수 없는 자금은 전 종목이 유동성 기준 미달로 빠져 빈 백테스트가 된다',
          '백테스트 기간이 미래로 뻗으면 종료일을 오늘로 잘라 알린다 — 자르지 않으면 엔진은 오늘까지만 돌리는데 화면은 요청한 날짜를 보여줘 둘이 어긋난다',
          '기간 전체가 보유 데이터 밖(전부 미래거나 1996년 이전)이면 창을 버리고 기간을 다시 묻는다 — 실행 버튼을 누른 뒤 엔진 오류로 알게 되지 않도록',
        ],
      },
      {
        kind: 'auto',
        title: '항목별 상태 표시',
        desc: '진행률 카드가 "완료/미완료" 둘로만 보여주던 것을 검사 결과에 맞춰 나눈다 — 표시 전용이라 되묻기·실행 판정은 바꾸지 않는다',
        items: [
          '완료 — 사용자가 말했거나 시스템이 확정한 값',
          '미확인 — 값은 있으나 기본값이라 사용자가 고른 적 없음',
          '해당 없음 — 단일 종목의 리밸런싱처럼 물을 대상이 아닌 항목 (진행률 분모에서 제외)',
          '확인 필요 — 엔진이 지원하지 않는 지표이거나 조건끼리 모순',
        ],
      },
      {
        branches: [
          {
            label: '빠진 조건이 있으면',
            nodes: [
              {
                kind: 'ask',
                title: '되묻기 + 추천값 칩 (한 턴에 한 질문)',
                desc: '조용히 기본값을 채우지 않고 질문한다. 확정된 조건만 부분 반영해 보여줌. 질문이 여러 개면(기준값 2개+청산 등) 첫 질문만 이번 턴에 묻고 나머지는 이월 큐로 넘긴다 — 답이 반영될 때마다 큐에서 다음 질문 하나를 자동 발행하고, 앞선 답으로 이미 채워진 항목은 건너뛴다(2026-08-03 사용자 결정: 질문 3개를 한 버블에 묶지 않기)',
              },
              {
                kind: 'auto',
                title: '질문↔답변 결속',
                desc: '질문과 함께 "이 칩은 어느 필드를 어떤 값으로 정하는가"를 확정해 붙인다. 결속이 없으면 다음 턴의 답변이 어느 질문의 답인지 알 수 없어 새 발화로 분류된다. 이월 큐도 이 결속에 실려 턴을 넘는다(무상태 에코)',
              },
            ],
          },
          {
            label: '완성이면',
            nodes: [
              { kind: 'auto', title: '전략 컴파일', desc: '구조화된 전략을 엔진 실행 형식으로 변환' },
              { kind: 'output', title: '백테스트 실행 가능한 전략', desc: '요약 카드와 함께 사용자에게 표시' },
            ],
          },
        ],
      },
    ],
    notes: [
      '해석 실패는 실패로 보고하고 되묻는다 — 옛날처럼 정규식으로 원문을 재해석하는 폴백은 금지.',
      '무엇이 아직 비었는지 판정하는 곳은 한 군데뿐이다(진행률·되묻기·플래너가 같은 판정을 본다).',
      '"해당 없음"과 "완료"는 이전에 같은 값으로 보였다 — 단일 종목 전략의 리밸런싱 칸에 체크가 켜졌다. 이제 구분해서 표시한다.',
      '되묻기는 어느 경로에서 나가든 결속을 달고 나간다 — 예전에는 플래너가 만든 질문에만 결속이 붙어, 플래너가 실패하거나 그 질문이 거부되면 폴백 질문의 답이 갈 곳을 잃었다.',
      '종목이 지정된 전략에는 "몇 종목을 고를까요?"를 묻지 않는다 — 고를 대상이 이미 정해져 있다.',
      '수정 요청은 "전략 수정기" 파이프라인이 따로 처리한다.',
    ],
    location: 'backend/strategy_conversation/',
  },
  {
    id: 'planner',
    name: '대화 플래너',
    tagline: '도구 실행 계획 수립',
    summary:
      '전략 해석에 필요한 사전 조사(이 용어가 업종인지 테마인지, 어떤 종목들이 해당되는지)를 AI가 계획하고, 실행은 전부 자동 러너가 대신하는 계획-실행 분리 구조. AI는 계획만 세우고 값을 직접 확정하지 못한다.',
    flow: [
      { kind: 'input', title: '사용자 입력', desc: '"비만치료 관련주로 전략 만들어줘"' },
      {
        kind: 'llm',
        title: 'AI가 작업 계획(그래프) 작성',
        desc: '어떤 조사 도구를 어떤 순서로 쓸지 JSON 계획으로만 출력 — 직접 실행 권한 없음',
      },
      {
        kind: 'guard',
        title: '계획 구조 검사 + 무효 항목 표시',
        desc: '허용된 도구만 사용했는지·순환이 없는지 자동 검증. 위반하면 즉시 고정 파이프라인으로 복귀',
      },
      {
        kind: 'auto',
        title: '도구 실행기 (자동)',
        items: [
          '투자 범위 분류 — 시장/업종/테마/종목 구분. 지표 어휘가 든 조건 구("영업이익률이 높은 종목")는 유니버스가 아님(NOT_UNIVERSE)으로 종결해 테마 해석·검색 체인에 태우지 않는다(2026-08-03: 조건 구가 테마로 오분류돼 검색 학습까지 돌다 계획 예산 소진)',
          '테마 후보 나열 — 비슷한 테마가 여럿이면 후보 수집. 후보가 정확히 1개면 그 정본 표기의 소속 기업 조회는 AI 판단 없이 자동으로 이어진다(범위가 갈리지 않으므로 절차 — 2026-08-02 감사 수정: AI가 관찰된 후보 60곳을 두고 다음 질문으로 건너뛰어 시드 2곳이 적용되던 범위 축소 차단). 원 표현("ESS")도 해석 완료로 전파해 다른 레인이 같은 표현을 이중 해석하지 않는다',
          '업종 정본 매핑 — "이차전지" → 정식 업종명',
          '테마 소속 기업 조회',
          '모르는 용어 검색 학습 (테마 학습기 호출)',
          '투자 범위 최종 확정',
          '기능 지원 여부 조회 (예: ETF는 재무지표 불가)',
        ],
      },
      {
        kind: 'auto',
        title: '실행 결과를 AI에게 다시 제시',
        desc: '같은 도구+인자는 한 번만 실행(무한 반복 차단), 턴 수 예산 초과 시 자동 중단 — 단, 직전 턴이 새 관찰(도구 실행)을 만들었으면 예산을 +2턴까지 연장한다(2026-08-02 감사 수정: 테마 표현은 분류→후보조회→질문에 3턴이 필요한데 예산 2에서 항상 소진돼 관찰된 카탈로그 테마가 버려졌다)',
      },
      {
        branches: [
          {
            label: '질문이 필요하면',
            nodes: [
              {
                kind: 'guard',
                title: '채워진 항목 재질문 차단',
                desc: '이미 결정된 항목(매수 조건 등)을 다시 묻는 질문은 자동으로 건너뛰고 다음 빈 항목 질문만 내보냄',
              },
              {
                kind: 'guard',
                title: '질문 채택 전 항목 대조',
                desc: '플래너는 전략 해석보다 먼저 계획하므로 무엇이 채워졌는지 모른다 — 해석이 끝난 뒤 질문 항목과 실제 빈 항목을 대조해, 다른 항목이 비었다는 이유로 이미 답한 질문이 나가는 것을 막음. 값만 비어 컴파일에서 빠진 조건(예: "영업이익률이 높은" — 값 확인 대기)이 있는 슬롯의 열린 질문도 거부한다 — 그 슬롯은 공백이 아니라 값 대기라, 채택하면 해석기의 기준값 질문("영업이익률 기준값을 얼마로 할까요?")을 일반 질문이 덮어쓴다(2026-08-03 사고)',
              },
              {
                kind: 'guard',
                title: '선택지 정본 대체',
                desc: '조건·설정 질문의 선택지 문구는 AI가 만들지 않는다 — AI가 계획에서 제안한 선택지는 폐기하고 항목별로 사람이 정해 둔 정본 목록으로 교체(ETF 전략에는 재무 선택지 제외). 지원되는 선택지만 노출됨을 정본으로 보증. 유니버스 범위 선택지는 카탈로그 후보 표기 그대로라 별도 정본',
              },
              {
                kind: 'guard',
                title: '선택지 값 결속 검사',
                desc: '선택지를 보여주기 전에 각 선택지가 뜻하는 전략 값을 미리 확정한다 — 값이 확정되지 않는 선택지(엔진이 표현할 수 없는 조건)는 사용자에게 아예 노출하지 않음',
              },
              {
                kind: 'guard',
                title: '미지원 개념 선택지 차단',
                desc: '미지원 개념(거래량 배수 등)을 언급하는 선택지는 일부만 값이 확정돼도 노출하지 않음 — 나머지 조건이 조용히 사라진 채 클릭되면 미지원 안내로 끝나기 때문(정본 목록 실수에 대한 이중 방어)',
              },
              {
                kind: 'ask',
                title: '범위 확인 질문',
                desc: '테마 후보가 2개 이상이면 임의로 고르지 않고 사용자에게 선택지를 보여줌',
              },
            ],
          },
          {
            label: '조사가 끝나면',
            nodes: [
              {
                kind: 'guard',
                title: '확정값은 도구 결과에서만 채택',
                desc: 'AI가 문장 속에서 주장한 값은 무시 — 환각 차단',
              },
              { kind: 'output', title: '확정된 투자 범위', desc: '전략 해석기에 전달' },
            ],
          },
        ],
      },
    ],
    notes: [
      '어떤 실패든 고정 파이프라인이 이어받는다 — 플래너는 단독 실패 지점이 될 수 없다.',
      '사용자에게 나가는 질문 문구는 출력 검문(규제 안전 필터)을 통과한다.',
      '선택지(칩)는 우리가 만들어 보여준 것이므로 값도 그때 함께 확정한다 — 사용자가 고르면 다시 해석하지 않고 확정해 둔 값을 그대로 쓴다.',
      '지금 값과 같은 선택지도 보여준다 — 고르면 값은 그대로 두고 "사용자가 확인함"으로만 바뀐다(화면에 보여준 값을 고를 수 없던 문제).',
      '한 번의 해석에서 플래너는 딱 한 차례만 계획한다 — 계획 예산(기본 2턴, 진전 시 최대 +2턴 연장)을 다 써도 처음부터 다시 계획하지 않고 고정 질문으로 넘긴다(재계획은 응답만 2배로 느리게 만들었다). 예산이 막는 것은 무진전 반복이지 생산적인 도구 사슬이 아니다.',
    ],
    location: 'backend/strategy_conversation/planner/ · tools/',
  },
  {
    id: 'classifier',
    name: '질문 분류기',
    tagline: '의도 분류 + 규제 가드',
    summary:
      '채팅 입력이 전략 설계인지, 종목 질문인지, 투자 지식 질문인지 가려서 담당 파이프라인에 배정한다. 입력의 의미는 전부 AI가 해석하고, 자동 규칙은 AI가 내놓은 결과의 형식만 검증한다.',
    flow: [
      { kind: 'input', title: '사용자 질문', desc: '채팅창에 입력된 모든 메시지가 여기를 먼저 지나감' },
      {
        kind: 'llm',
        title: 'AI 의미 해석',
        desc: '대화 맥락(직전 턴)과 "진행 중인 전략이 있는지", 그리고 "지금 답을 기다리는 질문"을 함께 넘겨 의도를 판정 — 전략 카드가 떠 있을 때의 짧은 발화("원자력 업종만")나 방금 던진 질문에 대한 답("아니야")을 잡담·인사로 오해하지 않게 한다',
        items: [
          '의도 라벨 — 전략 설계 / 종목 질문 / 투자 지식 / 인사 / 역할 밖 등',
          '언급된 종목명 (있으면)',
          '"이 종목"처럼 직전 종목을 가리키는지 여부',
          '워크플로 제어 — 멈춤 / 이어하기 / 취소 / 처음부터 / 되돌리기 / 정정 (기본값은 "제어 없음")',
          '값 없이 지목된 수정 대상 — "손절 바꿔줘"처럼 바꿀 것은 말했는데 값이 없으면 그 대상 (기본값은 "없음")',
        ],
      },
      {
        kind: 'auto',
        title: '형식 검증·정규화',
        desc: 'AI 출력에서만 동작 — 원문은 건드리지 않는다',
        items: [
          'JSON 경계 추출 · 코드펜스/사고 블록 제거',
          '라벨 표기 정규화 후 허용 목록 대조',
          '따옴표 빠진 값 표기 수리 — AI가 "NONE"을 따옴표 없이 내놓아 JSON이 깨지는 형식 결함(실측 34%)만 고친다. 의미는 건드리지 않는다',
          '해석 실패 시 임의 보정 없이 "실패" 표시와 함께 보고 — 화면은 이 표시를 보고 실패를 실패로 안내한다(일반 지식 답변으로 위장 금지)',
        ],
      },
      {
        kind: 'auto',
        title: '종목 정본 매핑',
        desc: 'AI가 뽑은 종목명 문자열만 종목 원본에 조회 — 원문 전체를 훑지 않는다',
      },
      {
        kind: 'guard',
        title: '규제 안전 가드 (라벨 기준)',
        desc: '안내 문구는 AI가 짓지 않고 라벨에 따라 확정된 문장을 쓴다',
        items: [
          '"뭐 살까?" (열린 종목 추천) → 추천 불가 안내 + 전략 설계 전환',
          '"어떤 전략이 좋아?" → 전략 빌더로 안내',
          '나이·자산 기반 맞춤 조언 → 정중히 거절',
          '실전 매매 요청 → 모의투자만 가능 안내',
          '뉴스·공시 기반 등 미제공 기능 → 안내',
        ],
      },
      {
        kind: 'guard',
        title: '되묻기 대상 검증',
        desc: 'AI는 대상을 정해진 목록(설정 값·영역·재무 지표) 안에서만 고르고, 무엇을 물을지(문구·선택지)는 자동 규칙이 그 대상에 맞춰 고른다 — 안내 문구를 AI가 짓지 않는다',
        items: [
          '목록 밖 표기는 "없음"으로 — 모르는 값을 되묻기로 승격하지 않는다',
          '규제 가드에 걸린 라벨이면 무시 — 정형 안내가 되묻기로 삼켜지지 않게',
          '진행 중인 전략이 없으면 무시 — 바꿀 대상이 없다',
          '이미 던진 질문의 답을 받는 턴이면 무시 — "초기자금 얼마로?"에 "3억원"이라고 답해도 대상은 여전히 초기자금으로 나오므로, 그대로 두면 같은 질문을 다시 던진다. 답의 해석은 전략 해석 AI가 하고, 어느 질문에 대한 답인지는 질문 문맥을 함께 넘겨 알려준다',
        ],
      },
      {
        kind: 'guard',
        title: '워크플로 제어 검증',
        desc: 'AI는 제어를 제안만 하고, 성립 여부는 자동 규칙이 정한다 — 성립하지 않으면 "제어 없음"으로 낮춰 기존 대화를 그대로 이어간다',
        items: [
          '규제 가드에 걸린 라벨이면 제어를 무시 — "그만할래" 한마디로 안내가 삼켜지지 않게',
          '진행 중인 전략이 없으면 멈춤·취소·처음부터·되돌리기는 성립하지 않음',
          '멈춘 적이 없으면 "이어하기"도 성립하지 않음',
        ],
      },
      {
        branches: [
          {
            label: '정정이면 ("아니 그런 뜻이 아니라 ~야")',
            nodes: [
              {
                kind: 'auto',
                title: '직전 변경 되돌린 뒤 재해석',
                desc: '되돌릴 지점을 AI에 묻지 않는다 — 정정은 언제나 방금 한 해석을 겨냥한다. 되돌린 자리에서 그 발화를 다시 해석하며, 사과나 해명을 덧붙이지 않는다',
              },
            ],
          },
          {
            label: '되돌리기 요청이면',
            nodes: [
              {
                kind: 'llm',
                title: '되돌릴 지점 판정',
                desc: '변경 이력("2. ETF로 바꿔줘 → 바뀐 항목: 유니버스")을 보고 어느 변경으로 돌아갈지 AI가 고른다. 이력에는 무엇이 바뀌었는지만 싣고 전략 값은 싣지 않는다',
              },
              {
                kind: 'guard',
                title: '지목한 지점 대조',
                desc: 'AI가 고른 번호·항목이 실제 이력에 있는지 확인한다. 없으면 "가장 최근 것"으로 보정하지 않고 되묻는다 — 보정하면 사용자가 의도하지 않은 변경이 조용히 사라진다',
              },
              {
                kind: 'auto',
                title: '이력에서 복원',
                desc: '그 변경 직전 상태로 되돌린다. 항목만 지정하면 나머지는 그대로 두고 그 항목만. "사용자가 말했다"는 기록도 함께 되돌린다',
              },
            ],
          },
          {
            label: '멈춤·취소·처음부터면',
            nodes: [
              {
                kind: 'auto',
                title: '전략 초안 유지 또는 폐기',
                desc: '취소·처음부터만 초안을 버린다. 멈춤은 조건을 그대로 보존하고, 이어하기는 진행만 재개',
              },
            ],
          },
        ],
      },
      {
        kind: 'output',
        title: '담당 파이프라인으로 전달',
        desc: '전략 해석기 / 전략 빌더 / 종목 질문 도우미 / 지식 답변 중 하나로 배정. 워크플로 제어가 성립하면 전략 초안 유지·폐기를 함께 지시한다',
      },
    ],
    notes: [
      '설정 기본값 질문(수수료·슬리피지)은 AI 환각 대신 설정 원본에서 결정적으로 답한다.',
      'AI가 응답하지 못하면 규칙으로 되돌아가 추측하지 않고 실패로 보고한다 — 잘못된 거절보다 안전하다.',
      '해석에 실패한 턴은 실패로 안내한다("다시 시도해 주세요") — 일반 지식 답변으로 흘려 정의 설명이 답변으로 위장되지 않게 한다(2026-08-03 사고). 진행 중인 전략이 있으면 전략 해석기에 넘겨 그쪽 AI가 다시 해석한다.',
      '이전의 "규칙 우선 → 애매하면 AI" 순서는 롤백 전용으로만 남아 있다(INTENT_CLASSIFIER_MODE=legacy).',
      '워크플로 상태(진행 중·멈춤 등)와 변경 이력은 서버에 저장하지 않고 화면이 매 요청에 돌려보낸다 — 기존 무상태 계약 그대로다.',
      '용어 질문·잡담은 워크플로를 멈추지 않는다. 멈춤은 사용자가 명시적으로 요청했을 때만 일어난다.',
      '전략을 만드는 중에 들어온 인사·역할 밖·용어 질문에는 안내로 답한 뒤, 답을 기다리던 질문(예: 리밸런싱 주기)을 선택지와 함께 그대로 다시 묻는다 — 한 마디 잡담에 진행 중인 질문이 사라지지 않게.',
      '되돌릴 지점 판정은 큰 모델(9B)을 쓴다 — 작은 모델은 이력에서 엉뚱한 변경을 골랐다(실측 4B 5/7, 9B 7/7). 잘못 고른 되돌리기는 사용자가 쌓아온 전략을 지운다.',
    ],
    location: 'backend/intent/interpreter.py · classifier.py · schemas.py',
  },
  {
    id: 'builder',
    name: '전략 빌더',
    tagline: '단계별 문답 설계',
    summary:
      '"어떤 종목을 사야 해?" 같은 열린 질문을 받았을 때, 추천 대신 짧은 문답을 쌓아 사용자가 직접 전략을 완성하게 돕는 상태 머신. 선택지 답변은 자동 규칙이, 자유 서술만 AI가 해석한다.',
    flow: [
      { kind: 'input', title: '열린 추천 질문', desc: '"뭐 살까?" → 추천 불가 안내 후 빌더 진입' },
      {
        kind: 'auto',
        title: '해석기 결과 이어받기',
        desc: '전략 해석기가 이미 읽어낸 조건(업종·테마·신규 상장 제한·청산 조건)을 빌더 상태로 옮긴다 — 이어받지 않으면 사용자가 말한 제한이 최종 전략에서 사라진다',
      },
      {
        kind: 'auto',
        title: '단계별 질문 진행',
        desc: '시장 → (신규 상장이면) 상장 시기 → 전략 유형 → 기준 기간 → 보유 종목 수 → 리밸런싱 주기. 이미 말한 정보(업종·종목)는 기억해 건너뜀',
      },
      {
        branches: [
          {
            label: '선택지·값 답변',
            nodes: [{ kind: 'auto', title: '자동 규칙 해석', desc: '칩 클릭·숫자 답은 형식 정규화만으로 처리' }],
          },
          {
            label: '자유 서술 답변',
            nodes: [{ kind: 'llm', title: 'AI 해석', desc: '"원자로 같은 거" → 에너지 업종처럼 미인식 표현만 AI가 매핑' }],
          },
          {
            label: '조건 삭제·변경 요청',
            nodes: [
              {
                kind: 'auto',
                title: '수정 규칙 우선 처리',
                desc: '"손절 빼줘"는 어느 단계에서든 즉시 반영. 값 없는 변경("시장 바꿔줘")은 재질문',
              },
            ],
          },
        ],
      },
      { kind: 'ask', title: '요약 카드 확인', desc: '누적된 전략을 보여주고 사용자가 확정' },
      {
        kind: 'auto',
        title: '누적 구조를 직접 컴파일',
        desc: '확정 시 자연어로 되돌려 재해석하지 않는다 — AI 전용 조건이 소실되던 사고 방지',
      },
      { kind: 'output', title: '백테스트 실행', desc: '기존 백테스트 파이프라인 재사용' },
    ],
    notes: [
      '단일 종목 모드에선 종목 선별 질문을 건너뛰고 "언제 사고 언제 팔까"만 묻는다.',
      '특정 전략 유형을 지정하면 그 유형에 맞는 파라미터만 순서대로 묻는다.',
    ],
    location: 'backend/intent/strategy_builder.py · builder_interpreter.py',
  },
  {
    id: 'modifier',
    name: '전략 수정기',
    tagline: '대화로 전략 고치기',
    summary:
      '이미 만든 전략에 "손절을 3%로 바꿔줘" 같은 수정 요청을 반영한다. AI가 바뀐 부분만 해석하고, 환각 방지 게이트와 결정적 병합이 원본 전략을 지킨다.',
    flow: [
      { kind: 'input', title: '수정 요청 + 기존 전략', desc: '"손절은 3%로, 종목은 5개만"' },
      {
        kind: 'input',
        title: '답을 기다리는 질문',
        desc: '직전 턴에 우리가 던진 되묻기 문구를 함께 넘긴다 — "3억원"처럼 필드 없이 값만 온 답이 어느 필드의 답인지는 이 질문이 정한다(없으면 귀속할 근거가 없어 같은 질문을 반복하게 된다)',
      },
      {
        kind: 'auto',
        title: '수정 단서 감지',
        desc: '어떤 필드(손절·종목 수·유니버스…)를 언급했는지 결정적으로 표시 — 이후 환각 판정의 기준',
      },
      {
        kind: 'data',
        title: '유사 수정 예시 검색',
        desc: '검증된 수정 지식·정답 예시 코퍼스에서 비슷한 요청을 찾아 AI에게 참고자료로 제공',
      },
      { kind: 'llm', title: 'AI 수정 해석', desc: '바뀌는 부분만 차분(diff)으로 출력' },
      {
        kind: 'guard',
        title: '환각 방지 게이트',
        desc: '사용자가 언급하지 않은 변경을 AI가 하려 하면 폐기 — 판정 단위는 조건 하나(지표·연산자·값을 함께 갈아끼우는 교체가 반쪽만 적용되지 않도록)',
        items: [
          '근거는 AI가 인용한 사용자 원문 조각 — 인용은 변경 자체에 붙을 수도, 새로 넣는 조건 안에 붙을 수도 있어 두 자리를 모두 본다(한쪽만 보면 정확히 인용한 요청이 근거 없음으로 버려진다)',
          '인용이 없으면 값의 숫자가 사용자가 말한 숫자와 맞는지로 대조',
          '인용이 있어도 그 인용의 숫자와 값이 10배·100배로 어긋나면 폐기 — 인용은 원문 조각이라 언제나 실재하므로, 자릿수가 틀린 값을 대신 통과시킨다("1000억원"을 100억으로 적어 넣던 사고)',
        ],
      },
      {
        kind: 'auto',
        title: '조건 추가 형태 보정',
        desc: '아직 아무 조건도 없는 자리에 AI가 "첫 번째 조건을 이렇게 바꿔라"라고 답하면(가리킬 대상이 없음) 같은 자리를 겨냥한 항목들을 조건 하나로 합쳐 추가로 바꾼다. AI가 이미 말한 값만 모으며, 조건의 정체(지표)가 없으면 합치지 않는다',
      },
      {
        kind: 'auto',
        title: '결정적 병합',
        desc: '차분을 원본 전략에 코드가 병합 — 목록형 조건(재무 필터 등)이 통째로 사라지는 것을 방지',
      },
      {
        kind: 'data',
        title: '테마 교체 지식 조회',
        desc: '"쿠팡 관련주로" 같은 테마 교체는 지식그래프·검색이 상장사를 다시 찾아 이전 테마에서 온 종목만 교체 — 종목코드는 AI가 알아내지 않는다',
      },
      {
        kind: 'auto',
        title: '시장 소속 필터',
        desc: '"코스피에만 속한 종목으로" 같은 시장 변경은 테마에서 온 지정 종목을 종목 마스터 정본 소속으로 좁힌다 — 직접 지목한 종목은 불변. 현재 목록에 해당 시장 종목이 없으면 테마 전체 구성으로 되돌아가 다시 좁힌다(코스피로 좁힌 뒤 "코스닥만"도 성립). 테마 전체에도 없으면 시장 변경까지 되돌려 전략을 유지하고 반영하지 못했음을 안내한다(침묵 금지)',
      },
      {
        branches: [
          {
            label: '값이 없으면',
            nodes: [{ kind: 'ask', title: '값 되묻기', desc: '"손절 바꿔줘"(값 없음)는 재질문 — 무변경 재렌더링 방지' }],
          },
          {
            label: '테마 범위가 갈리면',
            nodes: [
              {
                kind: 'ask',
                title: '테마 범위 되묻기',
                desc: '카탈로그 후보를 칩으로 제시하고 전략은 그대로 — 조용한 확정 금지(생성 경로와 같은 계약)',
              },
            ],
          },
          {
            label: '"응 그걸로"면',
            nodes: [
              {
                kind: 'auto',
                title: '현재값 확정',
                desc: '값은 그대로 두고 "사용자가 확인함"으로만 표시 — 무엇을 확정했는지는 직전 질문이 정한다(AI에게 묻지 않음)',
              },
            ],
          },
          {
            label: '검증이 거부하면',
            nodes: [
              {
                kind: 'ask',
                title: '검증 거부 되묻기',
                desc: '해석은 성공했는데 바뀐 전략이 검증에 걸리면(예: ETF 전환 시 기존 PER 조건 충돌) 전략은 그대로 두고 검증기의 오류 문구를 그대로 질문으로 전달한다 — "해석하지 못했어요"로 원인을 위장하지 않는다(2026-08-02 감사 수정). 유니버스 변경 턴에는 충돌 조건을 빼고 전환하는 해소 칩을 함께 제시',
              },
            ],
          },
          {
            label: '해석 실패면',
            nodes: [{ kind: 'ask', title: '전략 보존 + 되묻기', desc: '실패해도 기존 전략을 절대 훼손하지 않음' }],
          },
          {
            label: '말한 수치가 반영되지 않았으면',
            nodes: [
              {
                kind: 'guard',
                title: '재생성 요청 (안내 없음)',
                desc: '반영되지 않은 숫자를 증거로 실어 해석을 한 번 다시 요청한다. 재요청 후에도 남으면 로그에만 남기고 사용자에게는 알리지 않는다 — 대조가 크기만 보는 수치 비교라 맥락 없는 숫자 나열이 되고, 표현형이 다를 뿐 이미 반영된 조건(월 1회 리밸런싱 등)이 자주 걸린다',
              },
            ],
          },
          {
            label: '성공이면',
            nodes: [{ kind: 'output', title: '수정된 전략', desc: '요약 카드와 함께 표시, 즉시 재백테스트 가능' }],
          },
        ],
      },
    ],
    notes: [
      '"현대약품은 빼줘" 같은 제외 요청은 종목 지정으로 오독하지 않도록 삭제 판정이 우선한다.',
      '테마 전략의 종목은 출처(어느 테마에서 왔는지)를 함께 저장한다 — 그래야 다음 턴에 테마만 바꿀 수 있고, 사용자가 직접 지목한 종목은 테마 교체가 건드리지 않는다.',
      '전략을 바꾸지 못한 되묻기는 우선순위 표시를 달고 나간다 — 다른 설정 질문에 덮여 요청이 사라지지 않게.',
      '"지금 이 조건을 쓸 수 있나"(해당 없음·확인 필요)는 저장하지 않고 매번 다시 계산한다 — 그래서 ETF로 바꿨다가 코스피로 되돌리면 별도 조치 없이 원래대로 돌아온다. 원본 조건은 어느 쪽에서도 지우지 않는다.',
      '지식그래프 조회처럼 다시 만들기 비싼 결과만 "무엇을 근거로 만들었는지"를 함께 저장한다 — 근거가 바뀌면 다시 조회하지 않고도 낡았다는 것을 안다.',
      '"테마 범위 되묻기"에 답하지 않고 다른 화제로 넘어가면(2026-08-02 감사 수정) 유니버스는 바뀌지 않은 채 그 질문이 아직 열려 있었다는 사실을 안내한다 — 조용히 사라지지 않는다.',
      '요청을 반영하지 못한 턴(설명 답변·미지원·전량 거부)은 안내와 함께 직전에 답을 기다리던 질문을 다시 표시한다 — 미반영 안내가 열려 있던 되묻기를 화면에서 지우지 않는다(2026-08-02 감사 수정).',
    ],
    location: 'backend/strategy_conversation/primary.py · engine/modify_rag.py',
  },
  {
    id: 'validator',
    name: '전략 검증 도우미',
    tagline: '실행 가능성 진단',
    summary:
      '완성된 전략이 백테스트를 실제로 돌릴 수 있는 상태인지 구조적으로 진단한다. 전략의 우열은 평가하지 않는다(규제 안전) — 좋은 전략인지가 아니라 돌아가는 전략인지만 본다.',
    flow: [
      { kind: 'input', title: '완성된 전략', desc: '전략 연구소에서 파싱·수정이 끝난 전략' },
      {
        kind: 'auto',
        title: '구조 검사',
        items: ['필수 요소(유니버스·진입·청산) 존재 여부', '지표가 엔진 지원 목록에 있는지', '값 형식·범위가 올바른지'],
      },
      {
        kind: 'auto',
        title: '실행 가능성 검사',
        desc: '진입만 있고 청산이 없는 등 백테스트가 공회전할 조합을 찾아냄',
      },
      {
        kind: 'guard',
        title: '우열 평가 금지',
        desc: '"좋은 전략입니다" 류의 평가·추천 표현은 구조적으로 생성하지 않음',
      },
      { kind: 'output', title: '검증 리포트', desc: '보완이 필요한 항목을 객관적 사실로만 나열' },
    ],
    notes: [
      '과거 LLM 코칭 경로는 코드로 보존돼 있으나 현재 꺼져 있다(검증 모드가 기본). 죽은 코드로 오인해 지우지 말 것.',
      '"어떻게 해야 할까?" 같은 후속 질문에는 검증 도우미를 부르지 않는다 — 아직 정하지 않은 조건이 남아 있으면 진행률 순서대로 그 조건을 묻는 것이 답이고, 질문·선택지·진행률을 모두 같은 판정에서 만든다(검증 도우미는 자기 순서대로 답하므로 질문과 선택지가 어긋날 수 있다). 정할 것이 다 정해졌을 때만 검증 결과를 보여준다.',
    ],
    location: 'backend/ai/strategy_validation_agent.py · api/coach_routes.py',
  },
  {
    id: 'reporter',
    name: 'AI 리포트',
    tagline: '백테스트 결과 해설',
    summary:
      '백테스트가 끝난 뒤 결과 수치를 해설하는 전문가 리포트를 만든다. 진단·점수·근거는 전부 자동 규칙이 계산하고, AI는 이미 계산된 사실을 서술문으로 풀어 쓰는 역할만 한다.',
    flow: [
      { kind: 'input', title: '백테스트 결과', desc: 'CAGR·MDD·샤프·거래 내역 등 엔진 산출값' },
      {
        kind: 'auto',
        title: '규칙 기반 진단',
        desc: '과최적화 징후·리스크 설정 문제·거래 빈도 이상 등을 규칙으로 탐지해 문제점 목록 생성',
      },
      { kind: 'auto', title: '점수 계산', desc: '전략 점수·리스크 점수·과최적화 위험도 — 전부 결정적 산식' },
      {
        kind: 'data',
        title: '경험·통계 결합',
        items: [
          '유사 전략 실험 경험 회수 (벡터 메모리)',
          '전체 사용자 백테스트 통계 대비 백분위 계산 (방향 명시)',
          '뉴스 신호 정리',
        ],
      },
      { kind: 'auto', title: '근거 자료 정리', desc: '리포트 각 섹션이 인용할 수치 근거를 결정적으로 조립' },
      {
        kind: 'llm',
        title: 'AI 서술 생성 (9B 모델)',
        desc: '검증 전문가 관점의 10개 섹션 리포트로 서술 — 수치를 새로 계산하지 않고 전달받은 근거만 사용',
      },
      { kind: 'guard', title: '표현 검문', desc: '내부 지시문 누출·추천 표현을 후처리로 제거' },
      { kind: 'output', title: '리포트 화면', desc: '결과 페이지에 섹션별로 표시, 캐시됨' },
    ],
    location: 'backend/advisor/ · report_evidence',
  },
  {
    id: 'grounding',
    name: '테마 학습기',
    tagline: '지식그래프 + 용어 학습',
    summary:
      'AI가 모르는 신조어 테마("마운자로 관련주")를 만나면 인터넷 검색으로 학습해 종목 집단으로 해석한다. 학습 결과는 지식그래프와 어휘집에 영속 저장되어 다음부터는 검색 없이 즉시 해석된다.',
    flow: [
      { kind: 'input', title: '모르는 테마 용어', desc: '"ESS 관련주", "비만치료 관련주"' },
      { kind: 'data', title: '어휘집 캐시 조회', desc: '이미 학습한 용어면 검색·AI 없이 즉시 해석 (재검색 방지)' },
      {
        kind: 'data',
        title: '지식그래프 조회',
        items: ['운영자 시드 테마 (핵심 기업만 엄선)', '네이버 금융 테마 카탈로그 285개', '주달 테마 208개', '검색으로 학습된 기업 연결'],
      },
      { kind: 'data', title: '네이버 실시간 테마 조회', desc: '그래프에 없으면 네이버 금융 라이브 테마를 조회해 즉시 편입' },
      {
        kind: 'llm',
        title: '뉴스 검색 학습',
        desc: '그래도 없으면 뉴스 검색 → AI가 닫힌 업종 목록으로만 매핑. 외부 본문은 비신뢰 데이터로 취급 (프롬프트 인젝션 방어)',
      },
      {
        kind: 'guard',
        title: '정본 게이트',
        desc: '검색 결과가 뭐라 하든 지원 업종 목록 밖 이름은 탈락 → 되묻기로 폴백. 상장사명이 테마로 오인되는 것도 차단',
      },
      { kind: 'data', title: '어휘집 영속 저장', desc: '성공·실패 모두 기록 (실패도 90일간 재검색 억제, 미해결 항목만 조건부 재검색)' },
      {
        branches: [
          {
            label: '해석 성공',
            nodes: [{ kind: 'output', title: '테마 유니버스 확정', desc: '조회된 전체 종목이 백테스트 대상 (종수 상한 절단 금지). 유니버스가 단일 시장(코스피만 등)으로 확정돼 있으면 정본 시장 소속으로 좁힌다' }],
          },
          {
            label: '검색 소진',
            nodes: [{ kind: 'ask', title: '"전략 불가" 종결 안내', desc: '해석 불가 테마는 명확히 종결하고 대안 유도' }],
          },
        ],
      },
    ],
    notes: ['운영 콘솔의 Knowledge 탭에서 실제 그래프 데이터를 조회할 수 있다.'],
    location: 'backend/engine/term_grounding.py · knowledge_graph.py',
  },
  {
    id: 'stock',
    name: '종목 질문 도우미',
    tagline: '개별 종목 대응',
    summary:
      '"삼성전자 지금 사도 돼?" 같은 개별 종목 질문에 매수·매도 판단을 제공하지 않고(규제 안전), 그 종목을 소재로 한 전략 연구로 전환시키는 안내자.',
    flow: [
      { kind: 'input', title: '종목 언급 질문', desc: '"삼성전자 어때?", "제주반도체로 백테스트"' },
      {
        kind: 'auto',
        title: '종목명 인식',
        desc: '전 상장 종목 사전 기반 결정적 매칭 — 조사 경계("제주반도체로"의 "로") 처리 포함',
      },
      {
        kind: 'guard',
        title: '규제 가드',
        desc: '매수·매도·전망 판단 요청이면 판단 불가를 명확히 안내 — 종목 분석 기능은 의도적으로 제거된 상태',
      },
      {
        kind: 'auto',
        title: '전략 전환 안내',
        desc: '그 종목의 업종을 알면 업종 전략을, 아니면 해당 종목 백테스트 예시를 제시',
      },
      {
        kind: 'data',
        title: '단일 종목 연구 프로파일',
        desc: '과거 데이터 사전 분석(변동성·거래대금 등)을 결정론으로 계산해 문답의 근거로 사용',
      },
      {
        kind: 'output',
        title: '단일 종목 빌더 모드 진입',
        desc: '"이 종목을 언제 사고 언제 팔까" 중심의 전략 빌더로 연결',
      },
    ],
    notes: ['복수 종목을 언급하면 전체를 백테스트하고 채팅 수정으로 조정한다 — "한 종목만 고르기" 되묻기는 폐지됨.'],
    location: 'backend/stock_analysis/ · engine/stock_profile.py',
  },
]

// ─────────────────────────────────────────────────────────────────────────────

function NodeCard({ node }: { node: FlowNode }) {
  const meta = KIND_META[node.kind]
  return (
    <div className={`rounded-lg border ${meta.border} bg-white/[0.03] px-3.5 py-2.5`}>
      <div className="flex items-center gap-2">
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${meta.badge}`}>
          {meta.label}
        </span>
        <span className="text-sm font-bold text-gray-100">{node.title}</span>
      </div>
      {node.desc && <p className="mt-1 text-xs leading-relaxed text-gray-400">{node.desc}</p>}
      {node.items && (
        <ul className="mt-1.5 space-y-0.5">
          {node.items.map((item) => (
            <li key={item} className="flex gap-1.5 text-xs leading-relaxed text-gray-400">
              <span className="text-gray-600">·</span>
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Arrow() {
  return (
    <div className="flex justify-center py-1" aria-hidden>
      <svg width="10" height="16" viewBox="0 0 10 16" className="text-gray-600">
        <line x1="5" y1="0" x2="5" y2="10" stroke="currentColor" strokeWidth="1.5" />
        <path d="M1 9 L5 15 L9 9" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </div>
  )
}

function BranchStep({ step }: { step: FlowBranch }) {
  return (
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: `repeat(${step.branches.length}, minmax(0, 1fr))` }}
    >
      {step.branches.map((branch) => (
        <div key={branch.label} className="rounded-xl border border-dashed border-white/15 p-3">
          <p className="mb-2 text-center text-[11px] font-bold text-gray-500">{branch.label}</p>
          <div>
            {branch.nodes.map((node, i) => (
              <div key={node.title}>
                {i > 0 && <Arrow />}
                <NodeCard node={node} />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
      {(Object.keys(KIND_META) as NodeKind[]).map((kind) => (
        <span key={kind} className="flex items-center gap-1.5">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${KIND_META[kind].badge}`}>
            {KIND_META[kind].label}
          </span>
        </span>
      ))}
    </div>
  )
}

export default function AgentsTab() {
  const [agentId, setAgentId] = useState(AGENTS[0].id)
  const agent = AGENTS.find((a) => a.id === agentId) ?? AGENTS[0]

  return (
    <div>
      <div className="mb-1 flex items-end justify-between">
        <h2 className="text-xl font-black">Agents</h2>
        <Legend />
      </div>
      <p className="mb-4 text-xs font-bold text-gray-600">
        플랫폼에 탑재된 AI 파이프라인의 설계 구조. 코드가 아니라 운영자용 명칭으로 표기한다.
      </p>

      {/* 서브탭 */}
      <div className="mb-5 flex flex-wrap gap-1.5">
        {AGENTS.map((a) => (
          <button
            key={a.id}
            onClick={() => setAgentId(a.id)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition-colors ${
              a.id === agentId
                ? 'border-white/25 bg-white/10 text-white'
                : 'border-white/10 text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
          >
            {a.name}
          </button>
        ))}
      </div>

      {/* 선택된 agent */}
      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
        <div className="mb-1 flex items-baseline gap-2.5">
          <h3 className="text-lg font-black">{agent.name}</h3>
          <span className="text-xs font-bold text-gray-500">{agent.tagline}</span>
        </div>
        <p className="mb-5 max-w-3xl text-sm leading-relaxed text-gray-400">{agent.summary}</p>

        <div className="mx-auto max-w-2xl">
          {agent.flow.map((step, i) => (
            <div key={i}>
              {i > 0 && <Arrow />}
              {'branches' in step ? <BranchStep step={step} /> : <NodeCard node={step} />}
            </div>
          ))}
        </div>

        {agent.notes && agent.notes.length > 0 && (
          <div className="mt-6 rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3">
            <p className="mb-1.5 text-[11px] font-bold text-gray-500">운영 메모</p>
            <ul className="space-y-1">
              {agent.notes.map((note) => (
                <li key={note} className="flex gap-1.5 text-xs leading-relaxed text-gray-400">
                  <span className="text-gray-600">·</span>
                  {note}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="mt-4 text-right text-[11px] font-bold text-gray-600">구현 위치: {agent.location}</p>
      </div>
    </div>
  )
}
