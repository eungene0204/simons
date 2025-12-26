# 주식 데이터 API 추천 가이드

## 상황별 추천

### MVP / 빠른 개발 (무료 우선)
1. **Alpha Vantage** (현재 구현됨)
   - 무료 티어: 5 calls/min, 500 calls/day
   - 글로벌 주식 지원 (미국, 유럽 등)
   - 한국 주식 지원 안됨
   - 장점: 빠른 설정, 무료
   - 단점: 호출 제한, 한국 주식 없음

2. **Yahoo Finance (비공식)**
   - 무료
   - yfinance 라이브러리 사용 필요 (Node.js에서는 구현 복잡)
   - 장점: 무료, 다양한 데이터
   - 단점: 비공식, 안정성 낮음

### 한국 주식 전용
1. **한국투자증권 OpenAPI (KIS)**
   - 공식 API
   - 한국 주식 실시간 데이터
   - 무료 티어 있음
   - 장점: 공식, 한국 주식 완벽 지원
   - 단점: 설정 복잡, 인증 절차 필요
   - 링크: https://apiportal.koreainvestment.com/

2. **삼성증권 API**
   - 공식 API
   - 한국 주식 지원
   - 장점: 공식 API
   - 단점: 접근 제한적

### 프로덕션 / 유료 옵션
1. **Finnhub**
   - 무료: 60 calls/min
   - 유료: $19/月起
   - 글로벌 + 한국 주식 지원
   - 장점: 안정적, 한국 주식 지원
   - 단점: 무료 티어 제한적

2. **IEX Cloud**
   - 무료 티어: 제한적
   - 유료: $9/月起
   - 미국 주식 중심
   - 장점: 안정적, 빠름
   - 단점: 한국 주식 없음

3. **Polygon.io**
   - 유료: $29/月起
   - 글로벌 주식
   - 장점: 매우 안정적, 실시간 데이터
   - 단점: 비용

## 추천 조합

### 옵션 1: 빠른 시작 (현재 구현)
- **글로벌**: Alpha Vantage (무료)
- **한국**: Alpha Vantage는 한국 주식 미지원 → 다른 API 필요

### 옵션 2: 한국 주식 포함 (권장)
- **한국 주식**: 한국투자증권 OpenAPI
- **글로벌 주식**: Alpha Vantage 또는 Finnhub
- 코드에서 심볼에 따라 자동으로 API 선택

### 옵션 3: 프로덕션
- **통합**: Finnhub (한국 + 글로벌 모두 지원)
- 또는 **한국투자증권 + Finnhub** 조합

## 구현 전략

현재 코드 구조는 이미 여러 API를 지원하도록 설계되어 있습니다:

```typescript
// lib/stock-api/index.ts에서 프로바이더 선택
STOCK_API_PROVIDER=alpha-vantage  // 필요 시 kis 등
```

### 다음 단계 제안:
1. **즉시**: Alpha Vantage로 MVP 시작 (글로벌 주식)
2. **단기**: 한국투자증권 API 추가 구현 (한국 주식)
3. **중기**: Finnhub 추가 (한국 + 글로벌 통합 대안)

## API별 구현 필요 사항

### Alpha Vantage (현재 구현됨 ✅)
- 구현 완료
- 환경 변수: `ALPHA_VANTAGE_API_KEY`

### 한국투자증권 OpenAPI (구현 필요)
- 인증 토큰 발급 로직
- 한국 주식 심볼 형식 (예: "005930" - 삼성전자)
- API 엔드포인트 구현
- 환경 변수: `KIS_APP_KEY`, `KIS_APP_SECRET`, `KIS_ACCOUNT_NO`

### Finnhub (구현 필요)
- API 키만 필요
- 한국 + 글로벌 모두 지원
  (Naver 사용 시 별도 환경 변수 없음)

## 결론 및 추천

**MVP 단계**: Alpha Vantage로 시작 (이미 구현됨)

**한국 주식 추가 필요 시**: 
1. 한국투자증권 OpenAPI 구현 (추천)
2. 또는 Finnhub로 전환 (한국 + 글로벌 통합)

**프로덕션**: Finnhub 또는 한국투자증권 API 사용

