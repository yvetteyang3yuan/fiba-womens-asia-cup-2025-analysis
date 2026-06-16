import sqlite3
from pathlib import Path

import pandas as pd

from src.config import DB_PATH, EVENT_NAME, ensure_directories


# 三张核心表的字段顺序。插入 DataFrame 时会按这个顺序对齐字段。
GAME_COLUMNS = [
    "game_id",
    "game_no",
    "event_name",
    "game_date",
    "stage",
    "team_home",
    "team_away",
    "score_home",
    "score_away",
    "winner",
    "game_url",
]

TEAM_BOXSCORE_COLUMNS = [
    "game_id",
    "game_no",
    "team",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "fouls",
    "fg_pct",
    "three_pct",
    "ft_pct",
    "source_url",
]

PLAYER_BOXSCORE_COLUMNS = [
    "game_id",
    "game_no",
    "team",
    "player_name",
    "starter",
    "minutes",
    "minutes_float",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "fouls",
    "fgm",
    "fga",
    "fg_pct",
    "three_pm",
    "three_pa",
    "three_pct",
    "ftm",
    "fta",
    "ft_pct",
    "efficiency",
    "source_url",
]


# SQLite 建表语句。CREATE TABLE IF NOT EXISTS 可以保证重复运行不报错。
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    game_no INTEGER,
    event_name TEXT,
    game_date TEXT,
    stage TEXT,
    team_home TEXT,
    team_away TEXT,
    score_home INTEGER,
    score_away INTEGER,
    winner TEXT,
    game_url TEXT
);

CREATE TABLE IF NOT EXISTS team_boxscores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT,
    game_no INTEGER,
    team TEXT,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    fouls INTEGER,
    fg_pct REAL,
    three_pct REAL,
    ft_pct REAL,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS player_boxscores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT,
    game_no INTEGER,
    team TEXT,
    player_name TEXT,
    starter TEXT,
    minutes TEXT,
    minutes_float REAL,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    steals INTEGER,
    blocks INTEGER,
    turnovers INTEGER,
    fouls INTEGER,
    fgm INTEGER,
    fga INTEGER,
    fg_pct REAL,
    three_pm INTEGER,
    three_pa INTEGER,
    three_pct REAL,
    ftm INTEGER,
    fta INTEGER,
    ft_pct REAL,
    efficiency REAL,
    source_url TEXT
);
"""


EXPECTED_COLUMNS = {
    "games": GAME_COLUMNS,
    "team_boxscores": ["id", *TEAM_BOXSCORE_COLUMNS],
    "player_boxscores": ["id", *PLAYER_BOXSCORE_COLUMNS],
}


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """获取 SQLite 数据库连接。"""
    ensure_directories()
    return sqlite3.connect(db_path)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    """判断数据表是否已经存在。"""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return cursor.fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """读取数据表当前字段名。"""
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]


def _table_is_empty(conn: sqlite3.Connection, table_name: str) -> bool:
    """判断数据表是否为空。"""
    cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    return cursor.fetchone()[0] == 0


def _drop_empty_mismatched_tables(conn: sqlite3.Connection) -> None:
    """如果旧表为空且字段不一致，则删除后用新 schema 重建。"""
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        if not _table_exists(conn, table_name):
            continue
        current_columns = _table_columns(conn, table_name)
        if current_columns != expected_columns and _table_is_empty(conn, table_name):
            conn.execute(f"DROP TABLE {table_name}")


def init_db(db_path: Path = DB_PATH) -> None:
    """初始化 SQLite 数据库和三张核心数据表。"""
    ensure_directories()
    with get_connection(db_path) as conn:
        _drop_empty_mismatched_tables(conn)
        conn.executescript(SCHEMA_SQL)


def _prepare_dataframe(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """把传入 DataFrame 对齐到数据库字段，缺失字段补空值。"""
    data = df.copy()
    for column in columns:
        if column not in data.columns:
            data[column] = None
    return data[columns]


def insert_games(df: pd.DataFrame) -> None:
    """插入 games 表数据。"""
    if df.empty:
        return
    init_db()
    data = _prepare_dataframe(df, GAME_COLUMNS)
    data["event_name"] = data["event_name"].fillna(EVENT_NAME)
    with get_connection() as conn:
        data.to_sql("games", conn, if_exists="append", index=False)


def insert_team_boxscores(df: pd.DataFrame) -> None:
    """插入 team_boxscores 表数据。"""
    if df.empty:
        return
    init_db()
    data = _prepare_dataframe(df, TEAM_BOXSCORE_COLUMNS)
    with get_connection() as conn:
        data.to_sql("team_boxscores", conn, if_exists="append", index=False)


def insert_player_boxscores(df: pd.DataFrame) -> None:
    """插入 player_boxscores 表数据。"""
    if df.empty:
        return
    init_db()
    data = _prepare_dataframe(df, PLAYER_BOXSCORE_COLUMNS)
    with get_connection() as conn:
        data.to_sql("player_boxscores", conn, if_exists="append", index=False)


def replace_game(conn: sqlite3.Connection, game: dict, teams: list[dict], players: list[dict]) -> None:
    """按 game_id 覆盖写入单场比赛数据，兼容解析器调用。"""
    game_id = game["game_id"]
    conn.execute("DELETE FROM player_boxscores WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM team_boxscores WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM games WHERE game_id = ?", (game_id,))

    game_df = _prepare_dataframe(pd.DataFrame([game]), GAME_COLUMNS)
    game_df["event_name"] = game_df["event_name"].fillna(EVENT_NAME)
    game_df.to_sql("games", conn, if_exists="append", index=False)

    if teams:
        team_df = _prepare_dataframe(pd.DataFrame(teams), TEAM_BOXSCORE_COLUMNS)
        team_df.to_sql("team_boxscores", conn, if_exists="append", index=False)

    if players:
        player_df = _prepare_dataframe(pd.DataFrame(players), PLAYER_BOXSCORE_COLUMNS)
        player_df.to_sql("player_boxscores", conn, if_exists="append", index=False)
