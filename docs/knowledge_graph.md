# Investment Knowledge Graph (IKG) 설계 (FR-STR-070)

투자 개념·산업·공급망·기업·ETF·재무지표·거시경제를 **노드(Node)와 관계(Edge)** 로 잇는
지식 그래프. 목표는 단순 용어집이 아니라, 사용자가 어떤 자연어를 입력해도 의미를
이해하고 관련 지식을 연결해 **백테스트 가능한 유니버스**까지 이어지는 핵심 인프라다.

새로운 개념이 등장해도 기존 그래프를 수정하지 않고 노드·엣지 추가만으로 성장한다.

```
개념(HBM) → 산업(반도체) → 테마(AI/데이터센터) → 공급망(장비·소재)
  → 기업(SK하이닉스·한미반도체) → ETF(KODEX 반도체) → 지표(CAPEX)
  → 매크로(메모리 가격·AI 투자 확대) → 백테스트 유니버스
```

## 규제 안전 원칙

그래프는 **객관적 관계 데이터**(생산·공급·소속·영향)만 저장·표시한다.
- 허용: "한미반도체는 HBM 조립장비(TC본더)를 생산한다"(사실 관계), 관계 근거(via) 표시
- 금지: 추천·전망·우열을 표현하는 노드/엣지(예: `recommended`, `promising` 류),
  "관련주이므로 유망하다" 같은 서술. CLAUDE.md 규제 안전 원칙이 그래프 데이터에도 적용된다.

## 아키텍처 (Phase 1 — 구현됨)

### 저장소: 정본 재사용 + 시드 + 학습 오버레이

그래프는 별도 DB 없이 **로드 시 합성**된다(`engine/knowledge_graph.py::get_graph`,
파일 mtime 기반 캐시). 정본을 손으로 두 번 적지 않는다.

| 소스 | 노드 id | 생성 방식 |
|---|---|---|
| `data/knowledge-graph.json` | `hbm`, `smr`, … | git 추적 시드 — 수동 큐레이션(개념·테마·지표·매크로·상품). 확장은 Concept–Stock Builder 절차(`docs/kg_concept_builder.md`)로 — 조사 원장은 `data/kg-research/`, Core/Strong 관계만 시드 편입 |
| `universe_pit.CANONICAL_SECTORS` | `sector:반도체` | 39개 정본 섹터 자동 생성 |
| `data/korea-stocks.json` | `company:000660` | 엣지가 참조할 때만 자동 생성(심볼 검증) |
| `data/etf-master.json` | `etf:091160` | 엣지가 참조할 때만 자동 생성(심볼 검증) |
| `data/term_lexicon.json` (FR-STR-069) | `learned:폐배터리` | 검색 그라운딩 학습 항목을 오버레이 편입 + `belongs_to` 섹터 엣지 |

**무결성**: 엣지 끝점·타입은 로드 시 검증되고(`issues` 채널), 시드 무결성 테스트
(`test_knowledge_graph.py::test_seed_integrity_no_issues`)가 위반 0을 단언한다 —
오타 심볼·미지원 엣지 타입은 CI에서 잡힌다.

### 노드 스키마

```json
{"id": "hbm", "name": "HBM", "name_en": "High Bandwidth Memory",
 "category": "technology", "synonyms": ["고대역폭 메모리", "HBM3E"],
 "description": "D램을 수직 적층해 대역폭을 높인 메모리"}
```

카테고리: `concept`(개념) / `technology`(기술) / `theme`(테마) / `industry`(섹터 자동) /
`company` / `etf` / `metric`(재무지표) / `macro`(거시·수요동인) / `commodity`(원자재) /
`learned`(검색 학습). 비전의 중요도·신뢰도·검증일 필드는 학습 노드의
`sources`/`searched_at`(term_lexicon)로만 우선 커버한다(YAGNI — 필요 시 확장).

### 관계(Edge) 어휘

`is_a` `part_of` `belongs_to` `related_to` `uses` `used_by` `used_in` `requires`
`depends_on` `supplier` `customer` `competitor` `produced_by` `manufactured_by`
`demanded_by` `invests_in` `related_company` `related_etf` `related_metric`
`related_macro` `related_news` `related_universe` `cause` `affected_by`
`benefits_from` `risk_factor` `substitute` `next_generation` `predecessor` `successor`

엣지는 선택 필드 `note`로 관계의 사실 근거를 담을 수 있다(예: 한미반도체 — "TC본더 등
HBM 조립장비"). 동일 개념은 하나의 노드로 통합하고 표기 변형은 `synonyms`로 담는다
(HBM = High Bandwidth Memory = 고대역폭 메모리).

### 결정적 개념 인식 (`find_concepts`)

- 스캔 대상은 **시드 개념 노드의 이름·별칭만** — 자동 생성 노드(섹터/기업/ETF)와 학습
  노드는 각자 기존 경로(섹터 정규화·종목 인식·어휘집 스캔)가 담당한다.
- `normalize_sector`가 이미 해석하는 용어(AI·인공지능·원자력·방산 등)는 인덱스에서
  **자동 제외** — 상류의 결정적 섹터 어휘와 이중 매칭돼 어긋나는 일을 구조적으로 막는다.
- 라틴 약어(hbm·smr)는 라틴 문자 lookaround 경계 매칭('progress'의 'ess' 오매칭 방지,
  term_grounding·condition_builder와 동일 관례). 긴 용어 우선 매칭.

### 섹터 해석 — FR-STR-069 체인의 ①b 단계

빌더 업종 해석 체인: **어휘집 → ①b 지식그래프 → 내부 지식 LLM → 검색 그라운딩**.

- 개념에서 **소속 엣지(`is_a`/`part_of`/`belongs_to`)만** 깊이 3까지 순방향 탐색해
  `sector:*` 노드에 닿으면 즉시 반환. 예: "SMR 관련 투자" → smr –is_a→ 원자력
  –part_of→ 에너지/원자력 (LLM·검색 없이 0ms).
- **모호하면 None**(기존 되묻기/LLM 폴백 유지): 서로 다른 섹터 둘 이상에 닿는 경우
  ("HBM이랑 SMR"), 데이터센터처럼 의도적으로 다업종인 테마(시드에 소속 엣지를 두지 않음).

### 관계 확장 (`related_universe`)

개념 주변을 BFS(기본 깊이 2)로 펼쳐 `sectors` / `companies` / `etfs` / `concepts`
버킷으로 반환한다. 각 항목은 도달 경로(`via`)를 가진다:

```
"HBM 관련주" → concept=HBM
  companies: SK하이닉스(000660, HBM –produced_by→), 한미반도체(042700, –supplier→), …
  sectors:   반도체
  etfs:      KODEX 반도체(091160), TIGER 반도체TOP10(396500)
  concepts:  GPU, 메모리 반도체, 데이터센터(2단계), CAPEX, 메모리 가격
```

이 결과는 백테스트 유니버스 후보의 **객관적 관계 데이터**다(추천 아님). Phase 1에서는
백엔드 API로만 존재하며 라우트/UI 배선은 Phase 2.

### 그래프 확장(성장)

- **자동(구현됨)**: FR-STR-069 검색 그라운딩이 새 용어를 학습하면 term_lexicon에
  저장되고, 그래프가 이를 오버레이로 편입한다(`learned:*` 노드 + `belongs_to` 엣지) —
  검색 학습이 곧 그래프 성장이다. 시드·어휘집 파일 변경은 mtime으로 감지해 자동 재로드.
- **수동**: 시드 JSON에 노드·엣지 추가(무결성 테스트가 오타를 잡는다). 노드만 추가하는
  것은 금지 — 반드시 엣지도 함께 추가한다(고아 노드는 탐색에 잡히지 않는다).

## Phase 2/3 로드맵

- **Phase 2 — 유니버스 생성 배선** ✅ 파서 경로 구현됨(2026-07-25):
  `detect_theme_universe_clarification`(nl_parser)이 기존 깊이 1 되묻기에 더해
  `related_universe` 깊이 2가 공급망·인프라 상장사에 닿으면 **세 번째 칩**(확장 종목
  전체 나열, 상한 15)을 추가한다 — 질문 본문에 관계 근거(via의 중간 개념: "HD현대
  일렉트릭(전력기기)")를 요약 표시하고, 칩은 FR-STR-071 프로토콜(종목명 나열+'종목
  전체를 함께', TARGET 가드 단어 금지) 그대로 재파싱된다. 확장이 없는 개념(HBM처럼
  직접 연결이 전부)은 기존 2칩 유지. 테스트 `test_theme_universe_expansion.py`.
  **잔여**: 빌더 되묻기(`_theme_reask_prompt`) 배선은 동시 진행 중인 복수 업종 작업과
  파일 충돌을 피해 보류, ETF 테마 매칭(FR-STR-067)에 `related_etf` 엣지 활용도 미배선.
- **성능 실측 하니스**(2026-07-25): `scripts/qa_kg_concept_hits.py` — judal 테마명+시드
  용어 코퍼스(492개, "{용어} 관련주" 템플릿)로 ①결정적 인식 ②섹터 해석 ③종목 목록
  3지표를 git 이력 시드와 A/B 측정. 감사 전(45노드)→현재(84노드): 인식 74.4→93.5%,
  섹터 해석 23.0→41.9%, 종목 목록 63.6→83.7%. 시드 히트가 156→297로 늘며 미검증
  카탈로그 히트 47건이 검증 시드로 승격됨. (주의: 코퍼스에 현재 시드 동의어가 포함돼
  수치가 현재 쪽에 다소 유리한 편향 — 동일 코퍼스 고정 비교라 추세는 유효.)
- ~~**Phase 2 — 검색 그라운딩의 엣지 학습**~~ ✅ 구현됨(FR-STR-070b, 2026-07-25):
  `term_grounding._propose_edges` — 후보 앵커는 스니펫에 실제 등장한 시드 개념만
  결정적 수집(닫힌 세계), LLM은 목록 안에서 관계 유형만 선택(객관적 서브셋 7종).
  출처 교차지지 ≥2 자동 verified / 1개 pending, 로더는 verified만 합성. 운영 콘솔
  Knowledge 탭에서 사후 반려·수동 승인·용어 삭제(`/api/admin/knowledge`). 학습분은
  어휘집 엔트리(`edges`)에 저장 — git 시드에는 쓰지 않음(출처 분리). 기업 심볼
  타깃(supplier/produced_by → company:)은 향후 확장 시 korea-stocks 정본 게이트 필수.
- **Phase 3 — 뉴스·매크로 연결**: news_v2 감성 키워드 ↔ `related_news` 엣지,
  매크로 노드(금리·환율)와 백테스트 구간 통계의 객관적 연결 표시.

## 산출물

- 엔진: `backend/engine/knowledge_graph.py`
- 시드: `data/knowledge-graph.json` (개념 30노드 + 관계 100여 엣지 — HBM 공급망,
  전력기기/AI 전력 수요, 원자력/SMR, ESS/양극재, 휴머노이드 로봇, 바이오시밀러/CDMO,
  LNG/조선, 섹터 수준 ETF·매크로 엣지)
- 체인 배선: `engine/term_grounding.py::resolve_sector` ①b
- 테스트: `backend/tests/test_knowledge_graph.py` (무결성·스캔 규칙·섹터 해석·확장·
  학습 오버레이·체인 단락)
