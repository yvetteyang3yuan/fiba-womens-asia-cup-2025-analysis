import csv
import random
import re
import time
from pathlib import Path

import requests

from src.config import GAME_URLS_CSV, HEADERS, RAW_DEBUG_DIR, RAW_DIR, RAW_HTML_DIR, ensure_directories


HTML_MAP_CSV = RAW_DIR / "html_map.csv"
FAILED_GAME_URLS_CSV = RAW_DEBUG_DIR / "failed_game_urls.csv"

# 明确的拦截特征。不要把普通 login/sign in 字样直接视为 blocked。
BLOCK_KEYWORDS = [
    "access denied",
    "403 forbidden",
    "request blocked",
    "you don't have permission",
    "captcha",
    "verify you are human",
    "cloudflare ray id",
    "cf-error",
    "temporarily blocked",
    "unusual traffic",
    "验证码",
    "机器人",
]

# 如果页面已经包含比赛页特征，优先认为不是 blocked。
GAME_PAGE_KEYWORDS = [
    "boxscore",
    "game leaders",
    "team stats",
    "chn",
    "china",
    "new zealand",
    "korea",
    "japan",
    "australia",
]


def read_game_urls(csv_path: Path = GAME_URLS_CSV) -> list[dict]:
    """读取 data/raw/fiba_game_urls.csv 中的比赛 URL。"""
    if not csv_path.exists():
        raise FileNotFoundError(f"未找到比赛 URL 文件：{csv_path.as_posix()}")

    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for index, row in enumerate(reader, start=1):
            game_url = (row.get("game_url") or "").strip()
            if not game_url:
                continue

            game_no_raw = (row.get("game_no") or "").strip()
            try:
                game_no = int(game_no_raw)
            except ValueError:
                game_no = index

            rows.append({"game_no": game_no, "game_url": game_url})

    return rows


def _html_file_for_game(game_no: int, html_dir: Path = RAW_HTML_DIR) -> Path:
    """根据 game_no 生成 game_XX.html 文件路径。"""
    return html_dir / f"game_{game_no:02d}.html"


def _selenium_debug_html_path(game_no: int) -> Path:
    """生成 Selenium 单场调试 HTML 路径。"""
    return RAW_DEBUG_DIR / f"selenium_game_{game_no:02d}_debug.html"


def _selenium_debug_png_path(game_no: int) -> Path:
    """生成 Selenium 单场截图路径。"""
    return RAW_DEBUG_DIR / f"selenium_game_{game_no:02d}.png"


def is_blocked_page(html_text: str) -> bool:
    """判断 HTML 是否是明确的访问限制页面。"""
    if not html_text:
        return False

    lower_html = html_text.lower()
    if any(keyword in lower_html for keyword in GAME_PAGE_KEYWORDS):
        return False

    return any(keyword in lower_html for keyword in BLOCK_KEYWORDS)


def _looks_valid_html(html_text: str) -> bool:
    """简单判断是否拿到了有效 HTML。"""
    if not html_text or len(html_text.strip()) < 500:
        return False
    return bool(re.search(r"<html|<!doctype html", html_text, re.IGNORECASE))


def download_game_html_by_requests(game_no: int, game_url: str, html_dir: Path = RAW_HTML_DIR) -> tuple[Path | None, str]:
    """使用 requests 下载单场 HTML；失败只返回状态，不中断程序。"""
    ensure_directories()

    try:
        response = requests.get(game_url, headers=HEADERS, timeout=30)
    except requests.RequestException as exc:
        print(f"warning: game_{game_no:02d} requests 网络错误：{exc}")
        return None, "failed"

    if response.status_code == 403:
        print(f"warning: game_{game_no:02d} requests 返回 403")
        return None, "blocked"

    if response.status_code != 200:
        print(f"warning: game_{game_no:02d} requests 状态码不是 200：{response.status_code}")
        return None, "failed"

    if is_blocked_page(response.text):
        print(f"warning: game_{game_no:02d} requests 疑似访问限制页面")
        return None, "blocked"

    if not _looks_valid_html(response.text):
        print(f"warning: game_{game_no:02d} requests 未获取到有效 HTML")
        return None, "failed"

    html_path = _html_file_for_game(game_no, html_dir)
    html_path.write_text(response.text, encoding="utf-8")
    print(f"game_{game_no:02d}: requests 成功")
    return html_path, "success"


def download_game_html_by_selenium(game_no: int, game_url: str, html_dir: Path = RAW_HTML_DIR) -> tuple[Path | None, str]:
    """使用 Selenium 下载公开页面，并始终保存单场调试 HTML 和截图。"""
    ensure_directories()

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:
        print(f"warning: game_{game_no:02d} Selenium 未安装：{exc}")
        return None, "failed"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={HEADERS['User-Agent']}")

    driver = None
    html = ""
    title = ""
    debug_html_path = _selenium_debug_html_path(game_no)
    debug_png_path = _selenium_debug_png_path(game_no)

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_window_size(1440, 1200)
        driver.get(game_url)
        time.sleep(8)
        html = driver.page_source or ""
        title = driver.title or ""

        # 注意：必须先保存 debug，再判断 blocked。
        debug_html_path.write_text(
            f"<!-- title: {title} -->\n<!-- url: {game_url} -->\n{html}",
            encoding="utf-8",
        )
        try:
            driver.save_screenshot(str(debug_png_path))
        except Exception as exc:
            print(f"warning: game_{game_no:02d} Selenium 截图保存失败：{exc}")

    except Exception as exc:
        if html:
            debug_html_path.write_text(
                f"<!-- title: {title} -->\n<!-- url: {game_url} -->\n{html}",
                encoding="utf-8",
            )
        print(f"warning: game_{game_no:02d} Selenium 失败：{exc}")
        return None, "failed"
    finally:
        if driver is not None:
            driver.quit()

    if is_blocked_page(html):
        print(f"warning: game_{game_no:02d} Selenium 页面疑似访问限制，已保存 debug 文件")
        return None, "blocked"

    if not _looks_valid_html(html):
        print(f"warning: game_{game_no:02d} Selenium 未获取到有效 HTML，已保存 debug 文件")
        return None, "failed"

    html_path = _html_file_for_game(game_no, html_dir)
    html_path.write_text(html, encoding="utf-8")
    print(f"game_{game_no:02d}: Selenium 成功")
    return html_path, "selenium_success"


def save_html_map(rows: list[dict], csv_path: Path = HTML_MAP_CSV) -> None:
    """保存成功下载的 HTML 映射。"""
    ensure_directories()
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["game_no", "game_url", "html_file", "download_method", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)


def save_failed_game_urls(rows: list[dict], csv_path: Path = FAILED_GAME_URLS_CSV) -> None:
    """保存失败 URL；即使没有失败也写出表头。"""
    ensure_directories()
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["game_no", "game_url", "reason"])
        writer.writeheader()
        writer.writerows(rows)


def _polite_sleep() -> None:
    """每场比赛之间等待 3 到 5 秒。"""
    time.sleep(random.uniform(3, 5))


def crawl_all_games(
    csv_path: Path = GAME_URLS_CSV,
    html_dir: Path = RAW_HTML_DIR,
    use_selenium_fallback: bool = True,
) -> list[Path]:
    """逐场下载比赛 HTML；单场失败不会中断整体流程。"""
    ensure_directories()
    game_rows = read_game_urls(csv_path)
    saved_paths: list[Path] = []
    map_rows: list[dict] = []
    failed_rows: list[dict] = []
    stats = {"requests_success": 0, "selenium_success": 0, "failed": 0}

    for index, row in enumerate(game_rows):
        if index > 0:
            _polite_sleep()

        game_no = row["game_no"]
        game_url = row["game_url"]
        print(f"开始下载 game_{game_no:02d}: {game_url}")

        html_path = None
        status = "failed"
        download_method = None

        try:
            html_path, status = download_game_html_by_requests(game_no, game_url, html_dir)

            if status == "success":
                download_method = "requests"
                stats["requests_success"] += 1
            elif status in ["blocked", "failed"] and use_selenium_fallback:
                print(f"game_{game_no:02d}: requests {status}，改用 Selenium")
                html_path, status = download_game_html_by_selenium(game_no, game_url, html_dir)
                if status == "selenium_success":
                    download_method = "selenium"
                    stats["selenium_success"] += 1

            if html_path is None:
                print(f"warning: game_{game_no:02d} 最终下载失败：{status}")
                failed_rows.append({"game_no": game_no, "game_url": game_url, "reason": status})
                stats["failed"] += 1
                continue

            saved_paths.append(html_path)
            map_rows.append(
                {
                    "game_no": game_no,
                    "game_url": game_url,
                    "html_file": html_path.as_posix(),
                    "download_method": download_method,
                    "status": status,
                }
            )

        except Exception as exc:
            print(f"warning: game_{game_no:02d} 未知异常，继续下一场：{exc}")
            failed_rows.append({"game_no": game_no, "game_url": game_url, "reason": str(exc)})
            stats["failed"] += 1

    save_html_map(map_rows)
    save_failed_game_urls(failed_rows)

    actual_html_count = len(list(html_dir.glob("game_*.html")))
    print(f"总 URL 数量：{len(game_rows)}")
    print(f"requests 成功数量：{stats['requests_success']}")
    print(f"Selenium 成功数量：{stats['selenium_success']}")
    print(f"失败数量：{stats['failed']}")
    print(f"data/raw/html/ 中实际保存的 game_*.html 数量：{actual_html_count}")
    print(f"failed_game_urls.csv 路径：{FAILED_GAME_URLS_CSV.as_posix()}")
    print(f"html_map.csv 路径：{HTML_MAP_CSV.as_posix()}")
    print(f"Selenium debug HTML 路径示例：{(RAW_DEBUG_DIR / 'selenium_game_XX_debug.html').as_posix()}")

    return saved_paths
