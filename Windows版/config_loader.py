"""跨平台配置加载与用户数据目录管理。

职责：
1. 在用户数据目录 (~/个人助理数据/) 准备好默认 config.yaml（从模板复制）
2. 提供 .env 路径（配置向导写到这里）
3. 检测配置是否完整（决定弹向导还是直接进控制台）

关键设计：不改后端 core/config.py。通过把 config.yaml 放到用户数据目录、
并以用户数据目录为 cwd 启动 main.py，让后端代码自然读到正确配置。
"""
import os
import sys
import shutil

def _resolve_root():
    """解析项目根目录（含 config.yaml 模板 / core / bots / analysis）。

    PyInstaller 打包后：后端代码和 config.yaml 解压到 sys._MEIPASS。
    开发环境：__file__ 在 Windows版/ 下，根目录是上一级。
    """
    if hasattr(sys, "_MEIPASS"):
        meipass = sys._MEIPASS
        if os.path.isfile(os.path.join(meipass, "config.yaml")):
            return meipass
    dev_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return dev_root


# 用户数据目录（与 process_manager_win.DATA_DIR 一致）
DATA_DIR = os.path.join(os.path.expanduser("~"), "个人助理数据")

# 项目根目录
ROOT = _resolve_root()

# 关键文件路径
ENV_PATH = os.path.join(DATA_DIR, ".env")
CONFIG_PATH = os.path.join(DATA_DIR, "config.yaml")
CONFIG_TEMPLATE = os.path.join(ROOT, "config.yaml")  # 项目根的脱敏模板


def ensure_data_dir():
    """确保用户数据目录存在。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    return DATA_DIR


def ensure_default_config():
    """如果用户数据目录没有 config.yaml，从项目模板复制一份默认的。

    这样 main.py 启动时（cwd=DATA_DIR）能读到 config.yaml。
    只在首次运行时复制，不覆盖用户已有配置。
    同时确保 data/ 子目录存在（数据库要写在这里）。
    """
    ensure_data_dir()
    # 确保 data/ 子目录存在（config.yaml 里 db_path 是 ./data/habit_tracker.db）
    data_subdir = os.path.join(DATA_DIR, "data")
    os.makedirs(data_subdir, exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        if os.path.exists(CONFIG_TEMPLATE):
            shutil.copy2(CONFIG_TEMPLATE, CONFIG_PATH)
        else:
            # 模板不存在（打包场景），写一份内置默认配置
            _write_builtin_default(CONFIG_PATH)
    return CONFIG_PATH


def _write_builtin_default(path):
    """打包后项目根的 config.yaml 可能不存在，写一份内置默认配置。"""
    default_content = """# 个人助理默认配置（自动生成）
system:
  enable_ai: true
  db_path: "./data/habit_tracker.db"

ai:
  provider: "openai"
  api_key: ""
  api_base: "https://apihub.agnes-ai.com/v1"
  model_name: "agnes-2.0-flash"

schedules:
  morning_reminder: "09:00"
  fitness_reminder_monday: "16:00"
  fitness_reminder_thursday: "16:00"
  night_check: "21:00"
  daily_summary: "22:00"
  weekly_report: "23:00"
  archive: "03:00"

tasks:
  fixed:
    - name: "起床"
      remind_time: "09:00"
      days_of_week: ""
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(default_content)


def env_exists():
    """检测 .env 是否存在。"""
    return os.path.exists(ENV_PATH)


def env_is_complete():
    """检测 .env 是否包含必需的配置项（决定是否弹配置向导）。

    必需项：飞书两个应用 + chat_id + AI key。
    多维表格可选（不影响基础功能）。
    """
    if not os.path.exists(ENV_PATH):
        return False
    required = [
        "FEISHU_XIAONAO_APP_ID",
        "FEISHU_XIAONAO_SECRET",
        "FEISHU_XIAOZHI_APP_ID",
        "FEISHU_XIAOZHI_SECRET",
        "FEISHU_CHAT_ID",
        "AI_API_KEY",
    ]
    values = parse_env()
    return all(values.get(k, "").strip() for k in required)


def parse_env():
    """读取 .env 文件，返回 {key: value} 字典。"""
    result = {}
    if not os.path.exists(ENV_PATH):
        return result
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip().strip('"').strip("'")
    return result


def write_env(config_dict):
    """把配置字典写成 .env 文件（配置向导用）。

    config_dict: {
        "FEISHU_XIAONAO_APP_ID": "...", ...
        "BITABLE_TABLE_IDS": {"log":"tblX", ...}  # 特殊：写成 JSON
    }
    """
    ensure_data_dir()
    lines = ["# 个人助理配置（由配置向导生成）", ""]
    # 飞书应用
    lines.append("# 飞书应用")
    for k in ["FEISHU_XIAONAO_APP_ID", "FEISHU_XIAONAO_SECRET",
              "FEISHU_XIAOZHI_APP_ID", "FEISHU_XIAOZHI_SECRET",
              "FEISHU_CHAT_ID"]:
        if k in config_dict and config_dict[k]:
            lines.append(f"{k}={config_dict[k]}")
    lines.append("")
    # AI
    lines.append("# AI 模型")
    for k in ["AI_API_KEY", "AI_API_BASE", "AI_MODEL"]:
        if k in config_dict and config_dict[k]:
            lines.append(f"{k}={config_dict[k]}")
    lines.append("")
    # 多维表格（可选）
    bitable_keys = ["BITABLE_APP_ID", "BITABLE_APP_SECRET", "BITABLE_APP_TOKEN"]
    if any(config_dict.get(k) for k in bitable_keys):
        lines.append("# 多维表格同步应用")
        for k in bitable_keys:
            if k in config_dict and config_dict[k]:
                lines.append(f"{k}={config_dict[k]}")
        if config_dict.get("BITABLE_TABLE_IDS"):
            import json
            lines.append(f"BITABLE_TABLE_IDS={json.dumps(config_dict['BITABLE_TABLE_IDS'], ensure_ascii=False)}")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return ENV_PATH
