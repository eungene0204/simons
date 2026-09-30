-- 검색 그라운딩 학습 어휘집(2026-09-30) — git 밖 파일(data/term_lexicon.json)이 환경마다 따로
-- 자라 같은 문장이 로컬·운영에서 다르게 풀렸다('bts 관련주'). 공유 DB로 옮겨 한 곳에서 배운
-- 내용을 모든 환경이 읽는다. additive: 새 테이블만 추가, 기존 데이터 무영향.
CREATE TABLE "TermLexiconEntry" (
    "key" TEXT NOT NULL,
    "entry" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "TermLexiconEntry_pkey" PRIMARY KEY ("key")
);
