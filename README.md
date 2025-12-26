# Simons - 주식투자 도움 사이트

주식투자에 도움을 주는 MVP 웹사이트입니다.

## 기술 스택

- **Next.js 14**: React 기반 풀스택 프레임워크
- **TypeScript**: 타입 안정성
- **Tailwind CSS**: 빠른 스타일링
- **Prisma**: ORM 및 데이터베이스 관리
- **SQLite**: 개발용 데이터베이스
- **bcryptjs**: 비밀번호 해싱
- **JWT**: 세션 관리
- **Recharts**: 차트 라이브러리
- **Axios**: API 호출

## 시작하기

1. 의존성 설치:

```bash
npm install
```

2. 환경 변수 설정:
   `.env.local` 파일을 생성하고 다음 내용을 추가하세요:

```
DATABASE_URL="file:./dev.db"
JWT_SECRET=your_secret_key_here_change_in_production
```

3. 데이터베이스 마이그레이션:

```bash
npm run db:migrate
```

4. Prisma Client 생성:

```bash
npm run db:generate
```

5. 개발 서버 실행:

```bash
npm run dev
```

브라우저에서 [http://localhost:3000](http://localhost:3000)을 열어 확인하세요.

## 데이터베이스 관리

- **마이그레이션 실행**: `npm run db:migrate`
- **Prisma Studio 열기**: `npm run db:studio` (데이터베이스 GUI 도구)
- **Prisma Client 재생성**: `npm run db:generate`

## 로그인 시스템

- **회원가입**: `/register` 페이지에서 새 계정 생성
- **로그인**: `/login` 페이지에서 로그인
- **세션 관리**: JWT 토큰 기반 쿠키 세션
- **API 엔드포인트**:
  - `POST /api/register` - 회원가입
  - `POST /api/login` - 로그인
  - `POST /api/logout` - 로그아웃

## 추천 주식 데이터 API

### 한국 주식 지수 (코스피, 코스닥)

1. **Naver Finance (비공식)**
   - 별도 API 키 불필요 (엔드포인트 변경 가능성 있음)
   - MVP 단계에서 빠르게 적용

### 글로벌 주식

1. **Alpha Vantage** (무료): https://www.alphavantage.co/
   - 무료 티어: 5 calls/min, 500 calls/day
2. **Yahoo Finance API** (무료, 비공식): yfinance 라이브러리 사용
3. **IEX Cloud** (유료, 무료 티어 있음): https://iexcloud.io/

### 한국 주식 (개별 종목)

- 한국투자증권 OpenAPI, KIS Developers API
- 코스콤 오픈API

## 환경 변수 설정

### 한국 지수 (코스피, 코스닥)

Naver Finance 비공식 엔드포인트를 사용하므로 별도 환경 변수는 필요하지 않습니다.

### 기타 주식 데이터 API (선택)

```env
# Alpha Vantage (글로벌 주식용)
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key

# 사용할 API 프로바이더 선택
STOCK_API_PROVIDER=alpha-vantage
```

## 프로젝트 구조

```
simons/
├── app/              # Next.js App Router
│   ├── page.tsx     # 메인 페이지
│   ├── layout.tsx   # 레이아웃
│   └── api/         # API 라우트
├── components/       # React 컴포넌트
├── lib/             # 유틸리티 함수
├── types/           # TypeScript 타입 정의
└── public/          # 정적 파일
```

## 주요 기능 (MVP)

- [ ] 주식 검색
- [ ] 주가 차트 표시
- [ ] 실시간 주가 정보
- [ ] 주식 뉴스/분석
- [ ] 포트폴리오 추적 (선택적)
