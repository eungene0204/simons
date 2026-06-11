# AI 모델 파싱 분석 보고서

**테스트 일자**: 2025-06-09  
**목적**: 사용자가 'AI 모델'이라고 입력할 때 전략연구소의 NL 파서가 어떻게 인식하는지 파악

---

## 📋 Executive Summary

**결론**: 사용자가 'AI 모델'이라고 입력하면:
1. **규칙 기반 파싱으로는 인식 불가** ❌ 
2. **LLM이 자동으로 폴백되어 처리** ✅
3. **LLM이 생성한 신호는 키워드 검증을 통과** ✅
4. **최종적으로 `ai_model` 또는 `ai_drop_model` indicator로 변환** ✅

---

## 🔍 상세 분석

### 1. 규칙 기반 추출 단계

**상태**: ❌ **실패**

AI 모델은 규칙 기반 파싱으로 추출되지 않습니다.

```python
# _extract_technical_signals() 함수에서
# AI 모델 관련 regex 패턴이 없음
```

**이유**: 
- `backend/engine/nl_parser.py`의 `_extract_technical_signals()` 함수는 다음 신호들만 결정적으로 추출합니다:
  - 골든크로스/데드크로스 (MA 크로스오버)
  - RSI
  - MACD
  - 볼린저밴드
  - 브레이크아웃
  - 거래량 급증
  
- **AI 모델은 포함되지 않음** → 패턴 정의 가능하지만 현재는 LLM에 위임

### 2. LLM 폴백 단계

**상태**: ✅ **반드시 호출됨**

규칙 기반으로 충분하지 않으면 LLM이 호출됩니다.

```python
def parse(self, user_input: str) -> ParsedStrategy:
    parsed_by_rules = _parse_rule_based_strategy(user_input)
    if parsed_by_rules is not None:
        return parsed_by_rules
    
    # AI 모델은 규칙으로 추출 불가 → LLM 폴백
    if self.backend == "mlx":
        parsed = self._parse_mlx(user_input)
    else:
        parsed = self._parse_ollama(user_input)
```

**LLM 프롬프트**:

```
라인 249-251 (SYSTEM_PROMPT):
- AI 상승 예측 매수 / AI 모델 매수 → indicator: "ai_model", signal_type: "buy", threshold: 70
- AI 하락 예측 매도 / AI 모델 매도 → indicator: "ai_drop_model", signal_type: "sell", threshold: 70
- AI 모델이 X% 이상 확률로 상승 예측 → indicator: "ai_model", signal_type: "buy", threshold: X

예시 (라인 289-311):
입력: "AI 모델이 상승 예측한 종목에 매수, AI 하락 예측 시 매도, 최대 15종목, 손절 10%"
출력:
{
  "entry_signals": [{"indicator": "ai_model", "signal_type": "buy", "threshold": 70}],
  "exit_signals": [{"indicator": "ai_drop_model", "signal_type": "sell", "threshold": 70}],
  ...
}
```

### 3. 신호 검증 단계

**상태**: ✅ **대부분 통과**

LLM이 생성한 ai_model/ai_drop_model 신호는 LLM 환각 방지 검증을 통과합니다.

#### 검증 메커니즘

```python
# 라인 820-869: _validate_signals() 함수

_INDICATOR_KEYWORDS = {
    "ai_model": ["ai", "인공지능"],
    "ai_drop_model": ["ai", "인공지능"],
    ...
}

_DESCRIPTIVE_INDICATORS = {"ma_crossover", "breakout", "volume_spike"}

def _validate_signals(signals, user_input):
    for sig in signals:
        # 서술형 신호(ma_crossover, breakout, volume_spike)는
        # 표현이 다양해서 키워드 검증을 스킵하고 신뢰한다.
        if sig.indicator in _DESCRIPTIVE_INDICATORS:
            validated.append(sig)
            continue
        
        # 고정된 이름의 지표(rsi, macd, cci, ai_model 등)는
        # 프롬프트에 그 이름이나 동의어가 있는지 확인한다.
        keywords = _INDICATOR_KEYWORDS.get(sig.indicator, [])
        if any(kw in compact_prompt for kw in keywords):
            validated.append(sig)  # ✓ 통과
        # else: 신호 제거 (환각 의심)
```

#### 테스트 결과

| 프롬프트 | "ai" 포함 | 검증 결과 |
|---------|----------|---------|
| "AI 모델 매수" | ✅ | ✓ 통과 |
| "ai 모델" | ✅ | ✓ 통과 |
| "AI 모델이 상승 예측" | ✅ | ✓ 통과 |
| "인공지능 매수" | ✅ (인공지능) | ✓ 통과 |
| "머신러닝으로 매수" | ❌ | ✗ 차단 |
| "딥러닝" | ❌ | ✗ 차단 |

**⚠️ 주의**: 프롬프트에 "ai" 또는 "인공지능"이라는 단어가 없으면 LLM이 생성한 ai_model 신호가 차단됩니다.

### 4. 프롬프트 오버라이드 적용

**상태**: ✅ **성공적 적용**

```python
# 라인 1415-1450: _apply_prompt_overrides() 함수

def _apply_prompt_overrides(parsed: ParsedStrategy, user_input: str):
    updates = {}
    
    # Step 1: 명시적 universe 추출
    explicit_universe = _extract_explicit_universe(user_input)
    if explicit_universe is not None:
        updates["universe"] = explicit_universe
    
    # Step 2: 리스크 필드 (손절/익절/트레일링)
    updates.update(extract_risk_field_overrides(user_input))
    
    # Step 3: 랭킹 메트릭
    ranking_metric, ranking_lookback_days = _extract_ranking(user_input)
    if ranking_metric is not None:
        updates["ranking_metric"] = ranking_metric
    
    # Step 4: LLM 환각 신호 검증 제거
    validated_entry = _validate_signals(parsed.entry_signals, user_input)
    validated_exit = _validate_signals(parsed.exit_signals, user_input)
    
    # Step 5: 규칙 기반 추출 & 병합
    extracted_entry, extracted_exit = _extract_technical_signals(user_input)
    # ... 신호 병합 ...
    
    return parsed.model_copy(update=updates)
```

### 테스트 사례별 결과

#### Case 1: "AI 모델이 상승 예측한 종목 매수"

```
[Step 1] 규칙 기반 파싱: ❌ 실패 (LLM 필요)
[Step 2] LLM 폴백: ai_model(buy, threshold=70) 생성
[Step 3] 신호 검증: ✓ 통과 ("ai" 포함)
[Step 4] 프롬프트 오버라이드:
  entry_signals: [ai_model(buy, threshold=70)]
  exit_signals: []
  max_positions: 10
  stop_loss_pct: None
```

#### Case 2: "AI 모델 하락 예측 시 매도"

```
[Step 1] 규칙 기반 파싱: ❌ 실패 (LLM 필요)
[Step 2] LLM 폴백: ai_drop_model(sell, threshold=70) 생성
[Step 3] 신호 검증: ✓ 통과 ("ai" 포함)
[Step 4] 프롬프트 오버라이드:
  entry_signals: []
  exit_signals: [ai_drop_model(sell, threshold=70)]
```

#### Case 3: "AI 모델 상승 종목만 사서 10개 최대"

```
[Step 1] 규칙 기반 파싱: ❌ 실패 (LLM 필요)
[Step 2] LLM 폴백: ai_model(buy), max_positions=10 생성
[Step 3] 신호 검증: ✓ 통과 ("ai" 포함)
[Step 4] 프롬프트 오버라이드:
  entry_signals: [ai_model(buy, threshold=70)]
  exit_signals: []
  max_positions: 10  (규칙 기반 추출 - "10개")
```

---

## ⚠️ 주의사항 및 가능한 문제

### 1. 키워드 의존도

현재 검증은 프롬프트에 `"ai"` 또는 `"인공지능"`이 명시되어야 합니다.

**문제 사례**:
```python
# ❌ 이 경우 ai_model이 차단될 수 있음
"머신러닝으로 상승/하락 예측한 종목만 매수"  
"딥러닝 신호"
"신경망 매수"

# ✅ 이 경우는 통과
"AI 모델로 매수"
"인공지능 상승 예측"
"AI가 올라간다고 판단하면 매수"
```

### 2. AI 모델이 규칙 기반으로 추출되지 않는 이유

**현재 설계**: AI 모델은 LLM에만 위임
- 장점: 다양한 표현("머신러닝", "신경망", "예측 모델" 등)을 LLM이 유연하게 처리
- 단점: 항상 LLM 호출이 필요 (느림)

**개선 옵션**:
1. regex로 AI 관련 패턴을 `_extract_technical_signals()`에 추가
   ```python
   # 예: "ai모델", "인공지능", "머신러닝", "딥러닝", "신경망" 등
   if re.search(r"(?:ai|인공지능|머신러닝|딥러닝|신경망|예측모델).*?매수", compact):
       entry.append(TechnicalSignal(indicator="ai_model", ...))
   ```
   하지만 메모리의 [[feedback_nl_parser_hybrid.md]]에 따르면:
   > "phrasing마다 regex 추가 금지 — 핵심만 결정적, 긴 꼬리는 LLM 프롬프트+서술형 신호 신뢰"
   
   따라서 현재 설계(LLM 위임)가 의도된 것.

### 3. 키워드 화이트리스트의 제한

```python
_INDICATOR_KEYWORDS["ai_model"] = ["ai", "인공지능"]
```

프롬프트에 "인공지능 알고리즘", "AI 모델", "AI 예측" 등 다양한 표현이 있어도 검증은 `["ai", "인공지능"]`만 확인합니다.

---

## 🎯 권장사항

### 1. 사용자 입력 시 권장 표현

```
✅ 권장 (통과 확률 높음):
- "AI 모델이 상승 예측하면 매수"
- "AI 모델 하락 시 매도"
- "인공지능 신호 기반 매수"
- "AI로 선정한 종목 매수"

⚠️ 주의 (LLM이 맞게 파싱해도 검증에서 차단될 수 있음):
- "머신러닝으로 매수"
- "딥러닝 신호"
- "신경망 예측"  → "AI"를 명시하면 ✅
```

### 2. NL 파서 개선 방안

**현재 구조 유지하면서 검증 강화**:

```python
# 라인 831-832 수정 제안
_INDICATOR_KEYWORDS = {
    ...
    "ai_model": ["ai", "인공지능", "머신러닝", "딥러닝", "신경망", "예측모델"],
    "ai_drop_model": ["ai", "인공지능", "머신러닝", "딥러닝", "신경망", "예측모델"],
    ...
}
```

**단, 메모리의 NL 파서 하이브리드 원칙에 따르면**:
- 핵심 키워드만 결정적으로 정의
- 긴 꼬리(다양한 표현)는 LLM이 담당하도록 설계됨
- 따라서 위 개선은 설계 원칙과 충돌할 수 있음

### 3. 사용자 경험 개선

**설명/안내 추가**:
```
프롬프트: "머신러닝으로 매수"
파서 결과: ai_model 신호 생성
검증 단계: ❌ 차단 (키워드 미일치)

→ 사용자 피드백:
"머신러닝은 '인공지능(AI)' 신호로 해석됩니다. 
 명확하게 'AI 모델로 매수'라고 입력하면 더 정확한 처리가 됩니다."
```

---

## 📊 종합 흐름도

```
사용자 입력: "AI 모델이 상승 예측한 종목 매수"
│
├─→ [1] _parse_rule_based_strategy()
│   └─→ _extract_technical_signals() → [] (AI 패턴 없음)
│   └─→ 충분하지 않음 → LLM 폴백
│
├─→ [2] LLM (MLX/Ollama) 호출
│   └─→ SYSTEM_PROMPT의 예시 참고
│   └─→ ParsedStrategy 생성:
│       - entry_signals: [TechnicalSignal(indicator="ai_model", signal_type="buy", threshold=70)]
│       - exit_signals: []
│
├─→ [3] _apply_prompt_overrides()
│   ├─→ _validate_signals() 호출
│   │   └─→ "ai" 찾기: ✓ 있음 (AI 모델)
│   │   └─→ 검증 통과
│   ├─→ _extract_technical_signals() 호출
│   │   └─→ AI 관련 규칙 없음, [] 반환
│   └─→ 최종 ParsedStrategy 반환
│
└─→ 최종 결과:
    entry_signals: [ai_model(buy, threshold=70)]
    exit_signals: []
    max_positions: 10
    ...
```

---

## 📝 테스트 파일

- `test_ai_model_parsing.py` - 기본 인식 테스트
- `test_ai_model_detailed.py` - 전체 파이프라인 상세 테스트
- `AI_MODEL_PARSING_REPORT.md` - 이 보고서

**실행**:
```bash
python test_ai_model_parsing.py
python test_ai_model_detailed.py
```

---

**작성일**: 2025-06-09  
**상태**: ✅ 분석 완료
