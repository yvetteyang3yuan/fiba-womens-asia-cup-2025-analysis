import sys
from pathlib import Path

# 让 scripts/ 下的脚本可以直接运行并导入 src 包。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
