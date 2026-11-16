-- public 테이블 전체에 행 단위 보안(RLS)을 켠다(2026-11-17, 예방 조치).
-- 정책을 하나도 만들지 않으므로 Supabase Data API 역할(anon·authenticated)에게는 '전부 거부'가 된다.
-- 지금도 이 역할들은 public 스키마 권한이 없어 접근할 수 없다(운영 실측) — 권한이 실수로 열려도
-- 데이터가 나가지 않게 하는 두 번째 잠금이다.
-- 앱(Prisma·파이썬)은 테이블 소유자이자 BYPASSRLS인 postgres 역할로 붙으므로 영향이 없다.
-- FORCE는 걸지 않는다 — 소유자로 붙는 CI·로컬 테스트 DB도 그대로 동작한다.
-- 이후 새로 만드는 테이블에는 자동으로 켜지지 않는다: 새 테이블 마이그레이션에 ENABLE을 함께 넣는다.
SET lock_timeout = '5s';
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.relname);
  END LOOP;
END $$;
RESET lock_timeout;
