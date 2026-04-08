# Simons UI 가이드라인

> 기준: 대시보드 페이지 (`app/page.tsx`) 및 `components/dashboard/`
> 새 페이지/컴포넌트 작성 시 이 가이드라인을 준수한다.

---

## 1. 디자인 시스템 개요

**Dark Glass Morphism** 기반의 다크 테마 UI.

- 배경: 깊은 검정색 (`#0f0f0f`)
- 카드: 반투명 유리 효과 (`glass-card` 클래스)
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

### 통계 지표 색상 규칙

- 통계 지표는 `지표 종류별`로 색을 다르게 주지 않는다.
- 색상은 `상태 의미`가 있는 경우에만 사용한다.
- 수익/손실, 상승/하락처럼 방향성이 명확한 값만 상태 색상을 사용한다.
- `손익비`, `매매횟수`, `소요시간`처럼 중립 지표는 기본 텍스트 색상(`text-white`, `text-gray-200`)을 사용한다.
- `점수`처럼 등급 해석이 필요한 값은 사전에 정의된 기준에 따라 단계형 색상을 사용한다.
- 위계 구분은 색상보다 크기, 굵기, 간격을 우선한다.
- 한 줄 통계 요약이나 카드 내 메트릭 리스트처럼 여러 지표를 동시에 보여주는 구간에서는 값 색상을 기본적으로 하나의 중립 톤으로 통일한다.
- 여러 칸에 상태 색상을 동시에 적용해 시선을 분산시키지 않는다.

### 상태별 색상 배지

```
KOSPI:    bg-sky-500/15     text-sky-400
KOSPI200: bg-indigo-500/15  text-indigo-400
KOSDAQ:   bg-purple-500/15  text-purple-400
미국주식:  bg-emerald-500/15 text-emerald-400
```

### 금지 스타일

- 네온 아웃라인 UI는 사용하지 않는다.
- 버튼, 탭, 배지, 카드 등 주요 UI 요소에 고채도 네온 테두리, 과도한 외곽선 강조, 사이버펑크식 발광(glow) 효과를 적용하지 않는다.
- 강조가 필요한 경우에는 네온 효과 대신 색상 대비, 면 처리, 타이포그래피, 간격 체계로 해결한다.

---

## 3. 타이포그래피

### 폰트 패밀리

- 기본: `Arial, Helvetica, sans-serif`
- 숫자/수치 표시: `font-outfit` (커스텀 Tailwind 클래스)

### 텍스트 스타일 계층

| 계층 | 크기 | 굵기 | 추가 클래스 | 용도 |
|------|------|------|-------------|------|
| 섹션 제목 | `text-base` | `font-black` | `uppercase tracking-widest` | 카드 헤더 |
| 주요 수치 | `text-2xl` ~ `text-3xl` | `font-black` | `tabular-nums` | KPI, 핵심 지표 |
| 보조 수치 | `text-xl` | `font-black` | `tabular-nums` | 서브 지표 |
| 리스트 항목 | `text-sm` | `font-bold` | `truncate` | 테이블 행 |
| 라벨/배지 | `text-xs` | `font-bold` | `uppercase` | 태그, 상태 표시 |
| 캡션/보조 | `text-[10px]` ~ `text-xs` | `font-bold` | — | 단위, 날짜 |

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
p-4 md:p-5 lg:p-6   (반응형 페이지 패딩)
space-y-5            (섹션 간 세로 간격)
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
| 섹션 간 카드 | `gap-6` |
| 카드 그룹 내부 | `gap-4` |
| 소형 카드 그룹 | `gap-3` |
| 아이콘-텍스트 | `gap-2`, `gap-1.5` |
| 밀착 항목 | `gap-1` |

---

## 5. 카드 & 패널

### glass-card (기본 카드)

모든 카드/패널의 기본 단위. `globals.css`에 정의된 유틸리티 클래스.

```css
.glass-card {
  background: var(--card-bg);       /* rgb(22,22,22) */
  backdrop-filter: blur(24px);
  border: 1px solid var(--card-border);  /* rgba(255,255,255,0.05) */
  border-radius: 1rem;              /* rounded-2xl */
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  transition: all 500ms;
  overflow: hidden;
  position: relative;
}

.glass-card::before {
  /* 상단 하이라이트 그래디언트 */
  background: linear-gradient(from-white/[0.05] to-transparent);
}

.glass-card:hover {
  border-color: rgba(255,255,255,0.1);
}
```

**사용법:**
```tsx
<div className="glass-card p-5 h-full">
  {/* 내용 */}
</div>
```

### 구분선

```tsx
<div className="border-t border-white/[0.05]" />
```

### 카드형 테이블

- 분석 리스트, 종목 분석, 매매 기록, 월별 수익률처럼 행 단위 정보가 많은 표는 `overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0f0f10]` 같은 외곽 카드로 감싼다.
- 헤더는 `sticky top-0 z-10`을 사용해 고정할 수 있다.
- 첫 번째 헤더 셀은 `rounded-tl-2xl`, 마지막 헤더 셀은 `rounded-tr-2xl`을 사용해 외곽만 부드럽게 만든다.
- 행 내부는 과한 테두리 대신 `border-b border-white/[0.03]`와 `hover:bg-white/[0.02]`로 구분한다.
- 카드형 테이블은 표 본문보다 외곽 라운드와 여백을 우선하고, 셀마다 별도 라운드는 넣지 않는다.
- 같은 화면 안에 있는 표들은 가능한 한 동일한 외곽, 헤더 높이, 행 간격을 공유한다.

---

## 6. 테두리 반경

| 요소 | 클래스 |
|------|--------|
| 카드/패널 | `rounded-2xl` |
| 버튼/입력 | `rounded-xl` |
| 배지/라벨 | `rounded-md` |
| 차트 바 | `rounded-lg` |

---

## 7. 그림자

```css
카드:     box-shadow: 0 8px 32px rgba(0,0,0,0.3)
활성 바:  box-shadow: 0 4px 16px rgba({color},0.40)
버튼 호버: box-shadow: 0 0 15px rgba(59,130,246,0.4)
```

---

## 8. 레이아웃 패턴

### 페이지 기본 구조

```tsx
<div className="p-4 md:p-5 lg:p-6 space-y-5 w-full min-w-0">
  {/* 섹션들 */}
</div>
```

### 2컬럼 비대칭 그리드 (6:4 비율)

```tsx
<div className="grid grid-cols-1 lg:grid-cols-10 gap-6">
  <div className="lg:col-span-6">{/* 메인 */}</div>
  <div className="lg:col-span-4">{/* 서브 */}</div>
</div>
```

### 균등 분할 카드 그룹

```tsx
{/* 4개 균등 */}
<div className="flex gap-4">
  {items.map(item => <div key={item.id} className="flex-1 glass-card p-4" />)}
</div>

{/* 3컬럼 → 6컬럼 반응형 */}
<div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
  {/* 아이템 */}
</div>
```

### 카드 헤더 패턴

```tsx
<div className="flex items-center justify-between mb-4">
  <span className="text-base font-black uppercase tracking-widest text-white">
    섹션 제목
  </span>
  <button className="text-xs font-bold text-gray-500 hover:text-gray-300 transition-colors">
    더 보기
  </button>
</div>
```

### 아이콘 + 텍스트 패턴

```tsx
<div className="flex items-center gap-2">
  <IconComponent className="w-4 h-4 text-gray-500" />
  <span className="text-xs font-bold text-gray-500 uppercase tracking-widest">
    라벨
  </span>
</div>
```

### KPI 수치 표시 패턴

```tsx
<div className="flex flex-col gap-1">
  {/* 라벨 */}
  <div className="flex items-center gap-1.5 text-gray-500">
    <IconComponent className="w-3.5 h-3.5" />
    <span className="text-xs font-bold uppercase tracking-widest">항목명</span>
  </div>
  {/* 수치 */}
  <span className="text-2xl font-black text-white tabular-nums leading-none">
    1,234,567
  </span>
  {/* 보조 정보 */}
  <span className="text-xs font-bold text-gray-500">단위 또는 설명</span>
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
transition-all duration-500    (glass-card 전환)
transition-colors duration-200 (텍스트 색상 변화)
```

### 로딩 상태

```tsx
{/* 스켈레톤 */}
<div className="animate-pulse bg-white/[0.04] rounded-xl h-8 w-24" />

{/* Shimmer */}
<div className="shimmer rounded-xl h-8 w-24" />
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
```

### 아이콘 버튼

```tsx
<button className="
  p-1.5 rounded-lg
  text-gray-500 hover:text-gray-300
  hover:bg-white/10
  transition-all duration-200
">
  <IconComponent className="w-4 h-4" />
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
  <TrashIcon className="w-4 h-4" />
</button>
```

---

## 11. 배지 & 태그

```tsx
{/* 상태 배지 */}
<span className="
  px-2 py-0.5 rounded-md
  text-xs font-bold
  bg-sky-500/15 text-sky-400
">
  KOSPI
</span>

{/* 수치 변화 배지 */}
<span className={`
  text-xs font-bold tabular-nums
  ${isPositive ? 'text-[var(--main-red)]' : 'text-[var(--main-blue)]'}
`}>
  {isPositive ? '+' : ''}{value}%
</span>
```

---

## 12. 테이블 / 리스트

### 그리드 기반 테이블

```tsx
{/* 헤더 */}
<div className="grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-x-4 px-3 pb-2 border-b border-white/[0.05]">
  <span className="text-[10px] font-bold text-gray-600 uppercase">항목</span>
  <span className="text-[10px] font-bold text-gray-600 uppercase text-right">값1</span>
  {/* ... */}
</div>

{/* 행 */}
<div className="
  grid grid-cols-[minmax(0,1fr)_80px_120px_110px] gap-x-4
  px-3 py-2.5
  hover:bg-white/[0.02]
  transition-colors duration-150
  cursor-pointer
">
  {/* 셀 내용 */}
</div>
```

### 스크롤 컨테이너

```tsx
<div className="overflow-y-auto max-h-64 scrollbar-hide space-y-1">
  {/* 항목들 */}
</div>
```

---

## 13. 반응형 설계

모바일 우선(Mobile-First) 접근.

| 브레이크포인트 | 패딩 | 그리드 |
|---------------|------|--------|
| 기본 (모바일) | `p-4` | `grid-cols-1` |
| `sm` (≥640px) | — | `sm:grid-cols-3`, `sm:grid-cols-6` |
| `md` (≥768px) | `md:p-5` | — |
| `lg` (≥1024px) | `lg:p-6` | `lg:grid-cols-10`, `lg:col-span-6/4` |

---

## 14. 아이콘

- 라이브러리: `lucide-react`
- 기본 크기: `w-4 h-4` (일반), `w-3.5 h-3.5` (소형), `w-5 h-5` (대형)
- 색상: `text-gray-500` (기본), 컨텍스트에 따라 상태 색상 적용

---

## 15. 빈 상태 & 에러 상태

```tsx
{/* 빈 상태 */}
<div className="flex flex-col items-center justify-center h-full gap-3 py-8">
  <IconComponent className="w-8 h-8 text-gray-700" />
  <p className="text-sm font-bold text-gray-600">데이터가 없습니다</p>
</div>

{/* 로딩 스켈레톤 */}
<div className="animate-pulse space-y-3">
  <div className="h-4 bg-white/[0.04] rounded-lg w-3/4" />
  <div className="h-4 bg-white/[0.04] rounded-lg w-1/2" />
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

스크롤바 숨기기: `scrollbar-hide` 클래스 사용

---

## 체크리스트

새 페이지/컴포넌트 작성 시 확인:

- [ ] `glass-card` 클래스로 카드 구성
- [ ] 페이지 루트에 `p-4 md:p-5 lg:p-6 space-y-5` 적용
- [ ] 섹션 제목에 `text-base font-black uppercase tracking-widest` 적용
- [ ] 숫자 수치에 `tabular-nums` 적용
- [ ] 상태 색상에 CSS 커스텀 속성(`var(--main-red)` 등) 사용
- [ ] `transition-all duration-300` 호버 상태 처리
- [ ] 로딩 상태에 `animate-pulse` 스켈레톤 구현
- [ ] `truncate` + `min-w-0` 텍스트 오버플로우 방지
- [ ] 반응형: 모바일(`grid-cols-1`) → 데스크톱(`lg:grid-cols-10`) 순서
