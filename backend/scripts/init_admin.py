"""初始化 admin 账号密码。

用法（在 backend 目录下）:
    python scripts/init_admin.py
    python scripts/init_admin.py --password your_password
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from common.config.database import SessionLocal
from common.models import User
from common.utils.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="设置 admin 账号密码")
    parser.add_argument("--username", default="admin", help="用户名，默认 admin")
    parser.add_argument("--password", default="admin123", help="密码，默认 admin123")
    args = parser.parse_args()

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if not user:
            print(f"用户 {args.username} 不存在，请确认已执行 schema.sql")
            sys.exit(1)

        user.password_hash = hash_password(args.password)
        db.commit()
        print(f"已将用户 [{args.username}] 密码设置为: {args.password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
