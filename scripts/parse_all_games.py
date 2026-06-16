import _bootstrap  # noqa: F401

from src.config import DB_PATH
from src.db import init_db
from src.fiba_game_parser import (
    GAMES_CSV,
    PLAYER_BOXSCORES_CSV,
    TEAM_BOXSCORES_CSV,
    parse_games,
    parse_player_boxscores,
    parse_team_boxscores,
)


if __name__ == "__main__":
    # 初始化数据库，表已存在时不会报错。
    init_db()

    # 按依赖顺序解析：games -> team_boxscores -> player_boxscores。
    games_df = parse_games()
    team_boxscores_df = parse_team_boxscores()
    player_boxscores_df = parse_player_boxscores()

    print("解析完成。")
    print(f"games 行数：{len(games_df)}")
    print(f"team_boxscores 行数：{len(team_boxscores_df)}")
    print(f"player_boxscores 行数：{len(player_boxscores_df)}")
    print("CSV 保存路径：")
    print(f"- {GAMES_CSV.as_posix()}")
    print(f"- {TEAM_BOXSCORES_CSV.as_posix()}")
    print(f"- {PLAYER_BOXSCORES_CSV.as_posix()}")
    print(f"数据库保存路径：{DB_PATH.as_posix()}")
