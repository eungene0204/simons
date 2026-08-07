'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { adminFetch, ErrorNotice, inputClass } from './shared'

// 지표 온톨로지 시각화 — 전략 언어(지표 분류 계층 + 합성 개념)의 시스템 계약 그래프를
// 포스 레이아웃 캔버스로 표시한다(SOT: backend registry/concept_ontology.py + 시드
// data/indicator-ontology.json). KnowledgeGraphView와 같은 상호작용 관례(검색·선택·
// 툴팁·관계 패널)를 따르되, 노드가 100개 규모라 전쌍 반발력으로 충분하다.
//
// 색상: KG 뷰와 동일 팔레트 — 분류(파랑 다이아) / 지원 잎(청록 원) / 미지원 잎(회색 원)
// / 합성 개념(주황 원). 도형·범례가 2차 인코딩(색 단독 식별 금지 원칙).

interface OntNode {
  id: string
  name: string
  kind: 'class' | 'leaf' | 'concept'
  supported?: string
  category?: string
  data_source?: string
  unit?: string | null
  operators?: string[]
  synonyms?: string[]
  description?: string
}

interface OntEdge {
  source: string
  type: 'is_a' | 'expands_to' | 'requires'
  target: string
}

type GroupId = 'class' | 'supported' | 'unsupported' | 'concept'

const GROUPS: Record<GroupId, { label: string; color: string; shape: 'circle' | 'diamond' }> = {
  class: { label: '분류', color: '#3987e5', shape: 'diamond' },
  supported: { label: '지원 지표', color: '#199e70', shape: 'circle' },
  unsupported: { label: '미지원 지표', color: '#8a8983', shape: 'circle' },
  concept: { label: '합성 개념', color: '#d95926', shape: 'circle' },
}

const GROUP_ORDER: GroupId[] = ['class', 'supported', 'unsupported', 'concept']

function groupOf(node: OntNode): GroupId {
  if (node.kind === 'class') return 'class'
  if (node.kind === 'concept') return 'concept'
  return node.supported === 'UNSUPPORTED' ? 'unsupported' : 'supported'
}

interface SimNode extends OntNode {
  group: GroupId
  degree: number
  r: number
  x: number
  y: number
  vx: number
  vy: number
}

interface SimEdge extends OntEdge {
  a: SimNode
  b: SimNode
}

const HEIGHT = 560

// 정규화 키(공백 제거·소문자화) — KnowledgeGraphView와 동일 관례
function normKey(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase()
}

export default function IndicatorOntologyView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [error, setError] = useState('')
  const [data, setData] = useState<{ nodes: OntNode[]; edges: OntEdge[]; issues: string[] } | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [resetKey, setResetKey] = useState(0)
  const [tooltip, setTooltip] = useState<{
    x: number
    y: number
    name: string
    group: string
    description: string | null
  } | null>(null)
  const [query, setQuery] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const controllerRef = useRef<{ selectNode: (id: string) => void } | null>(null)

  useEffect(() => {
    adminFetch<{ nodes: OntNode[]; edges: OntEdge[]; issues: string[] }>('/api/admin/ontology/graph')
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '조회 실패'))
  }, [])

  // 이름·canonical ID·별칭 부분일치 검색 — 이름 시작 > 이름 포함 > ID·별칭 포함 순
  const matches = useMemo(() => {
    const nq = normKey(query)
    if (!nq || !data) return []
    const scored: { node: OntNode; score: number }[] = []
    for (const n of data.nodes) {
      const nameNorm = normKey(n.name)
      let score = -1
      if (nameNorm.startsWith(nq)) score = 0
      else if (nameNorm.includes(nq)) score = 1
      else if (normKey(n.id).includes(nq)) score = 2
      else if (n.synonyms?.some((s) => normKey(s).includes(nq))) score = 3
      if (score >= 0) scored.push({ node: n, score })
    }
    scored.sort((a, b) => a.score - b.score || a.node.name.length - b.node.name.length)
    return scored.slice(0, 8).map((s) => s.node)
  }, [query, data])

  const selectMatch = (node: OntNode) => {
    setQuery(node.name)
    setDropdownOpen(false)
    controllerRef.current?.selectNode(node.id)
  }

  const groupCounts = useMemo(() => {
    const counts = { class: 0, supported: 0, unsupported: 0, concept: 0 } as Record<GroupId, number>
    for (const n of data?.nodes ?? []) counts[groupOf(n)] += 1
    return counts
  }, [data])

  // 선택 노드의 관계 목록 — "RSI –is_a→ 모멘텀/오실레이터" 관례 표시
  const selectedRelations = useMemo(() => {
    if (!data || !selectedId) return []
    const names = new Map(data.nodes.map((n) => [n.id, n.name]))
    return data.edges
      .filter((e) => e.source === selectedId || e.target === selectedId)
      .map((e) => ({
        key: `${e.source}:${e.type}:${e.target}`,
        text: `${names.get(e.source) ?? e.source} –${e.type}→ ${names.get(e.target) ?? e.target}`,
      }))
  }, [data, selectedId])

  const selectedNode = useMemo(
    () => data?.nodes.find((n) => n.id === selectedId) ?? null,
    [data, selectedId]
  )

  // ── 포스 레이아웃 + 캔버스 렌더링(외부 라이브러리 없이, KG 뷰 축약판) ──────────
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container || !data) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const nodeById = new Map<string, SimNode>()
    // 결정적 초기 배치(피보나치 나선) — 새로고침마다 크게 달라지는 걸 줄인다
    const nodes: SimNode[] = data.nodes.map((n, i) => {
      const angle = i * 2.39996
      const radius = 22 * Math.sqrt(i + 1)
      const sim: SimNode = {
        ...n,
        group: groupOf(n),
        degree: 0,
        r: 0,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
      }
      nodeById.set(n.id, sim)
      return sim
    })
    const edges: SimEdge[] = []
    for (const e of data.edges) {
      const a = nodeById.get(e.source)
      const b = nodeById.get(e.target)
      if (!a || !b) continue
      a.degree += 1
      b.degree += 1
      edges.push({ ...e, a, b })
    }
    for (const n of nodes) n.r = Math.min(4 + Math.sqrt(n.degree) * 1.6, 15)

    const neighborIds = new Map<string, Set<string>>()
    for (const e of edges) {
      if (!neighborIds.has(e.a.id)) neighborIds.set(e.a.id, new Set())
      if (!neighborIds.has(e.b.id)) neighborIds.set(e.b.id, new Set())
      neighborIds.get(e.a.id)!.add(e.b.id)
      neighborIds.get(e.b.id)!.add(e.a.id)
    }

    let width = container.clientWidth
    let k = 0.9
    let ox = width / 2
    let oy = HEIGHT / 2
    let alpha = 1
    let hovered: SimNode | null = null
    let selected: SimNode | null = selectedId ? (nodeById.get(selectedId) ?? null) : null
    let dragNode: SimNode | null = null
    let panning = false
    let moved = 0
    let lastX = 0
    let lastY = 0
    let needsDraw = true
    let raf = 0
    let fitted = false
    let interacted = false

    const fitToView = () => {
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
      for (const n of nodes) {
        if (n.x < minX) minX = n.x
        if (n.x > maxX) maxX = n.x
        if (n.y < minY) minY = n.y
        if (n.y > maxY) maxY = n.y
      }
      if (!Number.isFinite(minX) || maxX - minX < 1) return
      k = Math.min(Math.max(Math.min(width / (maxX - minX + 120), HEIGHT / (maxY - minY + 120)), 0.2), 1.2)
      ox = width / 2 - ((minX + maxX) / 2) * k
      oy = HEIGHT / 2 - ((minY + maxY) / 2) * k
    }

    const dpr = window.devicePixelRatio || 1
    const resize = () => {
      width = container.clientWidth
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(HEIGHT * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${HEIGHT}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      needsDraw = true
    }
    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(container)

    // 전쌍 반발력 — 노드 100개 규모라 그리드 근사 없이 감당된다
    const tick = () => {
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i]
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j]
          let dx = n.x - b.x
          let dy = n.y - b.y
          let d2 = dx * dx + dy * dy
          if (d2 < 1) {
            dx = (Math.random() - 0.5) * 2
            dy = (Math.random() - 0.5) * 2
            d2 = dx * dx + dy * dy
          }
          if (d2 > 160_000) continue
          const f = (1600 / d2) * alpha
          n.vx += dx * f
          n.vy += dy * f
          b.vx -= dx * f
          b.vy -= dy * f
        }
      }
      for (const e of edges) {
        const dx = e.b.x - e.a.x
        const dy = e.b.y - e.a.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = ((d - 80) / d) * 0.06 * alpha
        e.a.vx += dx * f
        e.a.vy += dy * f
        e.b.vx -= dx * f
        e.b.vy -= dy * f
      }
      for (const n of nodes) {
        n.vx -= n.x * 0.015 * alpha
        n.vy -= n.y * 0.015 * alpha
        if (n === dragNode) {
          n.vx = 0
          n.vy = 0
          continue
        }
        n.vx *= 0.85
        n.vy *= 0.85
        n.x += n.vx
        n.y += n.vy
      }
      alpha *= 0.985
    }

    const draw = () => {
      ctx.clearRect(0, 0, width, HEIGHT)
      const neighborsOfSelected = selected ? (neighborIds.get(selected.id) ?? new Set<string>()) : null

      ctx.lineWidth = 1
      for (const e of edges) {
        const touchesSelected = selected && (e.a === selected || e.b === selected)
        ctx.strokeStyle = selected
          ? touchesSelected
            ? 'rgba(255,255,255,0.45)'
            : 'rgba(255,255,255,0.05)'
          : 'rgba(255,255,255,0.12)'
        ctx.beginPath()
        ctx.moveTo(e.a.x * k + ox, e.a.y * k + oy)
        ctx.lineTo(e.b.x * k + ox, e.b.y * k + oy)
        ctx.stroke()
      }

      for (const n of nodes) {
        const sx = n.x * k + ox
        const sy = n.y * k + oy
        if (sx < -30 || sx > width + 30 || sy < -30 || sy > HEIGHT + 30) continue
        const r = Math.max(n.r * k, 3)
        const dimmed = selected && n !== selected && !neighborsOfSelected?.has(n.id)
        ctx.globalAlpha = dimmed ? 0.15 : 1
        ctx.fillStyle = GROUPS[n.group].color
        ctx.beginPath()
        if (GROUPS[n.group].shape === 'diamond') {
          ctx.moveTo(sx, sy - r)
          ctx.lineTo(sx + r, sy)
          ctx.lineTo(sx, sy + r)
          ctx.lineTo(sx - r, sy)
          ctx.closePath()
        } else {
          ctx.arc(sx, sy, r, 0, Math.PI * 2)
        }
        ctx.fill()
        ctx.strokeStyle = '#0f0f0f'
        ctx.lineWidth = 2
        ctx.stroke()
        if (n === selected || n === hovered) {
          ctx.strokeStyle = '#ffffff'
          ctx.lineWidth = 1.5
          ctx.stroke()
        }
        ctx.globalAlpha = 1
      }

      // 라벨 — 노드 수가 적어 축소 시 분류·개념만, 확대(k≥1.1)나 강조 시 전부
      ctx.font = '600 11px sans-serif'
      ctx.textBaseline = 'middle'
      for (const n of nodes) {
        const sx = n.x * k + ox
        const sy = n.y * k + oy
        if (sx < -60 || sx > width + 60 || sy < -20 || sy > HEIGHT + 20) continue
        const emphasized =
          n === hovered || n === selected || (selected && neighborsOfSelected?.has(n.id))
        if (!emphasized && k < 1.1 && n.group !== 'class' && n.group !== 'concept') continue
        if (selected && !emphasized && n !== selected) continue
        ctx.globalAlpha = emphasized ? 1 : 0.75
        ctx.fillStyle = emphasized ? '#ffffff' : '#c3c2b7'
        ctx.fillText(n.name, sx + Math.max(n.r * k, 3) + 4, sy)
        ctx.globalAlpha = 1
      }
    }

    const loop = () => {
      if (alpha > 0.005) {
        tick()
        if (!fitted && alpha < 0.25) {
          if (!interacted) fitToView()
          fitted = true
        }
        needsDraw = true
      }
      if (needsDraw) {
        draw()
        needsDraw = false
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    const hitTest = (px: number, py: number): SimNode | null => {
      let best: SimNode | null = null
      let bestD = Infinity
      for (const n of nodes) {
        const dx = n.x * k + ox - px
        const dy = n.y * k + oy - py
        const d = Math.sqrt(dx * dx + dy * dy)
        if (d < Math.max(n.r * k, 6) + 3 && d < bestD) {
          best = n
          bestD = d
        }
      }
      return best
    }

    const pos = (e: PointerEvent | WheelEvent) => {
      const rect = canvas.getBoundingClientRect()
      return { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }

    const onPointerDown = (e: PointerEvent) => {
      const { x, y } = pos(e)
      interacted = true
      moved = 0
      lastX = x
      lastY = y
      dragNode = hitTest(x, y)
      panning = !dragNode
      canvas.setPointerCapture(e.pointerId)
    }

    const onPointerMove = (e: PointerEvent) => {
      const { x, y } = pos(e)
      if (dragNode) {
        moved += Math.abs(x - lastX) + Math.abs(y - lastY)
        dragNode.x = (x - ox) / k
        dragNode.y = (y - oy) / k
        alpha = Math.max(alpha, 0.12)
        needsDraw = true
      } else if (panning) {
        moved += Math.abs(x - lastX) + Math.abs(y - lastY)
        ox += x - lastX
        oy += y - lastY
        needsDraw = true
      } else {
        const hit = hitTest(x, y)
        if (hit !== hovered) {
          hovered = hit
          canvas.style.cursor = hit ? 'pointer' : 'grab'
          setTooltip(
            hit
              ? {
                  x,
                  y,
                  name: hit.name,
                  group: GROUPS[hit.group].label,
                  description: hit.description || null,
                }
              : null
          )
          needsDraw = true
        } else if (hit) {
          setTooltip((t) => (t ? { ...t, x, y } : t))
        }
      }
      lastX = x
      lastY = y
    }

    const onPointerUp = (e: PointerEvent) => {
      if (moved < 5) {
        const { x, y } = pos(e)
        const hit = hitTest(x, y)
        selected = hit && hit !== selected ? hit : null
        setSelectedId(selected?.id ?? null)
        needsDraw = true
      }
      dragNode = null
      panning = false
    }

    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      interacted = true
      const { x, y } = pos(e)
      const factor = Math.exp(-e.deltaY * 0.0015)
      const k2 = Math.min(Math.max(k * factor, 0.2), 4)
      ox = x - ((x - ox) / k) * k2
      oy = y - ((y - oy) / k) * k2
      k = k2
      needsDraw = true
    }

    const onLeave = () => {
      hovered = null
      setTooltip(null)
      needsDraw = true
    }

    // 검색 결과 선택 → 카메라를 그 노드로 이동+확대(최소 1.2배)하고 이웃 하이라이트
    controllerRef.current = {
      selectNode: (id: string) => {
        const n = nodeById.get(id)
        if (!n) return
        selected = n
        setSelectedId(id)
        interacted = true
        k = Math.max(k, 1.2)
        ox = width / 2 - n.x * k
        oy = HEIGHT / 2 - n.y * k
        needsDraw = true
      },
    }

    canvas.style.cursor = 'grab'
    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerup', onPointerUp)
    canvas.addEventListener('pointerleave', onLeave)
    canvas.addEventListener('wheel', onWheel, { passive: false })

    return () => {
      cancelAnimationFrame(raf)
      observer.disconnect()
      controllerRef.current = null
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerup', onPointerUp)
      canvas.removeEventListener('pointerleave', onLeave)
      canvas.removeEventListener('wheel', onWheel)
    }
    // selectedId는 캔버스 내부 클릭이 원천이므로 의존성에 넣지 않는다(재시뮬레이션 방지)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, resetKey])

  if (error) return <ErrorNotice message={error} />
  if (!data) return <p className="text-sm font-bold text-gray-600">온톨로지 불러오는 중…</p>

  return (
    <div className="space-y-3">
      <p className="text-xs font-bold text-gray-500">
        전략 언어(지표·합성 개념)의 시스템 계약 그래프입니다. 잎 정본은 IndicatorRegistry,
        분류 계층·합성 개념은 시드(data/indicator-ontology.json)에서 합성되며, 시드 수정만으로
        새 지식이 편입됩니다. 해석 LLM의 지표 어휘 프롬프트가 이 그래프에서 생성됩니다.
      </p>
      <div className="relative w-full max-w-xs">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setDropdownOpen(true)
          }}
          onFocus={() => setDropdownOpen(true)}
          onBlur={() => setTimeout(() => setDropdownOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && matches[0]) selectMatch(matches[0])
            else if (e.key === 'Escape') {
              setQuery('')
              setDropdownOpen(false)
            }
          }}
          placeholder="노드 검색 (이름·ID·별칭)"
          className={`${inputClass} w-full`}
        />
        {dropdownOpen && query && (
          <ul className="absolute z-20 mt-1 w-full max-h-64 overflow-y-auto rounded-lg border border-white/10 bg-[#1a1a1a] shadow-xl">
            {matches.length === 0 && (
              <li className="px-3 py-2 text-xs font-bold text-gray-600">일치하는 노드 없음</li>
            )}
            {matches.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault()
                    selectMatch(m)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-bold text-gray-200 hover:bg-white/10"
                >
                  <span
                    className={GROUPS[groupOf(m)].shape === 'circle' ? 'inline-block h-2 w-2 shrink-0 rounded-full' : 'inline-block h-2 w-2 shrink-0'}
                    style={{
                      backgroundColor: GROUPS[groupOf(m)].color,
                      transform: GROUPS[groupOf(m)].shape === 'diamond' ? 'rotate(45deg)' : undefined,
                    }}
                  />
                  <span className="truncate">{m.name}</span>
                  <span className="ml-auto shrink-0 text-[11px] font-bold text-gray-500">
                    {GROUPS[groupOf(m)].label}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs font-bold text-gray-400">
        {GROUP_ORDER.map((g) => (
          <span key={g} className="flex items-center gap-1.5">
            <span
              className={GROUPS[g].shape === 'circle' ? 'inline-block h-2.5 w-2.5 rounded-full' : 'inline-block h-2.5 w-2.5'}
              style={{
                backgroundColor: GROUPS[g].color,
                transform: GROUPS[g].shape === 'diamond' ? 'rotate(45deg)' : undefined,
              }}
            />
            {GROUPS[g].label} {groupCounts[g]}
          </span>
        ))}
        <span className="ml-auto text-gray-500">
          노드 {data.nodes.length} · 엣지 {data.edges.length}
        </span>
        <button
          onClick={() => {
            setSelectedId(null)
            setQuery('')
            setResetKey((v) => v + 1)
          }}
          className="rounded-md border border-white/10 px-2.5 py-1 text-gray-300 hover:bg-white/5"
        >
          다시 배치
        </button>
      </div>

      <div ref={containerRef} className="relative overflow-hidden rounded-xl border border-white/10 bg-white/[0.02]">
        <canvas ref={canvasRef} className="block touch-none" />
        {tooltip && (
          <div
            className="pointer-events-none absolute z-10 max-w-[260px] rounded-lg border border-white/10 bg-[#1a1a1a] px-3 py-2 shadow-xl"
            style={{
              left: Math.min(tooltip.x + 12, (containerRef.current?.clientWidth ?? 320) - 270),
              top: Math.min(tooltip.y + 12, HEIGHT - 90),
            }}
          >
            <p className="text-xs font-black text-white">{tooltip.name}</p>
            <p className="text-[11px] font-bold text-gray-500">{tooltip.group}</p>
            {tooltip.description && (
              <p className="mt-1 text-[11px] font-medium leading-snug text-gray-400">{tooltip.description}</p>
            )}
          </div>
        )}
      </div>

      {selectedNode && (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-black text-white">{selectedNode.name}</span>
            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-bold text-gray-400">
              {GROUPS[groupOf(selectedNode)].label}
            </span>
            <span className="text-[11px] font-bold text-gray-500">{selectedNode.id}</span>
            {selectedNode.supported && (
              <span
                className={`rounded-full px-2 py-0.5 text-[11px] font-bold ${
                  selectedNode.supported === 'UNSUPPORTED'
                    ? 'bg-red-500/15 text-red-400'
                    : selectedNode.supported === 'PARTIALLY_SUPPORTED'
                      ? 'bg-amber-500/15 text-amber-400'
                      : 'bg-emerald-500/15 text-emerald-400'
                }`}
              >
                {selectedNode.supported === 'UNSUPPORTED'
                  ? '미지원'
                  : selectedNode.supported === 'PARTIALLY_SUPPORTED'
                    ? '부분 지원'
                    : '지원'}
              </span>
            )}
            {selectedNode.unit && (
              <span className="text-[11px] font-bold text-gray-500">단위 {selectedNode.unit}</span>
            )}
            {selectedNode.operators && selectedNode.operators.length > 0 && (
              <span className="text-[11px] font-bold text-gray-500">
                연산자 {selectedNode.operators.join(' ')}
              </span>
            )}
          </div>
          {selectedNode.synonyms && selectedNode.synonyms.length > 0 && (
            <p className="mt-1 text-[11px] font-bold text-gray-500">
              별칭: {selectedNode.synonyms.join(' · ')}
            </p>
          )}
          {selectedNode.description && (
            <p className="mt-1 text-xs font-bold text-gray-400">{selectedNode.description}</p>
          )}
          <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
            {selectedRelations.map((r) => (
              <li key={r.key} className="text-xs font-bold text-gray-300">
                {r.text}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.issues.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs font-bold text-amber-400">
          온톨로지 검증 경고 {data.issues.length}건: {data.issues.slice(0, 3).join(' · ')}
          {data.issues.length > 3 && ' …'}
        </div>
      )}
    </div>
  )
}
