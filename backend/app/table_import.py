"""表格/文本导入入口：把 CSV / Excel 电子版检验单解析为识别草稿。

离线、免费、不上传数据。支持两种常见版式：
1. 长表（每行一条指标）：列名包含 名称/结果/单位/参考范围。
2. 简单两列：第一列指标名，第二列结果。

解析产出的每个字段都默认"待核对"，与 OCR 入口共用同一套后端。
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from .ingest import make_report

# 常见列名别名（用于在表头里找"哪列是结果、哪列是参考范围"）
_COL_NAME = {"名称", "项目", "检验项目", "指标", "项目名称", "item", "name", "test"}
_COL_VALUE = {"结果", "测定值", "检验结果", "结果值", "value", "result"}
_COL_UNIT = {"单位", "unit"}
_COL_REF = {"参考范围", "参考值", "参考区间", "正常范围", "范围", "ref", "range", "reference"}


def _find_col(headers: list[str], candidates: set[str]) -> Optional[int]:
    """在表头里找到匹配候选名的那一列，找不到返回 None。"""
    for i, h in enumerate(headers):
        if h is None:
            continue
        key = str(h).strip().lower()
        if key in {c.lower() for c in candidates}:
            return i
    return None


def parse_csv(text: str) -> list[dict]:
    """解析 CSV 文本，返回 [{"name","value","unit","ref_range"}, ...]"""
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(cell and cell.strip() for cell in r)]
    if not rows:
        return []

    headers = rows[0]
    # 无表头或两列简单版式：直接当 [名称, 结果] 处理
    has_header = any(
        str(h).strip().lower() in {c.lower() for c in _COL_NAME}
        for h in headers
    )

    result: list[dict] = []
    if has_header:
        c_name = _find_col(headers, _COL_NAME)
        c_value = _find_col(headers, _COL_VALUE)
        c_unit = _find_col(headers, _COL_UNIT)
        c_ref = _find_col(headers, _COL_REF)
        if c_name is None or c_value is None:
            # 找不到关键列，放弃（不瞎猜）
            return []
        for row in rows[1:]:
            if len(row) <= max(c_name, c_value):
                continue
            name = row[c_name].strip() if c_name < len(row) else ""
            value = row[c_value].strip() if c_value < len(row) else ""
            if not name or not value:
                continue
            result.append({
                "name": name,
                "value": value,
                "unit": row[c_unit].strip() if c_unit is not None and c_unit < len(row) else None,
                "ref_range": row[c_ref].strip() if c_ref is not None and c_ref < len(row) else None,
            })
    elif len(rows[0]) >= 4:
        # 无表头四列：名称, 结果, 单位, 参考范围
        for row in rows:
            name = row[0].strip() if len(row) > 0 else ""
            value = row[1].strip() if len(row) > 1 else ""
            if not name or not value:
                continue
            result.append({
                "name": name,
                "value": value,
                "unit": row[2].strip() if len(row) > 2 else None,
                "ref_range": row[3].strip() if len(row) > 3 else None,
            })
    else:
        # 简单两列：名称, 结果
        for row in rows:
            if len(row) < 2:
                continue
            name, value = row[0].strip(), row[1].strip()
            if not name or not value:
                continue
            result.append({"name": name, "value": value, "unit": None, "ref_range": None})
    return result


def ingest_csv_as_report(
    report_id: int,
    text: str,
    patient_label: str,
    exam_type: str,
    collected_at: str,
    hospital: str = "",
) -> Optional[object]:
    """把 CSV 文本导入为一份报告，返回报告的 dict，失败返回 None。"""
    rows = parse_csv(text)
    if not rows:
        return None
    report = make_report(
        report_id=report_id,
        patient_label=patient_label,
        exam_type=exam_type,
        collected_at=collected_at,
        hospital=hospital,
        source_note="由电子版表格导入，字段待人工核对",
        rows=rows,
    )
    return report
