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

/* 대화 표면 (전략연구소) */
--chat-accent:           #f0b429                  /* 단일 강조색, #0f0f0f 대비 10.2:1 */
--chat-accent-soft:      rgba(240,180,41,0.14)
--chat-accent-ink:       #191203                  /* accent 채운 버튼의 글자색 */
/* 모든 대화 박스가 이 한 값을 쓴다 — 반투명 유리, 그라디언트 없음(2026-08-05 확정) */
--chat-surface:           rgba(255,255,255,0.06)
--chat-user-surface:      var(--chat-surface)     /* 사용자 발화 버블 */
--chat-artifact-surface:  var(--chat-surface)     /* 구조화 산출물 카드 */
--chat-chip-surface:      transparent             /* 선택 칩 — 담긴 면이 비친다 (hover 0.07) */
--chat-hairline:          rgba(255,255,255,0.09)

/* WCAG AA 통과 보조 텍스트 */
--text-label:       #9ca3af                       /* 7.6:1 */
--text-placeholder: #8b8f96                       /* 5.9:1 */
```

### 강조색 단일화

- **한 화면의 장식용 강조색은 하나만 쓴다.** 강조색이 여러 개면 색이 의미를 잃는다.
- 의미색(`--main-red` 상승, `--main-blue` 하락, `--error-red` 오류)은 강조 목적으로 전용하지 않는다.
- 강조색에 역할을 부여하고 그 역할에만 쓴다. 전략연구소 대화의 `--chat-accent`는 "사용자 응답이 필요한 지점 + 진행 상태"만 담당한다.
- 링크도 강조색을 따른다. 별도의 링크 색을 도입하지 않는다.

### 텍스트 대비 (WCAG AA)

- 본문·라벨은 배경 대비 **4.5:1 이상**을 확보한다.
- `text-gray-500`(#6b7280)은 `#0f0f0f` 대비 **3.98:1로 미달**이다. 의미 있는 라벨에는 `text-[var(--text-label)]`를 쓴다.
- placeholder도 AA 대상이다. `placeholder-gray-600`은 미달이며 `placeholder:text-[var(--text-placeholder)]`를 쓴다.
- `text-gray-600` 이하는 순수 장식 텍스트에만 허용한다.

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

- 카드 내부의 섹션 제목, 차트 제목, 지표 라벨, 테이블 컬럼 헤더, KPI 카드 라벨은 `text-gray-500`으로 통일한다.
- `text-gray-600`은 보조 설명(sub-text), 힌트, 주석처럼 완전히 부차적인 텍스트에만 사용한다.
- `text-gray-400` 이상은 주요 텍스트(본문, 값)에만 사용한다.

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

폰트 스택은 `tailwind.config.js`의 `theme.extend.fontFamily`가 SOT다. `globals.css`의 `body`에서 `font-family`를 재지정하면 그 스택을 덮어쓰므로 선언하지 않는다.

- 기본(`font-sans`, `font-inter`): `var(--font-inter)` → `Pretendard` → `Apple SD Gothic Neo` → `Malgun Gothic` → `system-ui`
  - Inter는 라틴/숫자만 커버한다. 한글 글리프는 뒤따르는 한글 폰트로 글리프 단위 폴백된다.
  - Inter를 기본으로 두는 이유: 데이터 밀도가 높은 계기판형 UI에서 중성적인 그로테스크가 맞고, 숫자 정렬(`tabular-nums`)이 안정적이다.
- 숫자/수치 표시: `font-outfit` — KPI 수치, 섹션 제목, 차트 레이블에 사용

> ⚠️ 2026-07-25까지 `fontFamily` 확장이 없어 `font-outfit`·`font-inter`는 **정의되지 않은 죽은 클래스**였고(22개 파일이 사용 중), 실제 렌더 폰트는 `globals.css`의 Arial이었다. 회귀 가드: `app/analytics/new/chatSurfaceDesign.test.ts`

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
- 라틴 섹션 제목은 `uppercase tracking-widest` 적용. **한글 제목에는 적용하지 않는다** — `uppercase`는 한글에 아무 효과가 없고 `tracking-widest`는 가독성을 떨어뜨린다.
- 차트/지표/요약 카드의 제목성 텍스트는 가독성을 위해 `text-gray-400` 이상 밝기를 유지
- 긴 텍스트는 `truncate` 처리
- `leading-none` 또는 `leading-tight`로 줄 간격 최소화

### 소형 라벨(eyebrow) 배급제

`uppercase tracking-widest` 소형 라벨을 모든 블록 위에 붙이면 화면 전체가 같은 리듬으로 눌려 위계가 사라진다.

- 한 화면의 소형 라벨 수는 **섹션 수의 1/3 이하**로 제한한다.
- 라벨을 지우는 것이 기본이다. 위치가 이미 그 블록의 종류를 말해 준다.
- 위계는 라벨 대신 **크기·굵기·간격**으로 만든다.

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
    <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-500">
      {h}
    </span>
  ))}
</div>
{/* 헤더 구분선 */}
<div className="border-t border-white/[0.05] mb-1" />
```

- 컬럼 헤더 텍스트: `text-xs font-bold uppercase tracking-widest text-gray-500`
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

### 카드를 쓸 때 / 쓰지 않을 때

카드는 **위계를 전달할 때만** 쓴다. 모든 블록을 카드로 감싸면 아무것도 강조되지 않는다.

- 카드로 감쌀 것: 남아서 다시 참조되는 산출물(요약, 검증 결과, 공지, 오류)
- 카드 없이 둘 것: 흘러가는 텍스트, 상태 표시 → `border-l` 헤어라인 + 여백으로 묶는다
- 서로 다른 종류의 블록이 같은 카드 스타일을 공유하면 종류 구분이 사라진다. 표면을 분리한다.

## 6. 테두리 반경

**한 화면에서 반경 체계는 하나만 쓴다.** 아래 스케일을 벗어나면 레이아웃이 깨진 것처럼 보인다.

| 요소 | 클래스 |
|------|--------|
| 카드/패널/모달 | `rounded-2xl` |
| 버튼/입력/칩 | `rounded-xl` |
| 배지/라벨 | `rounded-md` |
| 차트 바 | `rounded-xl` |
| 입력 바(대화) | `rounded-[28px]` (pill, 대화 입력 바 전용) |

---

## 7. 그림자

```css
카드:           그림자 없음 (flat)
오버레이/모달:  shadow-2xl shadow-black/50
```

> §2 금지 스타일의 발광(glow) 금지와 일관되게, **버튼·카드·배지에 외곽 glow를 쓰지 않는다.**
> 이전 가이드는 §2에서 glow를 금지하면서 §7·§10에서 `0 0 15px rgba(59,130,246,0.4)` 버튼 glow를 규정해 서로 모순됐다(2026-07-25 해소).
> 그림자를 쓸 때는 배경 색조를 따라 틴트한다. 밝은 배경에 순검정 그림자를 쓰지 않는다.

---

## 8. 레이아웃 패턴

### 전체 높이

`100vh`를 쓰지 않는다. iOS Safari에서 주소창 높이 때문에 레이아웃이 튄다. `100dvh`를 쓴다.

```tsx
style={{ minHeight: "calc(100dvh - var(--top-menu-bar-height, 76px))" }}
```

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
        <Icon size={18} weight="bold" className="text-gray-500" />
        <span className="text-sm font-bold text-gray-500">{s.label}</span>
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

### 감속 설정(prefers-reduced-motion) 필수

- 반복(infinite) 애니메이션, 진입 연출, 스피너는 **반드시** `prefers-reduced-motion: reduce`에서 멈춘다.
- **연출을 인라인 `style={{ animation: ... }}`으로 넣지 않는다.** 인라인 선언은 CSS로 덮을 수 없어 감속 설정을 무시하게 된다. `globals.css`에 클래스로 정의하고 감속 블록에 함께 등록한다.
- Tailwind 유틸리티 애니메이션(`animate-spin` 등)은 `motion-reduce:animate-none`을 함께 붙인다.
- styled-jsx 스코프 클래스는 globals의 감속 규칙이 이기지 못하므로 같은 스코프 안에서 직접 끈다.
- 순서가 있는 진입 연출은 React 상태 타이머가 아니라 `animation-delay` 캐스케이드로 만든다(상태 타이머는 프레임마다 전체 리렌더를 유발한다).

### 애니메이션 대상

- `transform`과 `opacity`만 애니메이션한다. `top`/`left`/`width`/`height`는 쓰지 않는다.
- `blur` + `mix-blend-mode` 레이어를 스크롤·장시간 노출 요소에 겹치지 않는다(모바일 합성 비용).

### 보관 연출: 테두리 오로라(불꽃 발광) — 현재 미적용

> **§2 금지 스타일·§10 주요 버튼의 glow 금지와 충돌하므로 어디에도 적용하지 않는다.**
> 2026-07-25 전략연구소 백테스트 CTA에 시험 적용했다가 제거했다. 레시피만 보관한다.
> 다시 쓰려면 먼저 §2·§10의 glow 금지 조항에 예외를 명문화할 것.

버튼 테두리에서 하얗게 타오르는 빛. 원형 blob을 흩뿌리면 윤곽에서 어긋나 보이므로,
**버튼과 같은 실루엣을 바깥으로 키운 판 두 겹**을 blur한다. 반지름은 `버튼 반경 + 바깥 여백`
(rounded-xl 12px + 16px = 28px)으로 맞춰야 윤곽과 평행하게 번진다.
두 겹의 주기(4.6s / 3.1s)를 어긋내면 간섭이 생겨 불규칙하게 일렁인다 = 타는 느낌.
좌우 `translate`는 넣지 않는다(테두리에서 빛이 떨어져 나온다).

```css
@keyframes auroraFlameHalo {
  0%   { transform: scale3d(1, 1, 1);       opacity: 0.72; }
  30%  { transform: scale3d(1.04, 1.14, 1); opacity: 1; }
  55%  { transform: scale3d(1.01, 0.96, 1); opacity: 0.66; }
  80%  { transform: scale3d(1.05, 1.1, 1);  opacity: 0.95; }
  100% { transform: scale3d(1, 1, 1);       opacity: 0.72; }
}

@keyframes auroraFlameRim {
  0%   { transform: scale3d(1.01, 0.98, 1); opacity: 0.85; }
  35%  { transform: scale3d(0.99, 1.12, 1); opacity: 1; }
  60%  { transform: scale3d(1.04, 0.94, 1); opacity: 0.7; }
  85%  { transform: scale3d(1, 1.08, 1);    opacity: 0.98; }
  100% { transform: scale3d(1.01, 0.98, 1); opacity: 0.85; }
}

.aurora-cta {
  position: relative;
  display: inline-flex;
}

.aurora-cta::before,
.aurora-cta::after {
  content: "";
  position: absolute;
  pointer-events: none;
  will-change: transform, opacity;
}

/* 바깥으로 퍼지는 넓은 후광 */
.aurora-cta::before {
  inset: -16px;
  border-radius: 28px;               /* 12px(버튼) + 16px(여백) */
  background: rgba(255, 255, 255, 0.62);
  filter: blur(18px);
  animation: auroraFlameHalo 4.6s ease-in-out infinite;
}

/* 테두리에 딱 붙는 밝은 심지 */
.aurora-cta::after {
  inset: -5px;
  border-radius: 17px;               /* 12px + 5px */
  background: rgba(255, 255, 255, 0.95);
  filter: blur(7px);
  animation: auroraFlameRim 3.1s ease-in-out infinite;
}

/* 버튼을 빛 위로 올린다 — positioned 형제가 아니면 ::before/::after가 덮는다 */
.aurora-cta > * {
  position: relative;
  z-index: 1;
}

@media (prefers-reduced-motion: reduce) {
  .aurora-cta::before,
  .aurora-cta::after { animation: none; }
  /* 애니메이션을 끄면 opacity가 기본값 1로 돌아가 과하게 밝다 — 정적 값으로 고정 */
  .aurora-cta::before { opacity: 0.72; }
  .aurora-cta::after  { opacity: 0.85; }
}
```

```tsx
{/* 래퍼에 배경이 없어야 버튼 면은 그대로 두고 가장자리 바깥에만 번진다 */}
<span className="aurora-cta">
  <button className="rounded-xl bg-[var(--chat-accent)] ...">…</button>
</span>
```

주의할 점:

- 래퍼 없이 버튼 자신에게 `::before { z-index: -1 }`로 넣으면 안 된다. 음수 z-index 자식은
  요소의 **배경보다 위**에 그려져(CSS 페인팅 순서 3단계) 버튼 면을 뿌옇게 덮는다.
- `filter: blur`는 매 프레임 repaint를 부르므로 `transform`/`opacity`만 애니메이션하고
  `will-change: transform, opacity`로 레이어를 고정해 blur 결과를 캐시시킨다.
- 감속 설정에서 `animation: none`만 주면 opacity가 1로 복귀해 오히려 더 밝아진다.

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

강조색 단색 채움. 그라디언트와 glow는 쓰지 않는다. `:active`에 물리적 눌림을 준다.

```tsx
<button className="
  px-4 py-2 rounded-xl
  bg-[var(--chat-accent)] text-[var(--chat-accent-ink)]
  text-sm font-bold
  transition-colors duration-200
  hover:brightness-110
  active:translate-y-[1px]
  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--chat-accent)]/50
">
  버튼 텍스트
</button>
```

- 버튼 글자는 버튼 배경 대비 **4.5:1 이상**이어야 한다(흰 배경 + 흰 글자, 테두리 없는 투명 버튼 금지).
- 주 CTA 라벨은 데스크톱에서 **한 줄에 들어와야 한다**. 두 줄로 감기면 라벨을 줄인다.
- 같은 의도의 CTA를 한 화면에 두 개 두지 않는다(라벨 하나만 정해 전 화면에서 재사용).

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
    <span key={h} className="text-xs font-bold uppercase tracking-widest text-gray-500">
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

---

## 17. 대화 표면 위계 (전략연구소)

전략연구소 채팅은 한 화면에서 성격이 다른 블록 여섯 종류를 만든다. 표면을 셋으로 나눠 구분한다. 상수는 `app/analytics/new/page.tsx` 상단에 정의한다.

| 표면 | 상수 | 담는 것 |
|------|------|---------|
| 사용자 발화 | `USER_CHAT_BUBBLE_CLASS` | 우측 정렬 단색 카드(`--chat-user-surface`) |
| 대화 산문 | (표면 없음) | 어시스턴트 설명·로딩 상태, `현재까지 이해한 전략입니다`(빌더 요약). **카드도 레일도 없는 맨 텍스트** |
| 산출물 카드 | `ARTIFACT_CARD_CLASS` | 전략 요약, 전략 검증, 공지, 되묻기, 전략 확인 |
| 오류 카드 | (인라인) | `--error-red` 테두리. 의미색 |
| 선택 칩 | `CHOICE_CHIP_CLASS` | 면 값이 없다(`--chat-chip-surface: transparent`) — 담긴 면이 그대로 비쳐 버블·카드와 같은 색이 되고 **구분은 테두리가 한다**. 칩에 `--chat-surface`를 주면 카드(0.06) 위에서 알파가 겹쳐 0.12가 돼 칩만 밝아진다(2026-08-05 반려). 면이 없으므로 `.chat-glass`도 붙이지 않는다. 선택지는 `ChoiceOptionList`가 **세로 목록**으로 그리며 `chat-choice-rise`로 아래에서 위로 떠오른다. `직접 입력`은 목록 그 자리에서 인라인 입력창으로 바뀐다(하단 공용 입력창 재노출 방식 폐지) |
| 돌아가기 컨트롤 | `BACK_CONTROL_CLASS` | 되돌릴 길을 여는 컨트롤. 테두리·면·눌림으로 클릭 가능함을 알린다 |

> ⚠️ **탐색 컨트롤을 텍스트 색만으로 표시하지 않는다.** 강조색이 다른 역할에 예약돼 있으면 회색 텍스트로 남기기 쉬운데, 그러면 정적 캡션으로 읽혀 사용자가 되돌릴 길을 찾지 못한다(2026-07-25 '돌아가기' 제보). affordance는 색이 아니라 **테두리·면·`hover`·`active`·`focus-visible`**로 만든다.

- **세로 레일(`border-l`)은 어떤 색으로도 쓰지 않는다.** 산문은 카드가 없다는 사실 자체로 구분되고, 응답이 필요한 블록은 카드와 선택 칩으로 알린다. 오류 카드도 전체 테두리만 쓴다.
- **칩으로만 답하는 되묻기 카드는 화면 하단('대화 종료' 버튼이 있던 자리)에 고정한다(2026-08-05 지시).** `fixed bottom-4`, 폭은 하단 바와 같은 `max-w-4xl`, 길면 `max-h-[80dvh]` 안에서 스스로 스크롤한다. 고정 조건은 **입력 바가 숨는 동안**(`!shouldShowChatInput` + 칩 있음)뿐이다 — 입력 바가 보이는 되묻기까지 고정하면 같은 자리를 두고 겹친다. 고정하면 카드가 흐름에서 빠지므로 대화 하단 여백을 `pb-56` → `pb-[26rem]`로 함께 늘린다(마지막 메시지가 카드 뒤로 숨는 것을 막는 정적 예약, 고정 입력 바와 같은 방식).
- ⚠️ **고정본은 대화 트리 바깥(하단 입력 바와 같은 자리)에서 그린다.** 메시지 루프 안에서 `fixed`를 주면 화면 하단이 아니라 **화면 위쪽에 겹쳐 뜬다**(2026-08-05 실제 증상) — 진입 연출(`chat-enter`, `animation-fill-mode: both`)이 끝난 뒤에도 조상에 `transform: translate3d(0,0,0)`이 남아, 그 조상이 `position: fixed`의 고정 기준(containing block)이 되기 때문이다. 같은 카드를 두 자리에서 그리므로 렌더 함수 하나(`renderClarificationCard(msg, docked)`)를 공유한다.
- **고정된 옵션 카드 안 우하단에 '대화 종료'(`END_CHAT_CONTROL_CLASS`)를 둔다.** 카드가 하단을 덮으므로 화면에 독립적으로 떠 있던 종료 버튼은 카드 뒤로 가린다 — 그래서 카드가 고정된 동안에는 **바깥 버튼을 감추고 카드 안 버튼 하나만** 남긴다(어떤 옵션 카드에서도 대화를 끝낼 수 있어야 한다는 계약). 둘 다 그리면 같은 자리에 두 개가 겹친다.
- **옵션 카드만 불투명 면(`CLARIFICATION_CARD_CLASS`, `#101010`)을 쓴다.** 아래 "모든 박스가 한 값짜리 반투명 유리" 규칙의 유일한 예외다(2026-08-05 지시) — 화면 하단에 고정돼 뒤로 대화가 지나가므로, 반투명이면 지나가는 글자가 칩 위로 비쳐 읽기 어렵다. 불투명이라 `.chat-glass`도 붙이지 않는다(흐릴 배경이 없다).
- **되묻기 카드에는 아이콘을 두지 않는다(2026-08-05 지시).** 물음표 아이콘을 지우고 질문·`선택 예시`·칩을 카드 왼쪽 끝에 나란히 맞춘다 — 아이콘 자리를 비우려고 넣었던 `pl-6` 들여쓰기도 함께 없앤다. 질문임은 문장과 칩이 알린다.
- **강조색(`--chat-accent`)의 역할은 "사용자 차례 + 진행 상태" 하나로 고정한다.** 진행률 완료 표시, 로딩 스피너, 주 CTA, 링크까지 같은 색을 쓴다.
- 칩 문자열(`직접 입력`·`뒤로가기`·`돌아가기` 등)은 백엔드 답변 프로토콜의 일부다. **시각 작업에서 라벨 텍스트를 바꾸지 않는다** — 프론트·백엔드 동기화 지점이 4곳이다.
- 진행률 패널(`StrategyProgressPanel`)의 `xl:fixed` 우측 레일은 1280px 이상에서만 고정된다. 그 아래에서는 대화 흐름 상단 카드로 들어간다. **면은 없고 헤어라인 테두리 + `.chat-glass`만 쓴다**(2026-08-05 지시로 배경 삭제). 고정 패널이라 뒤로 채팅이 지나가므로 면이 없어도 블러는 남긴다 — 빼면 글자가 지나가는 대화 위에 겹쳐 읽히지 않는다.
- **유리 블러(`.chat-glass`)는 모든 박스가 같은 세기(12px)로 쓴다.** 페이지 배경이 균일한 검정이라 블러가 드러나는 곳은 박스끼리 겹칠 때(카드 위 칩)와 고정된 진행률 패널 뒤로 채팅이 지나갈 때뿐이다. 그래도 세기를 박스마다 다르게 두지 않는다. 배경에 빛/안개를 깔면 유리가 살아나지만 박스 위치별로 밝기가 달라져 사용자가 반려한 상태로 돌아간다 — 배경은 균일한 검정으로 유지한다(2026-08-05 선택).
- **면은 한 값짜리 반투명 유리다(`--chat-surface`).** 대화 화면의 **모든 박스**(사용자 버블·산출물 카드·오류 카드·선택 칩)가 같은 값을 쓴다. 예외는 위에 적은 둘뿐이다 — 하단에 고정되는 옵션 카드는 불투명(`#101010`), 진행률 패널은 면 없이 테두리만. 반투명이라 페이지 배경이 그대로 비치고, 칩처럼 카드 위에 얹힌 박스는 알파가 겹쳐 저절로 한 단 밝아진다 — 위치별로 값을 따로 맞추지 않는다.
- ⚠️ **면 안에서 밝기가 변하는 그라디언트를 쓰지 않는다.** 사용자 확정 사항이다(2026-08-05): "어디는 더 어둡고 어디는 더 밝고 그러는데 한 가지로 통일". 시안 3회를 거쳤다 — ① 흰빛 8.5% 그라디언트(세기 부족), ② 슬레이트 불투명 면(색이 다름), ③ 방향성 그라디언트(밝기 불균일). 셋 다 반려됐고 지금은 단일 값이다. `.chat-soft-surface` 클래스는 이때 삭제했다. 색(hue)도 넣지 않는다 — 강조색 단일화 잠금 그대로다.

회귀 가드: `app/analytics/new/chatSurfaceDesign.test.ts` (폰트 배선·감속 설정·강조색 단일화·100dvh·표면 분리)

---

## 18. 다국어(i18n) 표기 규칙 [2026-08-18]

- 사용자에게 보이는 모든 한국어 문자열은 `t("원문")`으로 감싼다 — JSX 텍스트·속성(placeholder/aria-label/title)·토스트·에러 메시지 모두. 원문이 곧 사전 키다(`lib/i18n/en.ts`).
- 값이 섞이면 템플릿 대신 자리표시자: `t("총 {0}회 거래", n)`. 인자로 넘기는 한국어 라벨도 감싼다: `t("{0} 리밸런싱", t(REBAL_LABELS[x]))`.
- **모듈 최상위 상수에서 `t()`를 부르지 않는다**(서버에서 첫 언어로 고정). 상수는 한국어 키로 두고 표시 지점에서 `{t(item.label)}`.
- **백엔드로 보내는 값은 감싸지 않는다**: 파서에 보내는 문장, 칩 문자열(결속 프로토콜), `=== "…"` 비교 대상. 칩은 목록에 한국어 정본을 두고 렌더에서만 `t(option)`.
- 날짜는 `toLocaleDateString(getLocale())`, 억·만·조 금액은 `formatCompactNumberEn()`을 먼저 시도(영어면 compact, 한국어면 null → 기존 표기).
- 새 문구를 추가하면 `lib/i18n/en.ts`에 영어를 함께 등재한다 — `tests/i18n-coverage.test.ts`가 누락을 막는다. 빠진 키는 `node scripts/i18n_extract_keys.js --missing`.
- KR/EN 토글은 상단 내비게이션 프로필 사진 왼쪽 한 곳뿐이다(`LanguageToggle`).

## 체크리스트

새 페이지/컴포넌트 작성 시 확인:

- [ ] 독립 패널은 `flat-card p-5 h-full`, 행 단위 컴포넌트는 `flat-card` 없이 `flex divide-x` 또는 `grid` 직접 사용
- [ ] 페이지 루트에 `border border-white/[0.08]` + 내부 `divide-y divide-white/[0.08]` 구조 적용
- [ ] 섹션 제목에 `text-base font-black uppercase tracking-widest font-outfit` 적용
- [ ] 숫자 수치에 `tabular-nums font-outfit` 적용
- [ ] 상태 색상에 CSS 커스텀 속성(`var(--main-red)` 등) 사용
- [ ] 테이블은 div 그리드 기반, 컬럼 헤더 `text-gray-500`, 행 `divide-y divide-white/[0.04]` + `hover:bg-white/[0.02] rounded-xl`
- [ ] 아이콘은 `phosphor-react` 사용
- [ ] `transition-colors duration-150` 행 호버 처리
- [ ] 로딩 상태에 `animate-pulse` 스켈레톤 구현
- [ ] `truncate` + `min-w-0` 텍스트 오버플로우 방지
- [ ] 반응형: 모바일(`grid-cols-1`) → 데스크톱(`lg:grid-cols-10`) 순서
- [ ] 장식용 강조색이 하나뿐인가 (의미색 `--main-red`/`--main-blue`/`--error-red`를 강조에 전용하지 않았는가)
- [ ] 반경 체계가 하나인가 (카드 `rounded-2xl` / 컨트롤 `rounded-xl` / 배지 `rounded-md`)
- [ ] 버튼·카드에 외곽 glow가 없는가, 버튼 글자 대비가 4.5:1 이상인가
- [ ] 라벨·placeholder 대비가 AA를 넘는가 (`text-gray-500`·`placeholder-gray-600` 미달)
- [ ] 소형 라벨(eyebrow) 수가 섹션 수의 1/3 이하인가, 한글에 `uppercase tracking-widest`를 쓰지 않았는가
- [ ] 모든 반복·진입 애니메이션이 `prefers-reduced-motion`에서 멈추는가, 연출을 인라인 `style`에 넣지 않았는가
- [ ] 전체 높이에 `100vh` 대신 `100dvh`를 썼는가
- [ ] 카드가 위계를 전달하는가 (흘러가는 텍스트를 카드로 감싸지 않았는가)
