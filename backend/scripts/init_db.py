"""执行 db/schema.sql 建库建表。

用法（在 backend 目录下）:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config.settings import settings


def split_sql_statements(sql: str) -> list[str]:
    """按分号拆分 SQL，忽略注释行。"""
    statements: list[str] = []
    buffer: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buffer).strip()
            if stmt:
                statements.append(stmt)
            buffer = []

    if buffer:
        stmt = "\n".join(buffer).strip()
        if stmt:
            statements.append(stmt)

    return statements


def main() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "db" / "schema.sql"
    if not schema_path.exists():
        print(f"找不到建表脚本: {schema_path}")
        sys.exit(1)

    sql = schema_path.read_text(encoding="utf-8")
    statements = split_sql_statements(sql)
    print(f"读取 {schema_path.name}，共 {len(statements)} 条 SQL")

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
                preview = stmt.replace("\n", " ")[:80]
                try:
                    cur.execute(stmt)
                    print(f"  [{i}/{len(statements)}] OK: {preview}...")
                except Exception as exc:
                    print(f"  [{i}/{len(statements)}] FAIL: {preview}...")
                    print(f"         错误: {exc}")
                    raise

        with conn.cursor() as cur:
            cur.execute(f"USE `{settings.mysql_database}`")
            cur.execute("SHOW TABLES")
            tables = [row[0] for row in cur.fetchall()]
            print(f"\n建表完成！共 {len(tables)} 张表:")
            for name in tables:
                print(f"  - {name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
