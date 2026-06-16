import csv
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, FeatureNotFound

from src.config import FIBA_GAMES_URL, GAME_URLS_CSV, HEADERS, RAW_DEBUG_DIR, RAW_DIR, ensure_directories


MIN_EXPECTED_GAMES = 15
MANUAL_GAME_URLS_CSV = RAW_DIR / "manual_game_urls.csv"

# 比赛链接格式：/en/events/fiba-womens-asiacup-2025/games/数字-队伍-队伍
GAME_URL_PATTERN = re.compile(
    r"(?:https?://www\.fiba\.basketball)?"
    r"(?P<path>/en/events/fiba-womens-asiacup-2025/games/[0-9]+-[A-Z]+-[A-Z]+)",
    re.IGNORECASE,
)

# 日期按钮可能显示成 JUL 13，也可能只显示 13，并配合 aria-label / role=tab。
DATE_TEXT_PATTERN = re.compile(
    r"("
    r"\bJUL\s*(13|14|15|16|17|18|19|20)\b|"
    r"\bJULY\s*(13|14|15|16|17|18|19|20)\b|"
    r"\b(mon|tue|wed|thu|fri|sat|sun)\b|"
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b|"
    r"\b(day|date|game day|schedule|fixtures?)\b|"
    r"\d{1,2}[/-]\d{1,2}|"
    r"\d{4}[/-]\d{1,2}[/-]\d{1,2}|"
    r"日期|比赛日|赛程"
    r")",
    re.IGNORECASE,
)

EXPLICIT_DATE_TEXTS = [
    "JUL 13",
    "JUL 14",
    "JUL 15",
    "JUL 16",
    "JUL 17",
    "JUL 18",
    "JUL 19",
    "JUL 20",
    "Jul 13",
    "Jul 14",
    "Jul 15",
    "Jul 16",
    "Jul 17",
    "Jul 18",
    "Jul 19",
    "Jul 20",
]

CSV_FIELDS = [
    "game_no",
    "stage",
    "team_home",
    "team_away",
    "score_home",
    "score_away",
    "game_url",
    "source_date",
]


def _make_soup(html: str) -> BeautifulSoup:
    """创建 BeautifulSoup 对象；lxml 不可用时回退到内置解析器。"""
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def _save_debug_html(html: str, output_path: Path) -> None:
    """保存调试 HTML，方便人工检查 FIBA 页面结构。"""
    ensure_directories()
    output_path.write_text(html, encoding="utf-8")


def _normalize_game_url(raw_url: str, base_url: str = FIBA_GAMES_URL) -> str | None:
    """校验比赛链接并转成完整 URL。"""
    if not raw_url:
        return None

    absolute_url = urljoin(base_url, raw_url)
    parsed = urlparse(absolute_url)
    url_without_query = parsed._replace(query="", fragment="").geturl()

    match = GAME_URL_PATTERN.search(url_without_query)
    if not match:
        return None
    return urljoin(base_url, match.group("path"))


def _extract_game_urls_from_html(html: str, base_url: str = FIBA_GAMES_URL) -> set[str]:
    """从 a[href]、页面源码、脚本字符串中提取比赛 URL。"""
    soup = _make_soup(html)
    urls: set[str] = set()

    for link in soup.select("a[href]"):
        game_url = _normalize_game_url(link.get("href", ""), base_url)
        if game_url:
            urls.add(game_url)

    for match in GAME_URL_PATTERN.finditer(html):
        game_url = _normalize_game_url(match.group("path"), base_url)
        if game_url:
            urls.add(game_url)

    return urls


def _rows_from_url_sources(url_sources: dict[str, set[str | None]]) -> list[dict]:
    """把 URL 与日期来源转换成最终 CSV 行。"""
    rows = []
    for game_no, game_url in enumerate(sorted(url_sources), start=1):
        source_dates = sorted(date for date in url_sources[game_url] if date)
        rows.append(
            {
                "game_no": game_no,
                "stage": None,
                "team_home": None,
                "team_away": None,
                "score_home": None,
                "score_away": None,
                "game_url": game_url,
                "source_date": "; ".join(source_dates) if source_dates else None,
            }
        )
    return rows


def _rows_from_urls(urls: set[str], source_date: str | None = None) -> list[dict]:
    """把 URL 集合转换成 CSV 行。"""
    return _rows_from_url_sources({url: {source_date} for url in urls})


def _add_urls(url_sources: dict[str, set[str | None]], urls: set[str], source_date: str | None) -> None:
    """把一批 URL 合并到 URL 来源字典中。"""
    for url in urls:
        url_sources.setdefault(url, set()).add(source_date)


def collect_game_urls_by_requests(games_page_url: str = FIBA_GAMES_URL) -> list[dict]:
    """辅助方案：使用 requests + BeautifulSoup 收集默认页面中的比赛 URL。"""
    ensure_directories()
    response = requests.get(games_page_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    time.sleep(2)

    html = response.text
    _save_debug_html(html, RAW_DEBUG_DIR / "games_page_requests.html")
    return _rows_from_urls(_extract_game_urls_from_html(html, games_page_url), source_date=None)


def _element_label(element) -> str | None:
    """提取日期按钮可读标签，用于 source_date 和调试输出。"""
    parts = []
    for attr in ["aria-label", "title", "data-date", "data-testid", "data-test"]:
        try:
            value = element.get_attribute(attr)
        except Exception:
            value = None
        if value:
            parts.append(str(value))

    try:
        text = element.text
    except Exception:
        text = ""
    if text:
        parts.insert(0, text)

    label = " ".join(part.strip() for part in parts if part and part.strip())
    label = re.sub(r"\s+", " ", label).strip()
    return label[:120] if label else None


def _looks_like_date_button(element) -> bool:
    """综合判断元素是否像日期 tab / 日期按钮 / 比赛日切换控件。"""
    label = _element_label(element) or ""
    if DATE_TEXT_PATTERN.search(label):
        return True

    try:
        role = (element.get_attribute("role") or "").lower()
        tag_name = (element.tag_name or "").lower()
        aria_selected = element.get_attribute("aria-selected")
        visible_text = (element.text or "").strip()
    except Exception:
        return False

    if role == "tab" and visible_text:
        return True
    if aria_selected is not None and visible_text:
        return True
    if tag_name in ["button", "a"] and re.fullmatch(r"\d{1,2}", visible_text):
        return True

    return False


def _click_target_for_date_element(element):
    """把包含日期文本的子元素提升到可点击祖先元素。"""
    try:
        return element.find_element(
            "xpath",
            "./ancestor-or-self::*[self::button or self::a or @role='tab' or @aria-selected][1]",
        )
    except Exception:
        return element


def _find_date_buttons(driver) -> list[dict]:
    """识别 button、a、role=tab、aria-selected 和含日期文本的疑似日期按钮。"""
    raw_elements = []

    for selector in ["button", "a", "[role='tab']", "[aria-selected]", "[data-date]", "[aria-label]"]:
        try:
            raw_elements.extend(driver.find_elements("css selector", selector))
        except Exception:
            continue

    for date_text in EXPLICIT_DATE_TEXTS:
        xpath = f"//*[contains(normalize-space(.), '{date_text}')]"
        try:
            raw_elements.extend(driver.find_elements("xpath", xpath))
        except Exception:
            continue

    buttons = []
    seen_keys: set[str] = set()
    for raw_element in raw_elements:
        element = _click_target_for_date_element(raw_element)
        if not _looks_like_date_button(element):
            continue

        label = _element_label(element)
        if not label:
            continue

        try:
            key = "|".join(
                [
                    element.tag_name or "",
                    element.get_attribute("outerHTML")[:500] or "",
                    label,
                ]
            )
        except Exception:
            key = label

        if key in seen_keys:
            continue
        seen_keys.add(key)
        buttons.append({"index": len(buttons), "label": label, "element": element})

    return buttons


def _safe_click(driver, element) -> bool:
    """安全点击 Selenium 元素；失败时打印 warning 并跳过。"""
    label = _element_label(element) or "unknown date element"
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        try:
            element.click()
            return True
        except Exception as exc:
            print(f"warning: 日期按钮不可点击，已跳过：{label} ({exc})")
            return False


def _collect_current_date(driver, base_url: str, debug_index: int) -> set[str]:
    """采集当前日期页面的比赛链接，并保存单日调试 HTML。"""
    html = driver.page_source
    _save_debug_html(html, RAW_DEBUG_DIR / f"games_page_date_{debug_index:02d}.html")
    return _extract_game_urls_from_html(html, base_url)


def collect_game_urls_by_selenium(games_page_url: str = FIBA_GAMES_URL) -> tuple[list[dict], dict]:
    """主方案：使用 Selenium 遍历所有日期 tab / 日期按钮收集比赛 URL。"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:
        raise RuntimeError("未安装 selenium，无法使用 Selenium。") from exc

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={HEADERS['User-Agent']}")

    url_sources: dict[str, set[str | None]] = {}
    date_counts: list[tuple[str | None, int]] = []
    all_date_html: list[str] = []

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(games_page_url)
        time.sleep(5)

        date_buttons = _find_date_buttons(driver)
        stats = {"date_button_count": len(date_buttons), "date_counts": date_counts}

        default_label = "default"
        default_urls = _collect_current_date(driver, games_page_url, 0)
        _add_urls(url_sources, default_urls, default_label)
        date_counts.append((default_label, len(default_urls)))
        all_date_html.append(f"\n<!-- source_date: {default_label} -->\n{driver.page_source}")

        for debug_index, button_info in enumerate(date_buttons, start=1):
            label = button_info["label"]
            element = button_info["element"]

            if not _safe_click(driver, element):
                date_counts.append((label, 0))
                continue

            time.sleep(2.5)
            urls = _collect_current_date(driver, games_page_url, debug_index)
            _add_urls(url_sources, urls, label)
            date_counts.append((label, len(urls)))
            all_date_html.append(f"\n<!-- source_date: {label} -->\n{driver.page_source}")

        _save_debug_html("\n".join(all_date_html), RAW_DEBUG_DIR / "games_page_all_dates.html")
    finally:
        driver.quit()

    return _rows_from_url_sources(url_sources), stats


def read_manual_game_urls(csv_path: Path = MANUAL_GAME_URLS_CSV) -> list[dict]:
    """读取人工补充 URL 文件；保留兼容人工补充流程。"""
    if not csv_path.exists():
        return []

    rows: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            game_url = _normalize_game_url(raw_row.get("game_url", ""))
            if not game_url:
                continue
            rows.append(
                {
                    "game_no": raw_row.get("game_no") or None,
                    "stage": raw_row.get("stage") or None,
                    "team_home": None,
                    "team_away": None,
                    "score_home": None,
                    "score_away": None,
                    "game_url": game_url,
                    "source_date": raw_row.get("source_date") or None,
                }
            )
    return rows


def merge_game_url_rows(*row_groups: list[dict]) -> list[dict]:
    """合并多组比赛 URL 行，并按 game_url 去重。"""
    rows_by_url: dict[str, dict] = {}

    for group in row_groups:
        for row in group:
            game_url = _normalize_game_url(row.get("game_url", ""))
            if not game_url:
                continue

            merged_row = {field: row.get(field) for field in CSV_FIELDS}
            merged_row["game_url"] = game_url

            old_row = rows_by_url.get(game_url)
            if old_row is None:
                rows_by_url[game_url] = merged_row
                continue

            for field in CSV_FIELDS:
                if field == "game_no":
                    continue
                if old_row.get(field) in [None, ""] and merged_row.get(field) not in [None, ""]:
                    old_row[field] = merged_row[field]

    rows = list(rows_by_url.values())
    rows.sort(key=lambda item: item["game_url"])
    for index, row in enumerate(rows, start=1):
        row["game_no"] = index
    return rows


def save_game_urls(rows: list[dict], csv_path: Path = GAME_URLS_CSV) -> None:
    """保存比赛 URL 到 data/raw/fiba_game_urls.csv。"""
    ensure_directories()
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in CSV_FIELDS})


def collect_game_urls(games_page_url: str = FIBA_GAMES_URL) -> tuple[list[dict], dict]:
    """主流程：Selenium 遍历日期按钮，requests 作为辅助补充。"""
    ensure_directories()

    request_rows = collect_game_urls_by_requests(games_page_url)
    print(f"requests 辅助收集到 {len(request_rows)} 场比赛")

    selenium_rows: list[dict] = []
    selenium_stats = {"date_button_count": 0, "date_counts": []}
    try:
        selenium_rows, selenium_stats = collect_game_urls_by_selenium(games_page_url)
    except Exception as exc:
        print(f"warning: Selenium 日期遍历失败：{exc}")

    auto_rows = merge_game_url_rows(selenium_rows, request_rows)
    stats = {
        "requests_count": len(request_rows),
        "date_button_count": selenium_stats["date_button_count"],
        "date_counts": selenium_stats["date_counts"],
        "auto_count": len(auto_rows),
    }

    return auto_rows, stats


def collect_and_save_game_urls(games_page_url: str = FIBA_GAMES_URL) -> list[dict]:
    """收集所有日期下的比赛 URL，合并人工补充，保存最终 CSV。"""
    auto_rows, stats = collect_game_urls(games_page_url)
    manual_rows = read_manual_game_urls()
    rows = merge_game_url_rows(auto_rows, manual_rows)
    save_game_urls(rows)

    print(f"识别到 {stats['date_button_count']} 个日期按钮")
    for source_date, count in stats["date_counts"]:
        print(f"日期 [{source_date or '未知'}] 收集到 {count} 场比赛")
    print(f"人工补充 URL 数量：{len(manual_rows)}")
    print(f"最终去重后总共收集到 {len(rows)} 场")
    print("比赛 URL 列表：")
    for row in rows:
        print(row["game_url"])

    if len(rows) < MIN_EXPECTED_GAMES:
        print("可能还有日期按钮未被识别，请人工检查 data/raw/debug/ 下的 HTML。")

    return rows
