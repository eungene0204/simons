# 검증(Validation) Agent QA 리포트

- 대상 예시: **80개**
- PASS(통과): **78** · CLARIFY(파서 되물음=의도됨): **2** · WARN(예상 밖 경고): **0** · FAIL(에러=차단): **0**

## ⚠️ 경고 코드 빈도

- `MISSING_TAKE_PROFIT`: 54건 (예상됨)

## 💬 파서 되물음(CLARIFY — 의도된 동작)

모호한 조건을 임의 추측하지 않고 사용자에게 숫자를 되묻는 케이스. 실제 프론트에서는 검증 단계에 도달하지 않는다.

- **11. 저PER 현금 많은 기업 고르기** — 말씀하신 조건을 숫자로 구체화해 주세요. 어느 정도를 기준으로 할까요?
- **16. 부채비율·ROE 보유 조건** — 말씀하신 조건을 숫자로 구체화해 주세요. 어느 정도를 기준으로 할까요?

## 전체 결과

| # | 카테고리/레벨 | 제목 | 판정 | errors | warnings |
|---|---|---|---|---|---|
| 1 | 가치투자/beginner | 저PBR 대형주 장기보유 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 2 | 기술분석/beginner | 이평선 골든크로스 따라가기 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 3 | 모멘텀/beginner | 신고가 돌파주 짧게 보유 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 4 | 복합전략/beginner | PER·RSI 반등 조건 | PASS | — | — |
| 5 | 복합전략/beginner | PBR·거래대금 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 6 | 가치투자/beginner | ROE·부채비율 분기 점검 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 7 | 기술분석/beginner | 박스권 상단 돌파 따라가기 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 8 | 모멘텀/beginner | 60일 수익률 상위 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 9 | 복합전략/beginner | 배당주 + 눌림목 진입 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 10 | 모멘텀/beginner | 수익률 상위 종목 주간 교체 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 11 | 가치투자/beginner | 저PER 현금 많은 기업 고르기 | CLARIFY | 파서 되물음 | |
| 12 | 기술분석/beginner | 20일선 위 종목만 보유 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 13 | 모멘텀/beginner | 거래대금·5일 상승 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 14 | 복합전략/beginner | ROE·이동평균 추세 조건 | PASS | — | — |
| 15 | 기술분석/beginner | 거래량 늘어난 20일선 위 종목 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 16 | 가치투자/beginner | 부채비율·ROE 보유 조건 | CLARIFY | 파서 되물음 | |
| 17 | 가치투자/intermediate | PBR·ROE 분기 점검 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 18 | 기술분석/intermediate | MACD + RSI 확인 매매 | PASS | — | — |
| 19 | 복합전략/intermediate | PBR·거래대금 돌파 조건 | PASS | — | — |
| 20 | 복합전략/intermediate | 재무 건전성 + 추세 확인 매매 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 21 | 모멘텀/intermediate | 거래량 급증 + EMA 추세 확인 | PASS | — | — |
| 22 | 모멘텀/intermediate | 돌파 후 거래량 확인 매매 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 23 | 가치투자/intermediate | 현금흐름·PBR 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 24 | 기술분석/intermediate | 볼린저 중심선 재돌파 스윙 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 25 | 모멘텀/intermediate | 상대강도 상위주 월간 교체 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 26 | 복합전략/intermediate | 퀄리티 필터 후 추세 진입 | PASS | — | — |
| 27 | 복합전략/intermediate | 변동성·ROE 이동평균 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 28 | 가치투자/intermediate | 배당 + 저PBR 월간 점검 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 29 | 기술분석/intermediate | 이격도 과열 회피형 추세 추종 | PASS | — | — |
| 30 | 모멘텀/intermediate | 신고가 후 눌림목 재진입 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 31 | 복합전략/intermediate | 가치 + 모멘텀 혼합 리밸런싱 | PASS | — | — |
| 32 | 기술분석/intermediate | 이중 이동평균 추세 유지 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 33 | 복합전략/expert | 중형주 퀄리티-밸류-모멘텀 결합 | PASS | — | — |
| 34 | 모멘텀/expert | ADX 추세 강도 기반 스윙 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 35 | 가치투자/expert | 현금흐름·밸류 조건 포트폴리오 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 36 | 복합전략/expert | 이중 기술 신호 확인 스윙 | PASS | — | — |
| 37 | 기술분석/expert | 볼린저밴드 상단 돌파 + 거래량 확인 | PASS | — | — |
| 38 | 모멘텀/expert | 거래대금 필터 월간 모멘텀 로테이션 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 39 | 가치투자/expert | 퀄리티 밸류 저변동 포트폴리오 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 40 | 기술분석/expert | 다중 시간축 EMA 정렬 추세 전략 | PASS | — | — |
| 41 | 모멘텀/expert | 상대강도 + 유동성 가중 로테이션 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 42 | 복합전략/expert | 섹터 중립 퀄리티 모멘텀 | PASS | — | — |
| 43 | 모멘텀/expert | 상대강도 점수 기반 주간 랭킹 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 44 | 가치투자/expert | 현금흐름 개선 기업 집중형 | PASS | — | — |
| 45 | 기술분석/expert | 볼륨 프로파일 돌파 확인 전략 | PASS | — | — |
| 46 | 모멘텀/expert | ADX + 상대강도 결합 스윙 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 47 | 복합전략/expert | 매출성장·PBR 추세 조건 | PASS | — | — |
| 48 | 복합전략/expert | 멀티팩터(퀄리티+모멘텀+밸류) 결합 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 49 | 가치투자/expert | 밸류 트랩 회피형 분산 보유 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 50 | 가치투자/beginner | ROE·부채비율 반년 보유 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 51 | 가치투자/beginner | 저PBR 자산주 분기 점검 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 52 | 가치투자/beginner | 저PER주 천천히 모으기 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 53 | 가치투자/intermediate | 대형주 PBR·ROE 월간 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 54 | 가치투자/intermediate | PER·PBR·거래대금 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 55 | 가치투자/intermediate | 부채비율·ROE 격월 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 56 | 가치투자/expert | 3중 가치 필터 분기 리밸런싱 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 57 | 가치투자/expert | 중형 가치주 익절 포함 | PASS | — | — |
| 58 | 가치투자/expert | 고ROE 저PER 유동성 집중 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 59 | 기술분석/beginner | RSI 과매도 반등 단순 매매 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 60 | 기술분석/beginner | 단기 골든크로스 추종 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 61 | 기술분석/beginner | 60일선 위 종목만 보유 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 62 | 기술분석/intermediate | MACD + 추세 필터 매매 | PASS | — | — |
| 63 | 기술분석/intermediate | 볼린저 하단 반등 스윙 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 64 | 기술분석/intermediate | ADX 추세 확인 EMA 매매 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 65 | 기술분석/expert | RSI·MACD 이중 확인 진입 | PASS | — | — |
| 66 | 기술분석/expert | EMA 정배열 눌림 재진입 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 67 | 기술분석/expert | 볼린저 상단 돌파 거래량 확인 | PASS | — | — |
| 68 | 모멘텀/beginner | 신고가 돌파 거래량 단타 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 69 | 모멘텀/beginner | 주간 수익률 상위 교체 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 70 | 모멘텀/intermediate | 유동성 필터 모멘텀 월간 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 71 | 모멘텀/intermediate | 신고가 거래대금 2배 확인 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 72 | 모멘텀/intermediate | 거래량 급증 추세 추종 | PASS | — | — |
| 73 | 모멘텀/expert | 대형 유동성 장기 모멘텀 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 74 | 모멘텀/expert | 전체 시장 신고가 로테이션 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 75 | 복합전략/beginner | ROE·골든크로스 조건 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 76 | 복합전략/beginner | 저PBR RSI 반등 결합 | PASS | — | — |
| 77 | 복합전략/intermediate | PER·ROE 신고가 조건 | PASS | — | — |
| 78 | 복합전략/intermediate | 재무 필터 EMA 추세 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |
| 79 | 복합전략/expert | 퀄리티 + 유동성 + MACD | PASS | — | — |
| 80 | 복합전략/expert | 멀티팩터 주간 로테이션 | PASS | — | `MISSING_TAKE_PROFIT`(take_profit_pct) |