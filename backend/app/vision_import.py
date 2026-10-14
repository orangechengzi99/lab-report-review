"""图片识别入口：用 DeepSeek deepseek-flash（多模态）识别检验单图片。

为什么用 deepseek-flash 而不是 deepseek-v4-pro：
- deepseek-v4-pro 是纯文本模型（text-only），不支持图片输入。
- deepseek-flash（即 DeepSeek-V4-Flash / V4.1-Flash）支持图片输入，
  且 OCR / 文档文字提取是其强项，价格便宜。

设计原则（与整个项目一致）：
1. 识别结果是"草稿"，产出字段一律默认 UNCHECKED，待人工核对。
2. 密钥复用 DEEPSEEK_API_KEY（与文本解析同一把 key）。
3. 识别失败/解析失败返回结构化错误，不抛栈。
4. 模型被要求：只提取图片可见内容、不补写、不猜、指标名保留原文。

图片格式：JPEG/PNG/GIF/WebP。以 base64 data URL 传入。
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
from typing import Optional

from .ingest import make_report


def _api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _base_url() -> str:
    return os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


def _vision_model() -> str:
    # 图片识别用多模态模型；可被环境变量覆盖
    return os.environ.get("DEEPSEEK_VISION_MODEL", "deepseek-flash")


class VisionNotConfigured(Exception):
    """未配置 DeepSeek API key。"""


def is_configured() -> bool:
    return bool(_api_key())


# 提示词：复用文本解析的思路，但输入是图片
_VISION_SYSTEM_PROMPT = """你是一个医疗检验报告结构化提取助手。

用户会给你一张医疗检验报告的照片/截图。你的任务是把图中可见的检验指标
提取成一个结构化列表。

必须严格遵守以下规则：
1. 只根据图片中可见内容提取，不要用外部医学知识补写图中不存在的信息。
2. 指标名称保留原文写法，不要标准化、不要翻译、不要替换成缩写或全称。
3. 每条指标提取 4 个字段：
   - name: 指标名称（原文）
   - value: 结果值（原文，如 "9.2"、"阴性"、"<1.7"）
   - unit: 单位（原文，没有则填空字符串 ""）
   - ref_range: 参考范围原文（没有则填空字符串 ""）
4. 如果图中某字段无法确认，填空字符串 ""，不要猜测。
5. 只提取检验指标，不要提取患者姓名、医院名称等个人信息。
6. 最终只输出一个 JSON 数组，不要输出任何解释、注释或 markdown 代码块标记。
   格式示例：[{"name":"白细胞计数","value":"9.2","unit":"10^9/L","ref_range":"3.5-9.5"}]
"""


def _call_vision(image_bytes: bytes, mime_type: str) -> list[dict]:
    """调用 deepseek-flash 识别图片，返回指标列表。"""
    if not is_configured():
        raise VisionNotConfigured("未配置 DEEPSEEK_API_KEY")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime_type};base64,{b64}"

    payload = json.dumps({
        "model": _vision_model(),
        "messages": [
            {"role": "system", "content": _VISION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请解析这张检验报告图片中的指标。"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        "temperature": 0,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{_base_url()}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_api_key()}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    return _parse_model_output(content)


def _parse_model_output(content: str) -> list[dict]:
    """把模型返回的文本解析成指标列表，容错处理代码块包裹。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise RuntimeError("模型返回的不是指标数组")
    rows = []
    for item in parsed:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        rows.append({
            "name": str(item.get("name", "")),
            "value": str(item.get("value", "")),
            "unit": item.get("unit") or None,
            "ref_range": item.get("ref_range") or None,
        })
    return rows


def _guess_mime(filename: str) -> str:
    """根据扩展名猜测 MIME 类型（默认 png）。"""
    ext = os.path.splitext(filename or "")[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/png")


def ingest_image_as_report(
    report_id: int,
    image_bytes: bytes,
    filename: str,
    patient_label: str,
    exam_type: str,
    collected_at: str,
    hospital: str = "",
    mime_type: Optional[str] = None,
) -> object:
    """识别一张检验单图片，组装为待核对报告，返回报告 dict。"""
    if not is_configured():
        raise VisionNotConfigured("未配置 DEEPSEEK_API_KEY，无法进行图片识别")

    rows = _call_vision(image_bytes, mime_type or _guess_mime(filename))
    if not rows:
        raise RuntimeError("未能从图片中解析出检验指标，请确认图片清晰或改用文本解析")

    report = make_report(
        report_id=report_id,
        patient_label=patient_label,
        exam_type=exam_type,
        collected_at=collected_at,
        hospital=hospital,
        source_note=f"由 DeepSeek 图片识别（{_vision_model()}），识别结果待人工核对",
        rows=rows,
    )
    return report
