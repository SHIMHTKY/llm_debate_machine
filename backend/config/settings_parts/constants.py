"""设置模块共享常量。

把路径、范围约束、环境变量入口全部集中在这里，
后续任何子模块只要依赖设置常量，都从这里拿，避免硬编码散落。
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# 项目根目录。settings.py 位于 backend/config，下标 parents[2] 正好回到仓库根。
BASE_DIR = Path(__file__).resolve().parents[3]
# settings.json 仍然沿用原来的 data 目录，不改存储位置。
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
ENV_FILE = BASE_DIR / ".env"

# 前端展示密钥时统一使用这个占位符，避免泄露真实 token。
MASKED_SECRET = "••••••••••••"

# 当前产品允许保存的辩手配置上限。
MAX_DEBATER_PRESETS = 24

# 上下文轮数的默认值与合法范围。
DEFAULT_CONTEXT_ROUNDS = 3
MIN_CONTEXT_ROUNDS = 2
MAX_CONTEXT_ROUNDS = 6

# 这两类枚举会参与设置合法性校验。
VALID_PROVIDERS = {"azure", "chatopenai"}
VALID_TOOL_MODES = {"bind_tools", "react"}

# 在模块导入阶段就加载 .env，这样后续默认配置函数可以直接读环境变量。
load_dotenv(ENV_FILE)
