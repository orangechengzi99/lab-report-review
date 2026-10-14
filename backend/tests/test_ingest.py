"""导入层测试：字段名匹配 + 表格解析 + OCR 降级。"""
import pytest

from app.ingest import match_analyte, build_analyte_from_raw, normalize_name
from app.models import AnalyteStatus
from app.table_import import parse_csv


def test_normalize_name_strips_space():
    assert normalize_name(" 白细胞 计数 ") == "白细胞计数"


def test_match_exact_std_name():
    m = match_analyte("血红蛋白")
    assert m is not None and m["std_name"] == "血红蛋白"


def test_match_alias_case_insensitive():
    m = match_analyte("HGB")
    assert m is not None and m["std_name"] == "血红蛋白"


def test_match_unknown_returns_none():
    assert match_analyte("某个不存在的指标") is None


def test_build_analyte_defaults_unchecked():
    a = build_analyte_from_raw(1, "血红蛋白", "98", "g/L", "115-150")
    assert a.status == AnalyteStatus.UNCHECKED
    # 识别出的数值绝不当"已确认值"
    assert a.value is None
    assert a.raw_unit == "g/L"
    assert a.raw_ref_range == "115-150"
    # 仅预解析报告原文中真实存在的参考范围
    assert a.ref_low == 115.0 and a.ref_high == 150.0


def test_build_analyte_does_not_invent_missing_unit_or_range():
    a = build_analyte_from_raw(1, "血红蛋白", "98")
    assert a.raw_unit is None and a.unit is None
    assert a.raw_ref_range is None
    assert a.ref_low is None and a.ref_high is None


def test_build_analyte_unknown_name_keeps_raw():
    a = build_analyte_from_raw(1, "奇怪指标", "123")
    assert a.name == "奇怪指标"
    assert a.status == AnalyteStatus.UNCHECKED


def test_parse_csv_two_column():
    rows = parse_csv("白细胞计数,9.2\n血红蛋白,98\n血小板,456\n")
    assert len(rows) == 3
    assert rows[0]["name"] == "白细胞计数"
    assert rows[0]["value"] == "9.2"


def test_parse_csv_with_header():
    text = "项目,结果,单位,参考范围\n白细胞计数,9.2,10^9/L,3.5-9.5\n血红蛋白,98,g/L,115-150\n"
    rows = parse_csv(text)
    assert len(rows) == 2
    assert rows[0]["ref_range"] == "3.5-9.5"
    assert rows[1]["unit"] == "g/L"


def test_parse_csv_four_col_no_header():
    text = "白细胞计数,9.2,10^9/L,3.5-9.5\n血红蛋白,98,g/L,115-150\n"
    rows = parse_csv(text)
    assert len(rows) == 2
    assert rows[0]["unit"] == "10^9/L"
    assert rows[0]["ref_range"] == "3.5-9.5"


def test_parse_csv_empty_returns_empty():
    assert parse_csv("") == []


def test_deepseek_not_configured():
    import os
    from app import deepseek_import
    assert deepseek_import.is_configured() == bool(os.environ.get("DEEPSEEK_API_KEY"))


def test_dictionary_loaded():
    from app.ingest import dictionary_size
    # 字典应有 73 项
    assert dictionary_size() == 73


def test_match_alt_alias_with_loinc():
    m = match_analyte("ALT")
    assert m is not None
    assert m["std_name"] == "丙氨酸氨基转移酶"
    assert m["loinc"] == "1742-6"
    assert m["category"] == "肝功能"


def test_build_analyte_uses_dictionary_category():
    analyte = build_analyte_from_raw(1, "ALT", "45", "U/L", "9-50")
    assert analyte.name == "丙氨酸氨基转移酶"
    assert analyte.category == "肝功能"


def test_match_tsh_alias():
    m = match_analyte("TSH")
    assert m is not None and m["std_name"] == "促甲状腺激素"


def test_match_hba1c_alias():
    m = match_analyte("HbA1c")
    assert m is not None and m["std_name"] == "糖化血红蛋白"
