"""DeepSeek 文本解析入口：把检验报告"文本"解析为结构化字段。

用 deepseek-v4-pro（纯文本模型）把报告文字整理成结构化字段。
（图片识别走独立的 vision_import.py，用多模态的 deepseek-flash。）

设计原则（与整个项目一致）：
1. 解析结果是"草稿"，产出字段一律默认 UNCHECKED，待人工核对。
2. 密钥可配置（环境变量 DEEPSEEK_API_KEY），未配置时优雅降级不报错。
3. 解析失败/JSON 解析失败都返回结构化错误，不抛栈。
4. 模型被明确要求：只提取文本中可见内容，不补写、不猜、不标准化指标名。
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

from .ingest import make_report


def _api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _base_url() -> str:
    return os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")


def _model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")

# 提示词：要求模型严格按 JSON 输出，且只提取文本可见内容
_SYSTEM_PROMPT = """你是一个医疗检验报告结构化提取助手。

用户会给你一段检验报告的文字内容（可能是复制自纸质报告、App 或 PDF）。
你的任务是把它提取成一个结构化的检验指标列表。

必须严格遵守以下规则：
1. 只根据用户提供的文本中可见内容提取，不要用外部医学知识补写文本中不存在的信息。
2. 指标名称保留原文写法，不要标准化、不要翻译、不要替换成缩写或全称。
3. 每条指标提取 4 个字段：
   - name: 指标名称（原文）
   - value: 结果值（原文，如 "9.2"、"阴性"、"<1.7"）
   - unit: 单位（原文，没有则填空字符串 ""）
   - ref_range: 参考范围原文（没有则填空字符串 ""）
4. 如果文本中某字段无法确认，填空字符串 ""，不要猜测。
5. 最终只输出一个 JSON 数组，不要输出任何解释、注释或 markdown 代码块标记。
   格式示例：[{"name":"白细胞计数","value":"9.2","unit":"10^9/L","ref_range":"3.5-9.5"}]
"""


class DeepseekNotConfigured(Exception):
    """未配置 DeepSeek API key。"""


def is_configured() -> bool:
    return bool(_api_key())


def _call_deepseek(text: str) -> list[dict]:
    """调用 DeepSeek，把报告文本解析为指标列表。"""
    if not is_configured():
        raise DeepseekNotConfigured("未配置 DEEPSEEK_API_KEY")

    payload = json.dumps({
        "model": _model(),
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"请解析以下检验报告文本：\n\n{text}"},
        ],
        "temperature": 0,  # 结构化提取用低温，减少随机性
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
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = data["choices"][0]["message"]["content"]
    return _parse_model_output(content)


def _parse_model_output(content: str) -> list[dict]:
    """把模型返回的文本解析成指标列表，容错处理可能的代码块包裹。"""
    text = content.strip()
    # 去掉可能的 ```json ... ``` 包裹
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


def ingest_text_as_report(
    report_id: int,
    text: str,
    patient_label: str,
    exam_type: str,
    collected_at: str,
    hospital: str = "",
) -> object:
    """把检验报告文本解析为待核对报告，返回报告 dict。"""
    if not is_configured():
        raise DeepseekNotConfigured("未配置 DEEPSEEK_API_KEY，无法进行文本解析")

    rows = _call_deepseek(text)
    if not rows:
        raise RuntimeError("未能从文本中解析出检验指标，请确认文本内容或改用表格导入")

    report = make_report(
        report_id=report_id,
        patient_label=patient_label,
        exam_type=exam_type,
        collected_at=collected_at,
        hospital=hospital,
        source_note=f"由 DeepSeek 文本解析（{_model()}），解析结果待人工核对",
        rows=rows,
    )
    return report
