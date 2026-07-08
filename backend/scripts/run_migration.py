"""执行 db/migrations/ 下的 SQL 迁移脚本。"""

import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config.settings import settings
from scripts.init_db import split_sql_statements


def run_migration(sql_file: Path) -> None:
    sql = sql_file.read_text(encoding="utf-8")
    statements = split_sql_statements(sql)
    print(f"执行迁移: {sql_file.name}，共 {len(statements)} 条 SQL")

    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                cur.execute(stmt)
                print(f"  [{i}/{len(statements)}] OK")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python scripts/run_migration.py db/migrations/xxx.sql")
        sys.exit(1)
    run_migration(Path(sys.argv[1]))
