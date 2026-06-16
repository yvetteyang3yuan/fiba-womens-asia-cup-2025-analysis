import pandas as pd

from src.db import get_connection


CHINA_KEYWORDS = ["China", "People's Republic of China", "中国"]


def safe_divide(a, b):
    """安全除法：分母为 0、空值或无法转换时返回 None。"""
    try:
        if pd.isna(a) or pd.isna(b):
            return None
        denominator = float(b)
        if denominator == 0:
            return None
        return float(a) / denominator
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def calculate_efg(fgm, three_pm, fga):
    """计算有效命中率 eFG% = (FGM + 0.5 * 3PM) / FGA。"""
    try:
        if pd.isna(fgm) or pd.isna(three_pm):
            return None
        return safe_divide(float(fgm) + 0.5 * float(three_pm), fga)
    except (TypeError, ValueError):
        return None


def calculate_ts(points, fga, fta):
    """计算真实命中率 TS% = PTS / (2 * (FGA + 0.44 * FTA))。"""
    try:
        if pd.isna(points) or pd.isna(fga) or pd.isna(fta):
            return None
        denominator = 2 * (float(fga) + 0.44 * float(fta))
        return safe_divide(points, denominator)
    except (TypeError, ValueError):
        return None


def calculate_ast_tov(assists, turnovers):
    """计算助攻失误比 AST/TOV = assists / turnovers。"""
    return safe_divide(assists, turnovers)


def calculate_per_minute(value, minutes_float):
    """计算每分钟数据。"""
    return safe_divide(value, minutes_float)


def calculate_per36(value, minutes_float):
    """计算每 36 分钟数据：value / minutes_float * 36。"""
    per_minute = calculate_per_minute(value, minutes_float)
    return None if per_minute is None else per_minute * 36


def _warn_missing_columns(df: pd.DataFrame, required_columns: list[str]) -> list[str]:
    """检查缺失字段并打印提示。"""
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        print(f"warning: 缺少字段，相关高级指标会填 None：{', '.join(missing)}")
    return missing


def _column_or_none(df: pd.DataFrame, column: str):
    """读取列；不存在时返回全 None 序列。"""
    if column in df.columns:
        return df[column]
    return pd.Series([None] * len(df), index=df.index)


def add_advanced_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """给 player_boxscores DataFrame 添加高级指标。"""
    result = df.copy()
    required_columns = [
        "fgm",
        "three_pm",
        "fga",
        "points",
        "fta",
        "assists",
        "turnovers",
        "rebounds",
        "minutes_float",
    ]
    _warn_missing_columns(result, required_columns)

    fgm = _column_or_none(result, "fgm")
    three_pm = _column_or_none(result, "three_pm")
    fga = _column_or_none(result, "fga")
    points = _column_or_none(result, "points")
    fta = _column_or_none(result, "fta")
    assists = _column_or_none(result, "assists")
    turnovers = _column_or_none(result, "turnovers")
    rebounds = _column_or_none(result, "rebounds")
    minutes_float = _column_or_none(result, "minutes_float")

    # 逐行计算，确保每一次除法都走安全函数。
    result["efg_pct_calc"] = [
        calculate_efg(row_fgm, row_three_pm, row_fga)
        for row_fgm, row_three_pm, row_fga in zip(fgm, three_pm, fga)
    ]
    result["ts_pct_calc"] = [
        calculate_ts(row_points, row_fga, row_fta)
        for row_points, row_fga, row_fta in zip(points, fga, fta)
    ]
    result["ast_tov"] = [
        calculate_ast_tov(row_assists, row_turnovers)
        for row_assists, row_turnovers in zip(assists, turnovers)
    ]
    result["points_per36"] = [
        calculate_per36(row_points, row_minutes)
        for row_points, row_minutes in zip(points, minutes_float)
    ]
    result["rebounds_per36"] = [
        calculate_per36(row_rebounds, row_minutes)
        for row_rebounds, row_minutes in zip(rebounds, minutes_float)
    ]
    result["assists_per36"] = [
        calculate_per36(row_assists, row_minutes)
        for row_assists, row_minutes in zip(assists, minutes_float)
    ]

    return result


def _is_china(value: str | None) -> bool:
    """判断队名是否指向中国女篮。"""
    if not value:
        return False
    return any(keyword.lower() in str(value).lower() for keyword in CHINA_KEYWORDS)


def load_games() -> pd.DataFrame:
    """读取 games 表。"""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM games", conn)


def load_player_boxscores() -> pd.DataFrame:
    """读取 player_boxscores 表。"""
    with get_connection() as conn:
        return pd.read_sql_query("SELECT * FROM player_boxscores", conn)


def china_game_summary() -> pd.DataFrame:
    """生成中国女篮比赛结果摘要。"""
    games = load_games()
    if games.empty:
        return games

    mask = games["team_home"].apply(_is_china) | games["team_away"].apply(_is_china)
    china_games = games.loc[mask].copy()

    def result(row):
        if not row.get("winner"):
            return None
        return "W" if _is_china(row["winner"]) else "L"

    china_games["china_result"] = china_games.apply(result, axis=1)
    return china_games


def china_player_summary() -> pd.DataFrame:
    """读取中国女篮球员数据，并添加高级指标。"""
    players = load_player_boxscores()
    if players.empty or "team" not in players:
        return players
    china_players = players[players["team"].apply(_is_china)].copy()
    return add_advanced_metrics(china_players)
