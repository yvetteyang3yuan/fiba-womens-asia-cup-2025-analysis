import _bootstrap  # noqa: F401

import pandas as pd

from src.config import CLEAN_DIR, ensure_directories
from src.visualization import save_china_player_charts


PLAYER_BOXSCORES_CSV = CLEAN_DIR / "player_boxscores.csv"
CHINA_PLAYER_SUMMARY_CSV = CLEAN_DIR / "china_player_summary.csv"


def _is_china_team(value) -> bool:
    """兼容 China 和 CHN 两种队名写法。"""
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text in ["china", "chn"] or "people's republic of china" in text


def build_china_player_summary(player_df: pd.DataFrame) -> pd.DataFrame:
    """按球员汇总中国女篮场均表现。"""
    if player_df.empty:
        return pd.DataFrame()
    if "team" not in player_df.columns:
        print("warning: player_boxscores.csv 缺少 team 字段，无法筛选中国队。")
        return pd.DataFrame()

    china_df = player_df[player_df["team"].apply(_is_china_team)].copy()
    if china_df.empty:
        print("warning: 未筛选到中国队球员数据，请检查 team 字段。")
        return pd.DataFrame()

    numeric_cols = ["points", "rebounds", "assists", "steals", "blocks", "efficiency", "minutes_float"]
    for col in numeric_cols:
        if col in china_df.columns:
            china_df[col] = pd.to_numeric(china_df[col], errors="coerce")
        else:
            print(f"warning: 缺少字段 {col}，对应汇总会为空。")
            china_df[col] = pd.NA

    summary = (
        china_df.groupby("player_name", dropna=False)
        .agg(
            games_played=("game_id", "nunique"),
            points_per_game=("points", "mean"),
            rebounds_per_game=("rebounds", "mean"),
            assists_per_game=("assists", "mean"),
            steals_per_game=("steals", "mean"),
            blocks_per_game=("blocks", "mean"),
            efficiency_per_game=("efficiency", "mean"),
            avg_minutes=("minutes_float", "mean"),
        )
        .reset_index()
    )

    metric_cols = [
        "points_per_game",
        "rebounds_per_game",
        "assists_per_game",
        "steals_per_game",
        "blocks_per_game",
        "efficiency_per_game",
        "avg_minutes",
    ]
    summary[metric_cols] = summary[metric_cols].round(2)
    return summary.sort_values(["points_per_game", "efficiency_per_game"], ascending=False)


if __name__ == "__main__":
    ensure_directories()

    if not PLAYER_BOXSCORES_CSV.exists():
        raise FileNotFoundError(f"未找到球员数据文件：{PLAYER_BOXSCORES_CSV.as_posix()}")

    player_df = pd.read_csv(PLAYER_BOXSCORES_CSV)
    summary_df = build_china_player_summary(player_df)
    summary_df.to_csv(CHINA_PLAYER_SUMMARY_CSV, index=False, encoding="utf-8-sig")

    figure_paths = save_china_player_charts(summary_df)

    print(f"中国女篮球员汇总已保存：{CHINA_PLAYER_SUMMARY_CSV.as_posix()}")
    print(f"中国女篮球员数量：{len(summary_df)}")
    for path in figure_paths:
        print(f"图表已保存：{path.as_posix()}")
