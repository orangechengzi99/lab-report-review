"""参考范围解析与规则判断。

只做"把参考范围字符串解析成上下限"，以及"数值是否落在此范围内"的规则判断。
不包含任何医学诊断逻辑，不跨报告套用统一阈值。

解析规则刻意保守：解析不了就返回 None，绝不猜。
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


# 匹配 "3.5-9.5" 或 "3.5～9.5" 或 "3.5~9.5" 或 "3.5 - 9.5"
_RANGE_RE = re.compile(
    r"^\s*(?P<low>-?\d+(?:\.\d+)?)\s*(?:[-~～—－]|至)\s*(?P<high>-?\d+(?:\.\d+)?)\s*$"
)

# 单边范围："≤26"、"<5.2"、">10"、"≥1.0"（只给出一侧界限）
_SINGLE_SIDED_RE = re.compile(
    r"^\s*(?P<op><=|>=|≤|＜|<|≧|≥|>|＞)\s*(?P<num>-?\d+(?:\.\d+)?)\s*$"
)

# 明确的定性结果。只接受完整匹配，避免把任意 OCR 文本误当成可确认结果。
_QUALITATIVE_TERMS = {
    "阴性", "阳性", "弱阳性", "可疑阳性", "未检出", "检出", "未见", "正常",
    "微量", "痕量",
}
_QUALITATIVE_GRADE_RE = re.compile(r"^(?:[-＋+]{1,4}|[1-4][＋+]|±)$")
_QUALITATIVE_WRAPPED_RE = re.compile(
    r"^(?:阴性\s*[（(]\s*[-－]\s*[）)]|(?:弱阳性|阳性)\s*[（(]\s*[＋+]\s*[）)])$"
)

# 检验单常把高低标记紧跟在数值后，如 "20.2 ↑"。箭头是报告原文的一部分，
# 但不改变数值本身；只接受这一种明确格式，不从任意混合文本里猜数字。
_VALUE_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*[↑↓]?\s*$")


def _normalize_range_text(text: str) -> str:
    """归一化范围文本里的分隔符。

    真实报告常见 "--"（长破折号被 OCR/模型转成两个短横），先折叠成单横线，
    避免被误判为负号导致解析失败。
    """
    return re.sub(r"[-－]{2,}", "-", text.strip())


def parse_ref_range(text: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """把参考范围字符串解析成 (下限, 上限)。

    支持：
    - 区间形式："3.5-9.5"、"3.5--9.5"（双横线归一）、"3.5～9.5"
    - 单边形式："≤26"、"<5.2"、">10"、"≥1.0"（另一侧为 None）
    不支持的形式（复杂区间、带文字说明）一律返回 None，不强行解释。
    """
    low, high, _, _ = parse_ref_range_details(text)
    return low, high


def parse_ref_range_details(
    text: Optional[str],
) -> tuple[Optional[float], Optional[float], bool, bool]:
    """解析参考范围，并保留上下限是否包含临界值。

    返回 ``(low, high, low_inclusive, high_inclusive)``。普通区间两端均
    视为包含；``<`` / ``>`` 不包含临界值，``≤`` / ``≥`` 与 ``<=`` /
    ``>=`` 包含临界值。
    """
    if not text:
        return None, None, True, True
    t = _normalize_range_text(text)
    m = _RANGE_RE.match(t)
    if m:
        low = float(m.group("low"))
        high = float(m.group("high"))
        if low > high:
            # 下限大于上限，视为解析异常，不猜
            return None, None, True, True
        return low, high, True, True
    m = _SINGLE_SIDED_RE.match(t)
    if m:
        num = float(m.group("num"))
        op = m.group("op")
        if op in ("≤", "<=", "<", "＜"):
            return None, num, True, op in ("≤", "<=")
        return num, None, op in ("≥", "≧", ">="), True
    return None, None, True, True


def compare_value_to_reference(
    value: float,
    low: Optional[float],
    high: Optional[float],
    reference_text: Optional[str] = None,
) -> Optional[str]:
    """返回 ``low`` / ``high``，范围内返回 ``None``。

    只有当参考原文解析出的边界与已保存边界一致时，才采用原文中的严格
    比较符；这样既能兼容旧数据，也不会让过期原文覆盖人工修改后的范围。
    """
    low_inclusive = True
    high_inclusive = True
    parsed_low, parsed_high, parsed_low_inclusive, parsed_high_inclusive = (
        parse_ref_range_details(reference_text)
    )
    if (parsed_low, parsed_high) == (low, high):
        low_inclusive = parsed_low_inclusive
        high_inclusive = parsed_high_inclusive

    if low is not None and (value < low or (value == low and not low_inclusive)):
        return "low"
    if high is not None and (value > high or (value == high and not high_inclusive)):
        return "high"
    return None


def is_numeric_value(text: Optional[str]) -> bool:
    """判断结果文本是否为可解析的数值。"""
    if text is None:
        return False
    t = text.strip()
    if not t:
        return False
    return _VALUE_RE.fullmatch(t) is not None


def parse_value(text: Optional[str]) -> Optional[float]:
    """把结果文本解析成数值，失败返回 None。"""
    if text is None:
        return None
    match = _VALUE_RE.fullmatch(text.strip())
    return float(match.group("num")) if match else None


def parse_qualitative_value(text: Optional[str]) -> Optional[str]:
    """返回可人工确认的定性结果原文；不是明确格式时返回 None。

    这里不把不同词语互相转换，也不判断医学意义，只确认它是常见、完整的
    定性结果格式。原始文本会按核对后的写法保存。
    """
    if text is None:
        return None
    value = text.strip()
    if not value:
        return None
    if value in _QUALITATIVE_TERMS:
        return value
    if _QUALITATIVE_GRADE_RE.fullmatch(value) or _QUALITATIVE_WRAPPED_RE.fullmatch(value):
        return value
    return None


def is_qualitative_value(text: Optional[str]) -> bool:
    """判断结果文本是否为明确的定性结果。"""
    return parse_qualitative_value(text) is not None
