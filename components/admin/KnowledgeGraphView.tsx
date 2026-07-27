'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { adminFetch, ErrorNotice, inputClass } from './shared'

// KG 시각화(FR-STR-070c) — 백엔드가 합성한 지식그래프(시드+정본 섹터·기업·ETF+학습
// 오버레이)를 포스 레이아웃 캔버스로 표시한다. 객관적 관계 데이터의 표시일 뿐
// 추천·전망이 아니다.
//
// 기본 화면은 테마 레벨(종목 숨김)이다 — 테마 카탈로그 확장으로 종목 노드가 전체의
// 8할이라 다 그리면 헤어볼이 된다. 종목은 노드 선택 시 그 이웃만 펼치고, 범례의
// '상장사' 토글로 전체 표시도 선택할 수 있다.
//
// 색상: 어두운 표면(#0f0f0f)에서 전쌍(all-pairs) 검증을 통과하는 3색(파랑·청록·주황)
// + 중립 회색 2단만 사용한다. 기업/ETF는 회색 계열이라 도형(원/사각형)·크기·라벨·
// 범례가 2차 인코딩으로 식별을 보장한다(색 단독 식별 금지 원칙).

interface KgNode {
  id: string
  name: string
  category?: string
  description?: string
  synonyms?: string[]
}

interface KgEdge {
  source: string
  type: string
  target: string
  support?: number
}

type GroupId = 'concept' | 'sector' | 'learned' | 'company' | 'etf'

const GROUPS: Record<GroupId, { label: string; color: string; shape: 'circle' | 'diamond' | 'square' }> = {
  concept: { label: '개념·테마', color: '#3987e5', shape: 'circle' },
  sector: { label: '섹터', color: '#199e70', shape: 'diamond' },
  learned: { label: '학습 용어', color: '#d95926', shape: 'circle' },
  company: { label: '상장사', color: '#8a8983', shape: 'circle' },
  etf: { label: 'ETF', color: '#c3c2b7', shape: 'square' },
}

const GROUP_ORDER: GroupId[] = ['concept', 'sector', 'learned', 'company', 'etf']

function groupOf(node: KgNode): GroupId {
  if (node.id.startsWith('sector:')) return 'sector'
  if (node.id.startsWith('company:')) return 'company'
  if (node.id.startsWith('etf:')) return 'etf'
  if (node.id.startsWith('learned:')) return 'learned'
  return 'concept'
}

interface SimNode extends KgNode {
  group: GroupId
  degree: number
  r: number
  x: number
  y: number
  vx: number
  vy: number
  // 시뮬레이션·렌더 참여 여부 — 기본 테마 레벨에서 종목은 비활성, 선택 시 이웃만 활성
  active: boolean
  // 화면에 한 번이라도 배치됐는지 — 처음 펼쳐지는 종목은 연결 노드 곁에서 시작시킨다
  placed: boolean
}

interface SimEdge extends KgEdge {
  a: SimNode
  b: SimNode
}

const HEIGHT = 560

// 정규화 키(공백 제거·소문자화) — 백엔드 knowledge_graph._norm_key와 동일 관례
function normKey(text: string): string {
  return text.replace(/\s+/g, '').toLowerCase()
}

export default function KnowledgeGraphView() {
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [error, setError] = useState('')
  const [data, setData] = useState<{ nodes: KgNode[]; edges: KgEdge[]; issues: string[] } | null>(null)
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
  const [showCompanies, setShowCompanies] = useState(false)
  // resetKey 재시뮬레이션에서도 토글 상태를 유지하기 위한 ref(이펙트가 초기값으로 읽음)
  const showCompaniesRef = useRef(false)
  // 진행 중인 포스 시뮬레이션에 명령을 보내는 통로 — 검색 결과 선택 시 레이아웃을
  // 재시작(resetKey)하지 않고 카메라만 이동시킨다(재배치는 위치가 흔들려 방해된다)
  const controllerRef = useRef<{
    selectNode: (id: string) => void
    setShowAll: (v: boolean) => void
  } | null>(null)

  const toggleCompanies = () => {
    const next = !showCompaniesRef.current
    showCompaniesRef.current = next
    setShowCompanies(next)
    controllerRef.current?.setShowAll(next)
  }

  // 이름·별칭 부분일치 검색 — 이름 시작 일치 > 이름 포함 > 별칭 포함 순으로 정렬
  const matches = useMemo(() => {
    const nq = normKey(query)
    if (!nq || !data) return []
    const scored: { node: KgNode; score: number }[] = []
    for (const n of data.nodes) {
      const nameNorm = normKey(n.name)
      let score = -1
      if (nameNorm.startsWith(nq)) score = 0
      else if (nameNorm.includes(nq)) score = 1
      else if (n.synonyms?.some((s) => normKey(s).includes(nq))) score = 2
      if (score >= 0) scored.push({ node: n, score })
    }
    scored.sort((a, b) => a.score - b.score || a.node.name.length - b.node.name.length)
    return scored.slice(0, 8).map((s) => s.node)
  }, [query, data])

  const selectMatch = (node: KgNode) => {
    setQuery(node.name)
    setDropdownOpen(false)
    controllerRef.current?.selectNode(node.id)
  }

  useEffect(() => {
    adminFetch<{ nodes: KgNode[]; edges: KgEdge[]; issues: string[] }>('/api/admin/knowledge/graph')
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : '조회 실패'))
  }, [])

  const groupCounts = useMemo(() => {
    const counts = { concept: 0, sector: 0, learned: 0, company: 0, etf: 0 } as Record<GroupId, number>
    for (const n of data?.nodes ?? []) counts[groupOf(n)] += 1
    return counts
  }, [data])

  // 선택 노드의 관계 목록(사이드 패널) — "HBM –produced_by→ SK하이닉스" 관례 표시
  const selectedRelations = useMemo(() => {
    if (!data || !selectedId) return []
    const names = new Map(data.nodes.map((n) => [n.id, n.name]))
    return data.edges
      .filter((e) => e.source === selectedId || e.target === selectedId)
      .map((e) => ({
        key: `${e.source}:${e.type}:${e.target}`,
        text: `${names.get(e.source) ?? e.source} –${e.type}→ ${names.get(e.target) ?? e.target}`,
        support: e.support,
      }))
  }, [data, selectedId])

  const selectedNode = useMemo(
    () => data?.nodes.find((n) => n.id === selectedId) ?? null,
    [data, selectedId]
  )

  // ── 포스 레이아웃 + 캔버스 렌더링(외부 라이브러리 없이) ─────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container || !data) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const nodeById = new Map<string, SimNode>()
    // 결정적 초기 배치(피보나치 나선) — 새로고침마다 크게 다른 모양이 되는 걸 줄인다
    const nodes: SimNode[] = data.nodes.map((n, i) => {
      const angle = i * 2.39996
      const radius = 26 * Math.sqrt(i + 1)
      const group = groupOf(n)
      const active = group !== 'company' || showCompaniesRef.current
      const sim: SimNode = {
        ...n,
        group,
        degree: 0,
        r: 0,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
        active,
        placed: active,
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
    // sqrt 스케일 — 카탈로그 테마는 차수가 수십이라 선형 스케일이면 대부분 상한에 붙는다
    for (const n of nodes) n.r = Math.min(3.5 + Math.sqrt(n.degree) * 1.3, 16)

    const neighborIds = new Map<string, Set<string>>()
    for (const e of edges) {
      if (!neighborIds.has(e.a.id)) neighborIds.set(e.a.id, new Set())
      if (!neighborIds.has(e.b.id)) neighborIds.set(e.b.id, new Set())
      neighborIds.get(e.a.id)!.add(e.b.id)
      neighborIds.get(e.b.id)!.add(e.a.id)
    }

    // 뷰 상태(줌·팬)와 상호작용 상태 — 리렌더 없이 캔버스만 다시 그린다
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
    let showAll = showCompaniesRef.current

    // 처음 펼쳐지는 종목은 연결된(이미 배치된) 노드 곁에서 시작한다 — 스파이럴
    // 원점에서 날아오면 어느 테마의 종목인지 시각적으로 끊긴다
    const place = (n: SimNode) => {
      const ids = neighborIds.get(n.id)
      if (ids) {
        for (const id of ids) {
          const nb = nodeById.get(id)
          if (nb?.active && nb.placed) {
            const a = Math.random() * Math.PI * 2
            const d = 40 + Math.random() * 40
            n.x = nb.x + Math.cos(a) * d
            n.y = nb.y + Math.sin(a) * d
            break
          }
        }
      }
      n.placed = true
    }

    // 기본은 테마 레벨 — 종목은 '전체 표시' 토글이 켜졌거나, 선택 노드 자신·이웃일 때만 활성
    const updateActive = () => {
      const neighbors = selected ? neighborIds.get(selected.id) : null
      for (const n of nodes) {
        const want =
          n.group !== 'company' || showAll || n === selected || (neighbors?.has(n.id) ?? false)
        if (want && !n.active && !n.placed) place(n)
        n.active = want
      }
      alpha = Math.max(alpha, 0.3)
      needsDraw = true
    }
    updateActive()

    // 레이아웃이 어느 정도 안정되면 전체 그래프가 보이도록 1회 자동 맞춤한다
    // (사용자가 먼저 줌/팬했으면 덮어쓰지 않는다)
    const fitToView = () => {
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
      for (const n of nodes) {
        if (!n.active) continue
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

    // 반발력은 공간 그리드 근사 — 인접 9칸은 노드끼리 정확 계산, 그 밖(컷오프 400px
    // 이내)은 칸의 무게중심×개수로 근사한다. 테마 카탈로그 확장으로 '전체 표시' 시
    // 3천 노드 규모라 전쌍 O(n²)는 프레임을 감당하지 못한다.
    const CELL = 80
    const RANGE = Math.ceil(400 / CELL)
    const tick = () => {
      const cells = new Map<number, { sx: number; sy: number; count: number; items: SimNode[] }>()
      for (const n of nodes) {
        if (!n.active) continue
        const key = (Math.floor(n.x / CELL) + 2048) * 4096 + (Math.floor(n.y / CELL) + 2048)
        let c = cells.get(key)
        if (!c) cells.set(key, (c = { sx: 0, sy: 0, count: 0, items: [] }))
        c.sx += n.x
        c.sy += n.y
        c.count += 1
        c.items.push(n)
      }
      for (const n of nodes) {
        if (!n.active) continue
        const ci = Math.floor(n.x / CELL) + 2048
        const cj = Math.floor(n.y / CELL) + 2048
        for (let di = -RANGE; di <= RANGE; di++) {
          for (let dj = -RANGE; dj <= RANGE; dj++) {
            const c = cells.get((ci + di) * 4096 + (cj + dj))
            if (!c) continue
            if (di >= -1 && di <= 1 && dj >= -1 && dj <= 1) {
              for (const b of c.items) {
                if (b === n) continue
                let dx = n.x - b.x
                let dy = n.y - b.y
                let d2 = dx * dx + dy * dy
                if (d2 < 1) {
                  dx = (Math.random() - 0.5) * 2
                  dy = (Math.random() - 0.5) * 2
                  d2 = dx * dx + dy * dy
                }
                const f = (1400 / d2) * alpha
                n.vx += dx * f
                n.vy += dy * f
              }
            } else {
              const dx = n.x - c.sx / c.count
              const dy = n.y - c.sy / c.count
              const d2 = dx * dx + dy * dy
              if (d2 < 1 || d2 > 160_000) continue
              const f = ((1400 * c.count) / d2) * alpha
              n.vx += dx * f
              n.vy += dy * f
            }
          }
        }
      }
      for (const e of edges) {
        if (!e.a.active || !e.b.active) continue
        const dx = e.b.x - e.a.x
        const dy = e.b.y - e.a.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = ((d - 70) / d) * 0.06 * alpha
        e.a.vx += dx * f
        e.a.vy += dy * f
        e.b.vx -= dx * f
        e.b.vy -= dy * f
      }
      for (const n of nodes) {
        if (!n.active) continue
        n.vx -= n.x * 0.02 * alpha
        n.vy -= n.y * 0.02 * alpha
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
        if (!e.a.active || !e.b.active) continue
        const touchesSelected = selected && (e.a === selected || e.b === selected)
        ctx.strokeStyle = selected
          ? touchesSelected
            ? 'rgba(255,255,255,0.45)'
            : 'rgba(255,255,255,0.04)'
          : 'rgba(255,255,255,0.10)'
        ctx.beginPath()
        ctx.moveTo(e.a.x * k + ox, e.a.y * k + oy)
        ctx.lineTo(e.b.x * k + ox, e.b.y * k + oy)
        ctx.stroke()
      }

      for (const n of nodes) {
        if (!n.active) continue
        const sx = n.x * k + ox
        const sy = n.y * k + oy
        if (sx < -30 || sx > width + 30 || sy < -30 || sy > HEIGHT + 30) continue
        const r = Math.max(n.r * k, 3)
        const dimmed =
          selected && n !== selected && !neighborsOfSelected?.has(n.id)
        ctx.globalAlpha = dimmed ? 0.15 : 1
        ctx.fillStyle = GROUPS[n.group].color
        ctx.beginPath()
        const shape = GROUPS[n.group].shape
        if (shape === 'diamond') {
          ctx.moveTo(sx, sy - r)
          ctx.lineTo(sx + r, sy)
          ctx.lineTo(sx, sy + r)
          ctx.lineTo(sx - r, sy)
          ctx.closePath()
        } else if (shape === 'square') {
          const s = r * 0.9
          ctx.rect(sx - s, sy - s, s * 2, s * 2)
        } else {
          ctx.arc(sx, sy, r, 0, Math.PI * 2)
        }
        ctx.fill()
        // 마크 간 2px 표면 링 — 겹칠 때 경계를 유지한다
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

      // 라벨 — 개념·섹터·학습은 항상, 기업·ETF는 확대(k≥1.5)·선택 이웃·호버 시만
      ctx.font = '600 11px sans-serif'
      ctx.textBaseline = 'middle'
      for (const n of nodes) {
        if (!n.active) continue
        const sx = n.x * k + ox
        const sy = n.y * k + oy
        if (sx < -60 || sx > width + 60 || sy < -20 || sy > HEIGHT + 20) continue
        const emphasized =
          n === hovered || n === selected || (selected && neighborsOfSelected?.has(n.id))
        const alwaysLabeled = n.group === 'concept' || n.group === 'sector' || n.group === 'learned'
        if (!alwaysLabeled && !emphasized && k < 1.5) continue
        // 축소 시에는 허브(연결 많은 노드)만 라벨링해 겹침을 줄인다 — 임계 차수는 줌에
        // 비례해 낮아진다. 학습 용어(9개 남짓)는 검토 대상이라 항상 라벨링한다.
        if (alwaysLabeled && !emphasized && n.group !== 'learned') {
          const minDegree = k < 0.55 ? 40 : k < 0.8 ? 20 : k < 1.2 ? 6 : 0
          if (n.degree < minDegree) continue
        }
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
        if (!n.active) continue
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
                  description: hit.description ?? null,
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
        updateActive()
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

    // 검색 결과 선택 → 카메라를 그 노드로 이동+확대(최소 1.1배)하고 이웃을 하이라이트.
    // 숨겨진 종목 노드를 선택하면 updateActive가 먼저 배치·활성화한 뒤 카메라를 옮긴다.
    controllerRef.current = {
      selectNode: (id: string) => {
        const n = nodeById.get(id)
        if (!n) return
        selected = n
        setSelectedId(id)
        updateActive()
        interacted = true
        k = Math.max(k, 1.1)
        ox = width / 2 - n.x * k
        oy = HEIGHT / 2 - n.y * k
        needsDraw = true
      },
      setShowAll: (v: boolean) => {
        showAll = v
        updateActive()
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
  if (!data) return <p className="text-sm font-bold text-gray-600">그래프 불러오는 중…</p>

  return (
    <div className="space-y-3">
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
          placeholder="노드 검색 (이름·별칭)"
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
        {GROUP_ORDER.map((g) => {
          const dot = (
            <span
              className={GROUPS[g].shape === 'circle' ? 'inline-block h-2.5 w-2.5 rounded-full' : 'inline-block h-2.5 w-2.5'}
              style={{
                backgroundColor: GROUPS[g].color,
                transform: GROUPS[g].shape === 'diamond' ? 'rotate(45deg)' : undefined,
              }}
            />
          )
          // 상장사는 기본 숨김(선택 시 이웃만 펼침) — 범례 칩이 전체 표시 토글을 겸한다
          if (g === 'company') {
            return (
              <button
                key={g}
                type="button"
                onClick={toggleCompanies}
                className={`flex items-center gap-1.5 rounded-md border px-2 py-0.5 ${
                  showCompanies
                    ? 'border-white/30 bg-white/10 text-gray-200'
                    : 'border-white/10 text-gray-400 hover:bg-white/5'
                }`}
              >
                {dot}
                {GROUPS[g].label} {groupCounts[g]} · {showCompanies ? '전체 표시' : '선택 시 표시'}
              </button>
            )
          }
          return (
            <span key={g} className="flex items-center gap-1.5">
              {dot}
              {GROUPS[g].label} {groupCounts[g]}
            </span>
          )
        })}
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
          <div className="flex items-center gap-2">
            <span className="text-sm font-black text-white">{selectedNode.name}</span>
            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-bold text-gray-400">
              {GROUPS[groupOf(selectedNode)].label}
            </span>
          </div>
          {selectedNode.description && (
            <p className="mt-1 text-xs font-bold text-gray-400">{selectedNode.description}</p>
          )}
          <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto">
            {selectedRelations.map((r) => (
              <li key={r.key} className="text-xs font-bold text-gray-300">
                {r.text}
                {r.support != null && (
                  <span className="ml-2 text-[11px] text-gray-500">출처 {r.support}개</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.issues.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs font-bold text-amber-400">
          그래프 검증 경고 {data.issues.length}건: {data.issues.slice(0, 3).join(' · ')}
          {data.issues.length > 3 && ' …'}
        </div>
      )}
    </div>
  )
}
