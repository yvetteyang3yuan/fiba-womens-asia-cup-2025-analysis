import _bootstrap  # noqa: F401

from src.fiba_html_crawler import FAILED_GAME_URLS_CSV, HTML_MAP_CSV, crawl_all_games


if __name__ == "__main__":
    print("开始下载全部比赛 HTML；requests 失败或 blocked 时会自动尝试 Selenium。")
    paths = crawl_all_games(use_selenium_fallback=True)
    print(f"下载流程结束，成功保存 {len(paths)} 个 HTML 文件到 data/raw/html/")
    print(f"HTML 映射表：{HTML_MAP_CSV.as_posix()}")
    print(f"失败 URL 表：{FAILED_GAME_URLS_CSV.as_posix()}")
