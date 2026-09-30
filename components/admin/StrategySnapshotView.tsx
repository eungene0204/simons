'use client'

// 대화 기록 한 턴에 우리가 보여 준 전략 카드 — 화면 카드 항목 그대로 + 해석 원본(JSON).
// 카드 항목은 기록 당시 사용자가 본 그대로다(지금 코드로 다시 만들지 않는다).

export type StrategySnapshotItem = {
  label: string
  value: string
  values?: string[]
  detail?: string
  detailCount?: number
}

export type StrategySnapshot = {
  summaryItems: StrategySnapshotItem[] | null
  parsed: unknown
  parsedOmitted?: boolean
}

export type StrategySource = 'log' | 'chat_snapshot'

export default function StrategySnapshotView({
  strategy,
  source,
}: {
  strategy: StrategySnapshot
  source?: StrategySource | null
}) {
  const items = strategy.summaryItems ?? []
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/[0.04] px-3 py-2.5">
      <div className="mb-1.5 flex items-center gap-2">
        <p className="text-xs font-black text-emerald-300">우리가 이해한 전략</p>
        {source === 'chat_snapshot' && (
          <span className="text-[11px] font-bold text-gray-500">(사용자 대화 기록에서 복원)</span>
        )}
      </div>
      {items.length > 0 ? (
        <dl>
          {items.map((item, i) => (
            <div
              key={`${item.label}-${i}`}
              className="grid grid-cols-[88px_minmax(0,1fr)] gap-3 py-1 text-xs leading-relaxed"
            >
              <dt className="break-keep font-bold text-gray-500">{item.label}</dt>
              <dd className="min-w-0 whitespace-normal break-keep font-bold text-gray-200">
                {item.values ? (
                  <span className="flex flex-col gap-0.5">
                    {item.values.map((part, pi) => (
                      <span key={`${part}-${pi}`}>{part}</span>
                    ))}
                  </span>
                ) : (
                  item.value
                )}
                {item.detail && (
                  <details className="mt-0.5">
                    <summary className="cursor-pointer text-[11px] text-gray-500">
                      {item.detailCount != null ? `${item.detailCount}개 펼치기` : '펼치기'}
                    </summary>
                    <p className="mt-1 text-[11px] font-normal text-gray-400">{item.detail}</p>
                  </details>
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-xs font-bold text-gray-500">카드 항목 기록이 없습니다 — 아래 원본을 확인하세요.</p>
      )}
      {strategy.parsed != null ? (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-[11px] font-bold text-gray-500">해석 원본(JSON)</summary>
          <pre className="mt-1 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-md bg-black/30 p-2 text-[11px] text-gray-400">
            {JSON.stringify(strategy.parsed, null, 2)}
          </pre>
        </details>
      ) : strategy.parsedOmitted ? (
        <p className="mt-1.5 text-[11px] font-bold text-gray-600">해석 원본은 크기 한도를 넘어 저장하지 않았습니다.</p>
      ) : null}
    </div>
  )
}
