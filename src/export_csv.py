from pathlib import Path

import pandas as pd

from src.config import CLEAN_DIR, ensure_directories
from src.db import get_connection, init_db


# SQLite 表名 -> 导出 CSV 文件名。
EXPORT_TABLES = {
    "games": "games_from_db.csv",
    "team_boxscores": "team_boxscores_from_db.csv",
    "player_boxscores": "player_boxscores_from_db.csv",
}


def export_table_to_csv(table_name: str, output_path: Path) -> tuple[Path, int]:
    """从 SQLite 导出单张表到 CSV，返回文件路径和行数。"""
    ensure_directories()
    init_db()

    with get_connection() as conn:
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)

    # 即使 df 为空，pandas 也会保留数据库字段并写出表头。
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path, len(df)


def export_tables_to_csv(clean_dir: Path = CLEAN_DIR) -> list[dict]:
    """导出 games、team_boxscores、player_boxscores 三张表。"""
    ensure_directories()
    results: list[dict] = []

    for table_name, file_name in EXPORT_TABLES.items():
        output_path = clean_dir / file_name
        path, row_count = export_table_to_csv(table_name, output_path)
        results.append(
            {
                "table": table_name,
                "path": path,
                "row_count": row_count,
            }
        )

    return results
