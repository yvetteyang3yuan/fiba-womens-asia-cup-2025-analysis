from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib import font_manager

from src.config import FIGURES_DIR, ensure_directories


CHINESE_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "Source Han Sans SC",
    "Arial Unicode MS",
]


def setup_chinese_font() -> bool:
    """尽量设置中文字体；如果系统没有中文字体，只提示不报错。"""
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in CHINESE_FONT_CANDIDATES:
        if font_name in available_fonts:
            plt.rcParams["font.sans-serif"] = [font_name]
            plt.rcParams["axes.unicode_minus"] = False
            return True

    print("warning: 未找到常见中文字体，图表中文标题可能显示为方块。")
    plt.rcParams["axes.unicode_minus"] = False
    return False


def save_top10_bar_chart(
    df: pd.DataFrame,
    metric_col: str,
    title: str,
    ylabel: str,
    output_path: Path,
) -> Path | None:
    """保存球员 Top 10 横向柱状图。"""
    ensure_directories()
    setup_chinese_font()

    if df.empty or metric_col not in df.columns or "player_name" not in df.columns:
        print(f"warning: 无法生成图表 {output_path.name}，缺少数据或字段：{metric_col}")
        return None

    plot_df = (
        df[["player_name", metric_col]]
        .dropna(subset=[metric_col])
        .sort_values(metric_col, ascending=False)
        .head(10)
        .sort_values(metric_col, ascending=True)
    )

    if plot_df.empty:
        print(f"warning: 无法生成图表 {output_path.name}，{metric_col} 没有可用数据。")
        return None

    plt.figure(figsize=(9, 5.5))
    sns.barplot(data=plot_df, x=metric_col, y="player_name", color="#c9272d")
    plt.title(title)
    plt.xlabel(ylabel)
    plt.ylabel("球员")
    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()
    return output_path


def save_china_player_charts(summary_df: pd.DataFrame, output_dir: Path = FIGURES_DIR) -> list[Path]:
    """生成中国女篮球员 Top 10 图表。"""
    ensure_directories()
    charts = [
        (
            "points_per_game",
            "中国队球员场均得分 Top 10",
            "场均得分",
            output_dir / "china_points_top10.png",
        ),
        (
            "rebounds_per_game",
            "中国队球员场均篮板 Top 10",
            "场均篮板",
            output_dir / "china_rebounds_top10.png",
        ),
        (
            "assists_per_game",
            "中国队球员场均助攻 Top 10",
            "场均助攻",
            output_dir / "china_assists_top10.png",
        ),
        (
            "efficiency_per_game",
            "中国队球员平均效率 Top 10",
            "平均效率",
            output_dir / "china_efficiency_top10.png",
        ),
    ]

    saved_paths: list[Path] = []
    for metric_col, title, ylabel, output_path in charts:
        path = save_top10_bar_chart(summary_df, metric_col, title, ylabel, output_path)
        if path:
            saved_paths.append(path)
    return saved_paths


def save_china_score_chart(china_games, output_dir: Path = FIGURES_DIR) -> Path | None:
    """兼容旧函数：保存中国女篮每场比分柱状图。"""
    ensure_directories()
    setup_chinese_font()
    if china_games.empty or "score_home" not in china_games:
        return None

    plot_df = china_games.copy()
    plot_df["match"] = plot_df["team_home"].fillna("") + " vs " + plot_df["team_away"].fillna("")

    plt.figure(figsize=(10, 5))
    sns.barplot(data=plot_df, x="match", y="score_home", color="#d84a4a", label="Home")
    sns.barplot(data=plot_df, x="match", y="score_away", color="#4a78d8", label="Away")
    plt.xticks(rotation=35, ha="right")
    plt.ylabel("得分")
    plt.xlabel("")
    plt.title("中国女篮相关比赛比分")
    plt.tight_layout()

    output_path = output_dir / "china_game_scores.png"
    plt.savefig(output_path, dpi=160)
    plt.close()
    return output_path
