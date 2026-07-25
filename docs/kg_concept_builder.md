# Concept–Stock Knowledge Builder (IKG 시드 확장 절차)

지식그래프(FR-STR-070) 시드를 **공식 근거 기반 조사**로 확장하는 운영 절차. 2026-07-25 첫 실행
(전고체 배터리·비만치료제)에서 확립된 규약이며, 아래 원문 프롬프트가 조사 방법론의 SOT다.

## 저장 규약 (코드 변경 없이 기존 로더 계약 재사용)

| 산출물 | 위치 | 내용 |
| --- | --- | --- |
| 조사 원장(dossier) | `data/kg-research/<concept-id>.json` | 프롬프트 §10 전체 JSON — 정의·ETF·전 후보 종목·관계유형·관련도 점수·출처·근거·제외 사유. git 추적(증거 원장) |
| 시드 그래프 | `data/knowledge-graph.json` | **Core/Strong 관계만** 편입. Moderate/Weak/Unverified는 원장에만 남긴다(기본 Backtest Universe 제외 원칙, §11) |

관계 유형 → 기존 `EDGE_TYPES` 매핑: Producer→`produced_by`, Supplier→`supplier`,
Customer→`customer`, Infrastructure/Related→`related_company`(또는 `related_to`),
Investor→`invests_in`, ETF→`related_etf`. 점수·출처 요약은 엣지 `note`에 한 줄로 남긴다.

## 편입 전 필수 가드 (실행 체크리스트)

1. **정본 존재 확인**: 종목은 `korea-stocks.json`, ETF는 `etf-master.json`에 심볼이 있어야
   한다(시드 로더가 fail-fast — 없는 심볼은 issues로 잡혀 무결성 테스트가 깨진다).
2. **섹터 어휘 충돌**: 새 노드 이름·동의어를 `normalize_sector`로 확인 — 이미 해석되는
   용어는 스캔 인덱스에서 자동 제외되므로 개념 인식이 무력화된다.
3. **학습 원장·테스트 용어 충돌**: `term_lexicon.json`의 학습 용어와 grounding 테스트
   (`test_term_grounding.py`)가 쓰는 용어(예: 마운자로·위고비·**폐배터리**)는 시드 동의어로
   넣지 않는다 — 시드가 학습을 덮어써(시드 우선) 학습 경로가 죽는다. 개별 약품명·상품명은
   학습 경로(FR-STR-069)에 맡기고 시드에는 개념·기술 명칭만 둔다. 실측(2026-07-25 2차 배치):
   `battery-recycling` 동의어에 '폐배터리'를 넣자 grounding 테스트 5건이 즉시 실패(시드가
   결정적 해석을 가로챔) — 동의어 제거로 해소. 편입 전 `grep <동의어> tests/test_term_grounding.py` 권장.
4. **검증**: `pytest tests/test_knowledge_graph.py tests/test_term_grounding.py` +
   `resolve_sector_from_text`/`theme_listed_companies` 스모크 후 전체 스위트.

## 처리 이력

| Concept | 원장 | 시드 편입(Core/Strong) | 일자 |
| --- | --- | --- | --- |
| 전고체 배터리 (`solid-state-battery`) | `data/kg-research/solid-state-battery.json` | 삼성SDI(Producer/Core)·이수스페셜티케미컬(Supplier/Core), ETF 0005D0·0209D0 | 2026-07-25 |
| 비만치료제 (`obesity-drug`) | `data/kg-research/obesity-drug.json` | 한미약품(Producer/Core)·펩트론(Supplier/Strong)·디앤디파마텍(Supplier/Strong), ETF 476070·476690·476310 | 2026-07-25 |
| 유리기판 (`glass-substrate`) | `data/kg-research/glass-substrate.json` | SKC(Producer/Core 88, 앱솔릭스)·삼성전기(Producer/Strong 78, CES 공식화·세종 파일럿). 필옵틱스·HB테크는 Moderate(수주 공시 미확인) | 2026-07-25 |
| 액침냉각 (`immersion-cooling`) | `data/kg-research/immersion-cooling.json` | **기업 엣지 0** — GST·케이엔솔 모두 Moderate(개발·협력 단계, 매출 미확인). 노드+used_in 데이터센터만 편입(억지 추가 금지 원칙 실적용) | 2026-07-25 |
| 폐배터리 리사이클링 (`battery-recycling`) | `data/kg-research/battery-recycling.json` | 성일하이텍(Producer/Core 92, 일관공정 주력)·새빗켐(Producer/Core 85, 재활용 매출 과반), ETF 446700. 동의어 '폐배터리'는 테스트 충돌로 제외 | 2026-07-25 |
| 우주발사체 (`space-launch-vehicle`) | `data/kg-research/space-launch-vehicle.json` | 한화에어로스페이스(Producer/Core 90, 누리호 체계종합·기술이전 2,400억)·이노스페이스(Producer/Core 92, 한빛 첫 상업발사), ETF 0207G0. 쎄트렉아이·컨텍은 위성/지상국 별개 Concept로 제외 | 2026-07-25 |
| 탄소배출권 (`carbon-credit`) | `data/kg-research/carbon-credit.json` | 에코아이(Producer/Core 95, 배출권 창출·판매 주력 — KIND 사업보고서). 무소속 개념(part_of 없음), 배출권 ETN은 정본 밖이라 ETF 미연결 | 2026-07-25 |
| 전력반도체 (`power-semiconductor`) | `data/kg-research/power-semiconductor.json` | DB하이텍(Producer/Core 89, 매출 비중 70%)·KEC(Strong 73)·아이에이(Strong 68, 자회사 트리노테크놀로지 SiC). 동의어에 SiC·GaN 포함 | 2026-07-25 |
| CXL (`cxl`) | `data/kg-research/cxl.json` | 삼성전자·SK하이닉스(Producer/Strong 72, CMM 양산)·네오셈(Supplier/Strong 75, 세계 최초 검사장비·삼성 납품). 오킨스전자는 Moderate | 2026-07-25 |
| 온디바이스 AI (`on-device-ai`) | `data/kg-research/on-device-ai.json` | 오픈엣지테크놀로지(Producer/Core 87, 엣지 AI 설계 IP 주력)·칩스앤미디어(Strong 70). 다업종 — part_of 없음(related_to AI만) | 2026-07-25 |
| AI 에이전트 (`ai-agent`) | `data/kg-research/ai-agent.json` | 솔트룩스(Producer/Strong 72, '구버' 100만·루시아 LLM). is_a AI로 소프트웨어/플랫폼 해석(깊이 2 체인) | 2026-07-25 |
| 양자컴퓨터 (`quantum-computing`) | `data/kg-research/quantum-computing.json` | **기업 엣지 0** — 핵심 기업 SDT 비상장(상장 시 재조사), 상장 테마주는 양자내성암호 인접 분야로 근거 미확인. 노드만 편입 | 2026-07-25 |
| 인공위성 (`satellite`) | `data/kg-research/satellite.json` | 쎄트렉아이(Core 92, KAIST 공급계약 공시)·인텔리안테크(Core 85, 위성 안테나 세계 1위)·AP위성(Strong 72), ETF 0207G0. '위성' 단독은 섹터 어휘라 동의어 제외(가드 ②) | 2026-07-25 |
| 마이크로바이옴 (`microbiome`) | `data/kg-research/microbiome.json` | CJ 바이오사이언스(Core 88)·쎌바이오텍(Core 85, DUOLAC 프로바이오틱스)·고바이오랩(Strong 68). 지놈앤컴퍼니는 전략 전환으로 Moderate | 2026-07-25 |
| 배터리 분리막 (`battery-separator`) | `data/kg-research/battery-separator.json` | SK아이이테크놀로지(Core 95, LiBS 주력·FCW 매각)·더블유씨피(Core 90, 분리막 전업 점유율 2위), ETF 462010·461950. '분리막' 단독은 섹터 어휘라 동의어 제외(가드 ②) | 2026-07-25 |
| 음극재 (`anode-material`) | `data/kg-research/anode-material.json` | 포스코퓨처엠(Core 90, 국내 유일 흑연계 양산·인조흑연 1조 수주)·대주전자재료(Core 90, 실리콘 음극재 세계 최초 상용화). 노드명 '음극재'는 섹터 어휘라 스캔 제외되나 앵커 유효('양극재' 전례) | 2026-07-25 |
| 수소연료전지 (`hydrogen-fuel-cell`) | `data/kg-research/hydrogen-fuel-cell.json` | 두산퓨얼셀(Core 95, 발전용 주기기 75%+유지보수 25%)·범한퓨얼셀(Core 88, 연료전지 매출 77%·잠수함 독점)·일진하이솔루스(Supplier/Strong 76, Type4 탱크 넥쏘 전량), ETF 367770·419650. '수소'는 섹터 어휘·'그린수소'는 테스트 용어라 동의어 제외. 288620은 정본명 '에스프리즘'(구 에스퓨얼셀 추정) — Unverified 원장만 | 2026-07-25 |
| 의료 AI (`medical-ai`) | `data/kg-research/medical-ai.json` | 루닛(Core 93, 인사이트·스코프 전업 해외 97%)·뷰노(Core 90, 딥카스 매출 74%)·제이엘케이(Core 85, 뇌졸중 FDA 5종), ETF 483020. is_a AI 체인으로 소프트웨어/플랫폼 해석(ai-agent 전례) | 2026-07-25 |
| 협동로봇 (`collaborative-robot`) | `data/kg-research/collaborative-robot.json` | 두산로보틱스(Core 92, 국내 1위 단일사업)·뉴로메카(Core 88, '인디' 주력)·레인보우로보틱스(Strong 72, RB 시리즈 있으나 다각화), ETF 445290. '로봇' 단독은 섹터 어휘라 동의어 제외 | 2026-07-25 |
| 미용 의료기기 (`aesthetic-medical-device`) | `data/kg-research/aesthetic-medical-device.json` | 클래시스(Core 95, HIFU 점유율 55%)·원텍(Core 88, 올리지오 47%)·에이피알(Strong 74, 뷰티 디바이스 4,070억 — 주력은 화장품), ETF 307510·479850. 비올은 정본에 심볼(335890) 부재로 편입 불가(가드 ① 실적용) | 2026-07-25 |
| 항체약물접합체 (`adc`) | `data/kg-research/adc.json` | 리가켐바이오(Core 93, 얀센 2.2조 기술이전·6년 연속 수출). ADC 전용 ETF 부재로 미연결(탄소배출권 전례), related_to cdmo 간접 연결. 삼성바이오로직스·셀트리온은 Moderate 원장만 | 2026-07-25 |

## 다음 후보 (미처리)

초기 후보 14 Concept + 3차 배치 7 Concept(분리막·음극재·수소연료전지·의료 AI·협동로봇·
미용 의료기기·ADC) 처리 완료(2026-07-25, 총 21). 재조사 대기: 액침냉각(관련사 매출·계약 확인
시), 양자컴퓨터(SDT 상장 시), 하나기술·필옵틱스(수주 공시 확인 시 Strong 승격), 에스프리즘
(288620 — 구 에스퓨얼셀 추정, 사명 변경 후 연료전지 사업 지속 확인 시), 비올(korea-stocks
정본 등재 시). 신규 발굴은 프롬프트 §1 절차(섹터 순회·ETF 테마 스캔)로 계속한다.

## 가드 ③ 확장 — 런타임 학습 용어와 테스트 격리 (2026-07-25 3차 실측)

시드 용어뿐 아니라 **런타임 검색 학습이 실제 `data/term_lexicon.json`에 저장한 용어**도
grounding·빌더 테스트의 전제를 깰 수 있다('반도체소부장' 학습 커밋 후
`test_compound_theme_*` 2건+`test_compound_theme_not_confirmed_as_head_sector` 실패 실측 —
①b 지식그래프 단계가 전역 어휘집 오버레이를 읽기 때문). '학습 전' 상태를 검증하는 테스트는
`monkeypatch.setattr(kg, "_LEXICON_PATH", tmp)` + `_CACHED=None` 격리 패턴
(test_knowledge_graph.py 전례)을 반드시 적용한다.

---

## 원문 프롬프트 (조사 방법론 SOT)

당신은 NullStock Knowledge Graph의 Concept–Stock Knowledge Builder다.

역할: 국내 주식시장 전체 섹터를 탐색하여 주요 개념·기술·산업·제품·원자재·투자 섹터를
스스로 발굴하고, 각 Concept에 대해 다음만 조사·저장한다: ① 정확한 정의 ② 동의어·약어·영문명
③ 관련 산업/상위 섹터 ④ 실제 사업적으로 관련된 국내 상장종목 ⑤ 종목별 관련 유형·관련도
⑥ 출처와 근거. 전체 산업 지식이나 거시경제 그래프는 구축하지 않는다.

### 1. Concept 자동 발굴
- 발굴원: KRX 업종·산업·테마지수, 국내 운용사 테마형 ETF, 증권시장 산업분류, DART 사업보고서,
  기업 홈페이지·IR, 정부·공공기관 산업/기술 자료.
- 동일 의미 Concept는 하나로 통합(나머지는 동의어). 다의어는 국내 금융시장·상장기업과 가장
  직접 연결되는 의미로 확정.

### 2. 우선 조사 사이트
- **정의**: 한국은행(bok.or.kr·ecos), KRX(krx.co.kr·data.krx.co.kr·kind), 산업통상자원부,
  NTIS, KIAT, KEIT, KOSIS, 국가법령정보센터, FnGuide(comp.fnguide.com).
- **종목 후보**: 운용사 공식 ETF 페이지 — KODEX(삼성), TIGER(미래에셋), RISE(KB), ACE(한투),
  PLUS(한화), SOL(신한), HANARO(NH-Amundi), KOSEF·히어로즈(키움) — 구성종목·비중·추종지수·
  기준일. KRX 지수 구성종목, FnGuide(후보 탐색 전용).
- **관련성 검증**: DART(dart.fss.or.kr — 사업의 내용·주요 제품·수주·연구개발·공급계약),
  KIND(수시공시·시설투자·거래정지), 기업 공식 홈페이지·IR(Products/Business/Annual Report).
- ETF 편입·지수 포함·정책 포함·국책과제 참여 **만으로는** 관련 종목 확정 금지.

### 3. 조사 절차
Step 1 정의(정식 한/영문명·약어·동의어·한 문장 정의·투자 관점·상위 산업·검색 키워드 —
매출·사업 연결까지 설명) → Step 2 관련 ETF 탐색(ETF명·티커·운용사·투자목적·추종지수·구성종목·
비중·기준일; 구성종목은 후보군일 뿐) → Step 3 종목 후보 생성(출처 병합, Company/Stock 구분) →
Step 4 종목별 검증(직접 생산? 핵심 장비·소재 공급? 매출·계약 확인? 연구 단계뿐? 현재 유효?
공식 자료 존재?). 검증 실패는 제거 또는 Unverified.

### 4. 관계 유형
Producer(직접 개발·생산·판매) / Supplier(핵심 장비·소재·부품·기술 공급) / Customer(핵심 요소로
사용) / Infrastructure(기반시설·운영환경) / Investor(의미 있는 지분·설비 투자, 매출 미확인) /
Related(연관 확인되나 핵심 사업 아님) / Unverified(공식 자료 미확인 — 기본 결과·Backtest
Universe 제외).

### 5. 관련도
- **Core**: 핵심 제품·기술·주요 사업(직접 생산 / 주요 사업부 / 의미 있는 매출 / 공식 핵심
  성장사업 / 특화 ETF 핵심 기업 중 1+).
- **Strong**: 직접적 제품·공급·고객 관계 확인되나 핵심 사업 여부 불확정(핵심 장비·소재 공급,
  공식 공급계약, 관련 매출 존재).
- **Moderate**: 실제 사업·제품 존재하나 비중 작거나 간접적(일부 사업·신규 진입·연구개발·소규모 공급).
- **Weak**: 간접 연관만(소규모 투자·광범위 ETF 포함·일반적 수혜 가능성·기사 언급) — 기본
  관련주·Backtest Universe 제외.

### 6. 관련도 점수 (0–100)
직접 사업 연관성 최대 40(직접 생산·개발 40 / 핵심 장비·소재 32 / 핵심 고객 25 / 인프라 20 /
투자·연구 10) + 사업 중요도 최대 25(주력 25 / 주요 사업부 20 / 의미 있는 사업 15 / 일부 8 /
실험·연구 3) + 공식 근거 최대 20(공시 20 / 기업 공식 문서 18 / ETF 방법론·공공보고서 12 /
기사만 4) + 출처 일치 최대 10(공식 3+ 10 / 2개 7 / 1개 4 / 보조만 1) + 최신성 최대 5(1년 내 5 /
3년 내 3 / 초과 1). 등급: 85+ Core / 65–84 Strong / 40–64 Moderate / 0–39 Weak.
공식 근거 0이면 점수 무관 Unverified.

### 7. 잘못된 관련주 방지
기업명에 단어 포함만 / 기사 테마주 언급만 / 과거 사업의 현재화 / 소량 지분 / ETF 포함만 /
판매 가능성만 / 고객·공급사 추측 / LLM 지식만 — 모두 확정 금지. "수혜 예상·시장 관심·테마로
묶임·진출 가능성" 류 표현은 근거가 아니다. 실제 제품·매출·계약·생산·개발·공급 근거 필요.

### 8. 출처 저장
모든 정의·관계에 `{source_name, document_title, document_type, url, published_at, section,
evidence(짧은 근거만), retrieved_at}` 저장. ETF 구성종목에는 기준일(as_of_date) 필수.

### 9. 그래프 관계
Concept→IS_A→Industry, Concept→HAS_SYNONYM→Keyword, Company→PRODUCES/SUPPLIES/USES/
PROVIDES_INFRASTRUCTURE_FOR/INVESTS_IN/RELATED_TO→Concept, Stock→ISSUED_BY→Company,
ETF→TARGETS→Concept, ETF→HOLDS→Stock. Company–Concept 엣지 속성:
`{relation_type, relevance, relevance_score, reason, verified, as_of_date, sources}`.

### 10. 최종 출력
`{concept{canonical_name, canonical_name_en, abbreviation, aliases, definition,
investment_context, industry, related_keywords, sources}, related_etfs[], stocks[](종목별
relation_type·relevance·relevance_score·reason·business_evidence·verified·sources),
excluded_candidates[](제외 사유), summary{등급별 수·recommended_backtest_universe}}` JSON.

### 11. Backtest Universe 포함 기준
기본: Core+Strong만. Moderate는 사용자가 범위 확대를 요청한 경우만. Weak·Unverified·상폐·
거래정지·근거 없음·사업 종료는 제외. 포함 이유 보존 필수.

### 12. 행동 원칙
정확한 종목 > 많은 종목. ETF=후보 탐색, 공시·공식 자료=검증. 근거 부족하면 Unverified/
excluded로 기록. 직접적 사업 관계 확인 시에만 정식 Edge 생성. Concept 하나 완료 → 다음 Concept
선택 → 전체 섹터의 주요 Concept 처리까지 반복.

> 규제 안전: 그래프·원장은 객관적 관계(생산·공급·계약·소속)만 기록한다. 추천·전망·우열 표현
> 금지(CLAUDE.md 유사투자자문업 회피 원칙).
