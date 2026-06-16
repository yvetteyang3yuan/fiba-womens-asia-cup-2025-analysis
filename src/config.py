from pathlib import Path

# 项目名称与官方页面。
EVENT_NAME = "FIBA Women's Asia Cup 2025"
FIBA_EVENT_URL = "https://www.fiba.basketball/en/events/fiba-womens-asiacup-2025"
FIBA_GAMES_URL = "https://www.fiba.basketball/en/events/fiba-womens-asiacup-2025/games"
FIBA_CHINA_TEAM_URL = "https://www.fiba.basketball/en/events/fiba-womens-asiacup-2025/teams/china/"

# 项目根目录：src/config.py 的上一级就是项目根目录。
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 数据与报告目录，全部使用 pathlib，避免写入本地绝对路径。
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_HTML_DIR = RAW_DIR / "html"
RAW_DEBUG_DIR = RAW_DIR / "debug"
CLEAN_DIR = DATA_DIR / "clean"
DATABASE_DIR = DATA_DIR / "database"
REPORTS_DIR = PROJECT_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"

# SQLite 数据库路径。
DB_PATH = DATABASE_DIR / "fiba2025.db"

# 原始比赛 URL 清单。
GAME_URLS_CSV = RAW_DIR / "fiba_game_urls.csv"

# 请求设置：不包含 cookie、token、账号密码。
REQUEST_SLEEP = 2
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    )
}

# 兼容项目中已存在的旧变量名，后续模块可以逐步改成上面的统一命名。
HTML_DIR = RAW_HTML_DIR
DEBUG_DIR = RAW_DEBUG_DIR
DATABASE_PATH = DB_PATH
GAMES_PAGE_URL = FIBA_GAMES_URL
REQUEST_HEADERS = HEADERS
REQUEST_SLEEP_SECONDS = REQUEST_SLEEP


def ensure_directories() -> None:
    """运行时自动创建项目所需目录。"""
    for path in [
        RAW_DIR,
        RAW_HTML_DIR,
        RAW_DEBUG_DIR,
        CLEAN_DIR,
        DATABASE_DIR,
        FIGURES_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


# 导入配置时立即创建目录，保证脚本运行前目录已经存在。
ensure_directories()
