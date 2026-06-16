import _bootstrap  # noqa: F401

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from src.config import CLEAN_DIR, FIGURES_DIR, ensure_directories
from src.visualization import setup_chinese_font


PLAYER_BOXSCORES_CSV = CLEAN_DIR / "player_boxscores.csv"
TEAM_BOXSCORES_CSV = CLEAN_DIR / "team_boxscores.csv"
TOURNAMENT_PLAYER_SUMMARY_CSV = CLEAN_DIR / "tournament_player_summary.csv"
TOURNAMENT_TEAM_SUMMARY_CSV = CLEAN_DIR / "tournament_team_summary.csv"


def _to_numeric(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """把指定字段转换为数值，无法转换时置为空。"""
    result = df.copy()
    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        else:
            print(f"warning: 缺少字段 {column}，相关统计可能为空。")
            result[column] = pd.NA
    return result


def build_tournament_player_summary(player_df: pd.DataFrame) -> pd.DataFrame:
    """生成全赛事球员汇总。"""
    numeric_cols = ["points", "rebounds", "assists", "steals", "blocks", "efficiency", "minutes_float"]
    player_df = _to_numeric(player_df, numeric_cols)

    summary = (
        player_df.groupby(["player_name", "team"], dropna=False)
        .agg(
            games_played=("game_id", "nunique"),
            total_points=("points", "sum"),
            total_rebounds=("rebounds", "sum"),
            total_assists=("assists", "sum"),
            total_steals=("steals", "sum"),
            total_blocks=("blocks", "sum"),
            avg_efficiency=("efficiency", "mean"),
            avg_minutes=("minutes_float", "mean"),
            points_per_game=("points", "mean"),
            rebounds_per_game=("rebounds", "mean"),
            assists_per_game=("assists", "mean"),
        )
        .reset_index()
    )

    round_cols = ["avg_efficiency", "avg_minutes", "points_per_game", "rebounds_per_game", "assists_per_game"]
    summary[round_cols] = summary[round_cols].round(2)
    return summary.sort_values("total_points", ascending=False)


def build_tournament_team_summary(team_df: pd.DataFrame, player_df: pd.DataFrame) -> pd.DataFrame:
    """生成全赛事球队汇总。"""
    numeric_cols = ["points", "rebounds", "assists", "steals", "blocks", "turnovers", "fouls"]
    team_df = _to_numeric(team_df, numeric_cols)
    player_df = _to_numeric(player_df, ["rebounds", "assists", "steals", "blocks"])

    summary = (
        team_df.groupby("team", dropna=False)
        .agg(
            games_played=("game_id", "nunique"),
            points_per_game=("points", "mean"),
            rebounds_per_game=("rebounds", "mean"),
            assists_per_game=("assists", "mean"),
            steals_per_game=("steals", "mean"),
            blocks_per_game=("blocks", "mean"),
            turnovers_per_game=("turnovers", "mean"),
            fouls_per_game=("fouls", "mean"),
        )
        .reset_index()
    )

    # 如果 team_boxscores 的篮板等字段为空，用 player_boxscores 按队聚合补充。
    player_team_summary = (
        player_df.groupby("team", dropna=False)
        .agg(
            player_rebounds_per_game=("rebounds", lambda x: x.sum() / player_df.loc[x.index, "game_id"].nunique()),
            player_assists_per_game=("assists", lambda x: x.sum() / player_df.loc[x.index, "game_id"].nunique()),
            player_steals_per_game=("steals", lambda x: x.sum() / player_df.loc[x.index, "game_id"].nunique()),
            player_blocks_per_game=("blocks", lambda x: x.sum() / player_df.loc[x.index, "game_id"].nunique()),
        )
        .reset_index()
    )
    summary = summary.merge(player_team_summary, on="team", how="left")
    for target, fallback in [
        ("rebounds_per_game", "player_rebounds_per_game"),
        ("assists_per_game", "player_assists_per_game"),
        ("steals_per_game", "player_steals_per_game"),
        ("blocks_per_game", "player_blocks_per_game"),
    ]:
        summary[target] = summary[target].fillna(summary[fallback])
    summary = summary.drop(columns=[col for col in summary.columns if col.startswith("player_")])

    metric_cols = [column for column in summary.columns if column.endswith("_per_game")]
    summary[metric_cols] = summary[metric_cols].round(2)
    return summary.sort_values("points_per_game", ascending=False)


def _save_rank_chart(
    df: pd.DataFrame,
    label_col: str,
    metric_col: str,
    title: str,
    xlabel: str,
    output_name: str,
    top_n: int | None = None,
):
    """保存横向排名柱状图。"""
    ensure_directories()
    setup_chinese_font()
    if df.empty or label_col not in df.columns or metric_col not in df.columns:
        print(f"warning: 无法生成图表 {output_name}，缺少字段。")
        return None

    plot_df = df[[label_col, metric_col]].dropna(subset=[metric_col]).sort_values(metric_col, ascending=False)
    if top_n:
        plot_df = plot_df.head(top_n)
    plot_df = plot_df.sort_values(metric_col, ascending=True)
    if plot_df.empty:
        print(f"warning: 无法生成图表 {output_name}，没有可用数据。")
        return None

    output_path = FIGURES_DIR / output_name
    plt.figure(figsize=(9, 6))
    sns.barplot(data=plot_df, x=metric_col, y=label_col, color="#c9272d")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("")
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()
    return output_path


if __name__ == "__main__":
    ensure_directories()
    setup_chinese_font()

    if not PLAYER_BOXSCORES_CSV.exists():
        raise FileNotFoundError(f"未找到球员数据：{PLAYER_BOXSCORES_CSV.as_posix()}")
    if not TEAM_BOXSCORES_CSV.exists():
        raise FileNotFoundError(f"未找到球队数据：{TEAM_BOXSCORES_CSV.as_posix()}")

    player_df = pd.read_csv(PLAYER_BOXSCORES_CSV)
    team_df = pd.read_csv(TEAM_BOXSCORES_CSV)

    player_summary = build_tournament_player_summary(player_df)
    team_summary = build_tournament_team_summary(team_df, player_df)

    player_summary.to_csv(TOURNAMENT_PLAYER_SUMMARY_CSV, index=False, encoding="utf-8-sig")
    team_summary.to_csv(TOURNAMENT_TEAM_SUMMARY_CSV, index=False, encoding="utf-8-sig")

    _save_rank_chart(
        player_summary,
        "player_name",
        "total_points",
        "全赛事球员得分榜 Top 15",
        "总得分",
        "tournament_points_top15.png",
        top_n=15,
    )
    _save_rank_chart(
        player_summary,
        "player_name",
        "total_rebounds",
        "全赛事球员篮板榜 Top 15",
        "总篮板",
        "tournament_rebounds_top15.png",
        top_n=15,
    )
    _save_rank_chart(
        player_summary,
        "player_name",
        "total_assists",
        "全赛事球员助攻榜 Top 15",
        "总助攻",
        "tournament_assists_top15.png",
        top_n=15,
    )
    _save_rank_chart(
        team_summary,
        "team",
        "points_per_game",
        "各队场均得分排名",
        "场均得分",
        "team_points_rank.png",
    )

    print("全赛事球员得分榜 Top 15：")
    print(player_summary[["player_name", "team", "total_points"]].head(15).to_string(index=False))
    print("全赛事球员篮板榜 Top 15：")
    print(player_summary[["player_name", "team", "total_rebounds"]].sort_values("total_rebounds", ascending=False).head(15).to_string(index=False))
    print("全赛事球员助攻榜 Top 15：")
    print(player_summary[["player_name", "team", "total_assists"]].sort_values("total_assists", ascending=False).head(15).to_string(index=False))
    print("各队场均得分排名：")
    print(team_summary[["team", "points_per_game"]].sort_values("points_per_game", ascending=False).to_string(index=False))
    print("各队场均篮板排名：")
    print(team_summary[["team", "rebounds_per_game"]].sort_values("rebounds_per_game", ascending=False).to_string(index=False))
    print(f"球员汇总已保存：{TOURNAMENT_PLAYER_SUMMARY_CSV.as_posix()}")
    print(f"球队汇总已保存：{TOURNAMENT_TEAM_SUMMARY_CSV.as_posix()}")
