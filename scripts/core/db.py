# scripts/core/db.py
"""SQLite 数据库连接与初始化。

设计原则：
- 单文件零运维，与 prices.json 同目录
- schema.sql 集中管理建表语句，支持幂等执行
- DAO 层封装 SQL，后续迁移 MySQL/Postgres 只需改本文件连接逻辑
"""
import sqlite3
from pathlib import Path
from typing import Optional

_DB_PATH = Path("data/prices.db")
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取 SQLite 连接，自动初始化 schema。

    使用 check_same_thread=False 支持 cron 脚本多线程场景。
    """
    path = db_path or _DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 支持按列名访问
    conn.execute("PRAGMA journal_mode=WAL")  # 并发读不阻塞写
    conn.execute("PRAGMA foreign_keys=ON")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    """读取 schema.sql 执行建表（幂等）。"""
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def reset_db(db_path: Optional[Path] = None) -> None:
    """重置数据库（仅测试用）。删除文件后重新初始化。"""
    path = db_path or _DB_PATH
    if path.exists():
        path.unlink()
    # WAL 模式会产生 -wal 和 -shm 文件，一并清理
    for suffix in ["-wal", "-shm"]:
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()
    get_connection(path)
