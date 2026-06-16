import _bootstrap  # noqa: F401

from src.fiba_url_collector import collect_and_save_game_urls


if __name__ == "__main__":
    rows = collect_and_save_game_urls()

    print(f"收集到的比赛数量：{len(rows)}")
    for row in rows:
        print(
            f"{row.get('game_no')}. "
            f"{row.get('source_date') or '未知日期'} "
            f"{row.get('game_url')}"
        )
