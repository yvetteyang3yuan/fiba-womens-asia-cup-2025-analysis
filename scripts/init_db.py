import _bootstrap  # noqa: F401

from src.config import DB_PATH
from src.db import init_db


if __name__ == "__main__":
    # 初始化 SQLite 数据库；表已存在时不会报错。
    init_db()
    print(f"SQLite 数据库和数据表已创建：{DB_PATH.as_posix()}")
