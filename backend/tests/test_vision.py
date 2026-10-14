"""图片识别入口（DeepSeek deepseek-flash）测试（不依赖真实 API key）。"""
import os
import pytest

from app import vision_import


def test_is_configured_reflects_env():
    assert vision_import.is_configured() == bool(os.environ.get("DEEPSEEK_API_KEY"))


def test_guess_mime():
    assert vision_import._guess_mime("a.png") == "image/png"
    assert vision_import._guess_mime("a.jpg") == "image/jpeg"
    assert vision_import._guess_mime("a.jpeg") == "image/jpeg"
    assert vision_import._guess_mime("a.webp") == "image/webp"
    assert vision_import._guess_mime("a.unknown") == "image/png"


def test_parse_model_output():
    out = vision_import._parse_model_output(
        '[{"name":"白细胞计数","value":"9.2","unit":"10^9/L","ref_range":"3.5-9.5"}]'
    )
    assert len(out) == 1
    assert out[0]["name"] == "白细胞计数"
    assert out[0]["value"] == "9.2"


def test_parse_model_output_code_fence():
    out = vision_import._parse_model_output(
        '```json\n[{"name":"血红蛋白","value":"98","unit":"g/L","ref_range":"115-150"}]\n```'
    )
    assert len(out) == 1
    assert out[0]["name"] == "血红蛋白"


def test_parse_model_output_skips_empty():
    out = vision_import._parse_model_output(
        '[{"name":"","value":"x"},{"name":"血红蛋白","value":"98"}]'
    )
    assert len(out) == 1


def test_ingest_without_key_raises():
    if os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("已配置 key，跳过未配置测试")
    with pytest.raises(vision_import.VisionNotConfigured):
        vision_import.ingest_image_as_report(1, b"fake", "a.png", "测试", "血常规", "2026-10-14")
