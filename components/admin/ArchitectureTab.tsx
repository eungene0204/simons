'use client'

import { useEffect, useState } from 'react'

// ─────────────────────────────────────────────────────────────────────────────
// 서비스 전체 구조(아키텍처) 시각화 탭.
// 코드에서 자동 추출하지 않는 정적 스냅샷이다 — 구조가 바뀌면 이 데이터를 함께 갱신할 것.
// 정본 문서: docs/software_architecture.md · docs/deployment.md · CLAUDE.md
// AI 파이프라인 각각의 내부 흐름은 Agents 탭이 담당하고, 여기서는 시스템 전체의
// 계층·경계·데이터 흐름을 다룬다.
// 카드에 detail이 있으면 클릭 시 상세 패널이 열린다.
// ─────────────────────────────────────────────────────────────────────────────

type Domain = 'user' | 'next' | 'py' | 'engine' | 'ai' | 'data' | 'ext' | 'guard'

const DOMAIN_META: Record<Domain, { label: string; badge: string; border: string }> = {
  user: { label: '사용자 화면', badge: 'bg-gray-500/20 text-gray-300', border: 'border-gray-500/40' },
  next: { label: 'Next.js 서버', badge: 'bg-sky-500/20 text-sky-300', border: 'border-sky-500/40' },
  py: { label: 'FastAPI 백엔드', badge: 'bg-emerald-500/20 text-emerald-300', border: 'border-emerald-500/40' },
  engine: { label: '백테스트 엔진', badge: 'bg-indigo-500/20 text-indigo-300', border: 'border-indigo-500/40' },
  ai: { label: 'AI·LLM', badge: 'bg-purple-500/20 text-purple-300', border: 'border-purple-500/40' },
  data: { label: '데이터 저장소', badge: 'bg-amber-500/20 text-amber-300', border: 'border-amber-500/40' },
  ext: { label: '외부 서비스', badge: 'bg-rose-500/20 text-rose-300', border: 'border-rose-500/40' },
  guard: { label: '안전장치', badge: 'bg-red-500/20 text-red-300', border: 'border-red-500/40' },
}

interface BoxDetail {
  overview?: string
  points?: string[]
  history?: string[]
  location?: string
}

interface ArchBox {
  domain: Domain
  title: string
  desc?: string
  items?: string[]
  detail?: BoxDetail
}

interface ArchLayer {
  title: string
  subtitle?: string
  location?: string
  boxes: ArchBox[]
}

type OnSelectBox = (box: ArchBox) => void

// ─── 렌더링 프리미티브 ────────────────────────────────────────────────────────

function BoxCard({ box, onSelect }: { box: ArchBox; onSelect?: OnSelectBox }) {
  const meta = DOMAIN_META[box.domain]
  const clickable = Boolean(box.detail && onSelect)

  const inner = (
    <>
      <div className="flex items-start gap-2">
        <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${meta.badge}`}>
          {meta.label}
        </span>
        <span className="text-sm font-bold leading-snug text-gray-100">{box.title}</span>
        {clickable && <span className="ml-auto shrink-0 text-[10px] font-bold text-gray-600">상세 ›</span>}
      </div>
      {box.desc && <p className="mt-1 text-xs leading-relaxed text-gray-400">{box.desc}</p>}
      {box.items && (
        <ul className="mt-1.5 space-y-0.5">
          {box.items.map((item) => (
            <li key={item} className="flex gap-1.5 text-xs leading-relaxed text-gray-400">
              <span className="text-gray-600">·</span>
              {item}
            </li>
          ))}
        </ul>
      )}
    </>
  )

  if (!clickable) {
    return <div className={`rounded-lg border ${meta.border} bg-white/[0.03] px-3 py-2.5`}>{inner}</div>
  }
  return (
    <button
      type="button"
      onClick={() => onSelect!(box)}
      className={`block w-full rounded-lg border ${meta.border} bg-white/[0.03] px-3 py-2.5 text-left transition-colors hover:bg-white/[0.07]`}
    >
      {inner}
    </button>
  )
}

function DetailModal({ box, onClose }: { box: ArchBox; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const meta = DOMAIN_META[box.domain]
  const detail = box.detail
  if (!detail) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden />
      <div className="relative max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-xl border border-white/15 bg-[#161616] p-5 shadow-2xl">
        <div className="mb-3 flex items-start gap-2.5">
          <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold ${meta.badge}`}>
            {meta.label}
          </span>
          <h3 className="text-base font-black leading-snug text-white">{box.title}</h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="ml-auto shrink-0 rounded-md border border-white/10 px-2 py-0.5 text-xs font-bold text-gray-400 hover:bg-white/5 hover:text-gray-200"
          >
            ✕
          </button>
        </div>

        {detail.overview ? (
          <p className="text-sm leading-relaxed text-gray-300">{detail.overview}</p>
        ) : (
          box.desc && <p className="text-sm leading-relaxed text-gray-300">{box.desc}</p>
        )}

        {detail.points && detail.points.length > 0 && (
          <div className="mt-4">
            <p className="mb-1.5 text-[11px] font-bold text-gray-500">핵심 설계·동작</p>
            <ul className="space-y-1">
              {detail.points.map((p) => (
                <li key={p} className="flex gap-1.5 text-xs leading-relaxed text-gray-300">
                  <span className="text-gray-600">·</span>
                  {p}
                </li>
              ))}
            </ul>
          </div>
        )}

        {detail.history && detail.history.length > 0 && (
          <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.02] px-3.5 py-2.5">
            <p className="mb-1.5 text-[11px] font-bold text-gray-500">운영 메모·사고 이력</p>
            <ul className="space-y-1">
              {detail.history.map((h) => (
                <li key={h} className="flex gap-1.5 text-xs leading-relaxed text-gray-400">
                  <span className="text-gray-600">·</span>
                  {h}
                </li>
              ))}
            </ul>
          </div>
        )}

        {detail.location && (
          <p className="mt-4 text-right text-[11px] font-bold text-gray-600">구현 위치: {detail.location}</p>
        )}
      </div>
    </div>
  )
}

function LayerSection({ layer, onSelect }: { layer: ArchLayer; onSelect?: OnSelectBox }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex items-baseline gap-2.5">
          <h4 className="text-sm font-black text-gray-100">{layer.title}</h4>
          {layer.subtitle && <span className="text-xs font-bold text-gray-500">{layer.subtitle}</span>}
        </div>
        {layer.location && <span className="text-[11px] font-bold text-gray-600">{layer.location}</span>}
      </div>
      <div className="grid gap-2.5" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
        {layer.boxes.map((box) => (
          <BoxCard key={box.title} box={box} onSelect={onSelect} />
        ))}
      </div>
    </section>
  )
}

function DownArrow({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-1.5" aria-hidden>
      <svg width="10" height="18" viewBox="0 0 10 18" className="text-gray-600">
        <line x1="5" y1="0" x2="5" y2="12" stroke="currentColor" strokeWidth="1.5" />
        <path d="M1 11 L5 17 L9 11" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      {label && <span className="text-[11px] font-bold text-gray-600">{label}</span>}
    </div>
  )
}

interface FlowBranchSpec {
  branches: { label: string; nodes: ArchBox[] }[]
}

type FlowStep = ArchBox | FlowBranchSpec

function FlowColumn({ steps, onSelect }: { steps: FlowStep[]; onSelect?: OnSelectBox }) {
  return (
    <div className="mx-auto max-w-2xl">
      {steps.map((step, i) => (
        <div key={i}>
          {i > 0 && <DownArrow />}
          {'branches' in step ? (
            <div
              className="grid gap-3"
              style={{ gridTemplateColumns: `repeat(${step.branches.length}, minmax(0, 1fr))` }}
            >
              {step.branches.map((branch) => (
                <div key={branch.label} className="rounded-xl border border-dashed border-white/15 p-3">
                  <p className="mb-2 text-center text-[11px] font-bold text-gray-500">{branch.label}</p>
                  <div>
                    {branch.nodes.map((node, j) => (
                      <div key={node.title}>
                        {j > 0 && <DownArrow />}
                        <BoxCard box={node} onSelect={onSelect} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <BoxCard box={step} onSelect={onSelect} />
          )}
        </div>
      ))}
    </div>
  )
}

function NotePanel({ title, notes }: { title?: string; notes: string[] }) {
  return (
    <div className="mt-5 rounded-lg border border-white/10 bg-white/[0.02] px-4 py-3">
      <p className="mb-1.5 text-[11px] font-bold text-gray-500">{title ?? '운영 메모'}</p>
      <ul className="space-y-1">
        {notes.map((note) => (
          <li key={note} className="flex gap-1.5 text-xs leading-relaxed text-gray-400">
            <span className="text-gray-600">·</span>
            {note}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      {(Object.keys(DOMAIN_META) as Domain[]).map((d) => (
        <span key={d} className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${DOMAIN_META[d].badge}`}>
          {DOMAIN_META[d].label}
        </span>
      ))}
    </div>
  )
}

// ─── 1. 전체 조감도 ──────────────────────────────────────────────────────────

const OVERVIEW_LAYERS: ArchLayer[] = [
  {
    title: '사용자 접점 (브라우저)',
    subtitle: 'Next.js 14 App Router 페이지',
    location: 'app/ · components/',
    boxes: [
      {
        domain: 'user',
        title: '전략 연구소 /analytics/new',
        desc: '서비스의 중심 화면 — 자연어 채팅으로 전략 설계·수정, 되묻기 칩, 백테스트 실행까지 한 화면',
        detail: {
          location: 'app/analytics/new/page.tsx · components/strategy/',
          overview:
            '자연어 채팅으로 전략을 설계하고 같은 화면에서 백테스트까지 실행하는 서비스의 중심 화면. 한 턴은 "상태 재평가 → 액션 선택 → 응답 조립" 순서로 처리된다(턴 중재 구조, 액션당 핸들러는 하나).',
          points: [
            '예시 프롬프트 탭 — 초보/중급/고급 × 가치투자·기술분석·모멘텀·복합전략. 예시 문구를 바꾸면 실제 파싱 검증까지 돌리는 것이 규칙',
            '채팅 전송은 SSE 스트림 — 수락 즉시 임시 전략 골격(skeleton)을 먼저 그리고, 해석 진행 단계를 실시간 표시',
            '파싱 결과는 노란 테두리 요약 카드로, 되묻기는 질문+추천값 칩(발행 시점 값 결속)으로 마지막 말풍선에만 렌더',
            '독립형 배치 백테스트(RunAllTestsModal) — 프롬프트 여러 개를 큐로 돌려 CAGR 기준 리더보드 정렬',
            'BacktestDashboard는 동적 import로 초기 로딩을 가볍게 유지',
          ],
          history: [
            '전략 생성 중 잡담·용어 질문이 끼어도 열려 있던 되묻기(질문·칩)를 스냅샷으로 되붙인다 — 한 마디에 질문이 통째로 사라지던 실측 사고의 수리(FR-SA-015)',
            '에러 말풍선도 응답으로 인정 — 파싱 실패 시 입력창이 사라지던 버그 수정',
          ],
        },
      },
      {
        domain: 'user',
        title: '백테스트 결과 /backtest/[id]',
        desc: '수익곡선·통계·거래 내역·AI 리포트·워크포워드/몬테카를로 검증. 저장 전략은 /analytics/[id]',
        detail: {
          location: 'app/backtest/[id]/ · app/analytics/[id]/ · components/strategy/backtest/',
          overview:
            '엔진이 계산한 결과를 통계·차트·거래 내역·AI 해설로 보여주는 화면. 결과는 전역 공유 저장 + 사용자별 이력 조인(soft delete)으로 관리된다.',
          points: [
            '수익곡선 + 벤치마크(KODEX 지수 ETF) — 벤치마크 미존재 구간은 null로 비워 가짜 선을 그리지 않음',
            '통계 요약 — CAGR·MDD·샤프·소르티노·승률·Profit Factor·켈리. 정의 불가 값은 0이 아니라 null',
            '거래 내역의 청산 사유(손절·익절·리밸런싱 편출 등)는 시뮬레이터가 확정한 라벨이 정본 — 프론트 재라벨 금지',
            'AI 리포트(10섹션)·워크포워드/몬테카를로 모달·XAI(SHAP) 모달 연결',
            '기록 목록은 서버 렌더 + 표시 캐시로 재진입 즉시 표시',
          ],
          history: [
            '표시 버그 4건 수리 이력 — 이름 자리표시자 판정 해시 고정 · 총수익 0원(finalEquity 폴백) · 매매기록 탭 비어보임(signals→tradesList) · null result 레이스(자동저장이 result 항상 포함)',
          ],
        },
      },
      {
        domain: 'user',
        title: '대시보드 /',
        desc: '포트폴리오 요약·계좌 수익 차트·가상매매 현황',
        detail: {
          location: 'app/page.tsx · components/dashboard/',
          overview: '로그인 직후 보는 홈 — 자산 요약과 가상매매 현황을 모아 보여준다.',
          points: [
            '포트폴리오 요약 바 + 계좌 수익 차트 — 수익률은 투자금 가중으로 합산',
            '가상매매 현황 위젯 — 신호·체결 로그 연동',
            'MarketSnapshot(시장 스냅샷) 위젯은 의도적 비활성 — 되살리지 않는다',
          ],
        },
      },
      {
        domain: 'user',
        title: '종목 /stock/[symbol] · /stock-order',
        desc: '차트·호가·종목정보·뉴스/공시·가상 주문 (5탭)',
        detail: {
          location: 'app/stock/[symbol]/ · app/stock-order/ · components/stock/ · components/order/',
          overview: '종목 상세와 가상 주문 화면. 실시간 값과 저빈도 값을 다른 경로로 분리한 것이 설계 핵심이다.',
          points: [
            '5탭 — 차트·호가 / 종목정보 / 뉴스·공시 / 거래현황 / 커뮤니티',
            '종목정보 탭은 비실시간 프로필 레이어(DB: 상장일·섹터·재무 요약·PER/PBR) — 현재가·등락률·거래량은 실시간 시세 경로에서 조회',
            '뉴스·공시 탭은 news_v2 캐시만 읽는다 — 조회 시점에 크롤러·LLM을 실행하지 않음',
            '실시간 시세는 KIS WebSocket 1세션 프록시로 공유',
            '주문 페이지의 선택 계좌는 OrderAccountContext로 공유',
          ],
        },
      },
      {
        domain: 'user',
        title: '가상계좌 /virtual-account',
        desc: '모의투자 계좌 목록·포트폴리오·거래 내역 (실전 매매 없음)',
        detail: {
          location: 'app/virtual-account/ · components/virtual-account/',
          overview: '모의투자 계좌의 목록·상세 화면. 실전 매매 기능은 존재하지 않는다.',
          points: [
            '계좌는 플랜(FREE/PRO/PREMIUM)에 정의된 계좌당 초기 투자금으로 독립 생성 — 클라이언트가 보낸 금액은 무시하고 서버가 확정',
            '해지는 확인 모달 먼저 — "남은 현금·보유 종목은 다른 계좌로 이전되지 않습니다" 고지 후에만 실행',
            '해지 시 보유 포지션을 현재가로 강제매도 후 CLOSED — 정산값은 원장(ACCOUNT_LIQUIDATION_RETURN)에만 기록',
            '일시 중지(PAUSED) 계좌는 기존 주문 가드가 거래를 자동 차단',
          ],
        },
      },
      {
        domain: 'user',
        title: '관심종목 /watchlist',
        desc: '관심 종목 그룹 관리',
        detail: {
          location: 'app/watchlist/ · components/watchlist/',
          overview: '관심 종목을 그룹으로 묶어 관리한다(WatchlistGroup → WatchlistSymbol 1:N).',
          points: ['그룹 생성·이동·삭제', '종목 상세·주문 화면으로 바로 연결'],
        },
      },
      {
        domain: 'user',
        title: '요금제 /pricing',
        desc: 'FREE/PRO/PREMIUM 구독 — 토스 자동결제(빌링) 체크아웃',
        detail: {
          location: 'app/pricing/ · app/api/payment/',
          overview:
            '토스페이먼츠 자동결제(빌링) 기반 구독. 카드를 한 번 등록해 빌링키를 발급받고 이후 매월 서버가 자동 청구한다.',
          points: [
            '체크아웃 3단계 — ① 서버 주문 생성(금액은 lib/plans.ts에서만 계산, PENDING 기록) ② 카드 등록창(requestBillingAuth) ③ 성공 페이지의 confirm → 빌링키 발급 → 첫 달 즉시 청구',
            '같은 주문의 재승인 요청(성공 페이지 새로고침)은 기존 결과 반환 — 멱등',
            '해지는 즉시 다운그레이드가 아니라 해지 예약 — 다음 결제일에 청구 없이 FREE 전환',
            'FREE 다운그레이드 외의 플랜 변경 API는 차단 — 결제 없는 유료 전환 불가',
          ],
          history: ['프로덕션 전환 시 빌링 계약이 완료된 상점의 라이브 키로 교체 필요 — 미계약 키는 NOT_SUPPORTED_METHOD 에러'],
        },
      },
      {
        domain: 'user',
        title: '인증 /login · /register',
        desc: 'JWT 쿠키 세션',
        detail: {
          location: 'app/login/ · app/register/ · lib/server/',
          overview: 'JWT 쿠키 세션 기반 인증.',
          points: [
            '정지(SUSPENDED)·삭제(DELETED)는 soft 처리 — 로그인(403)과 기존 세션(getCurrentUser가 null)을 모두 차단',
            '관리자 여부는 별도 축(User.role) — 부여는 DB 직접 변경으로만 가능',
          ],
        },
      },
      {
        domain: 'user',
        title: '운영 콘솔 /console',
        desc: '관리자 전용(role=ADMIN, 실패 시 404로 존재 은닉) — 지금 보고 있는 화면',
        detail: {
          location: 'app/console/page.tsx · components/admin/ · app/api/admin/',
          overview: '운영자 전용 단일 화면. 보안은 UI 숨김이 아니라 서버 권한 검증이 담당한다.',
          points: [
            'requireAdmin — JWT 쿠키 + role=ADMIN + status=ACTIVE 3중 검사, 실패 시 404로 존재 자체를 숨김',
            '기능별 관리자 API 각각에도 같은 게이트 — 페이지만 뚫어도 API가 막는다',
            '모든 변경은 AdminAuditLog(before/after JSON + IP)에 기록 — 감사 로그 삭제 API는 없다',
            '탭 10개 — Overview·Architecture·Users·Backtests·Virtual Accounts·Strategies·Plans·Knowledge·Agents·Audit Logs',
          ],
        },
      },
    ],
  },
  {
    title: 'Next.js 서버 (web 컨테이너)',
    subtitle: 'BFF — 인증·플랜·결제·프록시·캐시를 담당하는 중간 서버',
    location: 'app/api/ · lib/',
    boxes: [
      {
        domain: 'next',
        title: 'API 라우트 (FastAPI 프록시 + 자체 로직)',
        desc: '브라우저는 FastAPI를 직접 호출하지 않는다 — 모든 요청이 Next.js API 라우트를 거친다',
        detail: {
          location: 'app/api/ · lib/server/backend.ts',
          overview:
            '브라우저와 FastAPI 사이의 유일한 통로. 인증·플랜·캐시처럼 사용자 컨텍스트가 필요한 로직은 여기서 처리하고, 계산은 FastAPI로 넘긴다.',
          points: [
            'FastAPI 프록시는 fetch wrapper(lib/server/backend.ts)로 단일화',
            '전략 저장(strategy_id=SHA-256 canonical DSL)·배치 백테스트 큐(BatchRun)·자산 조회 같은 자체 로직 포함',
            '런타임 볼륨을 읽는 GET 라우트는 force-dynamic — 빌드 시점 데이터로 굳는 정적 prerender 함정 회피',
          ],
          history: [
            'route 파일의 비표준 export는 tsc·vitest·CI를 전부 통과하고 배포 빌드에서만 깨진다 — 순수 함수는 형제 모듈로 분리하는 것이 규칙',
          ],
        },
      },
      {
        domain: 'next',
        title: '백테스트 SSE 라우트',
        desc: '쿼터 소진(consumeBacktestQuota) → FastAPI 스트림 프록시 → 이력 자동저장. 실행 경로 2개 모두 쿼터를 거친다',
        detail: {
          location: 'app/api/strategy/backtest-stream/ · app/api/strategy/parse/stream/',
          overview: '백테스트 실행 요청의 관문 — 쿼터를 소진하고, FastAPI 스트림을 중계하고, 끝나면 이력을 저장한다.',
          points: [
            '실행 경로 2개(스트림 실행·저장+실행) 모두 consumeBacktestQuota를 거친다 — 한쪽만 세는 우회 없음',
            '파싱의 후행 교정 이벤트(parsed_updated)는 백테스트 실행 전이면 조용히 반영, 실행 후 도착하면 무시 — 실행 스냅샷 일관성',
            '이력 자동저장은 result를 항상 포함 — null result 레이스 방지',
            '결과 캐시 재사용은 폐지 — 항상 엔진을 재실행한다',
          ],
        },
      },
      {
        domain: 'next',
        title: '플랜 한도 시스템',
        desc: '계좌 수·저장 전략 수·월 백테스트 횟수(구독 시작일 기준 롤링 주기) — lib/plans.ts 기본값 + 콘솔 PlanConfig 오버라이드',
        detail: {
          location: 'lib/plans.ts · lib/server/planLimits.ts',
          overview:
            '플랜(FREE/PRO/PREMIUM)이 가상계좌 자금과 사용량 한도를 결정한다. 과거의 공유 "자산 지갑" 풀 모델은 폐기됐다.',
          points: [
            '3개 한도 — 가상계좌 수·저장 전략 수(주기 리셋 없는 상시 캡), 월 백테스트 횟수(주기 리셋)',
            '백테스트 주기는 구독 시작일 기준 롤링 1개월(currentPlanCycle) — 구독 이력 없으면 KST 캘린더 월 폴백',
            '기본값은 lib/plans.ts 하드코딩, 콘솔 PlanConfig 오버라이드가 있으면 getEffectivePlan()이 병합(null 필드=기본값, maxStrategies=-1=무제한)',
            '플랜 변경은 이미 생성된 계좌의 초기 투자금·잔고를 소급 변경하지 않는다',
          ],
        },
      },
      {
        domain: 'next',
        title: '토스 자동결제(빌링)',
        desc: '카드 1회 등록 → 빌링키 발급 → 매월 서버 자동 청구. 금액은 서버만 계산, 연속 3회 실패 시 FREE 전환',
        detail: {
          location: 'lib/server/tossPayments.ts · lib/server/billingRenewal.ts',
          overview: '서버 관점의 결제 계약 — 금액 계산·청구·갱신·실패 처리 전부 서버 전용이다.',
          points: [
            '토스 API 인증은 Basic(base64 시크릿키), 청구 멱등키=orderId',
            '매시 갱신 잡이 nextBillingAt 지난 구독을 청구 — 성공 시 예정 시각 기준 +1개월(재시도 지연으로 주기가 밀리지 않게)',
            '실패 시 1일 후 재시도, 연속 3회 실패면 FREE 전환 + 빌링 상태 해제 — 사용자별 실패 격리',
            '빌링키(User.tossBillingKey)·시크릿 키는 서버 전용 — 클라이언트 노출 없음',
          ],
        },
      },
      {
        domain: 'next',
        title: '인프로세스 스케줄러',
        desc: 'lib/scheduler.ts — 매시 정각 구독 갱신 청구(processDueBillingRenewals)',
        detail: {
          location: 'lib/scheduler.ts · instrumentation.ts',
          overview: '별도 크론 인프라 없이 Next.js 프로세스 안에서 도는 스케줄러 — 현재 잡은 매시 구독 갱신 청구다.',
          points: ['매시 정각(주말 포함) processDueBillingRenewals() 실행 — 지난 결제일 구독을 찾아 청구'],
          history: ['instrumentation 경로에 next/headers가 전이 import되면 기동이 깨진다 — import 경로 주의'],
        },
      },
      {
        domain: 'next',
        title: 'Prisma (앱 DB 접근 단일화)',
        desc: 'Supabase Postgres — 원격 DB라 트랜잭션 명시 타임아웃·왕복 배칭(Promise.all) 필수',
        detail: {
          location: 'lib/prisma.ts · prisma/schema.prisma',
          overview: '앱 DB(Supabase Postgres) 접근의 단일 창구. "원격 DB"라는 사실이 코드 패턴을 강제한다.',
          points: [
            'us-west-1 pooler 경유 필수',
            '순차 쿼리는 왕복 지연이 쌓인다 — 독립 쿼리는 Promise.all로 배칭',
            '대형 페이로드 $transaction은 명시 타임아웃 필수 — 기본 5초 초과가 저장 실패 500의 정체였다',
          ],
          history: ['배포는 마이그레이션을 실행하지 않는다 — 스키마 변경 시 prod에 prisma migrate deploy 수동 적용'],
        },
      },
      {
        domain: 'guard',
        title: '관리자 게이트 + 감사 로그',
        desc: 'requireAdmin(JWT+role+status) — 모든 변경은 AdminAuditLog(before/after+IP)에 기록, 삭제 API 없음',
        detail: {
          location: 'lib/server/adminAuth.ts · app/api/admin/',
          overview: '콘솔과 관리자 API 전체를 지키는 게이트.',
          points: [
            'requireAdmin — JWT + role=ADMIN + status=ACTIVE, 실패는 404(존재 은닉)',
            '기능별 관리자 API 각각이 게이트를 통과해야 동작',
            '모든 변경은 writeAuditLog로 AdminAuditLog에 기록(before/after + IP) — 감사 로그 삭제 API는 없다',
            '사용자 정지/삭제는 User.status soft 처리, 계좌 일시 중지는 status=PAUSED로 기존 주문 가드 재사용',
          ],
        },
      },
    ],
  },
  {
    title: 'FastAPI 백엔드 (backend 컨테이너)',
    subtitle: '전략 해석·백테스트·시장 데이터·가상매매의 본체',
    location: 'backend/',
    boxes: [
      {
        domain: 'py',
        title: '전략 대화 라우터',
        desc: '/strategy/parse(+stream) · /query/classify · /strategy/builder/step — AI 에이전트 계층 호출',
        detail: {
          location: 'backend/api/intent_routes.py · backend/strategy_conversation/',
          overview: '채팅 발화가 백엔드에서 처리되는 입구 — 의도 분류·전략 해석·빌더 한 턴이 여기로 들어온다.',
          points: [
            '/query/classify — 의도 라벨 + 워크플로 제어 축 + 값 조회 축 + 소속 목록 축을 한 번의 LLM 호출로 판정',
            '/strategy/parse(+stream) — LLM-first 해석 파이프라인 + SSE 진행 단계 스트리밍',
            '/strategy/builder/step — 무상태 상태 머신 한 턴(상태는 프론트가 보관·재전송)',
            'LLM 어댑터 2갈래 — 구조화 출력은 greedy, 설명문(/query/general)은 샘플링',
            '워크플로 상태·변경 이력은 서버에 저장하지 않는다 — 프론트가 매 요청에 에코(무상태 계약)',
          ],
        },
      },
      {
        domain: 'py',
        title: '백테스트 라우터',
        desc: '/backtest · /strategy/backtest-stream — 워치독(BACKTEST_TIMEOUT_S)이 감싸 행(hang)이어도 반드시 끝난다',
        detail: {
          location: 'backend/main.py · backend/engine/watchdog.py',
          overview: '백테스트 실행 API. 어떤 경우에도 "끝나지 않는 요청"이 없도록 워치독이 감싼다.',
          points: [
            '워치독 — 벽시계 제한(BACKTEST_TIMEOUT_S, 기본 600초) 안에 반드시 504/SSE 에러로 종료. 타임아웃 후 thread.join()으로 재차 대기하지 않는다',
            'AI 신호 백테스트는 fail-fast — 모델 로드 실패·비활성 시 0거래 침묵 진행 대신 즉시 명확한 에러',
            'SSE 경로의 파싱 검증은 후행(비차단) — 결과를 먼저 내보내고 교정은 result_update 이벤트로 후속 전송',
          ],
        },
      },
      {
        domain: 'py',
        title: '검증 라우터',
        desc: '/walk-forward · 몬테카를로 · /optimize(Optuna) — 결과는 SavedValidation으로 저장/불러오기',
        detail: {
          location: 'backend/engine/walk_forward.py 등',
          overview: '전략의 견고성을 확인하는 검증 도구 모음 — 워크포워드·몬테카를로·파라미터 최적화.',
          points: [
            '워크포워드 — 구간 분할 검증, 타임아웃 3600초(프록시는 3660초로 한 겹 밖에서 대기)',
            '엔진에 넘길 파라미터는 화이트리스트 검증',
            '사용자용 몬테카를로(결과 화면 표시)와 리서치 에이전트의 MC는 별개 구현',
            '검증 결과는 SavedValidation으로 저장/불러오기 — 재실행 없이 재조회',
          ],
        },
      },
      {
        domain: 'py',
        title: '시장 데이터 라우터',
        desc: '/market/* · /stock/* — 현재가·호가·지수·OHLCV (providers: KIS·pykrx·Naver)',
        detail: {
          location: 'backend/engine/market_data.py · providers/',
          overview: '현재가·호가·지수·캔들 조회 API. 공급자(KIS·pykrx·Naver·yfinance)를 추상화해 사용한다.',
          points: [
            '현재가 배치 조회·호가창 스트리밍·시장 지표(KOSPI·KOSDAQ·환율)',
            'OHLCV 캔들은 백테스트 엔진과 같은 parquet 경로에서 읽는다',
          ],
        },
      },
      {
        domain: 'py',
        title: 'AI 리포트·코치 라우터',
        desc: '/advisor/review(RAG+경험 메모리) · /strategy/coach(현재 검증 모드가 기본)',
        detail: {
          location: 'backend/advisor/ · backend/api/coach_routes.py',
          overview: '백테스트 결과 해설(advisor)과 전략 진단(코치 — 현재는 검증 모드)의 API.',
          points: [
            'advisor 하이브리드 — 진단·점수·백분위는 결정론 계산, LLM은 서술만',
            '코치는 검증 모드가 기본(_STRATEGY_AGENT_MODE 토글) — 과거 LLM 코칭 코드는 보존, 죽은 코드로 오인해 지우지 말 것',
            '역할 밖 요청은 scope guard가 가로챈다',
          ],
        },
      },
      {
        domain: 'py',
        title: '뉴스 파이프라인 (news_v2)',
        desc: '캐시 전용 조회 API + Hot/Warm/Cold 큐 백그라운드 수집·분석 — 전용 Postgres 사용',
        detail: {
          location: 'backend/news_v2/',
          overview: '종목 뉴스탭의 백그라운드 수집·분석 파이프라인. 조회 API는 캐시만 읽고, 무거운 일은 뒤에서 돈다.',
          points: [
            '조회 API(/v2/news/{symbol})는 stock_news_cache만 읽는다 — 조회 시점에 크롤러·LLM 미실행',
            '사용자 수요 기반 Priority Engine — 조회·검색·관심·보유 이벤트로 Hot/Warm/Cold 큐 배정',
            '전용 Postgres(NEWSV2_DB_URL) — 앱 DB와 분리해 부하 격리',
          ],
        },
      },
      {
        domain: 'py',
        title: '연구 에이전트 (Premium)',
        desc: '/research/* — 후보 생성→프리스크린→백테스트→견고성 검증→승격, SSE 이벤트 스트림',
        detail: {
          location: 'backend/research/',
          overview: '프리미엄 전용 — 템플릿 탐색 공간에서 후보 전략을 만들어 자동 백테스트·검증·승격까지 도는 상태머신.',
          points: [
            '후보 생성(SHA256 중복 제거, seeded) → 50종목 프리스크린 → 본 백테스트 → MC+WFA 견고성 검증',
            '복합 스코어 — tanh 한정 + Deflated Sharpe(다중 시도 보정)',
            '안전장치 — HoldoutGuard · CircuitBreaker · AIModelLeakGuard',
            '통과 후보는 가상계좌로 승격(promoter), 전 과정이 SSE 이벤트 + 감사 로그로 남는다',
          ],
        },
      },
      {
        domain: 'py',
        title: '가상매매 엔진 (인프로세스)',
        desc: 'VirtualTrader 비동기 루프 — 장 개장/정시/마감 사이클로 신호 평가·가상 체결',
        detail: {
          location: 'backend/engine/virtual_trader.py',
          overview: 'FastAPI 프로세스 안에서 도는 비동기 자동매매 루프 — 전체 흐름은 "가상매매" 서브탭 참고.',
          points: [
            '09:00 진입 평가 / 정시 청산 확인 / 15:30 마감 정산',
            '신호 유니버스는 매 사이클 전략 DSL에서 재해석 — 화면 모니터링 목록(상위 10종목)과 별개',
            '거래 비용 — 수수료 0.15% / 세금 0.30% / 슬리피지 0.20%',
          ],
        },
      },
      {
        domain: 'py',
        title: '관찰 계층 (observability)',
        desc: '로컬 trace(콘솔+JSONL) 기본 ON · LangSmith 기본 OFF — 실행 경로 불변',
        detail: {
          location: 'backend/observability/',
          overview: '에이전트 실행을 추적하는 계층 — 실행 경로를 바꾸지 않는 관찰 전용 설계.',
          points: [
            '로컬 trace(콘솔+JSONL) 기본 ON, LangSmith 기본 OFF',
            'chokepoint 5곳에서 span 기록 — 실행 계층을 import하지 않는 덕타이핑 어댑터',
            '스레드 경계는 부모 span을 명시 전파 — 안 하면 고아 trace가 된다',
            '평가 자산 — Evaluation Dataset 21개 + 결정론 evaluator 6축(LLM judge 없음)',
          ],
        },
      },
    ],
  },
  {
    title: 'AI 에이전트 계층',
    subtitle: '각 파이프라인의 상세 흐름은 Agents 탭 참고',
    location: 'backend/strategy_conversation/ · intent/ · advisor/ · engine/term_grounding.py',
    boxes: [
      {
        domain: 'ai',
        title: '전략 해석기',
        desc: '자연어 → 구조화 전략(StrategyIntent) — 의미는 AI만, 검증·컴파일은 결정론',
        detail: {
          location: 'backend/strategy_conversation/',
          overview:
            'LLM-first / Validation-heavy / Registry-driven — 자연어의 의미 해석은 LLM이 전담하고, 결정론 코드는 검증·컴파일·실행만 한다.',
          points: [
            '전용 9B 슬롯(STRATEGY_INTERPRETER_MODEL) — 온도 0 · JSON 강제 · think 끔',
            '프롬프트에 Registry 어휘(지표 온톨로지가 생성)를 주입 — 지원 지표 canonical ID 계약',
            '출력은 4단 검증 — 지원 여부(Capability) · 값 범위(Parameter) · 충돌(Conflict) · 완결성(Completeness)',
            '값 미정은 조용한 기본값 확정 없이 되묻기 — 추천값과 확정값을 분리(value_source)',
          ],
          history: ['상세 흐름도·사고 이력은 Agents 탭 "전략 해석기" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '대화 플래너',
        desc: '유니버스(업종·테마·종목) 사전 조사를 계획 — 실행은 자동 러너, 값 확정은 도구 결과만',
        detail: {
          location: 'backend/strategy_conversation/planner/ · tools/',
          overview: 'AI는 조사 계획(JSON 그래프)만 세우고 실행은 자동 러너가 하는 계획-실행 분리 구조.',
          points: [
            '유니버스 우선 — 시장/업종/테마/종목을 도구 호출로 먼저 확정',
            '확정값은 도구 결과에서만 채택 — AI가 문장 속에서 주장한 값은 무시(환각 차단)',
            '계획 예산 기본 2턴(+진전 시 최대 2턴 연장), 어떤 실패든 고정 파이프라인이 이어받는다',
            '테마 후보가 2개 이상이면 임의로 고르지 않고 사용자에게 되묻는다',
          ],
          history: ['상세 흐름도는 Agents 탭 "대화 플래너" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '질문 분류기',
        desc: '의도 라벨 + 워크플로 제어 + 규제 가드 — 채팅 입력이 가장 먼저 지나는 곳',
        detail: {
          location: 'backend/intent/interpreter.py · classifier.py',
          overview: '모든 채팅 입력이 가장 먼저 지나는 관문 — 의도를 판정해 담당 파이프라인에 배정한다.',
          points: [
            '한 번의 LLM 호출로 4축 판정 — 의도 라벨 · 워크플로 제어(멈춤·취소·되돌리기) · 값 조회(fact_metric) · 소속 목록(list_scope)',
            '성립 여부는 결정론이 정한다 — 규제 라벨이면 제어 거부, 불성립은 NONE 강등',
            '읽기 전용 질문("내가 뭘 정했지?")은 상태를 못 바꾸게 강등 — 답은 상태를 쥔 화면이 만든다',
            'AI 출력의 형식 결함(따옴표 없는 enum, 실측 34%)은 2차 파스로 수리 — 의미는 건드리지 않음',
          ],
          history: ['상세 흐름도는 Agents 탭 "질문 분류기" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '전략 빌더',
        desc: '열린 질문("뭐 살까?")을 추천 대신 단계별 문답으로 전환하는 상태 머신',
        detail: {
          location: 'backend/intent/strategy_builder.py · builder_interpreter.py',
          overview: '열린 추천 질문을 단계별 문답으로 전환하는 무상태 상태 머신 — 추천 대신 사용자가 직접 완성하게 돕는다.',
          points: [
            '시장 → 전략 유형 → 기준 기간 → 보유 종목 수 → 리밸런싱 순서 — 이미 말한 정보는 건너뜀',
            '칩·값 답변은 결정론 처리, 자유 서술만 LLM 해석 — 미인식 표현에 정규식 추가 금지',
            '확정 시 누적 구조를 직접 컴파일 — 자연어로 되돌려 재해석하지 않음(조건 소실 방지)',
          ],
          history: ['상세 흐름도는 Agents 탭 "전략 빌더" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '전략 수정기',
        desc: '차분(diff) 해석 + 환각 방지 게이트 + 결정적 병합 — 원본 전략 보호',
        detail: {
          location: 'backend/strategy_conversation/primary.py · engine/modify_rag.py',
          overview: '기존 전략에 수정 요청을 반영한다 — AI는 바뀐 부분(diff)만 내고, 게이트와 결정적 병합이 원본을 지킨다.',
          points: [
            '수정 단서를 결정적으로 감지해 환각 판정의 기준으로 사용',
            '환각 방지 게이트 — 인용 대조 + 값 자릿수 대조(10배·100배 어긋나면 폐기)',
            '결정적 병합 — 목록형 조건(재무 필터 등)이 통째로 사라지는 것을 방지',
            '실패해도 기존 전략은 절대 훼손하지 않고 되묻기',
          ],
          history: ['상세 흐름도는 Agents 탭 "전략 수정기" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '전략 검증 도우미',
        desc: '실행 가능성만 진단 — 우열 평가는 구조적으로 불가(규제 안전)',
        detail: {
          location: 'backend/ai/strategy_validation_agent.py',
          overview: '"좋은 전략인가"가 아니라 "돌아가는 전략인가"만 진단한다.',
          points: ['필수 요소·지원 지표·값 범위·공회전 조합 검사', '우열 평가·추천 표현은 구조적으로 생성 불가'],
          history: ['상세 흐름도는 Agents 탭 "전략 검증 도우미" 참고'],
        },
      },
      {
        domain: 'ai',
        title: 'AI 리포트',
        desc: '진단·점수는 결정론 계산, AI는 계산된 사실의 서술만 (10섹션 전문가 리포트)',
        detail: {
          location: 'backend/advisor/ · report_evidence.py',
          overview: '진단·점수·백분위는 전부 결정론 계산 — AI는 계산된 사실을 10섹션 서술로 풀어 쓰기만 한다.',
          points: [
            '섹션별 인용 수치는 결정적으로 조립(report_evidence) — AI가 수치를 새로 계산하지 않음',
            '전체 사용자 통계 대비 백분위는 방향 명시(높을수록 좋은 지표인지)',
            '표현 검문 — 내부 지시문 누출·추천·등급 표현을 후처리로 제거',
          ],
          history: ['상세 흐름도는 Agents 탭 "AI 리포트" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '테마 학습기',
        desc: '모르는 테마를 검색으로 학습 → 지식그래프·어휘집에 영속 저장',
        detail: {
          location: 'backend/engine/term_grounding.py · knowledge_graph.py',
          overview: '모르는 테마 용어를 검색으로 학습해 종목 집단으로 해석 — 결과는 어휘집·지식그래프에 영속된다.',
          points: [
            '조회 사슬 — 어휘집 캐시 → 지식그래프 → 네이버 라이브 테마 → 뉴스 검색 학습',
            '정본 게이트 — 지원 업종 목록 밖 이름은 탈락, 상장사명의 테마 오인 차단',
            '실패도 기록 — 90일간 재검색 억제, 미해결 항목만 조건부 재검색',
          ],
          history: ['상세 흐름도는 Agents 탭 "테마 학습기" 참고'],
        },
      },
      {
        domain: 'ai',
        title: '종목 질문 도우미',
        desc: '개별 종목 판단 요청을 전략 연구로 전환 — 종목 분석 기능은 의도적으로 없음',
        detail: {
          location: 'backend/stock_analysis/ · engine/stock_profile.py',
          overview: '개별 종목 판단 요청을 전략 연구로 전환한다 — 종목 분석 기능은 규제 안전을 위해 의도적으로 없다.',
          points: [
            '종목명 인식은 전 상장 종목 사전 기반 결정적 매칭 — 조사 경계("제주반도체로"의 "로") 처리 포함',
            '단일 종목 연구 프로파일 — 변동성·거래대금 등 결정론 사전 분석을 문답의 근거로 사용',
            '단일 종목 빌더 모드 — "언제 사고 언제 팔까" 중심의 문답으로 연결',
          ],
          history: ['상세 흐름도는 Agents 탭 "종목 질문 도우미" 참고'],
        },
      },
      {
        domain: 'ai',
        title: 'LLM 런타임',
        desc: '전 슬롯 Qwen 9B 단일화 — dev=로컬 Ollama, prod=Modal GPU(L4, scale-to-zero). /api/chat · think:false · JSON · 온도 0',
        detail: {
          location: 'backend 전역 LLM 어댑터 · Modal simons-ollama 앱',
          overview: '모든 LLM 슬롯이 Qwen 9B 하나로 통일돼 있다 — 4B는 형식 결함·오분류 실측으로 폐기됐다.',
          points: [
            'dev=로컬 Ollama(:11434), prod=Modal 서버리스 GPU(L4, scale-to-zero)',
            '호출 계약 — /api/chat · think:false · format=json · 구조화 출력은 온도 0(greedy), 설명문은 샘플링',
            '4B 폐기 근거 — bare enum JSON 깨짐 34%·기업명 테마 오분류. 비용은 반론이 아님(Modal은 warm GPU-초 과금)',
            '연결 실패는 503으로 정직하게 보고 — 정규식 폴백 부활 금지',
          ],
          history: [
            '파싱 전면 타임아웃의 단골 원인 2개 — ① ollama 미기동(11434부터 확인) ② 워밍업 num_ctx 불일치로 러너 재기동(/api/ps의 context_length 확인)',
          ],
        },
      },
      {
        domain: 'ai',
        title: '예측 AI (보조 도구)',
        desc: 'Conv1D+RoPE Transformer + XGBoost(v3 DOWN 헤드=청산 오버레이 전용) + SHAP 설명 — 진입 신호·단독 사용 금지',
        detail: {
          location: 'backend/ai/ · model/',
          overview: '가격 데이터 기반 예측 모델 — 전략의 보조 도구로만 쓰이고, 진입 신호·단독 사용은 금지다.',
          points: [
            '구조 — 45피처 Conv1D+RoPE+CLS Transformer + XGBoost 헤드(v2는 업/다운 분리)',
            'v3는 DOWN 헤드만 유효 — 청산 오버레이 전용',
            'SHAP 기반 설명(XAI 모달)으로 판단 근거 시각화',
            '실측 가치는 약세장 하방방어뿐 — 이 한계를 UI·문답에서 숨기지 않는다',
          ],
          history: [
            'AI 백테스트는 POLARS_MAX_THREADS=1 필수(Polars 데드락)',
            '재학습 절차 — 파케이 재생성 먼저, KMP/OMP 가드 확인',
          ],
        },
      },
    ],
  },
  {
    title: '백테스트 엔진',
    subtitle: '결정론 시뮬레이션 파이프라인 — 상세는 "백테스트 엔진" 서브탭',
    location: 'backend/engine/',
    boxes: [
      {
        domain: 'engine',
        title: 'PIT 유니버스',
        desc: 'universe_pit — 시점 기준 소속(상폐 포함, 생존편향 제거) + 섹터·테마·ETF 필터',
        detail: {
          location: 'backend/engine/universe_pit.py · universe_capabilities.py',
          overview: '"그 시점에 존재했고 그 시점에 그 집단에 속했던 종목"으로 백테스트한다 — 생존편향 제거의 핵심.',
          points: [
            '상폐 종목 포함(stock-master), 상폐 시 강제청산',
            '지수(KOSPI200 등)는 현재 명부가 아니라 일별 시총 상위 N 근사 — 현재 명부 자체가 생존편향이기 때문',
            '섹터는 KSIC 코드 정본 + 지식그래프 소속 오버레이, 테마는 지식그래프, ETF는 전용 마스터(재무지표 불가)',
            '"대형주"=KOSPI200, "소형주/중소형주"=시총 상한 조건(값 미정이면 되묻기)',
          ],
        },
      },
      {
        domain: 'engine',
        title: 'DataLoader',
        desc: 'parquet OHLCV 로드(Polars) + 재무 병합 + 수정주가·거래정지 가드',
        detail: {
          location: 'backend/engine/loader.py · dividends.py',
          overview: '종목별 parquet을 읽어 지표 계산이 가능한 형태로 준비한다.',
          points: [
            'Polars 읽기 + 인메모리 캐싱',
            '재무 지표 병합 — PIT 공시일(available_from) 기준으로 그 시점에 알 수 있던 값만',
            '수정주가·오류 프린트 정규화(_sanitize_corporate_actions)',
            '거래량 0 봉 = 거래정지 추정 → 신호·체결에서 제외',
            '배당 재투자 토탈리턴 보정(options.total_return) — 전략·벤치마크 양쪽 동일 적용(비교 일관성)',
          ],
          history: ['ohlcv dtype 불균질(us/ns/String) 함정 — 날짜 비교는 정규화 후에만'],
        },
      },
      {
        domain: 'engine',
        title: 'IndicatorEngine',
        desc: 'MA·RSI·MACD·볼린저·스토캐스틱 등 기술 지표 계산',
        detail: {
          location: 'backend/engine/indicators.py',
          overview: '기술 지표를 시계열 전체에 대해 벡터로 계산한다.',
          points: [
            'MA(5/10/20/60/120)·EMA·RSI·MACD·볼린저·스토캐스틱·CCI·ADX·거래량 급증·돌파·거래대금',
            'williams_r·mfi·roc 등 퀀트 지표 확장분 포함',
          ],
        },
      },
      {
        domain: 'engine',
        title: 'SignalEngine',
        desc: '조건 → boolean 벡터 — 신호(OR/AND 그룹)와 필터(항상 AND) 결합',
        detail: {
          location: 'backend/engine/signals.py',
          overview: '조건 하나를 boolean 벡터로 평가하고 그룹 논리로 결합한다.',
          points: [
            '신호 그룹은 OR/AND 선택, 재무 필터는 항상 AND, 최종 = 신호 AND 필터',
            '지원 지표 — 기술(ma_crossover·rsi·ema·macd·stochastic·cci·adx·bollinger·volume_spike·breakout·trading_value) · 재무(per/pbr/roe/부채비율/시가총액) · AI(ai_model·ai_drop_model) · 상한가 청산(price_limit_exit)',
          ],
        },
      },
      {
        domain: 'engine',
        title: 'Simulator',
        desc: '루프=의도 결정 + VectorBT=체결 — NAV 사이징·정수주·매도세·스탑·리밸런싱',
        detail: {
          location: 'backend/engine/simulator.py · rebalance.py',
          overview: '루프가 의도(무엇을 사고팔지)를 정하고 VectorBT from_orders가 체결을 계산하는 이중 구조.',
          points: [
            '리밸런싱 하이브리드 라우팅 — 순수 리밸런싱=목표비중 체결(targetpercent), 봉중간 리스크 혼재=커스텀 루프',
            '현실성 — NAV 사이징·정수주·매도 거래세·유동성(거래대금) 필터·거래정지 이월',
            '리스크 — 손절·익절(당일 종가 감지)·트레일링(peak 추적)·최대 보유일·리밸런싱 편출 매도',
            '벡터화 순서 고정 — 퇴장 → 리스크 → 리밸런싱 → 진입. 같은 날 매도+매수는 부기 즉시 갱신(고스트 포지션 방지)',
            '체결은 기본 next_open(다음날 시가, 룩어헤드 없음) — 독립 엔진(backtrader) 교차검증으로 일치 확인',
          ],
        },
      },
      {
        domain: 'engine',
        title: 'ResultHandler',
        desc: 'CAGR·MDD·샤프 등 산출 + 벤치마크 + 엔진 버전 기록(version.py SOT)',
        detail: {
          location: 'backend/engine/result_handler.py · version.py',
          overview: '시뮬레이션 결과를 지표로 환산해 직렬화한다 — 연환산 기준의 단일 SOT.',
          points: [
            '연수=달력 경과일÷365.25, 연환산 계수=√246(KRX 실측 연 거래일), 표준편차 ddof=1',
            '정의 불가 값은 null — 손실 0건의 profitFactor, 표본 없는 kelly(0으로 채우면 최악 성적으로 뒤집힌다)',
            '벤치마크 미존재 구간은 null(가짜 평탄선 금지), 부분 커버는 benchmark_partial 플래그',
            '엔진 버전(version.py SOT) 기록 — 결과값이 바뀌는 변경=MAJOR, UI 노출 금지',
          ],
        },
      },
    ],
  },
  {
    title: '지식·데이터 저장소',
    subtitle: '정본(SOT)이 어디인지가 핵심 — 상세는 "데이터 파이프라인" 서브탭',
    location: 'data/ · prisma/ · backend/vector_memory/',
    boxes: [
      {
        domain: 'data',
        title: 'OHLCV Parquet (4,052종목)',
        desc: '정본=프로덕션. 로컬은 npm run pull-data로 미러',
        detail: {
          location: 'data/ohlcv/*.parquet',
          overview: '백테스트·지표 계산·종목 값 조회가 전부 읽는 가격 데이터의 본체.',
          points: [
            '4,052개 종목, Polars 컬럼형 포맷',
            '정본=프로덕션 — 스케줄러가 매일 21:00 KST 수집, 로컬은 pull-data로 내려받기만(역방향 push 금지)',
            '과거 히스토리 백필은 KIS API 스크립트(중단 후 재개 가능)',
            '시총(market_cap) 컬럼 단위는 억원 — 날짜별 스냅샷 수확으로 재구축된 실측값',
          ],
        },
      },
      {
        domain: 'data',
        title: '재무 fundamentals',
        desc: 'KIS 10지표 + DART(지배주주순이익 등) — PIT 공시일(available_from) 기준',
        detail: {
          location: 'data/fundamentals/',
          overview: '재무 지표의 PIT 저장소 — "그 시점에 공시돼 있던 값"만 백테스트에 쓴다.',
          points: [
            'KIS 10지표 + DART 보강(지배주주순이익 — 계정ID 1순위 + 검산 폴백)',
            'available_from=공시일 — 정정공시 날짜로 오염됐던 1,611종목 클램프 수리 완료',
            '연간 레코드 기간 정합 가드 — KIS가 연간 목록에 끼워 보내는 분기 1행(PER 4배 왜곡) 차단',
          ],
        },
      },
      {
        domain: 'data',
        title: '종목 마스터 3종',
        desc: 'korea-stocks(현재 상장·섹터 SOT) · stock-master(PIT 상폐 포함) · etf-master',
        detail: {
          location: 'data/korea-stocks.json · stock-master.json · etf-master.json',
          overview: '"어떤 종목이 존재하고 어디에 속하는가"의 정본 3종 + 지수 명부 캐시.',
          points: [
            'korea-stocks.json — 현재 상장·섹터 SOT(섹터 분류는 KSIC 코드 정본)',
            'stock-master.json — PIT 마스터(상폐 포함), 상폐 종목 섹터 백필 — 생존편향 제거의 근거',
            'etf-master.json — ETF 유니버스(상폐 백필 병합)',
            'kospi200/kosdaq150 명부 캐시 — 가상매매 전용(백테스트는 시총 근사를 쓴다)',
          ],
        },
      },
      {
        domain: 'data',
        title: '지식그래프 + 테마 카탈로그',
        desc: '시드 + 네이버 285테마 + 주달 208테마 + 검색 학습 엣지 — 섹터 소속 정본',
        detail: {
          location: 'backend/engine/knowledge_graph.py · 콘솔 Knowledge 탭',
          overview: '개념·테마·업종·기업·ETF를 잇는 그래프 — 테마 해석과 섹터 소속의 정본.',
          points: [
            '소스 — 운영자 시드(Core/Strong만) + 네이버 테마 카탈로그 285 + 주달 208 + 검색 학습 엣지',
            '검색 학습 엣지는 출처 ≥2에서 자동 verified, 1개는 pending(콘솔에서 수동 승인·반려)',
            '섹터 소속(company→belongs_to→sector) 오버레이가 소속의 정본',
            '실물 데이터는 콘솔 Knowledge 탭에서 조회·관리',
          ],
        },
      },
      {
        domain: 'data',
        title: '지표 온톨로지 시드',
        desc: 'indicator-ontology.json — 어휘·분류 계층·합성 개념(골든크로스 등) 정본',
        detail: {
          location: 'data/indicator-ontology.json · registry/concept_ontology.py',
          overview: '지표 어휘·분류 계층·합성 개념의 시드 — 시드 수정만으로 해석기 어휘가 성장한다.',
          points: [
            '분류 계층(is_a) — "모멘텀 지표 하나" 같은 계열 발화를 선택 되묻기로 처리하는 근거',
            '합성 개념 전개 선언 — 골든크로스=ma_crossover crosses_above 5/20 같은 정본 조립',
            'polarity 전수 선언(지원 잎 51개) — 랭킹 방향 미언급 시 자연 방향으로 컴파일',
            'mtime 재로드 · 무결성은 CI 테스트가 단언 · 콘솔 Knowledge 탭에서 시각화·검색',
          ],
        },
      },
      {
        domain: 'data',
        title: 'RAG 코퍼스 (ChromaDB)',
        desc: 'bge-m3 임베딩 — 전략 조언·수정 예시 검색',
        detail: {
          location: 'backend/vector_memory/ · corpus/',
          overview: '의미 검색용 벡터 저장소 — 조언·수정 요청을 비슷한 사례로 찾는다.',
          points: [
            'bge-m3 의미 임베딩(1024차원) + 해싱 폴백',
            '전략 코퍼스 — 비-AI 전략 생성 → 병렬 백테스트 → 임베딩 적재',
            '수정 RAG는 검증된 예시+지식 2파일이 유일한 지식원 — 여기 없는 패턴은 LLM이 모른다',
          ],
        },
      },
      {
        domain: 'data',
        title: '앱 DB (Supabase Postgres)',
        desc: 'User·Strategy(SHA-256 id)·BacktestHistory·VirtualAccount·PaymentOrder·AdminAuditLog',
        detail: {
          location: 'prisma/schema.prisma · Supabase',
          overview: '사용자·전략·이력·계좌·결제·감사 — 서비스 상태의 본체.',
          points: [
            'Strategy.id = SHA-256(canonical DSL) — 저장 중복 제거·백테스트 캐시 키·조회 키를 하나로 통합',
            '주요 그룹 — User/PaymentOrder/PlanConfig · Strategy/BacktestHistory/BacktestResult/BatchRun · VirtualAccount 4종 · ResearchRun 3종 · AdminAuditLog',
            'Advisor 메모리는 Strategy를 insert-only 참조 — 사용자 저장본의 이름·설명을 덮어쓰지 않음',
            '백엔드(Python)는 backend/db.py 단일 어댑터로 접근 — NUMERIC→float 일괄 변환',
          ],
        },
      },
      {
        domain: 'data',
        title: '뉴스 Postgres + Redis',
        desc: 'news_v2 전용 DB(NEWSV2_DB_URL) + 큐/캐시용 Redis',
        detail: {
          location: 'docker-compose.yml postgres·redis 서비스',
          overview: '뉴스 파이프라인 전용 저장소 — 앱 DB와 분리해 부하·장애를 격리한다.',
          points: ['news_v2 원문·분석·캐시·priority 저장(NEWSV2_DB_URL)', 'Redis — 큐·캐시(256mb LRU)'],
        },
      },
    ],
  },
  {
    title: '외부 서비스',
    location: '.env 키 관리',
    boxes: [
      {
        domain: 'ext',
        title: '한국투자증권 KIS',
        desc: '시세·호가·재무·배당 API + 실시간 WebSocket(1세션 제한 → 로컬 프록시로 공유)',
        detail: {
          location: 'backend/engine/providers/ · kis_master.py',
          overview: '시세·재무의 1차 공급자.',
          points: [
            '시세·호가·재무·배당(예탁원) REST API',
            '실시간 WebSocket은 계정당 1세션 — 로컬 프록시(STOCK_REALTIME_PROXY_URL)로 여러 소비자가 공유',
            'OHLCV 과거 히스토리 백필 소스',
          ],
        },
      },
      {
        domain: 'ext',
        title: 'KRX / pykrx',
        desc: '시가총액 스냅샷·ETF 상폐 이력 (Open API 또는 로그인)',
        detail: {
          overview: '거래소 원천 데이터 — 시총 실측과 상폐 이력의 소스.',
          points: [
            '일별 시가총액 스냅샷(pykrx는 KRX_ID/PW 로그인 필수)',
            'ETF 상폐 멤버십(KRX Open API 키 — .env의 KRX_API_KEY)',
          ],
        },
      },
      {
        domain: 'ext',
        title: 'DART',
        desc: '공시 재무제표 — 연결/지배주주 구분, 정정공시 오염 방지 처리',
        detail: {
          overview: '금감원 공시 시스템 — 재무제표와 업종코드의 정본 소스.',
          points: [
            '지배주주순이익 등 세부 계정 — 계정ID 1순위 + 검산 폴백(지배+비지배=당기순이익), IFRS 접두 2벌 대응',
            'KSIC 업종코드 5자리(KRX는 3자리) — 섹터 분류 정본의 소스',
          ],
          history: ['정정공시(rcept) 날짜가 PIT 공시일을 수년 왜곡하던 오염 — 클램프로 수리 완료'],
        },
      },
      {
        domain: 'ext',
        title: '네이버 금융·뉴스',
        desc: '테마 카탈로그·라이브 테마·뉴스 RSS·검색 학습',
        detail: {
          overview: '테마 해석과 뉴스 수집의 소스.',
          points: [
            '테마 카탈로그(1순위 소스) + 라이브 테마 조회(그래프 미스 시 즉시 편입)',
            '뉴스 RSS 피드 수집',
            '검색 학습(테마 학습기) — 외부 본문은 비신뢰 데이터로 취급(프롬프트 인젝션 방어)',
          ],
        },
      },
      {
        domain: 'ext',
        title: '토스페이먼츠',
        desc: '자동결제(빌링) — 구독 결제 전담',
        detail: {
          overview: '구독 결제 전담 PG.',
          points: [
            'v2 SDK의 빌링 방식 — 카드 등록 1회 + 매월 서버 청구',
            '프로덕션은 자동결제(빌링) 계약이 완료된 상점의 라이브 키 필요 — 미계약 키는 NOT_SUPPORTED_METHOD',
          ],
        },
      },
      {
        domain: 'ext',
        title: 'Modal',
        desc: '프로덕션 LLM 서빙 (서버리스 GPU L4, scale-to-zero)',
        detail: {
          overview: '프로덕션 LLM 서빙 — 앱 박스에서 GPU를 분리한 서버리스 구성.',
          points: [
            'simons-ollama 앱 — GPU L4, min_containers=0(scale-to-zero), scaledown 300초',
            '콜드스타트 ~90–320초 — GET warmup·num_ctx 고정·undici headersTimeout:0으로 완화',
            '과금은 warm GPU-초 — "비용 때문에 작은 모델" 논리는 성립하지 않는다',
          ],
        },
      },
      {
        domain: 'ext',
        title: 'Supabase',
        desc: '앱 DB Postgres (us-west-1 pooler 필수)',
        detail: {
          overview: '앱 DB Postgres SaaS.',
          points: [
            'Next.js(Prisma)와 FastAPI(backend/db.py) 양쪽이 같은 DB를 본다',
            'us-west-1 pooler 경유 필수',
            '스키마 변경은 prod 수동 마이그레이션(배포가 실행해 주지 않음)',
          ],
        },
      },
      {
        domain: 'ext',
        title: 'LangSmith (선택)',
        desc: 'Trace 관찰 — 기본 OFF, APAC 리전',
        detail: {
          overview: '에이전트 trace의 외부 관찰 백엔드 — 기본은 로컬 trace만 쓴다.',
          points: ['기본 OFF — 로컬(콘솔+JSONL) trace가 기본', 'APAC 리전 엔드포인트 — 불일치 403을 계정 문제로 오진하기 쉬움(/info 200이면 리전부터 의심)'],
        },
      },
    ],
  },
]

// ─── 0. 구조 그래프 (SVG 노드-엣지 다이어그램) ───────────────────────────────

function findBox(title: string): ArchBox | undefined {
  for (const layer of OVERVIEW_LAYERS) {
    const hit = layer.boxes.find((b) => b.title === title)
    if (hit) return hit
  }
  return undefined
}

const SVG_STROKE: Record<Domain, string> = {
  user: '#9ca3af',
  next: '#38bdf8',
  py: '#34d399',
  engine: '#818cf8',
  ai: '#c084fc',
  data: '#fbbf24',
  ext: '#fb7185',
  guard: '#f87171',
}

const NODE_H = 58

interface GraphNodeSpec {
  id: string
  x: number
  y: number
  w: number
  domain: Domain
  title: string
  sub: string
  box?: ArchBox
}

const GRAPH_NODES: GraphNodeSpec[] = [
  {
    id: 'browser',
    x: 440,
    y: 24,
    w: 280,
    domain: 'user',
    title: '사용자 브라우저',
    sub: '페이지 9종 · nullstock.im',
    box: {
      domain: 'user',
      title: '사용자 브라우저',
      detail: {
        location: 'app/ · components/',
        overview: 'Next.js 14 App Router 페이지들 — 사용자가 만나는 모든 화면.',
        points: [
          '전략 연구소 · 백테스트 결과 · 대시보드 · 종목/주문 · 가상계좌 · 관심종목 · 요금제 · 인증 · 운영 콘솔',
          '페이지별 상세는 "전체 조감도"의 사용자 접점 계층 카드 참고',
        ],
      },
    },
  },
  {
    id: 'toss',
    x: 80,
    y: 140,
    w: 220,
    domain: 'ext',
    title: '토스페이먼츠',
    sub: '자동결제(빌링)',
    box: findBox('토스페이먼츠'),
  },
  {
    id: 'web',
    x: 440,
    y: 140,
    w: 280,
    domain: 'next',
    title: 'Next.js 서버',
    sub: 'BFF — 인증·플랜·결제·프록시',
    box: {
      domain: 'next',
      title: 'Next.js 서버 (BFF)',
      detail: {
        location: 'app/api/ · lib/',
        overview: '브라우저와 FastAPI 사이의 중간 서버 — 사용자 컨텍스트가 필요한 로직을 담당한다.',
        points: [
          '브라우저가 백엔드로 가는 유일한 통로(API 라우트 프록시)',
          '백테스트 쿼터 소진·이력 자동저장·플랜 한도 집행',
          '토스 자동결제(빌링)와 매시 갱신 스케줄러',
          'Prisma로 앱 DB(Supabase Postgres) 접근 단일화',
          '구성 요소별 상세는 "전체 조감도"의 Next.js 서버 계층 카드 참고',
        ],
      },
    },
  },
  {
    id: 'appdb',
    x: 850,
    y: 140,
    w: 260,
    domain: 'data',
    title: '앱 DB',
    sub: 'Supabase Postgres — 사용자·전략·이력',
    box: findBox('앱 DB (Supabase Postgres)'),
  },
  {
    id: 'api',
    x: 440,
    y: 280,
    w: 280,
    domain: 'py',
    title: 'FastAPI 백엔드',
    sub: '전략 대화·백테스트·시장 데이터',
    box: {
      domain: 'py',
      title: 'FastAPI 백엔드',
      detail: {
        location: 'backend/',
        overview: '전략 해석·백테스트·시장 데이터·가상매매의 본체.',
        points: [
          '라우터 그룹 — 전략 대화 · 백테스트 · 검증(WFA/MC/최적화) · 시장 데이터 · AI 리포트/코치 · 뉴스 · 연구 에이전트',
          '인프로세스로 가상매매 루프와 관찰 계층(trace)이 함께 돈다',
          '라우터별 상세는 "전체 조감도"의 FastAPI 계층 카드 참고',
        ],
      },
    },
  },
  {
    id: 'agents',
    x: 60,
    y: 430,
    w: 260,
    domain: 'ai',
    title: 'AI 에이전트 계층',
    sub: '파이프라인 9종 (Agents 탭)',
    box: {
      domain: 'ai',
      title: 'AI 에이전트 계층',
      detail: {
        location: 'backend/strategy_conversation/ · intent/ · advisor/',
        overview: '자연어의 의미를 해석하는 유일한 계층 — 검증·컴파일은 결정론 코드가 한다.',
        points: [
          '9종 — 전략 해석기 · 대화 플래너 · 질문 분류기 · 전략 빌더 · 전략 수정기 · 검증 도우미 · AI 리포트 · 테마 학습기 · 종목 질문 도우미',
          '각 파이프라인의 흐름도·사고 이력은 Agents 탭 참고',
          '에이전트별 요약 카드는 "전체 조감도"의 AI 에이전트 계층 참고',
        ],
      },
    },
  },
  {
    id: 'engine',
    x: 400,
    y: 430,
    w: 240,
    domain: 'engine',
    title: '백테스트 엔진',
    sub: 'Loader→지표→신호→시뮬→결과',
    box: {
      domain: 'engine',
      title: '백테스트 엔진',
      detail: {
        location: 'backend/engine/',
        overview: '전 구간 결정론 시뮬레이션 파이프라인 — AI는 조건에 AI 신호가 있을 때만 개입한다.',
        points: [
          'Phase 0 유니버스(PIT) → 1 데이터 로드 → 2 지표 → 4 신호 → 5 시뮬레이션 → 5.5 벤치마크 → 6 결과',
          '전체를 워치독이 감싼다 — 행(hang)이어도 반드시 종료',
          '단계별 상세는 "백테스트 엔진" 서브탭 참고',
        ],
      },
    },
  },
  {
    id: 'vt',
    x: 680,
    y: 430,
    w: 220,
    domain: 'py',
    title: '가상매매',
    sub: 'VirtualTrader — 장 사이클',
    box: findBox('가상매매 엔진 (인프로세스)'),
  },
  {
    id: 'news',
    x: 940,
    y: 430,
    w: 230,
    domain: 'py',
    title: '뉴스 파이프라인',
    sub: 'news_v2 — Hot/Warm/Cold 큐',
    box: findBox('뉴스 파이프라인 (news_v2)'),
  },
  {
    id: 'llm',
    x: 60,
    y: 600,
    w: 250,
    domain: 'ai',
    title: 'LLM 런타임',
    sub: 'Qwen 9B — dev Ollama · prod Modal',
    box: findBox('LLM 런타임'),
  },
  {
    id: 'knowledge',
    x: 350,
    y: 600,
    w: 240,
    domain: 'data',
    title: '지식 데이터',
    sub: 'KG·온톨로지·ChromaDB',
    box: findBox('지식그래프 + 테마 카탈로그'),
  },
  {
    id: 'market',
    x: 630,
    y: 600,
    w: 240,
    domain: 'data',
    title: '시장 데이터',
    sub: 'parquet 4,052 · 재무(PIT)',
    box: findBox('OHLCV Parquet (4,052종목)'),
  },
  {
    id: 'kis',
    x: 890,
    y: 600,
    w: 140,
    domain: 'ext',
    title: 'KIS 시세',
    sub: 'WS 1세션 프록시',
    box: findBox('한국투자증권 KIS'),
  },
  {
    id: 'newsdb',
    x: 1050,
    y: 600,
    w: 140,
    domain: 'data',
    title: '뉴스 저장소',
    sub: 'Postgres·Redis',
    box: findBox('뉴스 Postgres + Redis'),
  },
  {
    id: 'extdata',
    x: 350,
    y: 760,
    w: 240,
    domain: 'ext',
    title: '외부 데이터 소스',
    sub: 'KRX·DART·네이버',
    box: {
      domain: 'ext',
      title: '외부 데이터 소스 (KRX·DART·네이버)',
      detail: {
        overview: '지식·시장 데이터의 원천들.',
        points: [
          'KRX/pykrx — 일별 시가총액 스냅샷 · ETF 상폐 멤버십',
          'DART — 공시 재무제표 · KSIC 업종코드(섹터 정본의 소스)',
          '네이버 — 테마 카탈로그·라이브 테마 · 뉴스 RSS · 검색 학습',
          '각각의 상세는 "전체 조감도"의 외부 서비스 계층 카드 참고',
        ],
      },
    },
  },
  {
    id: 'sched',
    x: 630,
    y: 760,
    w: 240,
    domain: 'py',
    title: '수집 스케줄러',
    sub: '매일 야간 데이터 적재',
    box: {
      domain: 'py',
      title: '수집 스케줄러',
      detail: {
        location: 'docker compose scheduler 컨테이너 · scripts/',
        overview: '매일 야간 시장 데이터를 정본(프로덕션 parquet)에 적재하는 단일 인스턴스 잡.',
        points: [
          '매일 21:00 KST OHLCV 동기화 — 중복 실행 금지(단일 인스턴스)',
          '재무·시총·마스터 재구축은 별도 백필 스크립트(수동 실행)',
        ],
      },
    },
  },
]

interface GraphEdgeSpec {
  x1: number
  y1: number
  x2: number
  y2: number
  label?: string
  lx?: number
  ly?: number
  anchor?: 'start' | 'middle'
}

const GRAPH_EDGES: GraphEdgeSpec[] = [
  { x1: 580, y1: 82, x2: 580, y2: 140, label: 'HTTPS (Caddy)', lx: 588, ly: 115, anchor: 'start' },
  { x1: 440, y1: 169, x2: 300, y2: 169, label: '구독 결제(빌링)', lx: 370, ly: 160 },
  { x1: 720, y1: 169, x2: 850, y2: 169, label: 'Prisma', lx: 785, ly: 160 },
  { x1: 580, y1: 198, x2: 580, y2: 280, label: 'API 프록시 · SSE 중계', lx: 588, ly: 243, anchor: 'start' },
  { x1: 720, y1: 309, x2: 980, y2: 198, label: 'backend/db.py', lx: 838, ly: 247 },
  { x1: 856, y1: 430, x2: 1032, y2: 198, label: '주문·포지션 기록', lx: 952, ly: 310 },
  { x1: 468, y1: 338, x2: 190, y2: 430, label: '전략 대화·분류', lx: 315, ly: 380 },
  { x1: 538, y1: 338, x2: 520, y2: 430, label: '백테스트 실행', lx: 540, ly: 390, anchor: 'start' },
  { x1: 622, y1: 338, x2: 790, y2: 430, label: '장 사이클 루프', lx: 716, ly: 378 },
  { x1: 692, y1: 338, x2: 1055, y2: 430, label: '뉴스 캐시 API', lx: 880, ly: 396 },
  { x1: 138, y1: 488, x2: 125, y2: 600, label: '의미 해석 호출', lx: 140, ly: 548, anchor: 'start' },
  { x1: 268, y1: 488, x2: 470, y2: 600, label: '테마·어휘·RAG 조회', lx: 366, ly: 538 },
  { x1: 520, y1: 488, x2: 750, y2: 600, label: 'OHLCV·재무 읽기 (PIT)', lx: 636, ly: 538 },
  { x1: 790, y1: 488, x2: 960, y2: 600, label: '실시간 시세 구독', lx: 886, ly: 536 },
  { x1: 1055, y1: 488, x2: 1120, y2: 600, label: '수집·분석 저장', lx: 1096, ly: 542 },
  { x1: 470, y1: 658, x2: 470, y2: 760, label: '검색 학습·카탈로그 수집', lx: 478, ly: 714, anchor: 'start' },
  { x1: 750, y1: 760, x2: 750, y2: 658, label: '매일 야간 적재', lx: 758, ly: 714, anchor: 'start' },
  { x1: 870, y1: 789, x2: 960, y2: 668, label: 'OHLCV·시총 수집', lx: 940, ly: 740 },
]

function ArchitectureGraph({ onSelect }: { onSelect: OnSelectBox }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <svg viewBox="0 0 1200 840" className="w-full min-w-[900px]" role="img" aria-label="서비스 구조 그래프">
        <defs>
          <marker id="arch-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="#4b5563" />
          </marker>
        </defs>

        {GRAPH_EDGES.map((e, i) => {
          const lx = e.lx ?? (e.x1 + e.x2) / 2
          const ly = e.ly ?? (e.y1 + e.y2) / 2 - 6
          return (
            <g key={i}>
              <line
                x1={e.x1}
                y1={e.y1}
                x2={e.x2}
                y2={e.y2}
                stroke="#4b5563"
                strokeWidth="1.2"
                markerEnd="url(#arch-arrow)"
              />
              {e.label && (
                <text
                  x={lx}
                  y={ly}
                  fontSize="10.5"
                  fontWeight={700}
                  fill="#9ca3af"
                  textAnchor={e.anchor ?? 'middle'}
                  stroke="#111111"
                  strokeWidth={4}
                  paintOrder="stroke"
                >
                  {e.label}
                </text>
              )}
            </g>
          )
        })}

        {GRAPH_NODES.map((n) => {
          const clickable = Boolean(n.box)
          const stroke = SVG_STROKE[n.domain]
          return (
            <g
              key={n.id}
              onClick={clickable ? () => onSelect(n.box!) : undefined}
              className={clickable ? 'cursor-pointer transition-opacity hover:opacity-75' : undefined}
            >
              <rect
                x={n.x}
                y={n.y}
                width={n.w}
                height={NODE_H}
                rx={10}
                fill="#161616"
                stroke={stroke}
                strokeOpacity={0.6}
                strokeWidth={1.2}
              />
              <text
                x={n.x + n.w / 2}
                y={n.y + 25}
                textAnchor="middle"
                fontSize="14"
                fontWeight={800}
                fill="#f3f4f6"
              >
                {n.title}
              </text>
              <text x={n.x + n.w / 2} y={n.y + 43} textAnchor="middle" fontSize="10.5" fill="#9ca3af">
                {n.sub}
              </text>
              {clickable && (
                <text x={n.x + n.w - 8} y={n.y + 14} textAnchor="end" fontSize="9" fontWeight={700} fill="#6b7280">
                  상세 ›
                </text>
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}

// ─── 2. 대화 → 백테스트 여정 ─────────────────────────────────────────────────

const JOURNEY_STEPS: FlowStep[] = [
  {
    domain: 'user',
    title: '사용자 발화',
    desc: '"PER 낮은 반도체 대형주 사서 손절 5%로 백테스트해줘" — 전략 연구소 채팅 입력',
  },
  {
    domain: 'next',
    title: '프론트 턴 중재',
    desc: '상태 재평가 → 실행 가능한 액션 선택(decideConversationTurn, 순수 함수) → 응답 조립. 잡담이 끼어도 열려 있는 되묻기를 보존해 다시 세운다',
  },
  {
    domain: 'ai',
    title: '의도 분류 (/query/classify)',
    desc: '전략 설계인지·종목 질문인지·지식 질문인지 AI가 판정. 워크플로 제어(멈춤·취소·되돌리기)와 되묻기 대상도 같은 호출로 — 성립 여부는 결정론 코드가 정한다',
  },
  {
    domain: 'guard',
    title: '규제 안전 게이트',
    desc: '종목 추천·시장 전망·맞춤 조언은 여기서 정형 안내로 종결. 지표 값 조회·소속 목록 질문은 AI 없이 정본 데이터로 답한다',
  },
  {
    domain: 'ai',
    title: '대화 플래너 — 투자 범위 먼저',
    desc: '"반도체"가 업종인지 테마인지, 어떤 종목 집단인지 조사 도구를 계획. 실행은 자동 러너가 하고, 테마 후보가 갈리면 사용자에게 선택지를 되묻는다',
  },
  {
    domain: 'ai',
    title: 'LLM 전략 해석 (9B, 온도 0)',
    desc: '동의어·정성 표현·오타·문맥을 이해해 구조화 전략(StrategyIntent JSON)으로 출력. 입력의 숫자 목록을 체크리스트로 함께 넘겨 반영·미지원·무시를 선언하게 한다',
  },
  {
    domain: 'engine',
    title: '검증 계층 (결정론)',
    desc: '표기 정규화 → 형식 검사 → Registry 기반 지원 여부·값 범위·조건 충돌·완결성 검사. 미지원은 조용한 대체 없이 명시 안내',
  },
  {
    branches: [
      {
        label: '빠진 값이 있으면',
        nodes: [
          {
            domain: 'guard',
            title: '되묻기 + 추천값 칩',
            desc: '조용히 기본값을 채우지 않는다 — 한 턴에 한 질문, 나머지는 이월 큐. 칩은 발행 시점에 값이 결속된 정본만 노출',
          },
        ],
      },
      {
        label: '완성이면',
        nodes: [
          {
            domain: 'engine',
            title: '컴파일',
            desc: 'ParsedStrategy → BacktestRequest — 유니버스 심볼 해석, 단일/지정 종목 모드 분기',
          },
        ],
      },
    ],
  },
  {
    domain: 'next',
    title: 'SSE 실행 라우트',
    desc: '백테스트 쿼터 소진 → FastAPI 스트림 프록시 → 완료 시 이력 자동저장(BacktestHistory, result 항상 포함). 캐시 재사용 없이 항상 엔진 재실행',
  },
  {
    domain: 'engine',
    title: '엔진 실행 (워치독 아래)',
    desc: '데이터 로드 → 지표 → 신호 → 시뮬레이션 → 결과 — 상세는 "백테스트 엔진" 서브탭',
  },
  {
    domain: 'user',
    title: '결과 화면 + AI 리포트',
    desc: '수익곡선·통계·거래 내역·벤치마크 표시. AI 리포트는 결정론 근거 조립 후 9B가 서술만 — 표현 검문(추천·등급 표현 제거)을 거쳐 노출',
  },
]

// ─── 3. 백테스트 엔진 내부 ───────────────────────────────────────────────────

const ENGINE_STEPS: FlowStep[] = [
  {
    domain: 'engine',
    title: 'Phase 0 — 유니버스 확정 (universe_pit)',
    desc: '시점 기준(as-of) 소속으로 생존편향 제거 — 상폐 종목 포함, 상폐 시 강제청산',
    items: [
      '지수 유니버스(KOSPI200 등)는 현재 명부가 아니라 일별 시총 상위 N 근사 — 현재 명부 자체가 생존편향',
      '섹터(KSIC 코드 정본)·테마(지식그래프)·ETF(etf-master, 재무지표 불가) 필터',
      '시장 제약("코스피만")은 정본 소속 필터 — 직접 지목 종목은 불변',
    ],
  },
  {
    domain: 'engine',
    title: 'Phase 1 — 데이터 로드 (DataLoader)',
    desc: 'data/ohlcv/{symbol}.parquet를 Polars로 읽고 인메모리 캐싱',
    items: [
      '재무 지표 병합 (PIT available_from 기준 — 정정공시 날짜 오염 수리 완료)',
      '수정주가/오류 프린트 정규화 (_sanitize_corporate_actions)',
      '거래량 0 봉 = 거래정지 추정 → 신호·체결 제외',
      '배당 재투자 토탈리턴 보정 (options.total_return — 전략·벤치마크 동일 적용)',
    ],
  },
  {
    domain: 'engine',
    title: 'Phase 2 — 지표 계산 (IndicatorEngine)',
    desc: 'MA(5/10/20/60/120)·RSI·MACD·볼린저·스토캐스틱·CCI·ADX·거래량 급증·돌파 등',
  },
  {
    domain: 'ai',
    title: 'Phase 3 — AI 모델 프리로드 (필요 시)',
    desc: 'ai_model/ai_drop_model 조건이 있을 때만. 로드 실패·비활성 시 0거래 침묵 진행 대신 즉시 명확한 에러(fail-fast)',
  },
  {
    domain: 'engine',
    title: 'Phase 4 — 신호 생성 (SignalEngine)',
    desc: '조건 하나 → boolean 벡터(전체 시계열). 신호 그룹은 OR/AND, 필터는 항상 AND, 최종 = 신호 AND 필터',
  },
  {
    domain: 'engine',
    title: 'Phase 5 — 포트폴리오 시뮬레이션 (Simulator)',
    desc: '루프가 의도(무엇을 사고팔지)를 정하고, VectorBT from_orders가 체결을 계산하는 이중 구조',
    items: [
      '리밸런싱 라우팅 — 순수 리밸런싱은 목표비중 체결(from_orders targetpercent), 봉중간 리스크 혼재는 커스텀 루프',
      '리스크 관리 — 손절·익절(당일 종가 감지→청산), 트레일링 스탑(peak 추적), 최대 보유일, 리밸런싱 편출',
      '랭킹 — 재무·모멘텀 상위 K 선정 + 자연 방향(polarity) 보정, 분위 그룹 비교(FR-BT-060)',
      '현실성 — NAV 사이징·정수주·매도 거래세·유동성(거래대금) 필터·거래정지 이월',
      '체결 시점 — 기본 next_open(다음날 시가, 룩어헤드 없음). same_close는 연구용(경고 자동 첨부)',
    ],
  },
  {
    domain: 'engine',
    title: 'Phase 5.5 — 벤치마크 선택·로드',
    desc: '유니버스 시장 토큰 → KODEX 200/코스피/코스닥150. 유니버스가 비면 보유 종목 시장 다수결. 미존재 구간은 null(가짜 선 금지)',
  },
  {
    domain: 'engine',
    title: 'Phase 6 — 결과 계산 (ResultHandler)',
    desc: '수익률·위험·거래 통계 산출 + 엔진 버전 기록',
    items: [
      '연환산 단일 SOT — 연수=달력일÷365.25, 연환산 계수=√246(KRX 실측 거래일)',
      '정의되지 않는 값은 0이 아니라 null (손실 0건의 profitFactor 등 — 0이면 최악 성적으로 뒤집힌다)',
      '월별/연도별 분해·종목별 통계·벤치마크 부분 커버 표시(benchmark_partial)',
    ],
  },
  {
    domain: 'guard',
    title: '워치독',
    desc: 'BACKTEST_TIMEOUT_S(기본 600초) 벽시계 제한 — 엔진이 행에 빠져도 504/SSE 에러로 반드시 종료',
  },
]

// ─── 4. 데이터 파이프라인 ────────────────────────────────────────────────────

const DATA_LAYERS: ArchLayer[] = [
  {
    title: '외부 데이터 소스',
    boxes: [
      { domain: 'ext', title: 'KIS', desc: 'OHLCV 히스토리·재무 10지표·배당(예탁원)·실시간 시세' },
      { domain: 'ext', title: 'KRX / pykrx', desc: '일별 시가총액 스냅샷·ETF 상폐 멤버십' },
      { domain: 'ext', title: 'DART', desc: '공시 재무제표 — KSIC 업종코드(5자리)·지배주주순이익' },
      { domain: 'ext', title: '네이버 금융', desc: '테마 카탈로그·라이브 테마·뉴스 RSS·검색(테마 학습)' },
    ],
  },
  {
    title: '수집·백필 (스크립트 + 스케줄러)',
    location: 'scripts/ · backend/scripts/',
    boxes: [
      { domain: 'py', title: '일일 동기화 스케줄러', desc: 'scheduler 컨테이너 — 매일 21:00 KST OHLCV 수집 (단일 인스턴스, 중복 금지)' },
      { domain: 'py', title: '재무 백필', desc: 'backfill_fundamentals(KIS)·pull-data 후 remerge — 연간 레코드 기간 정합 가드(분기 행 혼입 차단)' },
      { domain: 'py', title: '시총 재구축', desc: 'rebuild_market_cap — 날짜별 스냅샷 수확, gap-fill 후 병합' },
      { domain: 'py', title: '마스터 빌드', desc: 'build_stock_master(PIT)·build_etf_master·build_index_rosters(지수 명부)·상폐 섹터 백필' },
      { domain: 'py', title: '지식 빌드', desc: 'KG 합성(시드+카탈로그+검색 학습)·지표 온톨로지 시드·RAG 코퍼스(생성→백테스트→임베딩→Chroma 적재)' },
    ],
  },
  {
    title: '정본 저장소 (어디가 SOT인가)',
    location: 'data/',
    boxes: [
      { domain: 'data', title: 'OHLCV parquet', desc: '4,052종목. 정본=프로덕션 — 로컬은 npm run pull-data 미러(로컬 parquet를 prod로 push 금지)' },
      { domain: 'data', title: 'fundamentals', desc: 'PIT 공시일(available_from) 기준 — 백테스트가 그 시점에 알 수 있던 값만 사용' },
      { domain: 'data', title: 'korea-stocks.json', desc: '현재 상장 종목·섹터 SOT (섹터 분류는 KSIC 코드 정본)' },
      { domain: 'data', title: 'stock-master.json', desc: 'PIT 종목 마스터 — 상폐 포함(생존편향 제거의 근거)' },
      { domain: 'data', title: '지식그래프', desc: '섹터 소속(company-belongs_to-sector)·테마·공급망 엣지 — 콘솔 Knowledge 탭에서 조회' },
      { domain: 'data', title: 'indicator-ontology.json', desc: '지표 어휘·분류 계층·합성 개념 시드 — 시드 수정만으로 어휘 성장' },
      { domain: 'data', title: 'ChromaDB', desc: 'bge-m3 임베딩 — 전략 조언·수정 RAG 검색' },
    ],
  },
  {
    title: '소비자',
    boxes: [
      { domain: 'engine', title: '백테스트 엔진', desc: 'OHLCV+재무+PIT 마스터 — 시점 기준 시뮬레이션' },
      { domain: 'py', title: '가상매매', desc: '지수 명부 캐시 + KIS 실시간 시세 — 현재 상장 기준' },
      { domain: 'ai', title: 'AI 에이전트', desc: 'KG·온톨로지·RAG 코퍼스 — 테마 해석·어휘·조언 근거' },
      { domain: 'py', title: '종목 값 조회', desc: '"삼성전자 PER 얼마야?" — 엔진과 같은 parquet에서 결정론으로 읽어 답변' },
    ],
  },
]

// ─── 5. 가상매매 ─────────────────────────────────────────────────────────────

const VIRTUAL_STEPS: FlowStep[] = [
  {
    domain: 'user',
    title: '가상계좌 + 전략 연결',
    desc: '플랜(FREE/PRO/PREMIUM)이 계좌당 초기 투자금과 계좌 수를 결정 — 클라이언트가 보낸 금액은 무시하고 서버가 확정',
  },
  {
    domain: 'py',
    title: '장 사이클 (VirtualTrader 비동기 루프)',
    desc: '09:00 개장 — 진입 신호 평가·매수 / 정시 — 청산 신호 확인 / 15:30 마감 — 포지션 계산·로그 저장',
  },
  {
    domain: 'py',
    title: '신호 유니버스 재해석 (매 사이클)',
    desc: '전략 DSL에서 다시 해석(resolve_live_universe) — 지수는 명부 파일로만, 명부가 없으면 시장 전체로 넓히지 않는다. 화면의 모니터링 목록(상위 10종목)과는 별개',
  },
  {
    domain: 'ext',
    title: 'KIS 실시간 시세 (WebSocket 1세션 프록시)',
    desc: 'KIS WS는 계정당 1세션 — 로컬 프록시(STOCK_REALTIME_PROXY_URL)로 공유. 조회는 신호∪보유∪미체결 종목으로 좁혀 부하 차단',
  },
  {
    domain: 'guard',
    title: '체결 무결성 가드',
    items: [
      'PENDING 주문은 조건부 UPDATE로 체결 — 이중 체결 방지',
      '거래정지 종목 필터(KIS 상태 코드 기준)',
      '상장 상태 머신 7단계 — 상폐 진행 종목 매수 차단(isBuyAllowed)',
      '거래 비용 반영 — 수수료 0.15% / 세금 0.30% / 슬리피지 0.20%',
    ],
  },
  {
    domain: 'next',
    title: '계좌 수명주기',
    desc: '일시 중지(PAUSED)=주문 자동 차단, 해지=보유 전량 현재가 강제매도 후 CLOSED — 남은 자산은 다른 계좌로 이전하지 않는다(정산 원장에만 기록)',
  },
  {
    domain: 'user',
    title: '포트폴리오·거래 내역 화면',
    desc: '보유 종목·평가손익·체결 로그 — 대시보드 가상매매 현황과 연동',
  },
]

// ─── 6. 배포 구조 ────────────────────────────────────────────────────────────

const DEPLOY_DEV: ArchBox[] = [
  { domain: 'next', title: 'next dev (:3000)', desc: '프론트 + API 라우트' },
  { domain: 'py', title: 'uvicorn (:8000)', desc: 'FastAPI + 엔진' },
  { domain: 'ai', title: '로컬 Ollama (:11434)', desc: 'Qwen 9B — LLM 슬롯 전부. 파싱 전면 실패는 대부분 ollama 미기동이 원인' },
  { domain: 'data', title: '로컬 parquet 미러', desc: '정본=프로덕션 — npm run pull-data로 내려받는다' },
  { domain: 'ext', title: 'Supabase Postgres', desc: '앱 DB (프로덕션과 공유 구조, us-west-1 pooler)' },
]

const DEPLOY_PROD: ArchBox[] = [
  { domain: 'ext', title: 'Caddy (HTTPS)', desc: 'nullstock.im — 리버스 프록시·인증서 자동' },
  { domain: 'next', title: 'web', desc: 'Next.js standalone — 프론트 + API 라우트 + 인프로세스 빌링 스케줄러' },
  { domain: 'py', title: 'backend', desc: 'FastAPI + VirtualTrader(인프로세스 자동매매)' },
  { domain: 'py', title: 'scheduler', desc: '매일 21:00 KST OHLCV 동기화 — 단일 인스턴스(중복 금지)' },
  { domain: 'data', title: 'redis · postgres(news)', desc: '뉴스 파이프라인 큐/캐시 + news_v2 전용 DB' },
  { domain: 'ext', title: 'Supabase Postgres', desc: '앱 DB (박스 밖 SaaS)' },
  { domain: 'ai', title: 'Modal simons-ollama', desc: '서버리스 GPU L4, scale-to-zero — 콜드스타트 ~90–320초는 warmup·num_ctx·타임아웃 해제로 완화' },
]

const DEPLOY_NOTES = [
  '프로덕션은 Vultr 단일 박스(/opt/simons)의 docker compose 하나가 전부다 — LLM만 Modal로 분리한 하이브리드.',
  'CI/CD: main 푸시 → GitHub Actions(ci.yml 테스트) → SSH로 Vultr 접속 → compose 빌드·기동 → 스모크 테스트 6블로커 확인.',
  '배포는 DB 마이그레이션을 실행하지 않는다 — 스키마 변경 시 prod에 수동 적용 필수.',
  'route 파일의 비표준 export는 tsc·vitest·CI를 전부 통과하고 배포 빌드에서만 깨진다 — 순수 함수는 형제 모듈로 분리.',
  'arm64(dev)↔x86_64(prod) 부동소수점 차이로 1거래가 갈릴 수 있다 — 프로덕션 결과가 정본.',
  'LLM 라우팅: dev=로컬 Ollama, prod=Modal. 연결 실패는 503으로 정직하게 보고(폴백 없음).',
]

// ─── 7. 규제 안전 계층 ───────────────────────────────────────────────────────

const SAFETY_PRINCIPLE: ArchBox = {
  domain: 'guard',
  title: '대원칙 — 우리는 투자 연구·시뮬레이션 플랫폼이다',
  desc: '투자 자문·추천·개인 맞춤 조언을 제공하지 않는다(유사투자자문업 회피). 시스템은 계산·백테스트·시뮬레이션·객관적 과거 데이터 표시만 하고, 모든 투자 판단은 사용자가 직접 한다.',
  items: [
    '금지 — 전략·종목·섹터·ETF·포트폴리오 추천, 시장 전망, 매수·매도 시점 제안, 나이·자산 기반 조언, 전략 우열 판단',
    '허용 — 과거 데이터 기준 수치("CAGR 12.4%였습니다"), 시뮬레이션 결과, 객관적 통계·차트·지표 값',
  ],
}

const SAFETY_LANE: FlowStep[] = [
  { domain: 'user', title: '사용자 원문', desc: '자연어 의미가 있는 유일한 입력' },
  { domain: 'ai', title: 'LLM 의미 해석', desc: '동의어·정성 표현·오타·문맥 — 원문의 의미를 판정하는 유일한 주체' },
  { domain: 'engine', title: '결정론 레인', desc: 'LLM 출력의 형식 검증·정규화(Regex는 여기서만) → Schema 검증 → Registry 도메인 검증 → 컴파일' },
  { domain: 'guard', title: '금지 구조', desc: 'Regex가 원문을 읽는 것, LLM 판정을 정규식이 재심하는 것, 검증 실패를 코드가 임의 보정하는 것 — 전부 계약 위반' },
]

const SAFETY_GATES: ArchLayer = {
  title: '규제 게이트 지도 — 파이프라인 어디에 어떤 방어가 있는가',
  boxes: [
    {
      domain: 'guard',
      title: '① 질문 분류기',
      desc: '열린 추천("뭐 살까?")·매수 판단·맞춤 조언·실전 매매 요청 → 라벨 기반 정형 안내(AI가 문구를 짓지 않는다). 지표 값·소속 목록 질문은 결정론 데이터로 답한다',
    },
    {
      domain: 'guard',
      title: '② 전략 해석기',
      desc: '역할 밖 행위(추천·전망·우열)는 거절 유지 — 미지원 개념이 섞인 전략 서술만 진행으로 강등',
    },
    {
      domain: 'guard',
      title: '③ 대화 플래너',
      desc: '사용자에게 나가는 질문 문구는 출력 검문(규제 필터) 통과 — 선택지 칩은 사람이 정한 정본 목록만',
    },
    {
      domain: 'guard',
      title: '④ 전략 검증 도우미',
      desc: '"좋은 전략입니다" 류 우열 평가를 구조적으로 생성하지 않음 — 실행 가능성만 진단',
    },
    {
      domain: 'guard',
      title: '⑤ AI 리포트',
      desc: '등급("양호")·권유 표현은 프롬프트 지시 후에도 남으면 출력 필터가 문장째 제거. 백분위는 방향 명시',
    },
    {
      domain: 'guard',
      title: '⑥ 일반 답변 (/query/general)',
      desc: 'guardrails 금지 표현 필터 + 면책 문구 — 결과 수치 설명은 확정 사실만 주입해 환각 차단',
    },
    {
      domain: 'guard',
      title: '⑦ 종목 질문',
      desc: '개별 종목 분석 기능 자체를 제거 — "판단 불가 + 그 종목에서 출발한 전략 연구 전환" 안내만',
    },
    {
      domain: 'guard',
      title: '⑧ UI·마케팅',
      desc: '"AI 투자 코치"·"추천 전략 TOP 10"·"수익률 보장" 등 금지 표현 목록 — 권장 표현은 "전략 연구소"·"백테스트 플랫폼"',
    },
  ],
}

// ─── 서브탭 정의 ─────────────────────────────────────────────────────────────

const SUBTABS = [
  { id: 'graph', label: '구조 그래프' },
  { id: 'map', label: '전체 조감도' },
  { id: 'journey', label: '대화 → 백테스트 여정' },
  { id: 'engine', label: '백테스트 엔진' },
  { id: 'data', label: '데이터 파이프라인' },
  { id: 'virtual', label: '가상매매' },
  { id: 'deploy', label: '배포 구조' },
  { id: 'safety', label: '규제 안전 계층' },
] as const

type SubtabId = (typeof SUBTABS)[number]['id']

const SUBTAB_INTRO: Record<SubtabId, string> = {
  graph:
    '핵심 구성 요소와 그 사이의 호출·데이터 흐름을 한 장의 그래프로 본다. 화살표는 요청·데이터가 흐르는 방향이고, 노드를 클릭하면 상세 설명이 열린다.',
  map: '사용자 브라우저부터 외부 서비스까지 — 요청이 위에서 아래로 흐른다. 카드를 클릭하면 상세 설명이 열린다.',
  journey:
    '사용자가 채팅 한 줄을 입력해 백테스트 결과를 받기까지의 전체 경로. 어느 단계가 AI 판단이고 어느 단계가 결정론인지가 핵심이다.',
  engine: '백테스트 요청 하나가 엔진 안에서 거치는 단계. 전 구간 결정론 — AI는 조건에 AI 신호가 있을 때만 개입한다.',
  data: '외부 소스 → 수집·백필 → 정본 저장소 → 소비자. 각 데이터의 정본(SOT)이 어디인지가 핵심이다.',
  virtual: '백테스트로 검증한 전략을 모의 시장에서 실시간으로 돌리는 경로. 실전 매매는 존재하지 않는다.',
  deploy: '개발(Mac)과 프로덕션(Vultr 단일 박스 + Modal LLM)의 실행 토폴로지와 배포 경로.',
  safety: '유사투자자문업 회피를 위한 다층 방어. 파이프라인의 어느 지점에 어떤 게이트가 박혀 있는지의 지도다.',
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────────────────────

export default function ArchitectureTab() {
  const [subtab, setSubtab] = useState<SubtabId>('graph')
  const [selected, setSelected] = useState<ArchBox | null>(null)

  return (
    <div>
      <div className="mb-1 flex items-end justify-between">
        <h2 className="text-xl font-black">Architecture</h2>
        <Legend />
      </div>
      <p className="mb-4 text-xs font-bold text-gray-600">
        널스탁 서비스 전체의 구조·설계 스냅샷. 코드가 아니라 운영자용 명칭으로 표기한다 — AI 파이프라인 각각의 내부는
        Agents 탭, 지식 데이터 실물은 Knowledge 탭 참고.
      </p>

      {/* 서브탭 */}
      <div className="mb-4 flex flex-wrap gap-1.5">
        {SUBTABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setSubtab(t.id)}
            className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition-colors ${
              t.id === subtab
                ? 'border-white/25 bg-white/10 text-white'
                : 'border-white/10 text-gray-500 hover:bg-white/5 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <p className="mb-4 max-w-3xl text-sm leading-relaxed text-gray-400">{SUBTAB_INTRO[subtab]}</p>

      {subtab === 'graph' && (
        <div>
          <ArchitectureGraph onSelect={setSelected} />
          <NotePanel
            notes={[
              '화살표는 호출·데이터가 흐르는 방향이다 — 브라우저 → Next.js → FastAPI가 유일한 요청 경로이고, 브라우저가 FastAPI를 직접 부르는 경로는 없다.',
              '이 그래프는 핵심 요소만 담은 요약이다 — 계층별 전체 구성은 "전체 조감도", 파이프라인 내부는 Agents 탭·각 서브탭 참고.',
              '앱 DB는 Next.js(Prisma)와 FastAPI(backend/db.py) 양쪽이 같은 Supabase Postgres를 본다.',
              '왼쪽 아래로 갈수록 AI·지식, 오른쪽 아래로 갈수록 시세·뉴스 — 하단이 데이터, 상단이 사용자다.',
            ]}
          />
        </div>
      )}

      {subtab === 'map' && (
        <div>
          {OVERVIEW_LAYERS.map((layer, i) => (
            <div key={layer.title}>
              {i > 0 && <DownArrow />}
              <LayerSection layer={layer} onSelect={setSelected} />
            </div>
          ))}
          <NotePanel
            notes={[
              '요청 경로는 브라우저 → Next.js API 라우트 → FastAPI 순서다 — 브라우저가 FastAPI를 직접 호출하는 경로는 없다.',
              '자연어의 의미 해석은 AI(LLM)만 한다 — 결정론 코드는 AI 출력의 형식 검증·정규화·컴파일만 담당한다(규제 안전 계층 서브탭 참고).',
              '백테스트와 가상매매는 의도적으로 다른 유니버스를 쓴다 — 백테스트=시점 기준 근사(생존편향 제거), 가상매매=현재 명부.',
            ]}
          />
        </div>
      )}

      {subtab === 'journey' && (
        <div>
          <FlowColumn steps={JOURNEY_STEPS} onSelect={setSelected} />
          <NotePanel
            notes={[
              '해석 실패는 실패로 보고하고 되묻는다 — 정규식으로 원문을 재해석하는 폴백은 금지(LLM 연결 실패도 503으로 정직하게).',
              '수정 요청("손절 3%로 바꿔줘")은 전략 수정기가, 열린 질문("뭐 살까?")은 전략 빌더가 따로 처리한다 — Agents 탭 참고.',
              '되묻기 칩은 발행 시점에 "어느 필드를 어떤 값으로 정하는가"가 결속된 것만 노출한다 — 클릭 시 재해석하지 않는다.',
              '백테스트 실행 경로는 2개(SSE 스트림·저장 실행) 모두 쿼터를 소진하고, 이력은 result를 항상 포함해 자동저장된다.',
            ]}
          />
        </div>
      )}

      {subtab === 'engine' && (
        <div>
          <FlowColumn steps={ENGINE_STEPS} onSelect={setSelected} />
          <NotePanel
            notes={[
              '엔진 버전은 backend/engine/version.py가 단일 SOT — 결과값이 바뀌는 변경은 MAJOR, 결과에 버전이 기록된다(UI 노출 금지).',
              '벡터화 단계 순서는 고정이다: 퇴장 처리 → 리스크 평가·주입 → 리밸런싱(재구성·탈락 매도) → 진입 처리.',
              '독립 엔진(backtrader) 교차검증으로 next_open 체결 일치를 확인했다.',
              '백테스트 결과 캐시 재사용은 폐지 — 항상 엔진을 재실행한다.',
            ]}
          />
        </div>
      )}

      {subtab === 'data' && (
        <div>
          {DATA_LAYERS.map((layer, i) => (
            <div key={layer.title}>
              {i > 0 && <DownArrow />}
              <LayerSection layer={layer} onSelect={setSelected} />
            </div>
          ))}
          <NotePanel
            notes={[
              'PIT(Point-In-Time) 원칙 — 백테스트는 "그 시점에 알 수 있던 값"만 쓴다: 재무는 공시일 기준, 유니버스는 as-of 소속, 상폐 종목 포함.',
              '로컬↔프로덕션 미러 방향은 한쪽뿐이다 — 정본=프로덕션, 로컬은 pull-data로 내려받기만 한다.',
              '섹터 분류 정본은 사명이 아니라 KSIC 코드다 — 사명 부분문자열 매칭은 "메가스터디→에너지" 같은 오분류를 만든 근본 원인이었다.',
              '시가총액 값의 단위는 억원이다(market_cap).',
            ]}
          />
        </div>
      )}

      {subtab === 'virtual' && (
        <div>
          <FlowColumn steps={VIRTUAL_STEPS} onSelect={setSelected} />
          <NotePanel
            notes={[
              '가상매매는 현재 명부, 백테스트는 시점 기준 근사 — 생존편향을 피하기 위한 의도적 분리다(같게 만들지 말 것).',
              '연구 에이전트(Premium)가 검증을 통과한 후보 전략을 가상계좌로 자동 승격하는 경로도 있다.',
              '금액 컬럼은 Postgres NUMERIC → float 변환을 db.connect()가 커넥션 단위로 일괄 처리한다.',
            ]}
          />
        </div>
      )}

      {subtab === 'deploy' && (
        <div>
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <h4 className="mb-1 text-sm font-black text-gray-100">개발 (Mac, arm64)</h4>
              <p className="mb-3 text-[11px] font-bold text-gray-600">로컬 프로세스 3개 + 미러 데이터</p>
              <div className="space-y-2.5">
                {DEPLOY_DEV.map((box) => (
                  <BoxCard key={box.title} box={box} onSelect={setSelected} />
                ))}
              </div>
            </section>
            <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
              <h4 className="mb-1 text-sm font-black text-gray-100">프로덕션 (Vultr 단일 박스 + Modal)</h4>
              <p className="mb-3 text-[11px] font-bold text-gray-600">docker compose · /opt/simons · nullstock.im</p>
              <div className="space-y-2.5">
                {DEPLOY_PROD.map((box) => (
                  <BoxCard key={box.title} box={box} onSelect={setSelected} />
                ))}
              </div>
            </section>
          </div>
          <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-4">
            <h4 className="mb-2 text-sm font-black text-gray-100">배포 경로 (CI/CD)</h4>
            <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-gray-300">
              <span className="rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5">main 푸시</span>
              <span className="text-gray-600">→</span>
              <span className="rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5">GitHub Actions (테스트)</span>
              <span className="text-gray-600">→</span>
              <span className="rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5">SSH → Vultr</span>
              <span className="text-gray-600">→</span>
              <span className="rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5">compose 빌드·기동</span>
              <span className="text-gray-600">→</span>
              <span className="rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5">스모크 6블로커</span>
            </div>
          </div>
          <NotePanel notes={DEPLOY_NOTES} />
        </div>
      )}

      {subtab === 'safety' && (
        <div className="space-y-5">
          <BoxCard box={SAFETY_PRINCIPLE} onSelect={setSelected} />
          <section className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
            <h4 className="mb-1 text-sm font-black text-gray-100">해석 레인 계약 — 자연어의 의미는 LLM만 해석한다</h4>
            <p className="mb-3 text-[11px] font-bold text-gray-600">
              규제 안전과 별개의 아키텍처 대원칙 — 모든 자연어 처리 코드가 이 구조를 따른다
            </p>
            <FlowColumn steps={SAFETY_LANE} onSelect={setSelected} />
          </section>
          <LayerSection layer={SAFETY_GATES} onSelect={setSelected} />
          <NotePanel
            notes={[
              '사용자에게 나가는 규제 안내 문구는 전부 라벨 기반의 정형 문장이다 — LLM이 안내 문구를 짓는 경로는 없다.',
              '게이트가 겹치는 것은 의도다 — 상류(분류기)가 놓쳐도 하류(해석기·리포트 필터)가 잡는 다층 방어.',
              '"삼성전자 PER 얼마야?"(사실 조회)와 "삼성전자 사도 될까?"(판단 요청)는 다른 축이다 — 사실 조회는 결정론 데이터로 답하고, 판단 요청만 거절한다.',
            ]}
          />
        </div>
      )}

      {selected && <DetailModal box={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
