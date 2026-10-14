"""pytest 全局配置。

关键：在导入 app 之前把数据库指向独立的临时库，
避免测试读写演示库 data/lab_reports.db 造成数据被改动。

临时目录刻意建在**项目内**（tests/.tmp/）而不是系统 Temp：
部分环境（CI 沙箱、受限的 Windows 用户）对系统 Temp 无写权限，
会导致 collection 阶段直接崩溃。放在项目内可完全规避。
"""
import os
import shutil
from pathlib import Path

_TMP_ROOT = Path(__file__).resolve().parent / ".tmp"
# 每次运行重建，避免残留上一次的库文件干扰
shutil.rmtree(_TMP_ROOT, ignore_errors=True)
_TMP_ROOT.mkdir(parents=True, exist_ok=True)

os.environ["LAB_REPORTS_DB"] = str(_TMP_ROOT / "test.db")
