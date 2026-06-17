# 2025 FIBA 女篮亚洲杯数据采集与中国女篮表现分析

## 项目简介

yvetteyang  motify readme file

本项目基于 FIBA 官方公开页面，收集 2025 FIBA 女篮亚洲杯全部比赛数据，整理比赛信息、球队技术统计和球员 boxscore，并进一步进行中国女篮球员表现分析和全赛事基础统计分析。

项目范围仅限 **2025 FIBA Women's Asia Cup Division A**，不包含 WCBA、WNBA 或其他赛事。

## 项目结构

```text
fiba-womens-asia-cup-2025-analysis/
├── README.md
├── requirements.txt
├── data/
│   ├── raw/
│   │   ├── html/                  # 原始比赛 HTML
│   │   ├── debug/                 # 调试 HTML、截图、失败 URL
│   │   ├── fiba_game_urls.csv     # 最终比赛 URL 清单
│   │   ├── manual_game_urls.csv   # 人工补充 URL
│   │   └── html_map.csv           # game_no、game_url、HTML 文件映射
│   ├── clean/                     # 清洗后 CSV 与分析结果
│   └── database/
│       └── fiba2025.db            # SQLite 数据库
├── src/
│   ├── config.py
│   ├── db.py
│   ├── fiba_url_collector.py
│   ├── fiba_html_crawler.py
│   ├── fiba_game_parser.py
│   ├── export_csv.py
│   ├── metrics.py
│   └── visualization.py
├── scripts/
│   ├── init_db.py
│   ├── collect_game_urls.py
│   ├── crawl_all_games.py
│   ├── parse_all_games.py
│   ├── export_data.py
│   ├── run_china_analysis.py
│   └── run_tournament_analysis.py
├── notebooks/
└── reports/
    └── figures/                  # 分析图表
```

## 数据来源

数据来自 FIBA 官方公开页面：

- FIBA Women's Asia Cup 2025 官方赛事页
- FIBA Women's Asia Cup 2025 Games 页面
- 各场比赛详情页

## 环境安装

```bash
conda create -n fiba2025 python=3.11
conda activate fiba2025
pip install -r requirements.txt
```

## 运行步骤

```bash
python scripts/init_db.py
python scripts/collect_game_urls.py
python scripts/crawl_all_games.py
python scripts/parse_all_games.py
python scripts/export_data.py
python scripts/run_china_analysis.py
python scripts/run_tournament_analysis.py
```

## 输出文件说明

`data/clean/`：

- `games.csv`：比赛基础信息
- `team_boxscores.csv`：球队技术统计
- `player_boxscores.csv`：球员 boxscore
- `games_from_db.csv`：从 SQLite 导出的比赛表
- `team_boxscores_from_db.csv`：从 SQLite 导出的球队统计表
- `player_boxscores_from_db.csv`：从 SQLite 导出的球员统计表
- `china_player_summary.csv`：中国女篮球员表现汇总
- `tournament_player_summary.csv`：全赛事球员汇总
- `tournament_team_summary.csv`：全赛事球队汇总

`reports/figures/`：

- 中国队球员场均得分、篮板、助攻、效率 Top 10 图表
- 全赛事球员得分、篮板、助攻 Top 15 图表
- 各队场均得分排名图表

`data/database/fiba2025.db`：

- SQLite 数据库，包含 `games`、`team_boxscores`、`player_boxscores` 三张核心表。

## 合规说明

本项目仅采集公开网页数据，不登录、不绕过验证码、不破解接口、不高频请求，仅用于学习研究。

项目中的网络请求设置了等待时间；如果遇到验证码、登录、Access Denied、Forbidden 或权限控制页面，程序会保存调试文件并提示人工检查，不会尝试绕过限制。

## 后续计划

- 球员画像
- 高级指标
- 球队攻防特征
- 聚类分析
- 比赛胜负影响因素分析
