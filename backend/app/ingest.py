"""识别结果导入层：把"原始报告"变成"待核对的识别草稿"。

本项目的核心立场：识别结果（无论来自 OCR 还是表格解析）都只是"草稿"，
必须经过人工核对才参与规则判断。因此这里产出的 Analyte 一律默认 UNCHECKED。

两条入口（图像 OCR、表格导入）最终都汇聚到 build_analyte_from_raw()，
产出统一的 Analyte 结构，共用后续的核对、规则、角色联动逻辑。

字段名匹配刻意保守：
- 有别名命中的，自动补全标准名 + 分类 + LOINC 编码，但数值仍待核对。
- 匹配不了的，保留原始名并标 UNCLEAR，绝不瞎猜。

指标字典来源：data/metric_dictionary.json（含 LOINC 编码），整理为独立 JSON
便于扩充与维护；字典数据的第三方许可见仓库根目录 THIRD_PARTY_NOTICES.md。
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from .models import Analyte, AnalyteStatus, Report
from .rules import parse_ref_range


# ---------------------------------------------------------------------------
# 字典加载：从 data/metric_dictionary.json 读取指标标准名 + 别名 + 分类 + LOINC。
# ---------------------------------------------------------------------------
_DICT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "metric_dictionary.json"
)

_metrics: list[dict] = []
_std_to_meta: dict[str, dict] = {}   # 标准名(normalized) -> meta
_alias_to_std: dict[str, str] = {}   # 别名(normalized) -> 标准名


def _load_dictionary() -> None:
    """惰性加载指标字典，构建标准名与别名索引。"""
    global _metrics, _std_to_meta, _alias_to_std
    if _metrics:
        return
    try:
        with open(_DICT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _metrics = data.get("metrics", [])
    except (FileNotFoundError, json.JSONDecodeError):
        _metrics = []

    _std_to_meta = {}
    _alias_to_std = {}
    for m in _metrics:
        std = m.get("standardName", "")
        meta = {
            "std_name": std,
            "category": m.get("category", ""),
            "loinc": m.get("loinc", ""),
        }
        _std_to_meta[normalize_name(std)] = meta
        for alias in m.get("aliases", []):
            key = normalize_name(alias)
            if key:
                _alias_to_std[key] = std


def normalize_name(raw: str) -> str:
    """去掉名称里的空白/全角空格，便于匹配。"""
    if not raw:
        return ""
    return re.sub(r"\s+", "", raw).strip()


def match_analyte(raw_name: str) -> Optional[dict]:
    """根据原始字段名，尝试匹配到标准检验项。匹配不到返回 None。

    返回 {"std_name", "category", "loinc"}。
    """
    _load_dictionary()
    key = normalize_name(raw_name)
    if not key:
        return None
    lower_key = key.lower()

    # 1. 精确匹配标准名（不区分大小写）
    if key in _std_to_meta:
        return dict(_std_to_meta[key])
    # 标准名不区分大小写兜底
    for std_key, meta in _std_to_meta.items():
        if std_key.lower() == lower_key:
            return dict(meta)

    # 2. 匹配别名
    if key in _alias_to_std:
        std = _alias_to_std[key]
        return dict(_std_to_meta.get(normalize_name(std), {"std_name": std, "category": "", "loinc": ""}))
    for alias_key, std in _alias_to_std.items():
        if alias_key.lower() == lower_key:
            return dict(_std_to_meta.get(normalize_name(std), {"std_name": std, "category": "", "loinc": ""}))

    return None


def build_analyte_from_raw(
    analyte_id: int,
    raw_name: str,
    raw_value: str,
    raw_unit: Optional[str] = None,
    raw_ref_range: Optional[str] = None,
) -> Analyte:
    """从"识别出的原始字段"构建一条待核对的指标。

    产出状态恒为 UNCHECKED（草稿），数值留空待人工确认；
    仅解析报告原文里实际出现的参考范围；数值、单位或范围缺失时保持为空，
    绝不从内置字典补写医学数据。
    """
    name = raw_name or "（未识别字段名）"
    matched = match_analyte(raw_name)

    if matched:
        std_name = matched["std_name"]
        category = matched.get("category") or "其他"
    else:
        std_name = name
        category = "其他"

    # 只解析报告原文；空字符串统一为 None，避免下游误把“缺失”当作已知。
    clean_unit = raw_unit.strip() if raw_unit and raw_unit.strip() else None
    clean_ref = raw_ref_range.strip() if raw_ref_range and raw_ref_range.strip() else None
    ref_low, ref_high = parse_ref_range(clean_ref)

    return Analyte(
        id=analyte_id,
        name=std_name,
        raw_name=raw_name or "",
        raw_value=raw_value or "",
        raw_unit=clean_unit,
        raw_ref_range=clean_ref,
        value=None,           # 数值留空：识别结果不直接当"已确认值"
        unit=None,            # 核对后的单位留空；报告原文只保存在 raw_unit
        ref_low=ref_low,
        ref_high=ref_high,
        status=AnalyteStatus.UNCHECKED,
        category=category,
    )


def make_report(
    report_id: int,
    patient_label: str,
    exam_type: str,
    source_note: str,
    rows: list[dict],
    collected_at: Optional[str] = None,
    hospital: str = "",
    image_url: Optional[str] = None,
) -> Report:
    """把一批"原始行"（每行含 name/value/unit/ref_range）组装成一份报告。"""
    analytes: list[Analyte] = []
    for i, row in enumerate(rows):
        a = build_analyte_from_raw(
            analyte_id=report_id * 100 + i + 1,
            raw_name=row.get("name", ""),
            raw_value=str(row.get("value", "")) if row.get("value") is not None else "",
            raw_unit=row.get("unit"),
            raw_ref_range=row.get("ref_range"),
        )
        analytes.append(a)
    return Report(
        id=report_id,
        patient_label=patient_label,
        exam_type=exam_type,
        collected_at=collected_at,
        source_note=source_note,
        hospital=hospital,
        image_url=image_url,
        analytes=analytes,
    )


def dictionary_size() -> int:
    """返回字典指标总数（供测试/展示用）。"""
    _load_dictionary()
    return len(_metrics)
