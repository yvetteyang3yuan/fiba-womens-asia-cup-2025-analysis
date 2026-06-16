import csv
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from bs4 import BeautifulSoup, FeatureNotFound

from src.config import CLEAN_DIR, EVENT_NAME, GAME_URLS_CSV, RAW_DEBUG_DIR, RAW_DIR, RAW_HTML_DIR, ensure_directories
from src.db import get_connection, init_db


HTML_MAP_CSV = RAW_DIR / "html_map.csv"
GAMES_CSV = CLEAN_DIR / "games.csv"
TEAM_BOXSCORES_CSV = CLEAN_DIR / "team_boxscores.csv"
PLAYER_BOXSCORES_CSV = CLEAN_DIR / "player_boxscores.csv"

GAME_COLUMNS = [
    "game_id",
    "game_no",
    "event_name",
    "game_date",
    "stage",
    "team_home",
    "team_away",
    "score_home",
    "score_away",
    "winner",
    "game_url",
]

TEAM_BOXSCORE_COLUMNS = [
    "game_id",
    "game_no",
    "team",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "fouls",
    "fg_pct",
    "three_pct",
    "ft_pct",
    "source_url",
]

PLAYER_BOXSCORE_COLUMNS = [
    "game_id",
    "game_no",
    "team",
    "player_name",
    "starter",
    "minutes",
    "minutes_float",
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "turnovers",
    "fouls",
    "fgm",
    "fga",
    "fg_pct",
    "three_pm",
    "three_pa",
    "three_pct",
    "ftm",
    "fta",
    "ft_pct",
    "efficiency",
    "source_url",
]

TEAM_CODE_MAP = {
    "AUS": "Australia",
    "CHN": "China",
    "INA": "Indonesia",
    "IDN": "Indonesia",
    "JPN": "Japan",
    "KOR": "Korea",
    "LBN": "Lebanon",
    "NZL": "New Zealand",
    "PHI": "Philippines",
}


def _make_soup(html: str) -> BeautifulSoup:
    """创建 BeautifulSoup 对象；lxml 不可用时回退到内置解析器。"""
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


def _clean_text(value: str | None) -> str | None:
    """清理文本空白。"""
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned or None


def _to_int(value: str | int | float | None) -> int | None:
    """把比分转换为整数。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _to_float(value: str | int | float | None) -> float | None:
    """把百分比或普通数字转换为浮点数。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("%", "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _minutes_to_float(value: str | int | float | None) -> float | None:
    """把 19:08、19:8 或数字分钟转换为浮点分钟。"""
    if value in [None, ""]:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = re.match(r"^(\d+):(\d{1,2})$", text)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return round(minutes + seconds / 60, 2)
    return _to_float(text)


def _split_made_attempts(value: str | None) -> tuple[int | None, int | None]:
    """拆分 7/12 这类投篮字段。"""
    if not value:
        return None, None
    match = re.search(r"(\d+)\s*/\s*(\d+)", str(value))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _read_csv_rows(csv_path: Path) -> list[dict]:
    """读取 CSV；文件不存在时返回空列表。"""
    if not csv_path.exists():
        return []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _read_csv_df(csv_path: Path) -> pd.DataFrame:
    """读取 CSV 为 DataFrame；文件不存在时返回空表。"""
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)


def _game_id_from_url(game_url: str | None, fallback: str | None = None) -> str | None:
    """从 FIBA 比赛 URL 中提取 game_id。"""
    if game_url:
        slug = urlparse(game_url).path.rstrip("/").split("/")[-1]
        if slug:
            return slug
    return fallback


def _team_codes_from_url(game_url: str | None) -> tuple[str | None, str | None]:
    """从 URL slug 中提取主客队三字母代码，并映射为队名。"""
    game_id = _game_id_from_url(game_url)
    if not game_id:
        return None, None
    match = re.search(r"\d+-([A-Z]+)-([A-Z]+)$", game_id, re.IGNORECASE)
    if not match:
        return None, None
    home_code = match.group(1).upper()
    away_code = match.group(2).upper()
    return TEAM_CODE_MAP.get(home_code, home_code), TEAM_CODE_MAP.get(away_code, away_code)


def _pick_first(*values):
    """返回第一个非空值。"""
    for value in values:
        if value not in [None, ""]:
            return value
    return None


def _fallback_by_url(rows: list[dict]) -> dict[str, dict]:
    """把 fiba_game_urls.csv 按 game_url 建索引。"""
    result = {}
    for row in rows:
        game_url = row.get("game_url")
        if game_url:
            result[game_url] = row
    return result


def _extract_json_ld(soup: BeautifulSoup) -> list[dict]:
    """提取页面中的 JSON-LD 数据。"""
    objects = []
    for script in soup.select("script[type='application/ld+json']"):
        text = script.string or script.get_text()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            objects.extend(item for item in data if isinstance(item, dict))
        elif isinstance(data, dict):
            objects.append(data)
    return objects


def _parse_date_from_html(soup: BeautifulSoup, page_text: str) -> str | None:
    """从 HTML 中解析比赛日期。"""
    for attr in ["datetime", "content"]:
        for tag in soup.select(f"[{attr}]"):
            value = tag.get(attr)
            if value and re.search(r"2025[-/]\d{1,2}[-/]\d{1,2}", value):
                return value[:10]

    for obj in _extract_json_ld(soup):
        for key in ["startDate", "datePublished", "dateCreated"]:
            value = obj.get(key)
            if isinstance(value, str) and value:
                return value[:10]

    match = re.search(r"\b(2025[-/]\d{1,2}[-/]\d{1,2})\b", page_text)
    return match.group(1).replace("/", "-") if match else None


def _parse_stage_from_text(page_text: str) -> str | None:
    """从页面文本中解析比赛阶段。"""
    stage_keywords = [
        "Final",
        "Semi-Finals",
        "Semi-finals",
        "Quarter-Finals",
        "Quarter-finals",
        "Classification",
        "Group Phase",
        "Group",
    ]
    lower_text = page_text.lower()
    for keyword in stage_keywords:
        if keyword.lower() in lower_text:
            return keyword
    return None


def _parse_score_and_teams(soup: BeautifulSoup, page_text: str) -> dict:
    """从标题、页面文本和 meta 中尽量解析队名与比分。"""
    candidates = []
    if soup.title:
        candidates.append(soup.title.get_text(" "))
    for selector in ["h1", "meta[property='og:title']", "meta[name='twitter:title']"]:
        for tag in soup.select(selector):
            candidates.append(tag.get("content") or tag.get_text(" "))
    candidates.append(page_text[:1500])

    patterns = [
        r"\b([A-Z]{3})\s+(\d{2,3})\s*[-:]\s*(\d{2,3})\s+([A-Z]{3})\b",
        r"([A-Za-z .'-]{2,40}?)\s+(\d{2,3})\s*[-:]\s*(\d{2,3})\s+([A-Za-z .'-]{2,40})",
        r"([A-Za-z .'-]{2,40}?)\s+v(?:s)?\.?\s+([A-Za-z .'-]{2,40}).*?(\d{2,3})\s*[-:]\s*(\d{2,3})",
    ]

    for text in candidates:
        text = _clean_text(text) or ""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                continue
            if "v" in pattern:
                team_home = _clean_text(match.group(1))
                team_away = _clean_text(match.group(2))
                score_home = _to_int(match.group(3))
                score_away = _to_int(match.group(4))
            else:
                team_home = _clean_text(match.group(1))
                score_home = _to_int(match.group(2))
                score_away = _to_int(match.group(3))
                team_away = _clean_text(match.group(4))
            return {
                "team_home": team_home,
                "team_away": team_away,
                "score_home": score_home,
                "score_away": score_away,
            }

    return {"team_home": None, "team_away": None, "score_home": None, "score_away": None}


def _looks_messy_team(value: str | None) -> bool:
    """判断队名是否混入了页面导航或过长文本。"""
    if not value:
        return True
    bad_words = ["overview", "boxscore", "play by play", "shot chart", "game stats", "hide video"]
    lower_value = value.lower()
    return len(value) > 40 or any(word in lower_value for word in bad_words)


def _parse_game_from_html(html_path: Path, base_row: dict) -> dict:
    """解析单场比赛 HTML，失败时抛出异常交给上层复制 debug。"""
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = _make_soup(html)
    page_text = _clean_text(soup.get_text(" ")) or ""

    parsed = _parse_score_and_teams(soup, page_text)
    home_from_url, away_from_url = _team_codes_from_url(base_row.get("game_url"))
    score_home = _to_int(_pick_first(parsed["score_home"], base_row.get("score_home")))
    score_away = _to_int(_pick_first(parsed["score_away"], base_row.get("score_away")))
    parsed_home = None if _looks_messy_team(parsed["team_home"]) else parsed["team_home"]
    parsed_away = None if _looks_messy_team(parsed["team_away"]) else parsed["team_away"]
    team_home = _pick_first(base_row.get("team_home"), home_from_url, parsed_home)
    team_away = _pick_first(base_row.get("team_away"), away_from_url, parsed_away)

    winner = None
    if score_home is not None and score_away is not None:
        if score_home > score_away:
            winner = team_home
        elif score_away > score_home:
            winner = team_away

    return {
        "game_id": _game_id_from_url(base_row.get("game_url"), html_path.stem),
        "game_no": _to_int(base_row.get("game_no")),
        "event_name": EVENT_NAME,
        "game_date": _pick_first(_parse_date_from_html(soup, page_text), base_row.get("source_date")),
        "stage": _pick_first(_parse_stage_from_text(page_text), base_row.get("stage")),
        "team_home": team_home,
        "team_away": team_away,
        "score_home": score_home,
        "score_away": score_away,
        "winner": winner,
        "game_url": base_row.get("game_url"),
    }


def _copy_parse_failed_html(html_path: Path, game_no: int | None) -> None:
    """把解析失败的 HTML 复制到 debug 目录。"""
    if not html_path.exists():
        return
    prefix = f"game_{game_no:02d}" if game_no else html_path.stem
    debug_path = RAW_DEBUG_DIR / f"{prefix}_parse_failed.html"
    shutil.copy2(html_path, debug_path)


def _table_to_dict_rows(table) -> list[dict]:
    """把 HTML table 转成字典列表。"""
    header_cells = table.select("thead th")
    if not header_cells:
        first_row = table.select_one("tr")
        header_cells = first_row.select("th,td") if first_row else []
    headers = [_clean_text(cell.get_text(" ")) or f"col_{i + 1}" for i, cell in enumerate(header_cells)]

    rows = []
    body_rows = table.select("tbody tr") or table.select("tr")[1:]
    for tr in body_rows:
        values = [_clean_text(cell.get_text(" ")) for cell in tr.select("th,td")]
        if not any(values):
            continue
        if len(headers) != len(values):
            headers = [f"col_{i + 1}" for i in range(len(values))]
        rows.append(dict(zip(headers, values)))
    return rows


def _normalize_key(value: str) -> str:
    """规范字段名，便于匹配不同页面写法。"""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _pick_stat(row: dict, aliases: list[str]):
    """从表格行中按多个别名取统计值。"""
    normalized = {_normalize_key(str(key)): value for key, value in row.items()}
    for alias in aliases:
        key = _normalize_key(alias)
        if key in normalized:
            return normalized[key]
    return None


def _row_to_team_boxscore(row: dict, game: dict, source_url: str | None) -> dict | None:
    """尝试把表格行转换成球队统计行。"""
    team = _pick_stat(row, ["team", "teams", "name", "col_1"])
    if not team:
        return None
    team = _clean_text(str(team))
    if _looks_messy_team(team):
        return None

    points = _to_int(_pick_stat(row, ["points", "pts", "p"]))
    rebounds = _to_int(_pick_stat(row, ["rebounds", "reb", "tot", "total rebounds"]))
    assists = _to_int(_pick_stat(row, ["assists", "ast"]))
    steals = _to_int(_pick_stat(row, ["steals", "stl"]))
    blocks = _to_int(_pick_stat(row, ["blocks", "blk"]))
    turnovers = _to_int(_pick_stat(row, ["turnovers", "to", "tov"]))
    fouls = _to_int(_pick_stat(row, ["fouls", "pf", "personal fouls"]))

    if all(value is None for value in [points, rebounds, assists, steals, blocks, turnovers, fouls]):
        return None

    return {
        "game_id": game.get("game_id"),
        "game_no": _to_int(game.get("game_no")),
        "team": team,
        "points": points,
        "rebounds": rebounds,
        "assists": assists,
        "steals": steals,
        "blocks": blocks,
        "turnovers": turnovers,
        "fouls": fouls,
        "fg_pct": _to_float(_pick_stat(row, ["fg%", "fg pct", "field goals %", "field goal percentage"])),
        "three_pct": _to_float(_pick_stat(row, ["3p%", "3pt%", "3 pts %", "three pct", "three point percentage"])),
        "ft_pct": _to_float(_pick_stat(row, ["ft%", "free throws %", "free throw percentage"])),
        "source_url": source_url,
    }


def _parse_team_boxscores_from_html(html_path: Path, game: dict) -> list[dict]:
    """从单场 HTML 中解析两队球队统计。"""
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = _make_soup(html)
    rows: list[dict] = []

    for table in soup.select("table"):
        for table_row in _table_to_dict_rows(table):
            parsed = _row_to_team_boxscore(table_row, game, game.get("game_url"))
            if parsed:
                rows.append(parsed)

    # 去重：同一场同一队只保留第一行。
    unique_rows = []
    seen = set()
    for row in rows:
        key = (row.get("game_id"), row.get("team"))
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    return unique_rows[:2] if len(unique_rows) > 2 else unique_rows


def _fallback_team_boxscores(game: dict) -> list[dict]:
    """解析不到球队统计时，用 games 信息补两队基础行。"""
    rows = []
    teams = [
        (game.get("team_home"), game.get("score_home")),
        (game.get("team_away"), game.get("score_away")),
    ]
    for team, points in teams:
        if not team:
            continue
        rows.append(
            {
                "game_id": game.get("game_id"),
                "game_no": _to_int(game.get("game_no")),
                "team": team,
                "points": _to_int(points),
                "rebounds": None,
                "assists": None,
                "steals": None,
                "blocks": None,
                "turnovers": None,
                "fouls": None,
                "fg_pct": None,
                "three_pct": None,
                "ft_pct": None,
                "source_url": game.get("game_url"),
            }
        )
    return rows


def _decode_next_text(html: str) -> str:
    """把 Next.js flight 脚本里常见的转义引号还原，便于提取 JSON 片段。"""
    return html.replace('\\"', '"').replace("\\/", "/")


def _extract_json_value_after_key(text: str, key: str):
    """从文本中提取 key 后面的 JSON 数组或对象。"""
    marker = f'"{key}":'
    start = text.find(marker)
    if start < 0:
        marker = f"{key}:"
        start = text.find(marker)
    if start < 0:
        return None

    pos = start + len(marker)
    while pos < len(text) and text[pos].isspace():
        pos += 1
    if pos >= len(text) or text[pos] not in "[{":
        return None

    opening = text[pos]
    closing = "]" if opening == "[" else "}"
    depth = 0
    in_string = False
    escaped = False

    for index in range(pos, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                raw_json = text[pos : index + 1]
                try:
                    return json.loads(raw_json)
                except json.JSONDecodeError:
                    return None
    return None


def _player_name(player: dict) -> str | None:
    """拼接球员姓名。"""
    first_name = _clean_text(player.get("firstName"))
    last_name = _clean_text(player.get("lastName"))
    return _clean_text(" ".join(part for part in [first_name, last_name] if part))


def _build_roster_maps(decoded_html: str, game: dict) -> tuple[dict[str, dict], dict[str, str]]:
    """从 playersTeamA/B 构造 personId 到球员信息和队名的映射。"""
    players_a = _extract_json_value_after_key(decoded_html, "playersTeamA") or []
    players_b = _extract_json_value_after_key(decoded_html, "playersTeamB") or []
    team_a = game.get("team_home")
    team_b = game.get("team_away")

    roster: dict[str, dict] = {}
    player_team: dict[str, str] = {}
    for player in players_a:
        person_id = str(player.get("personId"))
        roster[person_id] = player
        player_team[person_id] = team_a
    for player in players_b:
        person_id = str(player.get("personId"))
        roster[person_id] = player
        player_team[person_id] = team_b
    return roster, player_team


def _extract_game_detail_teams(decoded_html: str) -> list[dict]:
    """提取 gameDetails.c 里的两队统计对象。"""
    game_details = _extract_json_value_after_key(decoded_html, "gameDetails")
    if not isinstance(game_details, dict):
        return []
    teams = game_details.get("c")
    return teams if isinstance(teams, list) else []


def _stats_to_player_row(stats: dict, player: dict, team: str | None, game: dict) -> dict:
    """把 FIBA Stats 字段转换为 player_boxscores 字段。"""
    minutes = stats.get("TP")
    return {
        "game_id": game.get("game_id"),
        "game_no": _to_int(game.get("game_no")),
        "team": team,
        "player_name": _player_name(player),
        "starter": str(bool(stats.get("Starter"))) if stats.get("Starter") is not None else None,
        "minutes": minutes,
        "minutes_float": _minutes_to_float(minutes),
        "points": _to_int(stats.get("PTS")) or 0,
        "rebounds": _to_int(stats.get("REB")) or 0,
        "assists": _to_int(stats.get("AS")) or 0,
        "steals": _to_int(stats.get("ST")) or 0,
        "blocks": _to_int(_pick_first(stats.get("BS"), stats.get("BLK"))) or 0,
        "turnovers": _to_int(stats.get("TO")) or 0,
        "fouls": _to_int(stats.get("PF")) or 0,
        "fgm": _to_int(stats.get("FGM")) or 0,
        "fga": _to_int(stats.get("FGA")) or 0,
        "fg_pct": _to_float(stats.get("FGP")),
        "three_pm": _to_int(stats.get("FG3M")) or 0,
        "three_pa": _to_int(stats.get("FG3A")) or 0,
        "three_pct": _to_float(stats.get("FG3P")),
        "ftm": _to_int(stats.get("FTM")) or 0,
        "fta": _to_int(stats.get("FTA")) or 0,
        "ft_pct": _to_float(stats.get("FTP")),
        "efficiency": _to_float(stats.get("EFF")),
        "source_url": game.get("game_url"),
    }


def _parse_player_boxscores_from_next_data(html: str, game: dict) -> list[dict]:
    """从 Next.js 脚本数据中解析球员 boxscore。"""
    decoded = _decode_next_text(html)
    roster, player_team = _build_roster_maps(decoded, game)
    teams = _extract_game_detail_teams(decoded)
    rows: list[dict] = []

    for team_obj in teams:
        for child in team_obj.get("Children", []) or []:
            player_id = str(child.get("Id", "")).replace("P_", "")
            stats = child.get("Stats") or {}
            player = roster.get(player_id, {})
            if not player and not stats:
                continue
            row = _stats_to_player_row(stats, player, player_team.get(player_id), game)
            if row.get("player_name"):
                rows.append(row)

    return rows


def _table_row_to_player_boxscore(row: dict, game: dict) -> dict | None:
    """尝试把 HTML 表格行转换为球员 boxscore。"""
    player_name = _pick_stat(row, ["player", "player name", "name", "col_1", "col_2"])
    if not player_name:
        return None
    player_name = _clean_text(str(player_name))
    if not player_name or _looks_messy_team(player_name):
        return None

    fg_made, fg_attempts = _split_made_attempts(_pick_stat(row, ["fg", "field goals", "fgm/fga"]))
    three_made, three_attempts = _split_made_attempts(_pick_stat(row, ["3pt", "3p", "3pm/3pa"]))
    ft_made, ft_attempts = _split_made_attempts(_pick_stat(row, ["ft", "free throws", "ftm/fta"]))
    minutes = _pick_stat(row, ["min", "minutes", "minutes played"])

    return {
        "game_id": game.get("game_id"),
        "game_no": _to_int(game.get("game_no")),
        "team": _pick_stat(row, ["team"]),
        "player_name": player_name,
        "starter": _pick_stat(row, ["starter", "start"]),
        "minutes": minutes,
        "minutes_float": _minutes_to_float(minutes),
        "points": _to_int(_pick_stat(row, ["pts", "points"])) or 0,
        "rebounds": _to_int(_pick_stat(row, ["reb", "rebounds"])) or 0,
        "assists": _to_int(_pick_stat(row, ["ast", "assists"])) or 0,
        "steals": _to_int(_pick_stat(row, ["stl", "steals"])) or 0,
        "blocks": _to_int(_pick_stat(row, ["blk", "blocks"])) or 0,
        "turnovers": _to_int(_pick_stat(row, ["to", "tov", "turnovers"])) or 0,
        "fouls": _to_int(_pick_stat(row, ["pf", "fouls"])) or 0,
        "fgm": _to_int(_pick_stat(row, ["fgm"])) if fg_made is None else fg_made,
        "fga": _to_int(_pick_stat(row, ["fga"])) if fg_attempts is None else fg_attempts,
        "fg_pct": _to_float(_pick_stat(row, ["fg%", "fg pct"])),
        "three_pm": _to_int(_pick_stat(row, ["3pm"])) if three_made is None else three_made,
        "three_pa": _to_int(_pick_stat(row, ["3pa"])) if three_attempts is None else three_attempts,
        "three_pct": _to_float(_pick_stat(row, ["3p%", "3pt%", "three pct"])),
        "ftm": _to_int(_pick_stat(row, ["ftm"])) if ft_made is None else ft_made,
        "fta": _to_int(_pick_stat(row, ["fta"])) if ft_attempts is None else ft_attempts,
        "ft_pct": _to_float(_pick_stat(row, ["ft%", "ft pct"])),
        "efficiency": _to_float(_pick_stat(row, ["eff", "efficiency"])),
        "source_url": game.get("game_url"),
    }


def _parse_player_boxscores_from_html(html_path: Path, game: dict) -> list[dict]:
    """从单场 HTML 解析球员 boxscore。"""
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    rows = _parse_player_boxscores_from_next_data(html, game)
    if rows:
        return rows

    soup = _make_soup(html)
    table_rows: list[dict] = []
    for table in soup.select("table"):
        for raw_row in _table_to_dict_rows(table):
            parsed = _table_row_to_player_boxscore(raw_row, game)
            if parsed:
                table_rows.append(parsed)
    return table_rows


def parse_games(
    html_dir: Path = RAW_HTML_DIR,
    html_map_csv: Path = HTML_MAP_CSV,
    game_urls_csv: Path = GAME_URLS_CSV,
    output_csv: Path = GAMES_CSV,
) -> pd.DataFrame:
    """解析 games 表，输出 data/clean/games.csv，并写入 SQLite games 表。"""
    ensure_directories()
    html_map_rows = _read_csv_rows(html_map_csv)
    url_rows = _read_csv_rows(game_urls_csv)
    url_fallback = _fallback_by_url(url_rows)
    map_by_url = {row.get("game_url"): row for row in html_map_rows if row.get("game_url")}

    all_urls = []
    for row in url_rows:
        if row.get("game_url") and row.get("game_url") not in all_urls:
            all_urls.append(row.get("game_url"))
    for row in html_map_rows:
        if row.get("game_url") and row.get("game_url") not in all_urls:
            all_urls.append(row.get("game_url"))

    games: list[dict] = []
    for index, game_url in enumerate(all_urls, start=1):
        fallback_row = url_fallback.get(game_url, {})
        map_row = map_by_url.get(game_url, {})
        base_row = {**fallback_row, **map_row}
        base_row["game_url"] = game_url
        if not base_row.get("game_no"):
            base_row["game_no"] = index

        html_file = base_row.get("html_file")
        html_path = Path(html_file) if html_file else html_dir / f"game_{_to_int(base_row.get('game_no')) or index:02d}.html"

        try:
            if html_path.exists():
                game = _parse_game_from_html(html_path, base_row)
            else:
                home_from_url, away_from_url = _team_codes_from_url(game_url)
                game = {
                    "game_id": _game_id_from_url(game_url),
                    "game_no": _to_int(base_row.get("game_no")),
                    "event_name": EVENT_NAME,
                    "game_date": base_row.get("source_date"),
                    "stage": base_row.get("stage"),
                    "team_home": _pick_first(base_row.get("team_home"), home_from_url),
                    "team_away": _pick_first(base_row.get("team_away"), away_from_url),
                    "score_home": _to_int(base_row.get("score_home")),
                    "score_away": _to_int(base_row.get("score_away")),
                    "winner": None,
                    "game_url": game_url,
                }
            games.append({column: game.get(column) for column in GAME_COLUMNS})
        except Exception as exc:
            print(f"warning: game_no={base_row.get('game_no')} 解析失败：{exc}")
            _copy_parse_failed_html(html_path, _to_int(base_row.get("game_no")))
            home_from_url, away_from_url = _team_codes_from_url(game_url)
            games.append(
                {
                    "game_id": _game_id_from_url(game_url),
                    "game_no": _to_int(base_row.get("game_no")),
                    "event_name": EVENT_NAME,
                    "game_date": base_row.get("source_date"),
                    "stage": base_row.get("stage"),
                    "team_home": _pick_first(base_row.get("team_home"), home_from_url),
                    "team_away": _pick_first(base_row.get("team_away"), away_from_url),
                    "score_home": _to_int(base_row.get("score_home")),
                    "score_away": _to_int(base_row.get("score_away")),
                    "winner": None,
                    "game_url": game_url,
                }
            )

    df = pd.DataFrame(games, columns=GAME_COLUMNS)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM games")
        df.to_sql("games", conn, if_exists="append", index=False)

    print(f"games 行数：{len(df)}")
    if url_rows and len(df) < len(url_rows) * 0.9:
        print("warning: games 行数明显少于 fiba_game_urls.csv 的行数，请检查 HTML 下载和解析结果。")

    return df


def parse_team_boxscores(
    html_dir: Path = RAW_HTML_DIR,
    html_map_csv: Path = HTML_MAP_CSV,
    games_csv: Path = GAMES_CSV,
    output_csv: Path = TEAM_BOXSCORES_CSV,
) -> pd.DataFrame:
    """解析球队统计，输出 CSV 并写入 SQLite team_boxscores 表。"""
    ensure_directories()
    games_df = _read_csv_df(games_csv)
    if games_df.empty:
        games_df = parse_games()

    html_map_rows = _read_csv_rows(html_map_csv)
    html_map_by_url = {row.get("game_url"): row for row in html_map_rows if row.get("game_url")}

    all_rows: list[dict] = []
    for _, game_series in games_df.iterrows():
        game = game_series.where(pd.notna(game_series), None).to_dict()
        game_no = _to_int(game.get("game_no"))
        game_url = game.get("game_url")
        map_row = html_map_by_url.get(game_url, {})
        html_file = map_row.get("html_file")
        html_path = Path(html_file) if html_file else html_dir / f"game_{game_no:02d}.html"

        try:
            if html_path.exists():
                rows = _parse_team_boxscores_from_html(html_path, game)
            else:
                rows = []

            if not rows:
                rows = _fallback_team_boxscores(game)

            all_rows.extend(rows)
            print(f"game_{game_no:02d} 球队统计行数：{len(rows)}")
        except Exception as exc:
            print(f"warning: game_{game_no:02d} 球队统计解析失败：{exc}")
            _copy_parse_failed_html(html_path, game_no)
            rows = _fallback_team_boxscores(game)
            all_rows.extend(rows)
            print(f"game_{game_no:02d} 球队统计行数：{len(rows)}")

    df = pd.DataFrame(all_rows, columns=TEAM_BOXSCORE_COLUMNS)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM team_boxscores")
        df.to_sql("team_boxscores", conn, if_exists="append", index=False)

    print(f"team_boxscores 总行数：{len(df)}")
    expected_rows = len(games_df) * 2
    if expected_rows and len(df) < expected_rows * 0.8:
        print("warning: team_boxscores 总行数明显少于比赛数 x 2，请检查 HTML 结构和解析逻辑。")

    return df


def parse_player_boxscores(
    html_dir: Path = RAW_HTML_DIR,
    html_map_csv: Path = HTML_MAP_CSV,
    games_csv: Path = GAMES_CSV,
    output_csv: Path = PLAYER_BOXSCORES_CSV,
) -> pd.DataFrame:
    """解析球员 boxscore，输出 CSV 并写入 SQLite player_boxscores 表。"""
    ensure_directories()
    games_df = _read_csv_df(games_csv)
    if games_df.empty:
        games_df = parse_games()

    html_map_rows = _read_csv_rows(html_map_csv)
    html_map_by_url = {row.get("game_url"): row for row in html_map_rows if row.get("game_url")}

    all_rows: list[dict] = []
    for _, game_series in games_df.iterrows():
        game = game_series.where(pd.notna(game_series), None).to_dict()
        game_no = _to_int(game.get("game_no"))
        game_url = game.get("game_url")
        map_row = html_map_by_url.get(game_url, {})
        html_file = map_row.get("html_file")
        html_path = Path(html_file) if html_file else html_dir / f"game_{game_no:02d}.html"

        rows: list[dict] = []
        try:
            if html_path.exists():
                rows = _parse_player_boxscores_from_html(html_path, game)
            else:
                print(f"warning: game_{game_no:02d} HTML 不存在，无法解析球员数据。")

            if not rows:
                _copy_parse_failed_html(html_path, game_no)

            all_rows.extend(rows)
            print(f"game_{game_no:02d} 球员数量：{len(rows)}")
        except Exception as exc:
            print(f"warning: game_{game_no:02d} 球员 boxscore 解析失败：{exc}")
            _copy_parse_failed_html(html_path, game_no)
            print(f"game_{game_no:02d} 球员数量：0")

    df = pd.DataFrame(all_rows, columns=PLAYER_BOXSCORE_COLUMNS)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM player_boxscores")
        df.to_sql("player_boxscores", conn, if_exists="append", index=False)

    print(f"player_boxscores 总行数：{len(df)}")
    zero_games_estimate = 0
    if not games_df.empty:
        parsed_game_ids = set(df["game_id"].dropna()) if not df.empty else set()
        zero_games_estimate = sum(1 for game_id in games_df["game_id"].dropna() if game_id not in parsed_game_ids)
    if zero_games_estimate:
        print(f"warning: 有 {zero_games_estimate} 场比赛解析到 0 名球员，已复制对应 HTML 到 data/raw/debug/。")

    return df


def parse_all_games(html_dir: Path = RAW_HTML_DIR) -> None:
    """兼容旧入口：解析 games、team_boxscores 和 player_boxscores。"""
    parse_games(html_dir=html_dir)
    parse_team_boxscores(html_dir=html_dir)
    parse_player_boxscores(html_dir=html_dir)
