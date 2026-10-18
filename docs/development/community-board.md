# 자유게시판 구현 명세

Task: 로그인 없는 텍스트 자유게시판과 관리자 검수 구현.

Boundary: Y — Anonymous Community Board (사용자 승인 2026-10-19).

Files allowed: app/board/**, app/api/board/**, lib/board/**, prisma/schema.prisma,
prisma/migrations/20261019000000_community_board/**, components/providers/QueryProvider.tsx,
components/strategy/StrategyExampleTabs.tsx, lib/i18n/en.ts, tests/board.test.ts,
docs/development/community-board.md, docs/architecture/boundaries.md,
docs/PROJECT_PLAN.md, docs/software_architecture.md, docs/SRS.md.
추가 분류 마이그레이션: prisma/migrations/20261019010000_add_board_notice_category/migration.sql.
즉시 공개 마이그레이션: prisma/migrations/20261019020000_board_immediate_publication/migration.sql.
기존 연결 회귀 테스트: components/__tests__/StrategyExampleTabs.test.tsx,
components/__tests__/AuthSessionGuard.test.tsx.

Do not: 기존 인증·전략·백테스트 계약 변경, HTML/첨부 제공, 비밀번호/IP 공개.

Requirements: PostgreSQL 영속 저장, 익명 비밀번호 검증, 공지/정보/질문/건의/자유 분류,
검색·분류·페이지 처리, 댓글 CRUD, 신고·관리자 검수, DB 기반 요청 제한,
허니팟·중복·링크 검사, 기존 다크 테마와 공개 경로 연결.

UI 보정: 분류 선택 상자는 내용에 맞춰 폭을 줄이고, 사용자 정의 화살표를 오른쪽 테두리에서
12px 안쪽에 배치해 화살표 오른쪽 여백을 확보한다.
목록은 전체 게시글 수를 매 요청마다 세지 않고 21번째 결과로 다음 페이지 유무를 판단한다.
화면에서는 최근 조회 목록을 짧게 재사용해 페이지 이동과 브라우저 이력 복귀를 빠르게 표시한다.

Run: npm run db:generate; npm run test:frontend; npm run lint; npm run build.
실제 DB 환경에서는 마이그레이션 및 HTTP 저장/재시작 검증.

Deliver: 동작 코드, 마이그레이션, 검증 결과와 운영 제한 기록.

사용자가 전체 구현을 승인했으므로 이 기능의 파일 수/줄 수 제한은 예외로 한다.

## 실행 및 운영

- 공개 경로: /board (상세는 ?id=<ID>, 작성은 ?view=new).
- 관리 화면: /board?view=admin. 기존 token 쿠키와 ACTIVE/ADMIN DB 권한을
  requireAdmin으로 검증한다. 비인증 접근은 API에서 404로 차단한다.
- 기존 PostgreSQL DATABASE_URL, DIRECT_URL 및 JWT_SECRET 사용.
  별도 BOARD_ABUSE_SECRET을 설정하면 악용 방지 HMAC 키를 인증 키와 분리한다.
- npm run db:generate, npx prisma migrate deploy 이후 npm run dev 또는
  npm run build && npm start. 실행 중이던 서버는 Prisma client 갱신을 위해 재시작한다.
- 마이그레이션은 20261019000000_community_board 하나이며 기존 테이블은 변경하지 않는다.
- BOARD_TRUSTED_IP_HEADER는 선택 설정이다. 외부 요청에서 해당 헤더를 제거하고
  실제 연결 IP 하나로 덮어쓰는 신뢰된 ingress를 구성한 경우에만 설정한다.
  쉼표로 이어진 전달 체인은 허용하지 않는다. 설정이 없거나 유효 IP가 아니면
  모든 요청에 보수적인 공통 제한을 적용한다. 기본으로 X-Forwarded-For를 신뢰하지 않는다.
- 원본 IP는 게시판 DB에 저장하지 않는다. UTC 날짜별 HMAC 식별자는 신고에
  최대 24시간, 요청 제한에 버킷 만료 시점까지 필요하며 다음 쓰기 요청에서 정리한다.
  트래픽이 없어도 물리적 보존 기간을 지키려면 운영 DB 스케줄러에서 매시간
  아래 두 쿼리를 실행한다.

```sql
DELETE FROM "BoardGuard" WHERE "expiresAt" < CURRENT_TIMESTAMP;
UPDATE "BoardReport" SET "reporter" = NULL
WHERE "expiresAt" < CURRENT_TIMESTAMP AND "reporter" IS NOT NULL;
```

## 제한과 검수

- 생성 8회/10분, 모든 쓰기 40회/10분, 비밀번호 확인 식별자당 10회/10분,
  대상당 30회/10분. 신고 10회/일, 동일 대상 1회/일. 고정 시간 버킷이며
  DB atomic upsert로 여러 프로세스에서도 공유한다.
- 정규화한 동일 제목/본문은 5분간 반복 등록을 차단한다. 링크 최대 3개,
  HTML 태그 및 긴 반복 문자를 거절하고 허니팟을 검사한다.
- 자동 검수는 게시글/댓글을 작성 즉시 공개한다. 명백한 정책 위반 패턴은 저장을 거절한다.
  규칙 기반 검수에는 오탐과 누락이 가능하며 유료 AI나 CAPTCHA를 사용하지 않는다.
  게시 이후 신고는 관리자에게 전달되며 신고 수만으로 상태를 변경하거나 삭제하지 않는다.
- 숨김/삭제 콘텐츠는 모든 공개 조회에서 제외한다. 댓글은 부모 게시글도
  공개 상태여야 읽거나 변경할 수 있다. 공개 댓글만 목록 카운트에 포함한다.
- 신고 검토와 게시물 조치는 BoardAudit에 관리자 ID, 대상, 상태, 사유, 시각을 기록한다.
  실제 관리자가 신고 큐를 처리해야 한다.
- 본문은 React 텍스트로 렌더링한다. 비밀번호는 4~64자(UTF-8 72바이트 이내)로 검증해 bcrypt cost 12로 저장하고
  조회 응답은 명시적인 필드 선택만 사용한다.
- 사용자 비밀번호 변경/복구, 첨부, HTML 편집, 실시간 댓글 갱신은 제공하지 않는다.

## 검증 기록 (2026-10-19)

- 배포 CI 회귀 수정: 즉시 게시 검수 함수의 반환값 대신 허용/거절 동작을 검증하고,
  게시판 화면 테스트에 실제 앱과 동일한 QueryClientProvider를 구성한다.
  각 테스트는 독립 QueryClient를 사용해 조회 캐시가 다음 테스트에 섞이지 않도록 한다.
- 재배포 전 재검증: 게시판 15개 테스트 및 전체 프런트 테스트 2,558개 통과
  (345개 파일 통과, 1개 파일/2개 테스트 skip). lint와 격리 폴더의 production build 성공.
  이전 배포 CI의 backend/engine-version-guard는 통과했으며 실패는 게시판 테스트 3건이었다.

- npm run db:generate 성공. npx prisma migrate deploy로 기존 연결 DB에
  신규 마이그레이션 적용 완료. DB 연결 및 게시판 테이블 조회 확인.
- npm run test:frontend: 345개 파일 통과, 1개 파일 skip;
  2,558개 테스트 통과, 2개 skip. 기존 메뉴 순서 테스트는 가이드→게시판→약관
  요구사항에 맞춰 갱신했다. i18n 커버리지·모션 감소 가드도 통과했다.
- 게시판 전용 API/화면 회귀 15개 통과. 비밀번호 해시, 비밀번호 오류/성공,
  부모 공개 필터, 검색/분류/페이지, 신고/요청 제한, 관리자 접근 차단,
  허니팟, 텍스트 XSS 렌더링을 포함한다.
- npm run lint 성공(기존 다른 기능의 hook/img 경고는 남음).
- npm run build 성공. 실행 중인 개발 서버의 .next와 충돌하지 않도록
  소스를 /tmp/simons-board-validation에 복사한 별도 작업 폴더에서 검증했다.
- 실제 localhost:3000 HTTP 및 PostgreSQL 검증: 게시글/댓글 생성·수정·삭제,
  올바른/잘못된 비밀번호, 명시적인 bcrypt 해시 DB 확인, 반복 조회,
  검색·분류·2페이지, 위반 콘텐츠 거절, 관리자 숨김과 감사 기록,
  신고 저장 및 중복 신고 429, HTML 거절 및 허니팟 거절 확인.
- 프런트엔드 서버를 실제 종료·재시작한 뒤 저장된 글의 제목/수정 본문을
  HTTP로 재조회해 영속성을 확인했다. 상세 페이지 200, 올바른 비밀번호
  게시글 삭제 200, 삭제 후 상세 404 확인. 생성한 QA 글·댓글·신고·감사 기록과
  임시 QA 관리자만 DB에서 정리했다. 개발 서버는 3000 포트에서 재시작된 상태다.
- 공유 단위 테스트 외 별도 미국 검사/예시 게이트/실모델 호출은 사용자 지시로 제외.
- 연결 가능한 브라우저가 없어 실제 모바일/데스크톱 스크린샷 검증은 수행하지 못했다.
  반응형 클래스와 화면 컴포넌트 테스트로 검증했다.
