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
방향성 관례: Producer/Supplier/Customer/Related는 `{source: concept, type, target: company}`
(기존 다수 전례 — "concept –produced_by→ company"로 읽는다). **Investor만 예외**로
`{source: company, type: "invests_in", target: concept}`를 쓴다("회사가 개념에 투자한다"가
자연스러운 읽기 방향이라 2026-07-25 누락 연결 감사에서 첫 사용 시 확정 — `neighbors()`/
`listed_companies()`는 양방향을 다 보므로 기능에는 영향 없음, 순전히 가독성 문제).

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
| K-팝 기획사 (`kpop-agency`) | `data/kg-research/kpop-agency.json` | 하이브(Core 95)·에스엠(92)·JYP(92)·와이지(88), ETF 475050·395290. '엔터'·'엔터테인먼트'는 섹터 어휘라 동의어 제외(가드 ②) | 2026-07-25 |
| 드라마 제작사 (`drama-production`) | `data/kg-research/drama-production.json` | 스튜디오드래곤(Core 95, 국내 최대 전업)·에이스토리(Core 87, 우영우 IP)·팬엔터테인먼트(Strong 78), ETF 395150·228810, uses 웹툰(IP 파이프라인). '드라마' 단독은 '드라마틱' substring 오폭 위험으로 동의어 제외 | 2026-07-25 |
| 웹툰 (`webtoon`) | `data/kg-research/webtoon.json` | 디앤씨미디어(Core 90, 나혼렙 IP·출판 1위)·키다리스튜디오(Core 88, 봄툰·레진)·와이랩(Strong 75), ETF 395150. 노드명 '웹툰'은 섹터 어휘라 스캔 제외·동의어(웹소설 등)가 담당('양극재' 전례). 미스터블루는 게임 겸업 Moderate | 2026-07-25 |
| 팬덤 플랫폼 (`fandom-platform`) | `data/kg-research/fandom-platform.json` | 디어유(Core 92, 구독 단일 사업·SM/JYP 지분)·하이브(Strong 74, 위버스). 다업종(소프트웨어+미디어)이라 part_of 없음(온디바이스 AI 전례). '버블'·'위버스' 상품명 동의어 금지(가드 ③) | 2026-07-25 |

## 누락 연결 감사 (Missing-Edge Audit, 2026-07-25 배치 1)

사용자 제보("현대차-로봇처럼 실제론 밀접한데 안 잡힌 연결")로 시작한 **기존 개념의 회사 커버리지
감사** — 신규 Concept 발굴이 아니라, 이미 시드에 있는 개념 노드에 붙어야 할 대기업 지분투자·부품
공급 관계가 빠진 사례를 찾아 보완한다. Concept-Stock Builder 절차(§4 Investor 관계유형)를 그대로
쓰되 출발점이 "회사"라는 점만 다르다.

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 휴머노이드 로봇 (`robot-humanoid`) | 현대자동차(Investor/Strong 78, 보스턴다이내믹스 지분 100% 확보+아틀라스 2028~2030 생산현장 투입 로드맵)·삼성전자(Investor/Strong 78, 레인보우로보틱스 지분 35.0%·최대주주·연결자회사 편입)·LG전자(Supplier/Strong 70, 액추에이터 B2B 공급 공식화+CES 2026 '클로이드' PoC) | `data/kg-research/robot-humanoid.json`(신규 — 기존 3사는 2026-07-24 최초 배치 편입분이라 이번 감사에서 재조사하지 않고 unspecified로 표시) |
| AI 에이전트 (`ai-agent`) | NAVER(Producer/Strong 72, 'AI 국민비서' 행정안전부 공동 구축 — 클로바X·큐: 실험서비스는 2026-04 종료 후 본 서비스 통합 전략 전환) | `data/kg-research/ai-agent.json`(기존 원장에 추가) |

회귀 가드: `test_knowledge_graph.py::test_conglomerate_diversification_edges_present`.

### 배치 2 (2026-07-25, "계속 진행해줘")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| LNG운반선 (`lng-carrier`) | HD한국조선해양(Core 88)·한화오션(Core 85)·삼성중공업(Core 85) — 2026년 K조선 3사 LNG선 대형 수주(각 1조~2.6조원대)+한국 대형 LNG선 시장 점유율 약 65~69% | `data/kg-research/lng-carrier.json`(신규 — 개념은 2026-07-24 최초 배치에 있었으나 상장사 엣지가 하나도 없던 공백) |
| 원자력 (`nuclear`) | 한전KPS(Producer/Core 87, 국내 전 원전 정비 전담·원자력정비 매출 비중 34%) | `data/kg-research/nuclear.json`(신규 — 기존 3사는 2026-07-24 최초 배치분이라 unspecified로 표시) |
| 협동로봇 (`collaborative-robot`) | 현대위아(Producer/Strong 68, 모빌리솔루션사업부 신설+CES 2026 협동로봇 시연·아직 PoC 단계) | 기존 원장에 추가 |
| K-팝 기획사 (`kpop-agency`) | 큐브엔터(Producer/Core 85, (여자)아이들·비투비 — 재조사 대기 후보였던 Moderate에서 매출 872억원 공식 확인해 Core로 승격) | 기존 원장에 추가 |
| CDMO (`cdmo`) | 롯데바이오로직스 — **편입 보류**. 송도 1공장 완공·2026년 말 상업생산 예정 등 사업 실체는 확인했으나 `korea-stocks.json` 정본에 별도 상장 심볼이 없어(롯데지주 비상장 자회사) 가드 ①(정본 존재 확인)을 통과하지 못함. 별도 상장 시 재조사 | — |

회귀 가드: `test_knowledge_graph.py::test_missing_edge_audit_batch2_present`.

### 배치 3 (2026-07-25, "계속 진행해줘" 이어서)

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 데이터센터 (`data-center`) | 삼성에스디에스(Producer/Strong 72, DBO 사업 진출+동탄 액침냉각 시범)·LG씨엔에스(Producer/Strong 70, 자카르타 하이퍼스케일 AI 데이터센터 구축) | `data/kg-research/data-center.json`(신규 — 개념은 2026-07-24 최초 배치에 있었으나 상장사 엣지가 하나도 없던 공백) |
| 인공위성 (`satellite`) | 한국항공우주/KAI(Producer/Core 85, 다목적실용위성 30년 본체개발 주관사·7호 2025-12 발사) | 기존 원장에 추가 |

편입 보류(검증했으나 근거 부족): LG화학→battery-cathode(양극재 사업 실재하나 2026년 생산능력을
28만톤→17만톤으로 축소 중·"실적 부진" — 매출 비중 미확인이라 Moderate), 동아에스티→biosimilar
(스텔라라 바이오시밀러 176억원/2025 vs 전체 매출 7,451억원 — 비중 2.4%로 "일부 사업"에 그쳐
Moderate). 둘 다 시드 미편입, 재조사 후보로만 기록.

회귀 가드: `test_knowledge_graph.py::test_missing_edge_audit_batch3_present`.

## Part B — 신규 Concept 편입 (judal 미대응 108개 후보, 2026-07-25 "PART B로 진행")

사용자 지시로 Part A(기존 개념 감사)에서 Part B(judal 카탈로그에만 있고 우리 그래프엔 대응
개념이 없는 주요 테마의 신규 편입)로 전환. 절차는 기존 Concept-Stock Builder와 동일(§1~§12).

### 배치 1 (2026-07-25)

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 자율주행 (`autonomous-driving`) | 현대모비스(Core 85, ADAS 부품 2천만 건+ 공급 경험)·HL만도(Core 82, 2021년 ADAS+MHE 통합해 자율주행 전문 조직 HL클레무브 출범), ETF 385520·394660·414270 | `data/kg-research/autonomous-driving.json` |
| 사이버보안 (`cybersecurity`) | 안랩(Core 90, 국내 보안 상장사 매출 1위 2,330억원)·파수AI(Strong 70, 데이터보안 전문·삼성/포스코/CJ 고객사, 舊 파수) | `data/kg-research/cybersecurity.json`. 시큐아이는 정본 미등재로 편입 불가 |
| 전기차 충전 (`ev-charging`) | 채비(Core 85, 舊 대영채비 — 충전이 사업 전부, 2026 1분기 매출 207억원) | `data/kg-research/ev-charging.json` |
| 양자암호통신 (`quantum-cryptography`) | SK텔레콤(Investor/Strong 70, 스위스 IDQ 지분 50%+ 인수·700억원·1대 주주 — 기존 `quantum-computing`과는 related_to로만 연결, is_a는 부적절) | `data/kg-research/quantum-cryptography.json` |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch1_present`.

### 배치 2 (2026-07-25, "계속 진행")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 5G 장비 (`5g-equipment`) | RFHIC(Core 88, GaN 전력증폭기·트랜지스터가 매출 99%+)·케이엠더블유(Core 85, 국내 유일 5G MMR 개발·매출 90% 해외) | `data/kg-research/5g-equipment.json`. '5G' 단독은 카탈로그가 담당(폭넓은 통신주), 이 개념은 'RF 부품'/'기지국 장비' 등 구체 문구로만 스캔(HBM 전례) |
| 핀테크 (`fintech`) | 카카오페이(Core 90, 2026 1분기 매출 3,003억원 역대 최대) | `data/kg-research/fintech.json` |
| PCB (`pcb`) | 심텍(Core 87, 모듈PCB·서브스트레이트 세계적 기업)·대덕전자(Core 85, 서브스트레이트·MLB 글로벌 리더·2025 매출 1조653억원) | `data/kg-research/pcb.json` |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch2_present`.
편입 보류: 유콘시스템(드론)은 korea-stocks.json 정본 미등재로 확인 실패, 드론 개념은 이번엔
편입하지 않음(억지 추가 금지). 에이스테크(5G)는 사업 근거 깊이 부족으로 제외.

### 배치 3 (2026-07-25, "계속 진행해줘")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 게임 (`gaming`) | 크래프톤(Core 92, 2026 1분기 영업이익 1위 5,616억원)·NC(Core 88, 舊 엔씨소프트 — 리니지 클래식 흥행으로 실적 반등)·넷마블(Core 90, 2025 매출 2조8,351억원 사상 최대) | `data/kg-research/gaming.json`. 넥슨은 매출 1위(1조4,201억)지만 도쿄증권거래소 상장이라 정본 밖(가드 ①) |
| LED (`led-tech`) | 서울반도체(Core 85, 2025년 매출 1조135억원) | `data/kg-research/led-tech.json` |
| 광통신 (`optical-communication`) | 오이솔루션(Core 80, 2025년 매출 574억원 79.2%↑·2026년 흑자전환 전망) | `data/kg-research/optical-communication.json`. data-center·5g-equipment와 related_to(AI 데이터센터·5G 전송 수요 공유) |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch3_present`.

### 배치 4 (2026-07-25, "계속 진행")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 니켈 (`nickel`) | 회사 엣지 없음(기존 구리·리튬과 동일한 순수 원자재 노드) — battery-cathode가 requires로 연결 | 이차전지 양극재(NCM/NCA) 핵심 원료 |
| 희토류 (`rare-earth`) | 회사 엣지 없음 — sector:자동차부품이 affected_by로 연결 | 전기차 모터·풍력터빈 영구자석 핵심 원료 |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch4_present`.

**편입 시도했으나 보류(근거 부족)**: 수소차 — 효성첨단소재(탄소섬유가 수소탱크 소재이나 매출
비중 미확인)·이엠코리아(수소충전소 매출 140억원, 2019년 자료로 낡음)·효성하이드로젠(액화수소
충전소 매출 연 10억원대·상업생산 지연) 모두 Core/Strong 기준 미달. 스마트팩토리 — 로보스타
(반도체 이송장비+스마트팩토리 RPS로 사업 확장 중이나 구체 매출 비중 미확인)·싸이맥스(반도체
장비 전문이라 스마트팩토리보다는 반도체 장비에 가까움) 모두 근거 깊이 부족. 고려아연은 니켈
제련소(2026 준공 예정)·희토류 정제(2026-2030 R&D)를 진행 중이나 아직 가동 전 단계라 회사
엣지로 편입하지 않고 원자재 노드만 편입(억지 추가 금지 원칙).

### 배치 5 (2026-07-25, "계속 진행")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 생체인식 (`biometrics`) | 슈프리마(Core 88, 바이오인식 보안 전업·수출 81%·지문인식 알고리즘 세계 1위 4회) | `data/kg-research/biometrics.json` |
| 렌터카 (`car-rental`) | 롯데렌탈(Core 85, 국내 1위·2025 매출 2조9,188억원) | `data/kg-research/car-rental.json`. SK렌터카는 매각(비상장화)으로 정본 밖 |
| 광고 (`advertising`) | 제일기획(Strong 75)·이노션(Strong 72) — 둘 다 등록 업종 자체가 광고업, 최신 매출 공시는 미확인이라 Strong | `data/kg-research/advertising.json` |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch5_present`.

### 배치 6 (2026-07-25, "계속 진행")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 건강기능식품 (`health-supplements`) | 콜마비앤에이치(Core 85, 건기식 OEM/ODM·2026 1분기 영업이익 189%↑)·뉴트리(Core 82, 에버콜라겐 등 이너뷰티 자체 브랜드·최근 실적 부진하나 사업 관련성은 명확) | `data/kg-research/health-supplements.json` |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch6_present`.
편입 보류: 하림펫푸드(반려동물)·캐리마(3D프린터) 모두 비상장(정본 미등재)으로 확인 실패.

### 배치 7 (2026-07-25, "계속 진행")

| 개념 | 신규 편입 | 근거 |
| --- | --- | --- |
| 폴더블폰 (`foldable-phone`) | KH바텍(Core 85, 2025년 전사 매출 4,249억원 중 힌지 매출 2,539억원·44%↑ 반등) | `data/kg-research/foldable-phone.json` |

회귀 가드: `test_knowledge_graph.py::test_part_b_new_concepts_batch7_present`.
편입 보류: 창투사(미래에셋벤처투자·SBI인베스트먼트)는 구체적 실적 근거 미확보로 보류. 파인테크닉스
(폴더블 부품 후보)는 정본 업종 분류가 조명장치 제조업이라 관련성 미확인.

남은 범위: judal 미대응 108개 후보 중 나머지(전기차·LCD 부품/소재·방산주·영상콘텐츠·사물인터넷·
MLCC·6G·초전도체·드론(재조사)·LFP배터리·수소차(재조사) 등) 신규 Concept 편입. Part A(기존 개념
감사) 잔여 48개도 병행 가능.

## 다음 후보 (미처리)

초기 후보 14 + 3차 배치 7(분리막·음극재·수소연료전지·의료 AI·협동로봇·미용 의료기기·ADC)
+ 4차 엔터 배치 4(K-팝 기획사·드라마 제작사·웹툰·팬덤 플랫폼, 사용자 요청 "엔터 정보 부족")
처리 완료(2026-07-25, 총 25). 재조사 대기: 액침냉각(관련사 매출·계약 확인 시), 양자컴퓨터
(SDT 상장 시), 하나기술·필옵틱스(수주 공시 확인 시 Strong 승격), 에스프리즘(288620 — 구
에스퓨얼셀 추정, 사명 변경 후 연료전지 사업 지속 확인 시), 비올(korea-stocks 정본 등재 시),
큐브엔터·미스터블루·콘텐트리중앙·삼화네트웍스(근거 보강 시 승격). 신규 발굴은 프롬프트 §1
절차(섹터 순회·ETF 테마 스캔)로 계속한다.
**누락 연결 감사(위)는 별도 트랙 — 기존 54개 개념 감사 + judal 미대응 108개 테마 검토가 남았다.**

## 카탈로그 레이어 — 외부 테마 분류 일괄 편입 (2026-07-25)

시드 절차(개별 검증)와 별개로, 사용자가 신뢰 소스로 지정한 외부 테마→종목 분류를
**카탈로그 레이어**로 일괄 편입할 수 있다. 첫 적용: 주달(judal.co.kr) 209테마·2,673엣지.

| 구분 | 시드 | 카탈로그 |
| --- | --- | --- |
| 파일 | `data/knowledge-graph.json` | `data/kg-theme-catalog.json` |
| 검증 | Core/Strong 개별 검증(본 문서 절차) | 소스 단위 신뢰(개별 검증 생략 — 사용자 지시) |
| 스캔 우선순위 | 1위 | 3위(시드 > 학습 > 카탈로그, 로더 삽입 순서) |
| 섹터 해석 | 소속 엣지로 참여 | **불참**(소속 엣지 없음 — 테마→종목 조회 전용) |
| 무결성 | issues 단언 대상 | 정본 밖 심볼 조용히 스킵(학습 데이터와 동일) |

- 수집·갱신: `cd backend && python3 scripts/ingest_judal_themes.py`(전체 재수집 후 덮어쓰기).
- 수집 스크립트가 기계적 가드 4종을 강제한다: ① 정본 심볼 필터 ② 섹터 어휘 이름 스킵
  (반도체·로봇 등 32개 — 도달 불가 죽은 노드 방지) ③ 시드 중복 스킵(15개 — 큐레이션 우선
  계약) ④ 테스트 정본 용어 스킵(폐배터리·메타버스 — `TEST_RESERVED_TERMS`).
- 포함 범위(사용자 결정 2026-07-25): 산업·기술·원자재 테마+그룹주 테마. 제외: 정치인·인물(9),
  계절·재해·질병 이벤트(37), 시장 분류 목록(ETF·스팩·고배당 등 19).
- 주의: 시드 중복으로 스킵된 테마(의료AI 23종목 등)는 시드의 Core/Strong만 서빙된다 —
  병합하려면 별도 정책 결정 필요. 카탈로그 관련주는 미검증이므로 `related_company`
  단일 타입, 관련도 점수 없음.

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
