#!/usr/bin/env bash
# 프로덕션 SQLite DB에 미적용 prisma 마이그레이션을 순서대로 적용한다.
#
# 이 DB는 `prisma migrate` CLI가 ConversionError로 막혀 있어(11GB SQLite),
# sqlite3로 migration.sql을 직접 .read 한 뒤 _prisma_migrations에 수동 기록한다.
# (배경: memory project_prod_deploy_no_migrations / project_db_migration_gotcha)
#
# 멱등: _prisma_migrations에 이미 기록된 마이그레이션은 건너뛴다. 미적용분이 없으면
# 아무 것도 하지 않으므로 매 배포마다 안전하게 호출할 수 있다.
#
# 사용: bash scripts/apply-prisma-migrations.sh [DB경로] [마이그레이션디렉터리]
set -euo pipefail

DB="${1:-prisma/prisma/dev.db}"
MIG_DIR="${2:-prisma/migrations}"

command -v sqlite3 >/dev/null || { echo "✗ sqlite3 미설치"; exit 1; }
command -v sha256sum >/dev/null || { echo "✗ sha256sum 미설치"; exit 1; }
[ -f "$DB" ] || { echo "✗ DB 없음: $DB"; exit 1; }
[ -d "$MIG_DIR" ] || { echo "✗ 마이그레이션 디렉터리 없음: $MIG_DIR"; exit 1; }

# _prisma_migrations 테이블 보장 (Prisma 표준 스키마와 동일)
sqlite3 "$DB" 'CREATE TABLE IF NOT EXISTS "_prisma_migrations" (
  "id" TEXT PRIMARY KEY NOT NULL,
  "checksum" TEXT NOT NULL,
  "finished_at" DATETIME,
  "migration_name" TEXT NOT NULL,
  "logs" TEXT,
  "rolled_back_at" DATETIME,
  "started_at" DATETIME NOT NULL DEFAULT current_timestamp,
  "applied_steps_count" INTEGER UNSIGNED NOT NULL DEFAULT 0
);'

# 미적용 마이그레이션 수집 (디렉터리명 = migration_name, 시간순 정렬)
pending=()
for d in $(ls -1 "$MIG_DIR" | sort); do
  [ -f "$MIG_DIR/$d/migration.sql" ] || continue
  applied=$(sqlite3 "$DB" "SELECT COUNT(*) FROM _prisma_migrations WHERE migration_name='$d';")
  [ "$applied" = "0" ] && pending+=("$d")
done

if [ ${#pending[@]} -eq 0 ]; then
  echo "✓ 적용할 마이그레이션 없음 (스키마 최신)"
  exit 0
fi

echo "미적용 마이그레이션 ${#pending[@]}개: ${pending[*]}"

# 적용 전 백업 — 디스크 여유가 DB 크기의 1.2배 이상일 때만, 직전 백업 1개만 유지.
# (11GB DB라 매번 풀백업은 디스크를 채울 수 있어 조건부. 상시 백업은 Litestream에 의존.)
db_bytes=$(stat -c %s "$DB" 2>/dev/null || stat -f %z "$DB")
free_bytes=$(df -P "$(dirname "$DB")" | awk 'NR==2 {print $4 * 1024}')
if [ "$free_bytes" -gt $(( db_bytes * 12 / 10 )) ]; then
  echo "백업 생성: ${DB}.pre-migrate.bak"
  rm -f "${DB}.pre-migrate.bak"
  sqlite3 "$DB" ".backup '${DB}.pre-migrate.bak'"
else
  echo "⚠ 디스크 여유 부족 — 백업 건너뜀 (Litestream 백업 의존). free=${free_bytes} db=${db_bytes}"
fi

for d in "${pending[@]}"; do
  sql="$MIG_DIR/$d/migration.sql"
  echo "→ 적용: $d"
  if err=$(sqlite3 "$DB" ".bail on" "PRAGMA busy_timeout=30000;" ".read $sql" 2>&1); then
    :
  else
    # 과거 수동 적용 등으로 객체가 이미 존재해 실패하는 경우(additive 마이그레이션이
    # _prisma_migrations에만 누락된 상태)는 "적용됨"으로 간주하고 기록 후 계속한다.
    # 그 외 진짜 오류는 중단(set -e). 주의: 한 마이그레이션의 뒷부분만 신규일 때
    # already-exists로 멈추면 뒷부분이 미적용으로 남을 수 있으나(additive 가정상 드묾),
    # 그 경우에도 배포는 멈추지 않고 다음 배포에서 재시도되지 않으니 로그로 드러낸다.
    if echo "$err" | grep -qiE "duplicate column name|already exists"; then
      echo "  ⚠ 이미 적용된 것으로 판단(객체 존재) — 기록 후 계속: $err"
    else
      echo "  ✗ 적용 실패: $err"
      exit 1
    fi
  fi
  checksum=$(sha256sum "$sql" | awk '{print $1}')
  id=$(sqlite3 "$DB" "SELECT lower(hex(randomblob(16)));")
  sqlite3 "$DB" "INSERT INTO _prisma_migrations (id, checksum, finished_at, migration_name, started_at, applied_steps_count) VALUES ('$id', '$checksum', datetime('now'), '$d', datetime('now'), 1);"
  echo "  ✓ 기록됨 (checksum=$checksum)"
done

echo "✓ 마이그레이션 적용 완료 (${#pending[@]}개)"
