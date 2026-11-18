'use client'

import { useState, type ReactNode } from 'react'
import { formatDateTime } from './shared'
import StrategySnapshotView, { type StrategySnapshot, type StrategySource } from './StrategySnapshotView'

// 대화 기록 한 턴 — 사용자 입력과 우리 응답을 나란히(좁은 화면은 위아래로) 한 카드에 보여 준다.
// Q&A Logs 탭과 Users 탭의 사용자 대화 패널이 같이 쓴다(2026-11-18 — 표의 두 줄 말줄임을 대체).

export interface QaTurn {
  id: string
  sessionId: string
  turnIndex: number
  question: string
  answer: string
  answerKind: string
  chipAnswer: boolean
  createdAt: string
  latencyMs?: number | null
  userEmail?: string | null
  recoveredFromSnapshot?: boolean
  strategy: StrategySnapshot | null
  strategySource: StrategySource | null
}

// 답변 종류 — app/analytics/new/qaLog.ts의 QaAnswerKind와 같은 값이다.
export const ANSWER_KINDS: { id: string; label: string }[] = [
  { id: '', label: '전체' },
  { id: 'strategy', label: '전략 요약' },
  { id: 'coach', label: '코치 답변' },
  { id: 'info', label: '안내' },
  { id: 'clarification', label: '되묻기' },
  { id: 'text', label: '산문' },
  { id: 'error', label: '오류' },
]

const KIND_LABEL: Record<string, string> = Object.fromEntries(
  ANSWER_KINDS.filter((k) => k.id).map((k) => [k.id, k.label])
)

function KindBadge({ kind }: { kind: string }) {
  const tone =
    kind === 'error'
      ? 'bg-red-500/15 text-red-300'
      : kind === 'clarification'
        ? 'bg-amber-500/15 text-amber-300'
        : kind === 'strategy'
          ? 'bg-emerald-500/15 text-emerald-300'
          : 'bg-white/10 text-gray-300'
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${tone}`}>
      {KIND_LABEL[kind] ?? kind}
    </span>
  )
}

function formatLatency(ms: number | null | undefined): string | null {
  if (ms == null) return null
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// 긴 응답은 처음 몇 줄만 — 길이(줄 수·글자 수)로만 판단한다.
const LONG_ANSWER_LINES = 12
const LONG_ANSWER_CHARS = 600

function isLongText(text: string): boolean {
  return text.length > LONG_ANSWER_CHARS || text.split('\n').length > LONG_ANSWER_LINES
}

export default function QaTurnCard({
  turn,
  showUser = false,
  action,
}: {
  turn: QaTurn
  showUser?: boolean
  action?: ReactNode
}) {
  const long = isLongText(turn.answer)
  const [answerOpen, setAnswerOpen] = useState(false)
  const latency = formatLatency(turn.latencyMs)

  return (
    <article className="flat-card rounded-xl px-4 py-3" data-testid="qa-turn-card">
      <header className="mb-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-bold text-gray-500">
        <KindBadge kind={turn.answerKind} />
        <span>{formatDateTime(turn.createdAt)}</span>
        {showUser && (
          <span className="text-gray-300">{turn.userEmail ?? '비로그인'}</span>
        )}
        <span>
          대화 {turn.sessionId.slice(0, 8)} #{turn.turnIndex}
        </span>
        {latency && <span>· {latency}</span>}
        {turn.recoveredFromSnapshot && <span>· 복구 기록(대화 저장 시각 기준)</span>}
        {action && <span className="ml-auto">{action}</span>}
      </header>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section className="rounded-lg border border-sky-400/20 bg-sky-400/[0.05] px-3 py-2.5">
          <p className="mb-1 flex items-center gap-1.5 text-[11px] font-black text-sky-300">
            사용자 입력
            {turn.chipAnswer && (
              <span className="rounded bg-white/10 px-1 py-px text-[10px] text-gray-300">칩 선택</span>
            )}
          </p>
          <p className="whitespace-pre-wrap break-words text-sm font-bold leading-relaxed text-gray-100">
            {turn.question}
          </p>
        </section>

        <section className="min-w-0 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
          <p className="mb-1 text-[11px] font-black text-gray-400">널스탁 응답</p>
          <p
            className={`whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-300 ${
              long && !answerOpen ? 'line-clamp-[12]' : ''
            }`}
          >
            {turn.answer}
          </p>
          {long && (
            <button
              type="button"
              className="mt-1 text-[11px] font-bold text-gray-500 hover:text-gray-300"
              onClick={() => setAnswerOpen((v) => !v)}
            >
              {answerOpen ? '접기' : '응답 전체 보기'}
            </button>
          )}
          {turn.strategy && (
            <div className="mt-2">
              <StrategySnapshotView strategy={turn.strategy} source={turn.strategySource} />
            </div>
          )}
        </section>
      </div>
    </article>
  )
}
