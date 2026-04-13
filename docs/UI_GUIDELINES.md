# Simons UI 가이드라인

> 기준: 대시보드 페이지 (`app/page.tsx`) 및 `components/dashboard/`
> 새 페이지/컴포넌트 작성 시 이 가이드라인을 준수한다.

---

## 1. 디자인 시스템 개요

**Flat Dark** 기반의 다크 테마 UI.

- 배경: 깊은 검정색 (`#0f0f0f`)
- 카드: 평면 단색 카드 (`flat-card` 클래스, 그림자/블러 없음)
- 강조색: 빨강/파랑/초록 3색 체계
- 폰트: 굵고 대담한 스타일 (`font-black`, `font-bold`)

---

## 2. 색상 시스템

### CSS 커스텀 속성 (`globals.css`)

```css
--background:    #0f0f0f                    /* 페이지 배경 */
--foreground:    #e0e0e0                    /* 기본 텍스트 */
--main-blue:     rgb(55, 122, 244)          /* 상승/포지티브 */
--main-red:      rgb(239, 68, 68)           /* 하락/네거티브 */
--main-green:    rgb(34, 197, 94)           /* 수익/성공 */
--card-bg:       rgb(22, 22, 22)            /* 카드 배경 */
--card-border:   rgba(255, 255, 255, 0.05)  /* 카드 테두리 */
--glass-bg:      rgba(255, 255, 255, 0.02)  /* 유리 배경 */
--glass-border:  rgba(255, 255, 255, 0.12)  /* 유리 테두리 */
--accent-blue:   #3b82f6
--success-green: #10b981
--error-red:     #ef4444
--text-muted:    #64748b
```

### 텍스트 색상 사용 기준

| 용도 | 클래스 |
|------|--------|
| 주요 텍스트 | `text-white` |
| 보조 텍스트 | `text-gray-400` |
| 비활성/힌트 | `text-gray-500`, `text-gray-600` |
| 라벨/캡션 | `text-gray-300` |
| 수익 (양수) | `text-[var(--main-red)]` 또는 `text-emerald-400` |
| 손실 (음수) | `text-[var(--main-blue)]` |
| 강조 | `text-indigo-400`, `text-sky-500`, `text-purple-400` |

- 카드 내부의 섹션 제목, 차트 제목, 지표 라벨은 기본적으로 `text-gray-400`를 사용한다.
- `text-gray-500`, `text-gray-600`은 비활성 문구, 힌트, 주석에만 사용하고 핵심 제목/지표 라벨에는 사용하지 않는다.
- 테이블 컬럼 헤더는 `text-gray-600`을 사용한다 (본문 라벨보다 한 단계 더 흐리게).

### 통계 지표 색상 규칙

- 통계 지표는 `지표 종류별`로 색을 다르게 주지 않는다.
- 색상은 `상태 의미`가 있는 경우에만 사용한다.
- 수익/손실, 상승/하락처럼 방향성이 명확한 값만 상태 색상을 사용한다.
- `손익비`, `매매횟수`, `소요시간`처럼 중립 지표는 기본 텍스트 색상(`text-white`, `text-gray-200`)을 사용한다.
- `점수`처럼 등급 해석이 필요한 값은 사전에 정의된 기준에 따라 단계형 색상을 사용한다.
- 위계 구분은 색상보다 크기, 굵기, 간격을 우선한다.
- 한 줄 통계 요약이나 카드 내 메트릭 리스트처럼 여러 지표를 동시에 보여주는 구간에서는 값 색상을 기본적으로 하나의 중립 톤으로 통일한다.
- 여러 칸에 상태 색상을 동시에 적용해 시선을 분산시키지 않는다.

### 점수 / 등급 색상 시스템

숫자 점수를 등급별 색상으로 표현하는 공통 기준:

```tsx
const color =
  score >= 80 ? "text-emerald-400" :
  score >= 60 ? "text-blue-400" :
  score >= 40 ? "text-amber-400" :
  "text-red-400";
```

### 상태별 색상 배지

```
KOSPI:    bg-sky-500/15     text-sky-400
KOSPI200: bg-indigo-500/15  text-indigo-400
KOSDAQ:   bg-purple-500/15  text-purple-400
미국주식:  bg-emerald-500/15 text-emerald-400
```

### 방향성 배지 (수익/손실)

```tsx
{/* 양수/음수 색상 배지 */}
<span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md ${
  isPositive
    ? "bg-[var(--main-red)]/10 text-[var(--main-red)]"
    : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"
}`}>
  {value}
  {isPositive ? <ArrowUpRight size={12} weight="bold" /> : <ArrowDownRight size={12} weight="bold" />}
</span>

{/* 중립 정보 배지 */}
<span className="inline-flex items-center text-xs font-bold px-2 py-0.5 rounded-md bg-white/[0.06] text-gray-400">
  중립 텍스트
</span>
```

### 금지 스타일

- 네온 아웃라인 UI는 사용하지 않는다.
- 버튼, 탭, 배지, 카드 등 주요 UI 요소에 고채도 네온 테두리, 과도한 외곽선 강조, 사이버펑크식 발광(glow) 효과를 적용하지 않는다.
- 강조가 필요한 경우에는 네온 효과 대신 색상 대비, 면 처리, 타이포그래피, 간격 체계로 해결한다.

---

## 3. 타이포그래피

### 폰트 패밀리

- 기본: `Arial, Helvetica, sans-serif`
- 숫자/수치 표시: `font-outfit` (커스텀 Tailwind 클래스) — KPI 수치, 섹션 제목, 차트 레이블에 사용

### 텍스트 스타일 계층

| 계층 | 크기 | 굵기 | 추가 클래스 | 용도 |
|------|------|------|-------------|------|
| 섹션 제목 | `text-base` | `font-black` | `uppercase tracking-widest font-outfit` | 카드 헤더 |
| 주요 수치 | `text-2xl` ~ `text-3xl` | `font-black` | `tabular-nums font-outfit` | KPI, 핵심 지표 |
| 보조 수치 | `text-xl` | `font-black` | `tabular-nums font-outfit` | 서브 지표 |
| 리스트 항목 | `text-sm` ~ `text-base` | `font-bold` | `truncate` | 테이블 행 |
| 라벨/배지 | `text-xs` | `font-bold` | `uppercase` | 태그, 상태 표시 |
| 캡션/보조 | `text-[10px]` ~ `text-xs` | `font-bold` | — | 단위, 날짜, 부제목 |

### 공통 텍스트 규칙

- 숫자는 항상 `tabular-nums` 적용 (숫자 정렬 일관성)
- 섹션 제목은 `uppercase tracking-widest` 적용
- 차트/지표/요약 카드의 제목성 텍스트는 가독성을 위해 `text-gray-400` 이상 밝기를 유지
- 긴 텍스트는 `truncate` 처리
- `leading-none` 또는 `leading-tight`로 줄 간격 최소화

---

## 4. 간격 & 패딩 시스템

### 페이지 레이아웃 패딩

```
p-2 md:p-3   (반응형 페이지 패딩)
space-y-1    (섹션 간 세로 간격 — 카드가 바짝 붙도록)
```

### 카드 내부 패딩

| 카드 크기 | 패딩 |
|-----------|------|
| 일반 카드 | `p-5` |
| 중형 카드 | `p-4` |
| 소형 카드 | `p-3` |

### 그리드 갭

| 용도 | 갭 |
|------|----|
| 섹션 간 카드 | `gap-1` |
| 카드 그룹 내부 | `gap-4` |
| 소형 카드 그룹 | `gap-3` |
| 아이콘-텍스트 | `gap-2`, `gap-1.5` |
| 밀착 항목 | `gap-1` |

---

## 5. 카드 & 패널

### flat-card (기본 카드)

모든 카드/패널의 기본 단위. `globals.css`에 정의된 유틸리티 클래스.

- 배경색은 페이지 배경(`var(--background)`)과 동일 — 카드가 배경에 녹아드는 flat 효과
- 테두리·그림자·라운드 없음 — 경계는 컨테이너 레벨 `divide-*`로 처리

```css
.flat-card {
  background: var(--background);   /* #0f0f0f — 페이지 배경과 동일 */
  overflow: hidden;
}
```

**레이아웃 구분 방식 (divide 패턴):**
```tsx
{/* 페이지 전체 외곽 + 행 구분 */}
<div className="border border-white/[0.08]">
  <div className="divide-y divide-white/[0.08]">
    <ComponentA />  {/* 행1 */}
    {/* 열 구분이 필요한 행 — 6:4 비율 */}
    <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
      <div className="lg:col-span-6"><ComponentB /></div>
      <div className="lg:col-span-4"><ComponentC /></div>
    </div>
    {/* 열 구분이 필요한 행 — 3:7 비율 */}
    <div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
      <div className="lg:col-span-3"><ComponentD /></div>
      <div className="lg:col-span-7"><ComponentE /></div>
    </div>
  </div>
</div>

{/* 수평 통계 바 (KPI 카드 가로 나열) */}
<div className="flex divide-x divide-white/[0.08]">
  {items.map(item => <div key={item.id} className="flex-1 px-5 py-4" />)}
</div>

{/* 그리드 아이템 개별 구분 (시장 지표, 관심 종목 등) */}
<div className="grid grid-cols-3 sm:grid-cols-6 border-t border-l border-white/[0.08]">
  {items.map(item => <div key={item.id} className="border-r border-b border-white/[0.08] p-3" />)}
</div>
```

### flat-card 사용 범위

- **flat-card 사용**: 독립 패널 카드 (예: `StrategyList`, `RecentBacktestList`, `BacktestActivityChart`) → `flat-card p-5 h-full`
- **flat-card 미사용**: 행 전체를 차지하는 컴포넌트 (예: `PortfolioSummaryBar`, `VirtualTradingStatus`, `MarketSnapshot`, `WatchlistSnapshot`) → `flex divide-x` 또는 `grid ... border-t border-l` 직접 사용

### 구분선

```tsx
<div className="border-t border-white/[0.05]" />
```

### 그리드 기반 테이블 헤더

모든 테이블의 컬럼 제목은 div 그리드 기반으로 구성한다. `<table>/<thead>/<th>` 사용을 지양한다.

```tsx
{/* 헤더 행 */}
<div className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-2 px-2 mb-2">
  {["전략명", "점수", "평균 수익률", "총 수익금"].map((h) => (
    <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-600">
      {h}
    </span>
  ))}
</div>
{/* 헤더 구분선 */}
<div className="border-t border-white/[0.05] mb-1" />
```

- 컬럼 헤더 텍스트: `text-xs font-bold uppercase tracking-widest text-gray-600`
- 헤더 구분: 배경색 대신 `border-t border-white/[0.05]` 구분선 사용
- 그리드 컬럼 정의는 `grid-cols-[minmax(0,1fr)_80px_...]` 형태로 가변+고정 혼합

### 그리드 기반 테이블 행

> **규칙: 모든 테이블에서 행 보더라인 사용 금지**
> 행 간 시각적 구분은 **`divide-y divide-white/[0.04]`** + **호버(`hover:bg-white/[0.02]`)** 조합으로 처리한다.

```tsx
{/* ✅ 올바른 패턴 */}
<div className="divide-y divide-white/[0.04]">
  {items.map((item) => (
    <div
      key={item.id}
      className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors cursor-pointer"
    >
      {/* 셀 내용 */}
    </div>
  ))}
</div>

{/* ❌ 금지 패턴 */}
<div className="border-b border-white/[0.03] ...">  {/* 개별 행 보더 사용 금지 */}
</div>
```

### 카드형 테이블

- 분석 리스트, 종목 분석, 매매 기록, 월별 수익률처럼 행 단위 정보가 많은 표는 외곽 카드로 감싼다.
- 같은 화면 안에 있는 표들은 가능한 한 동일한 헤더 높이, 행 간격을 공유한다.

---

## 6. 테두리 반경

| 요소 | 클래스 |
|------|--------|
| 카드/패널 | `rounded-2xl` |
| 버튼/입력 | `rounded-xl` |
| 배지/라벨 | `rounded-md` |
| 차트 바 | `rounded-xl` |

---

## 7. 그림자

```css
카드:           그림자 없음 (flat)
활성 차트 바:   box-shadow: 0 0 16px rgba({color},0.35)
버튼 호버:      box-shadow: 0 0 15px rgba(59,130,246,0.4)
```

---

## 8. 레이아웃 패턴

### 페이지 기본 구조

```tsx
<div className="w-full min-w-0 border border-white/[0.08]">
  <div className="divide-y divide-white/[0.08]">
    {/* 각 섹션 행 */}
  </div>
</div>
```

### 2컬럼 비대칭 그리드 — 6:4 비율

```tsx
<div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
  <div className="lg:col-span-6">{/* 메인 */}</div>
  <div className="lg:col-span-4">{/* 서브 */}</div>
</div>
```

### 2컬럼 비대칭 그리드 — 3:7 비율

```tsx
<div className="grid grid-cols-1 lg:grid-cols-10 divide-y lg:divide-y-0 lg:divide-x divide-white/[0.08]">
  <div className="lg:col-span-3">{/* 좁은 패널 (차트 등) */}</div>
  <div className="lg:col-span-7">{/* 넓은 패널 (리스트 등) */}</div>
</div>
```

### 수평 통계 바 (KPI 카드 가로 나열)

```tsx
<div className="flex divide-x divide-white/[0.08] items-stretch">
  {stats.map((s) => (
    <div key={s.label} className="flex-1 flex flex-col justify-between px-5 py-4">
      {/* 상단: 아이콘 + 라벨 */}
      <div className="flex items-center gap-2">
        <Icon size={18} weight="bold" className="text-gray-400" />
        <span className="text-sm font-bold text-gray-400">{s.label}</span>
      </div>
      {/* 하단: 수치 + 배지 */}
      <div className="flex items-end gap-3">
        <span className="text-3xl font-black tabular-nums font-outfit leading-none text-white">
          {s.value}
        </span>
        {/* 배지 */}
      </div>
    </div>
  ))}
</div>
```

### 섹션 카드 헤더 (제목 + 부제목)

```tsx
<div className="flex items-center justify-between mb-5">
  <div>
    <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
      섹션 제목
    </h2>
    <p className="text-xs text-gray-500 mt-0.5">보조 설명 문구</p>
  </div>
  {/* 우측: 버튼 또는 아이콘 */}
  <button className="text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors">
    전체 보기
  </button>
</div>
```

### 섹션 카드 헤더 (제목 + 우측 수치)

```tsx
<div className="flex items-center justify-between mb-5">
  <div>
    <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
      섹션 제목
    </h2>
    <p className="text-xs text-gray-500 mt-0.5">보조 설명</p>
  </div>
  <div className="text-right">
    <p className="text-2xl font-black text-white font-outfit tabular-nums">{totalCount}</p>
    <p className="text-[10px] uppercase tracking-widest text-gray-500 font-bold">라벨</p>
  </div>
</div>
```

### 아이콘 + 텍스트 패턴

```tsx
<div className="flex items-center gap-2">
  <IconComponent size={15} weight="bold" className="text-gray-500" />
  <span className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
    라벨
  </span>
</div>
```

### KPI 수치 표시 패턴

```tsx
<div className="flex flex-col gap-1">
  {/* 라벨 */}
  <div className="flex items-center gap-1.5 text-gray-500">
    <IconComponent size={14} />
    <span className="text-xs font-bold uppercase tracking-widest">항목명</span>
  </div>
  {/* 수치 */}
  <span className="text-2xl font-black text-white tabular-nums font-outfit leading-none">
    1,234,567
  </span>
  {/* 보조 정보 */}
  <span className="text-xs font-bold text-gray-500">단위 또는 설명</span>
</div>
```

### 변화폭 표시 패턴

```tsx
{/* 인라인 변화폭 (수익률 셀 등) */}
<div className={`flex items-center gap-0.5 ${isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
  {isPos ? <ArrowUpRight size={12} weight="bold" /> : <ArrowDownRight size={12} weight="bold" />}
  <span className="text-xs font-black tabular-nums font-outfit">{fmtPct(value)}</span>
</div>

{/* 소형 컨텍스트 (시장 지표 등) */}
<div className={`flex items-center gap-0.5 ${isPos ? "text-[var(--main-red)]" : "text-[var(--main-blue)]"}`}>
  {isPos ? <CaretUp size={10} weight="fill" /> : <CaretDown size={10} weight="fill" />}
  <span className="text-xs font-bold">{Math.abs(changePercent).toFixed(2)}%</span>
</div>
```

### LIVE 인디케이터

실시간 데이터가 갱신되는 섹션 헤더에 사용.

```tsx
<div className="flex items-center gap-2">
  <h2 className="text-base font-black uppercase tracking-widest text-white font-outfit">
    섹션 제목
  </h2>
  <span className="flex items-center gap-1 text-[10px] text-green-400 font-bold">
    <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
    LIVE
  </span>
</div>
```

### 시장/종목 그리드 (border 패턴)

시장 지표, 관심 종목처럼 타일형으로 나열할 때 사용.

```tsx
<div className="grid grid-cols-3 sm:grid-cols-6 border-t border-l border-white/[0.08]">
  {items.map(item => (
    <div key={item.id} className="border-r border-b border-white/[0.08] p-3">
      <p className="text-[10px] uppercase tracking-widest text-gray-400 font-bold mb-1">
        {item.name}
      </p>
      <p className="text-lg font-black text-white tabular-nums font-outfit leading-tight">
        {item.value}
      </p>
    </div>
  ))}
</div>
```

---

## 9. 애니메이션

### 진입 애니메이션

```css
.animate-fade-in    { animation: fadeIn 0.4s ease-out; }
.animate-slide-in   { animation: slideIn 0.4s ease-out; }
.animate-slide-up   { animation: slideUp 0.3s ease-out; }
```

### 공통 전환

```
transition-all duration-300    (일반 상호작용)
transition-colors duration-150 (행 호버)
transition-colors duration-200 (텍스트 색상 변화)
```

### 로딩 상태

```tsx
{/* 스켈레톤 */}
<div className="animate-pulse bg-white/[0.04] rounded-xl h-8 w-24" />

{/* Shimmer */}
<div className="shimmer rounded-xl h-8 w-24" />

{/* 타일 그리드 스켈레톤 */}
<div className="grid grid-cols-3 sm:grid-cols-6 border-t border-l border-white/[0.08]">
  {[...Array(6)].map((_, i) => (
    <div key={i} className="border-r border-b border-white/[0.08] p-3 animate-pulse">
      <div className="h-2 bg-white/5 rounded w-2/3 mb-3" />
      <div className="h-5 bg-white/5 rounded w-3/4 mb-2" />
      <div className="h-3 bg-white/5 rounded w-1/2" />
    </div>
  ))}
</div>
```

---

## 10. 버튼

### 주요 버튼

```tsx
<button className="
  px-4 py-2 rounded-xl
  bg-gradient-to-r from-blue-600 to-indigo-600
  text-white text-sm font-bold
  transition-all duration-300
  hover:shadow-[0_0_15px_rgba(59,130,246,0.4)]
  hover:opacity-90
">
  버튼 텍스트
</button>
```

### 보조/텍스트 버튼

```tsx
<button className="
  text-xs font-bold text-gray-500
  hover:text-gray-300
  transition-colors duration-200
">
  텍스트 버튼
</button>

{/* 강조 색상 버전 */}
<button className="text-xs font-bold text-indigo-400 hover:text-indigo-300 transition-colors">
  전체 보기
</button>
```

### 아이콘 버튼

```tsx
<button className="
  p-1.5 rounded-lg
  text-gray-500 hover:text-gray-300
  hover:bg-white/10
  transition-all duration-200
">
  <IconComponent size={16} />
</button>
```

### 삭제 버튼

모든 삭제 버튼은 배경색으로 위험도를 표현하지 않는다.
- 삭제 버튼은 `테두리`, `폰트`, `아이콘`에만 레드 계열을 사용한다.
- 기본 상태와 호버 상태 모두 배경은 투명하게 유지한다.
- 삭제 버튼의 강조는 채운 빨간 배경이 아니라 얇은 레드 보더와 레드 텍스트/아이콘으로 처리한다.

```tsx
<button className="
  px-3 py-1.5 rounded-lg
  border border-red-500/30
  bg-transparent
  text-red-500
  transition-colors duration-200
">
  <TrashIcon size={16} />
</button>
```

---

## 11. 배지 & 태그

```tsx
{/* 유니버스/상태 배지 */}
<span className="px-2 py-0.5 rounded-md text-xs font-bold bg-sky-500/15 text-sky-400">
  KOSPI
</span>

{/* 방향성 수치 배지 (수익률 등) */}
<span className={`inline-flex items-center gap-0.5 text-xs font-bold px-2 py-0.5 rounded-md ${
  isPositive
    ? "bg-[var(--main-red)]/10 text-[var(--main-red)]"
    : "bg-[var(--main-blue)]/10 text-[var(--main-blue)]"
}`}>
  {value}
  {isPositive ? <ArrowUpRight size={12} weight="bold" /> : <ArrowDownRight size={12} weight="bold" />}
</span>

{/* 중립 정보 배지 */}
<span className="inline-flex items-center text-xs font-bold px-2 py-0.5 rounded-md bg-white/[0.06] text-gray-400">
  중립 텍스트
</span>
```

---

## 12. 테이블 / 리스트

### 그리드 기반 테이블 (권장)

```tsx
{/* 헤더 */}
<div className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-2 px-2 mb-2">
  {["항목", "값1", "값2", "값3"].map((h) => (
    <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-600">
      {h}
    </span>
  ))}
</div>
<div className="border-t border-white/[0.05] mb-1" />

{/* 행 */}
<div className="divide-y divide-white/[0.04]">
  {items.map((item) => (
    <div
      key={item.id}
      className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-2 items-center px-2 py-3 hover:bg-white/[0.02] rounded-xl transition-colors cursor-pointer"
    >
      {/* 셀 내용 */}
    </div>
  ))}
</div>
```

### 스크롤 컨테이너

```tsx
<div className="overflow-y-auto max-h-64 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent">
  {/* 항목들 */}
</div>
```

---

## 13. 반응형 설계

모바일 우선(Mobile-First) 접근.

| 브레이크포인트 | 패딩 | 그리드 |
|---------------|------|--------|
| 기본 (모바일) | `p-4` | `grid-cols-1` |
| `sm` (≥640px) | — | `sm:grid-cols-3`, `sm:grid-cols-4`, `sm:grid-cols-6` |
| `md` (≥768px) | `md:p-5` | — |
| `lg` (≥1024px) | `lg:p-6` | `lg:grid-cols-10`, `lg:col-span-6/4`, `lg:col-span-3/7` |

---

## 14. 아이콘

- 라이브러리: `phosphor-react`
- 기본 크기: `size={16}` (일반), `size={14}` (소형), `size={20}` (대형)
- 기본 weight: `weight="bold"` (선형), `weight="fill"` (방향 표시용 캐럿)
- 색상: `className="text-gray-500"` (기본), 컨텍스트에 따라 상태 색상 적용

```tsx
import { Wallet, TrendUp, CaretUp, CaretDown, ArrowUpRight, ArrowDownRight } from "phosphor-react";

{/* 기본 아이콘 */}
<Icon size={18} weight="bold" className="text-gray-400" />

{/* 방향 표시 아이콘 */}
{isPositive ? <CaretUp size={10} weight="fill" /> : <CaretDown size={10} weight="fill" />}
```

---

## 15. 빈 상태 & 에러 상태

```tsx
{/* 빈 상태 */}
<div className="py-8 text-center">
  <p className="text-gray-500 text-sm">데이터가 없습니다</p>
  <p className="text-gray-600 text-xs mt-1">보조 안내 문구</p>
</div>

{/* 로딩 스켈레톤 */}
<div className="space-y-1">
  {[...Array(4)].map((_, i) => (
    <div key={i} className="h-11 bg-white/[0.03] rounded-xl animate-pulse" />
  ))}
</div>
```

---

## 16. 스크롤바

커스텀 스크롤바 스타일 (`globals.css`에 정의):

```css
::-webkit-scrollbar       { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
```

인라인 커스텀 스크롤바 (컴포넌트 단위):
```tsx
className="[&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-white/10 [&::-webkit-scrollbar-track]:bg-transparent"
```

스크롤바 숨기기: `scrollbar-hide` 클래스 사용

---

## 체크리스트

새 페이지/컴포넌트 작성 시 확인:

- [ ] 독립 패널은 `flat-card p-5 h-full`, 행 단위 컴포넌트는 `flat-card` 없이 `flex divide-x` 또는 `grid` 직접 사용
- [ ] 페이지 루트에 `border border-white/[0.08]` + 내부 `divide-y divide-white/[0.08]` 구조 적용
- [ ] 섹션 제목에 `text-base font-black uppercase tracking-widest font-outfit` 적용
- [ ] 숫자 수치에 `tabular-nums font-outfit` 적용
- [ ] 상태 색상에 CSS 커스텀 속성(`var(--main-red)` 등) 사용
- [ ] 테이블은 div 그리드 기반, 컬럼 헤더 `text-gray-600`, 행 `divide-y divide-white/[0.04]` + `hover:bg-white/[0.02] rounded-xl`
- [ ] 아이콘은 `phosphor-react` 사용
- [ ] `transition-colors duration-150` 행 호버 처리
- [ ] 로딩 상태에 `animate-pulse` 스켈레톤 구현
- [ ] `truncate` + `min-w-0` 텍스트 오버플로우 방지
- [ ] 반응형: 모바일(`grid-cols-1`) → 데스크톱(`lg:grid-cols-10`) 순서
- [ ] 실시간 데이터 섹션에 LIVE 인디케이터 추가
