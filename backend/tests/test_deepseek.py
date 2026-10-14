"""DeepSeek 文本解析入口测试（不依赖真实 API key）。"""
import os
import pytest

from app import deepseek_import


def test_is_configured_reflects_env():
    # 环境里通常没配 key，未配置时返回 False
    assert deepseek_import.is_configured() == bool(os.environ.get("DEEPSEEK_API_KEY"))


def test_parse_model_output_plain_array():
    out = deepseek_import._parse_model_output(
        '[{"name":"白细胞计数","value":"9.2","unit":"10^9/L","ref_range":"3.5-9.5"}]'
    )
    assert len(out) == 1
    assert out[0]["name"] == "白细胞计数"
    assert out[0]["value"] == "9.2"
    assert out[0]["unit"] == "10^9/L"
    assert out[0]["ref_range"] == "3.5-9.5"


def test_parse_model_output_code_fence():
    # 模型有时会包一层 ```json ... ```
    out = deepseek_import._parse_model_output(
        '```json\n[{"name":"血红蛋白","value":"98","unit":"g/L","ref_range":"115-150"}]\n```'
    )
    assert len(out) == 1
    assert out[0]["name"] == "血红蛋白"


def test_parse_model_output_empty_strings():
    # 空字符串的 unit/ref 应转为 None
    out = deepseek_import._parse_model_output(
        '[{"name":"平均红细胞体积","value":"88","unit":"","ref_range":""}]'
    )
    assert out[0]["unit"] is None
    assert out[0]["ref_range"] is None


def test_parse_model_output_skips_empty_name():
    out = deepseek_import._parse_model_output(
        '[{"name":"","value":"x"},{"name":"血红蛋白","value":"98"}]'
    )
    assert len(out) == 1
    assert out[0]["name"] == "血红蛋白"


def test_parse_model_output_invalid_json_raises():
    with pytest.raises(Exception):
        deepseek_import._parse_model_output("这不是 JSON")


def test_ingest_without_key_raises():
    if os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("已配置 key，跳过未配置测试")
    with pytest.raises(deepseek_import.DeepseekNotConfigured):
        deepseek_import.ingest_text_as_report(1, "白细胞 9.2", "测试", "血常规", "2026-10-14")
