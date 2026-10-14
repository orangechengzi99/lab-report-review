"""SQLite 持久化存储层。

用 Python 内置 sqlite3，零外部依赖。
数据库文件默认放在项目根目录 data/lab_reports.db（已加入 .gitignore）。
首次启动自动建表 + 种子数据；之后重启不丢数据。

可用环境变量 LAB_REPORTS_DB 覆盖数据库路径（测试用独立临时库，避免污染演示数据）。

设计原则：
- API 接口不变，main.py 改动最小
- 每次请求获取独立连接，用完即关（sqlite3 线程安全）
- 自增主键由数据库管理，不再手动分配 id
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Optional

from .models import Report, Analyte, AnalyteStatus

# 数据库路径：环境变量优先，其次项目根目录 / data/lab_reports.db
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_DEFAULT_DB = os.path.join(_PROJECT_ROOT, "data", "lab_reports.db")
_DB_PATH = os.environ.get("LAB_REPORTS_DB") or _DEFAULT_DB
_DB_DIR = os.path.dirname(_DB_PATH)

_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    """获取数据库连接（每次调用新连接，用完关闭）。"""
    conn = sqlite3.connect(_DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # 并发读更好
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ------------------------------------------------------------------ 建表 SQL
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_label  TEXT NOT NULL,
    exam_type      TEXT NOT NULL,
    collected_at   TEXT,
    source_note    TEXT DEFAULT '',
    hospital        TEXT DEFAULT '',
    image_url       TEXT DEFAULT '',
    created_at     TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS analytes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    raw_name        TEXT NOT NULL DEFAULT '',
    raw_value       TEXT NOT NULL DEFAULT '',
    raw_unit        TEXT,
    raw_ref_range   TEXT,
    value           REAL,
    result_text     TEXT,
    unit            TEXT,
    ref_low         REAL,
    ref_high        REAL,
    ref_text        TEXT,
    status          TEXT NOT NULL DEFAULT 'unchecked',
    note            TEXT,
    category        TEXT DEFAULT '其他'
);

CREATE INDEX IF NOT EXISTS idx_analytes_report ON analytes(report_id);
"""


def init_db(seed: bool = True) -> None:
    """初始化数据库（建表 + 可选种子数据）。"""
    os.makedirs(_DB_DIR, exist_ok=True)
    with _lock:
        conn = _get_db()
        try:
            conn.executescript(_SCHEMA_SQL)
            report_columns = {row[1] for row in conn.execute("PRAGMA table_info(reports)")}
            if "hospital" not in report_columns:
                conn.execute("ALTER TABLE reports ADD COLUMN hospital TEXT DEFAULT ''")
            if "image_url" not in report_columns:
                conn.execute("ALTER TABLE reports ADD COLUMN image_url TEXT DEFAULT ''")
            analyte_columns = {row[1] for row in conn.execute("PRAGMA table_info(analytes)")}
            if "result_text" not in analyte_columns:
                conn.execute("ALTER TABLE analytes ADD COLUMN result_text TEXT")
            if "ref_text" not in analyte_columns:
                conn.execute("ALTER TABLE analytes ADD COLUMN ref_text TEXT")
            conn.commit()
        finally:
            conn.close()

    if seed:
        _seed_if_empty()
        seed_trend_demo()


# ------------------------------------------------------------------ 种子数据
def _seed_if_empty() -> None:
    """如果 reports 表为空，插入 2 份演示报告。"""
    with _lock:
        conn = _get_db()
        try:
            row = conn.execute("SELECT COUNT(*) FROM reports").fetchone()
            if row[0] > 0:
                return  # 已有数据，不重复插入

            demo = _build_demo_reports()
            for r in demo:
                cur = conn.execute(
                    "INSERT INTO reports (id, patient_label, exam_type, collected_at, source_note) VALUES (?, ?, ?, ?, ?)",
                    (r.id, r.patient_label, r.exam_type, r.collected_at, r.source_note),
                )
                rid = r.id  # 使用原始 ID
                for a in r.analytes:
                    conn.execute(
                        """INSERT INTO analytes
                           (id, report_id, name, raw_name, raw_value, raw_unit, raw_ref_range,
                            value, result_text, unit, ref_low, ref_high, ref_text, status, note, category)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (a.id, rid, a.name, a.raw_name, a.raw_value, a.raw_unit, a.raw_ref_range,
                         a.value, a.result_text, a.unit, a.ref_low, a.ref_high, a.ref_text,
                         a.status.value, a.note,
                         a.category),
                    )
            conn.commit()
        finally:
            conn.close()


def _build_demo_reports() -> list[Report]:
    """构造 2 份演示报告（与原 sample_data 一致）。"""
    return [
        Report(
            id=1,
            patient_label="DEMO-001（虚构）",
            exam_type="血常规",
            collected_at="2026-10-01",
            source_note="手工构造的演示数据，非真实患者报告",
            analytes=[
                Analyte(id=101, name="白细胞计数", raw_name="白细胞计数 WBC",
                        raw_value="9.2", raw_unit="10^9/L", raw_ref_range="3.5-9.5",
                        value=9.2, unit="10^9/L", ref_low=3.5, ref_high=9.5,
                        status=AnalyteStatus.CONFIRMED, category="血常规"),
                Analyte(id=102, name="血红蛋白", raw_name="血红蛋白 HGB",
                        raw_value="98", raw_unit="g/L", raw_ref_range="115-150",
                        value=98.0, unit="g/L", ref_low=115.0, ref_high=150.0,
                        status=AnalyteStatus.CONFIRMED, category="血常规"),
                Analyte(id=103, name="血小板计数", raw_name="血小板 PLT",
                        raw_value="456", raw_unit="10^9/L", raw_ref_range="125-350",
                        value=456.0, unit="10^9/L", ref_low=125.0, ref_high=350.0,
                        status=AnalyteStatus.CONFIRMED, category="血常规"),
                Analyte(id=104, name="中性粒细胞百分比", raw_name="中性粒 %",
                        raw_value="72.5", raw_unit="%", raw_ref_range="40-75",
                        value=None, unit=None, ref_low=None, ref_high=None,
                        status=AnalyteStatus.UNCHECKED, category="血常规"),
                Analyte(id=105, name="平均红细胞体积", raw_name="MCV",
                        raw_value="88", raw_unit="fL", raw_ref_range=None,
                        value=88.0, unit="fL", ref_low=None, ref_high=None,
                        status=AnalyteStatus.CONFIRMED, category="血常规"),
                Analyte(id=106, name="抗环瓜氨酸肽抗体", raw_name="抗CCP抗体",
                        raw_value="阴性", raw_unit=None, raw_ref_range=None,
                        value=None, result_text="阴性", unit=None, ref_low=None, ref_high=None,
                        status=AnalyteStatus.CONFIRMED, category="风湿免疫"),
            ],
        ),
        Report(
            id=2,
            patient_label="DEMO-002（虚构）",
            exam_type="生化全项",
            collected_at="2026-10-08",
            source_note="手工构造的演示数据，非真实患者报告",
            analytes=[
                Analyte(id=201, name="空腹血糖", raw_name="GLU 空腹",
                        raw_value="6.8", raw_unit="mmol/L", raw_ref_range="3.9-6.1",
                        value=None, unit=None, ref_low=None, ref_high=None,
                        status=AnalyteStatus.UNCHECKED, category="生化全项"),
                Analyte(id=202, name="总胆固醇", raw_name="TC",
                        raw_value="5.4", raw_unit="mmol/L", raw_ref_range="<5.2",
                        value=None, unit=None, ref_low=None, ref_high=None,
                        status=AnalyteStatus.UNCHECKED, category="生化全项"),
                Analyte(id=203, name="谷丙转氨酶", raw_name="ALT",
                        raw_value="45", raw_unit="U/L", raw_ref_range="9-50",
                        value=None, unit=None, ref_low=None, ref_high=None,
                        status=AnalyteStatus.UNCHECKED, category="肝功能"),
            ],
        ),
    ]


# ------------------------------------------------------------------ 趋势演示数据
# 4 次虚构随访检查（同一批指标跨时间），用于展示趋势图功能。
# 明确标注为手工构造的演示数据，非真实患者数据。
_TREND_DATES = ["2025-06-10", "2025-10-15", "2026-01-20", "2026-06-18"]

# 指标名, 单位, 分类, 各时间点数值, 参考范围
_TREND_SERIES = [
    ("白细胞计数", "10^9/L", "血常规", [6.2, 7.8, 9.1, 9.2], "3.5-9.5"),
    ("血红蛋白", "g/L", "血常规", [132, 124, 105, 98], "115-150"),
    ("血小板计数", "10^9/L", "血常规", [210, 235, 380, 456], "125-350"),
    ("平均红细胞体积", "fL", "血常规", [88, 87, 86, 88], "82-100"),
    ("空腹血糖", "mmol/L", "生化全项", [5.1, 5.6, 6.2, 6.8], "3.9-6.1"),
    ("总胆固醇", "mmol/L", "生化全项", [4.8, 5.0, 5.3, 5.4], "<5.2"),
    ("谷丙转氨酶", "U/L", "肝功能", [22, 28, 38, 45], "9-50"),
    ("促甲状腺激素", "mIU/L", "甲状腺功能", [2.1, 1.8, 2.4, 2.2], "0.27-4.2"),
]


def seed_trend_demo() -> None:
    """插入演示用的跨时间随访报告（幂等：已有 DEMO-TREND 则跳过）。"""
    with _lock:
        conn = _get_db()
        try:
            exists = conn.execute(
                "SELECT COUNT(*) FROM reports WHERE patient_label LIKE 'DEMO-TREND%'"
            ).fetchone()[0]
            if exists:
                return

            from .rules import parse_ref_range, parse_value

            for i, date in enumerate(_TREND_DATES):
                cur = conn.execute(
                    "INSERT INTO reports (patient_label, exam_type, collected_at, source_note, hospital) VALUES (?, ?, ?, ?, ?)",
                    (f"DEMO-TREND-{i + 1}（虚构）", "随访复查", date,
                     "手工构造的随访演示数据，非真实患者报告", "演示医院"),
                )
                rid = cur.lastrowid
                for name, unit, category, values, ref_txt in _TREND_SERIES:
                    val = float(values[i])
                    low, high = parse_ref_range(ref_txt)
                    # 依据参考范围给出规则判断，决定初始核对状态
                    status = "confirmed"
                    conn.execute(
                        """INSERT INTO analytes
                           (report_id, name, raw_name, raw_value, raw_unit, raw_ref_range,
                            value, unit, ref_low, ref_high, status, note, category)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (rid, name, name, str(val), unit, ref_txt,
                         val, unit, low, high, status, None, category),
                    )
            conn.commit()
        finally:
            conn.close()


# ------------------------------------------------------------------ 行 → 对象转换
def _row_to_report(row: sqlite3.Row, analytes: list[Analyte]) -> Report:
    keys = row.keys()
    return Report(
        id=row["id"],
        patient_label=row["patient_label"],
        exam_type=row["exam_type"],
        collected_at=row["collected_at"],
        source_note=row["source_note"] or "",
        hospital=(row["hospital"] if "hospital" in keys else "") or "",
        image_url=(row["image_url"] if "image_url" in keys else None) or None,
        analytes=analytes,
    )


def _row_to_analyte(row: sqlite3.Row) -> Analyte:
    status = AnalyteStatus(row["status"]) if row["status"] else AnalyteStatus.UNCHECKED
    keys = row.keys()
    return Analyte(
        id=row["id"],
        name=row["name"],
        raw_name=row["raw_name"] or "",
        raw_value=row["raw_value"] or "",
        raw_unit=row["raw_unit"],
        raw_ref_range=row["raw_ref_range"],
        value=row["value"],
        result_text=(row["result_text"] if "result_text" in keys else None),
        unit=row["unit"],
        ref_low=row["ref_low"],
        ref_high=row["ref_high"],
        ref_text=(row["ref_text"] if "ref_text" in keys else None),
        status=status,
        note=row["note"],
        category=(row["category"] if "category" in keys else None) or "其他",
    )


# ------------------------------------------------------------------ 公开接口（与原 sample_data 兼容）
def get_all_reports() -> list[Report]:
    conn = _get_db()
    try:
        rows = conn.execute("SELECT * FROM reports ORDER BY id").fetchall()
        result = []
        for r in rows:
            arows = conn.execute(
                "SELECT * FROM analytes WHERE report_id = ? ORDER BY id", (r["id"],)
            ).fetchall()
            result.append(_row_to_report(r, [_row_to_analyte(a) for a in arows]))
        return result
    finally:
        conn.close()


def get_report(report_id: int) -> Report | None:
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        arows = conn.execute(
            "SELECT * FROM analytes WHERE report_id = ? ORDER BY id", (report_id,)
        ).fetchall()
        return _row_to_report(row, [_row_to_analyte(a) for a in arows])
    finally:
        conn.close()


def add_report(report: Report) -> Report:
    """新增一份报告及其所有指标，返回带 DB 分配 id 的副本。"""
    conn = _get_db()
    try:
        cur = conn.execute(
            "INSERT INTO reports (patient_label, exam_type, collected_at, source_note, hospital, image_url) VALUES (?, ?, ?, ?, ?, ?)",
            (report.patient_label, report.exam_type, report.collected_at,
             report.source_note, getattr(report, 'hospital', ''),
             getattr(report, 'image_url', None)),
        )
        rid = cur.lastrowid
        for a in report.analytes:
            conn.execute(
                """INSERT INTO analytes
                   (report_id, name, raw_name, raw_value, raw_unit, raw_ref_range,
                    value, result_text, unit, ref_low, ref_high, ref_text, status, note, category)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (rid, a.name, a.raw_name, a.raw_value, a.raw_unit, a.raw_ref_range,
                 a.value, a.result_text, a.unit, a.ref_low, a.ref_high, a.ref_text,
                 a.status.value, a.note,
                 getattr(a, 'category', '其他')),
            )
        conn.commit()
        # 返回带真实 id 的对象
        return get_report(rid)
    finally:
        conn.close()


def update_report(
    report_id: int,
    *,
    patient_label: str,
    exam_type: str,
    collected_at: str,
    hospital: str,
) -> Report | None:
    """更新报告基本信息，保留原图、来源说明、指标与核对状态。"""
    conn = _get_db()
    try:
        cursor = conn.execute(
            """UPDATE reports
               SET patient_label = ?, exam_type = ?, collected_at = ?, hospital = ?
               WHERE id = ?""",
            (patient_label, exam_type, collected_at, hospital, report_id),
        )
        conn.commit()
        if cursor.rowcount != 1:
            return None
    finally:
        conn.close()
    return get_report(report_id)


def update_analyte(analyte_id: int, **kwargs) -> Analyte | None:
    """更新单条指标字段，返回更新后的对象。"""
    allowed = {"name", "value", "result_text", "unit", "ref_low", "ref_high", "ref_text", "status", "note", "category"}
    sets = []
    vals = []
    for k, v in kwargs.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            # status 可能是 enum
            vals.append(v.value if hasattr(v, 'value') else v)
    if not sets:
        return None
    vals.append(analyte_id)

    conn = _get_db()
    try:
        conn.execute(f"UPDATE analytes SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
        row = conn.execute("SELECT * FROM analytes WHERE id = ?", (analyte_id,)).fetchone()
        return _row_to_analyte(row) if row else None
    finally:
        conn.close()


def update_analytes_batch(report_id: int, updates: list[tuple[int, dict]]) -> Report | None:
    """在一个事务中更新同一报告的多条指标；任意一条失败则全部回滚。"""
    allowed = {"name", "value", "result_text", "unit", "ref_low", "ref_high", "ref_text", "status", "note", "category"}
    conn = _get_db()
    try:
        conn.execute("BEGIN")
        for analyte_id, kwargs in updates:
            fields = [(key, value) for key, value in kwargs.items() if key in allowed]
            if not fields:
                raise ValueError("批量更新内容为空")
            sets = ", ".join(f"{key} = ?" for key, _ in fields)
            values = [value.value if hasattr(value, "value") else value for _, value in fields]
            values.extend([analyte_id, report_id])
            cursor = conn.execute(
                f"UPDATE analytes SET {sets} WHERE id = ? AND report_id = ?",
                values,
            )
            if cursor.rowcount != 1:
                raise ValueError(f"指标 {analyte_id} 不属于当前报告")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return get_report(report_id)


def get_next_id() -> int:
    """获取下一个可用的 report id（给导入模块用）。"""
    conn = _get_db()
    try:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM reports").fetchone()
        return row[0]
    finally:
        conn.close()


# 模块加载时自动初始化
init_db(seed=True)

# 兼容旧代码引用
_next_id = property(lambda self: get_next_id())  # type: ignore[assignment]
