"""加载 .env 环境变量（轻量实现，不引入 python-dotenv 依赖）。

.env 文件放在项目根目录（backend/ 的上一级），键值对每行一条，例如：
    DEEPSEEK_API_KEY=sk-xxxx

本模块在包导入时自动执行，把 .env 里的变量注入到 os.environ（不覆盖已存在的值）。
"""
import os

# __file__ = backend/app/__init__.py
# 两次 dirname → backend/，再上一级 → 项目根目录
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")


def _load_dotenv() -> None:
    if not os.path.exists(_ENV_PATH):
        return
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()
