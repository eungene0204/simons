"""Restore an app-schema snapshot to a private, disposable PostgreSQL cluster."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from dotenv import dotenv_values
import pyarrow.parquet as parquet
import psycopg
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parents[1]
COUNTS = """
SELECT (SELECT count(*) FROM "Strategy"),
       (SELECT count(*) FROM "BacktestHistory"),
       (SELECT count(*) FROM "BacktestResult"),
       (SELECT count(*) FROM "BacktestHistory" h JOIN "Strategy" s ON s.id=h."strategyId"),
       (SELECT count(*) FROM "BacktestResult" r JOIN "Strategy" s ON s.id=r."strategyId"),
       (SELECT count(*) FROM "ResearchNote" WHERE slug='myth-01-breakout-chasing'
          AND status='PUBLISHED')
"""


def main():
    conn = conninfo_to_dict(dotenv_values(ROOT / ".env")["DIRECT_URL"])
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    # Supply credentials only to the source client. Local commands use the private socket.
    source_env = dict(env, PGHOST=conn["host"], PGPORT=conn.get("port", "5432"),
                      PGDATABASE=conn["dbname"], PGUSER=conn["user"],
                      PGPASSWORD=conn["password"], PGSSLMODE="require",
                      PGOPTIONS="-c default_transaction_read_only=on")
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="ns-drill-", dir="/tmp") as directory:
        tmp = Path(directory)
        cluster = tmp / "pg"
        dump = tmp / "app.dump"
        with psycopg.connect(**conn, sslmode="require") as source:
            source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            snapshot, as_of = source.execute("SELECT pg_export_snapshot(), now()").fetchone()
            expected = source.execute(COUNTS).fetchone()
            if min(expected) < 1:
                raise RuntimeError("Source lacks linked strategies, results or the published KR note")
            subprocess.run(["pg_dump", "-Fc", "--schema=public", "--no-acl",
                            "--lock-wait-timeout=10s", "--snapshot", snapshot, "-f", dump],
                           env=source_env, check=True)
        # The local KR price mirror is the recovery source for this drill.
        prices = ROOT / "data/ohlcv"
        inputs = sorted(prices.glob("*.parquet"))
        if not inputs:
            raise RuntimeError("Empty KR price mirror")
        started = time.monotonic()
        local = dict(env, PGHOST=directory, PGUSER="drill", PGDATABASE="postgres")
        subprocess.run(["initdb", "-D", cluster, "-U", "drill", "--no-locale", "-E", "UTF8"],
                       env=local, stdout=subprocess.DEVNULL, check=True)
        subprocess.run(["pg_ctl", "-D", cluster, "-l", tmp / "server.log", "-o",
                        f"-k {directory} -c listen_addresses=''","-w", "start"], env=local, check=True)
        try:
            # The archive creates public. Remove only initdb's empty namespace.
            with psycopg.connect(host=directory, user="drill", dbname="postgres") as fresh:
                fresh.execute("DROP SCHEMA public RESTRICT")
            subprocess.run(["pg_restore", "--exit-on-error", "--no-owner", "--no-acl",
                            "-d", "postgres", dump], env=local, check=True)
            with psycopg.connect(host=directory, user="drill", dbname="postgres") as restored:
                if restored.execute(COUNTS).fetchone() != expected:
                    raise RuntimeError("Restored counts or relationships differ from snapshot")
            out = tmp / "ohlcv"
            out.mkdir()
            for src in inputs:
                dest = Path(shutil.copyfile(src, out / src.name))
                if (hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dest.read_bytes()).digest()
                        or parquet.ParquetFile(dest).metadata.num_rows < 1):
                    raise RuntimeError(f"Invalid restored price file: {src.name}")
            print(f"snapshot={as_of.isoformat()} restore_seconds={time.monotonic()-started:.1f} "
                  f"counts={expected} verified_price_files={len(inputs)}")
        finally:
            subprocess.run(["pg_ctl", "-D", cluster, "-m", "fast", "-w", "stop"], env=local, check=True)


if __name__ == "__main__":
    main()
