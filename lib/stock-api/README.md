# Stock API Provider

주식 데이터를 가져오기 위한 추상화된 API 프로바이더 시스템입니다.

## 지원하는 API

### 현재 구현
- **Alpha Vantage**: 무료 티어 지원 (5 calls/min, 500 calls/day)

### 향후 추가 가능
- Yahoo Finance API
- IEX Cloud
- Finnhub
- 한국투자증권 API (한국 주식)

## 사용 방법

### 환경 변수 설정

`.env.local` 파일에 다음을 추가하세요:

```env
# Stock API Configuration
STOCK_API_PROVIDER=alpha-vantage
ALPHA_VANTAGE_API_KEY=your_api_key_here
```

### API 엔드포인트

#### 1. 주식 실시간 가격 조회
```
GET /api/stock/quote?symbol=AAPL
```

#### 2. 주식 검색
```
GET /api/stock/search?q=apple
```

#### 3. 과거 데이터 조회
```
GET /api/stock/historical?symbol=AAPL&interval=daily&period=compact
```

#### 4. 주식 개요 정보
```
GET /api/stock/overview?symbol=AAPL
```

## 기능

- **자동 재시도**: API 호출 실패 시 자동 재시도 (최대 3회)
- **캐싱**: 메모리 기반 캐싱으로 API 호출 최소화
- **에러 핸들링**: 통일된 에러 처리
- **타입 안정성**: TypeScript로 완전한 타입 지원

## 캐시 설정

- **Quote**: 60초 (1분)
- **Search**: 3600초 (1시간)
- **Historical**: 300초 (5분)
- **Overview**: 3600초 (1시간)

## API Key 얻기

### Alpha Vantage
1. https://www.alphavantage.co/support/#api-key 방문
2. 무료 API 키 신청
3. 이메일 확인 후 API 키 복사

### 제한 사항
- 무료 티어: 5 calls/min, 500 calls/day
- 캐싱을 통해 제한을 최소화합니다


