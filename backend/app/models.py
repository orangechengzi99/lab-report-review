"""数据模型定义。

本项目的核心不是"识别得准"，而是"识别结果如何被核对、如何不越界、如何可追溯"。
因此数据模型刻意区分三层状态，并保留原始值与参考范围原文，避免静默覆盖。

字段说明：
- raw_value / raw_unit / raw_ref_range: 从报告"识别"出来的原始字符串（未清洗）。
- value / result_text / unit: 人工核对确认后的定量或定性结果与单位。
- status: 每条指标的核对状态，见 AnalyteStatus。
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field, asdict
from typing import Optional


class AnalyteStatus(str, enum.Enum):
    """指标核对状态。

    关键设计：任何新进来的指标默认都是 UNCHECKED（待核对），
    绝不自动判定为"正常"或"已确认"。
    """
    UNCHECKED = "unchecked"        # 待核对：识别结果尚未经人工确认
    CONFIRMED = "confirmed"        # 已核对：定量或定性结果已经人工确认
    UNCLEAR = "unclear"            # 存疑：无法可靠对应、结果或单位不明，需人工处理


class Interpretation(str, enum.Enum):
    """基于"报告自带参考范围"的判断结果。

    注意：这是对"是否落在本报告参考范围内"的规则判断，
    不是医学诊断，也不跨报告套用统一阈值。

    这里刻意区分两类"没有结论"：
    - UNCHECKED：还没人工核对，所以**不给判读**（原因在流程，不在数据）；
    - NO_RANGE / NOT_NUMERIC / UNCLEAR_UNIT：已核对，但**原料本身比不了**
      （报告没给范围 / 结果是定性描述 / 单位对不齐）。

    两者绝不能混用：把 UNCHECKED 报成 NO_RANGE，等于替调用方认定
    "这份报告没写参考范围"，而事实可能只是"我们还没看"。
    """
    WITHIN = "within"              # 范围内
    HIGH = "high"                  # 高于参考上限
    LOW = "low"                    # 低于参考下限
    NO_RANGE = "no_range"          # 报告未提供参考范围，无法比较
    NOT_NUMERIC = "not_numeric"    # 已核对的定性结果（如"阴性/阳性"），数值规则不适用
    UNCLEAR_UNIT = "unclear_unit"  # 单位不明，无法与参考范围对齐
    UNCHECKED = "unchecked"        # 未核对：尚未人工确认，不给出任何判读


@dataclass
class Analyte:
    """一条检验指标。

    保留 raw_* 字段是为了追溯：核对前后都能回看"识别器到底读到了什么"。
    """
    id: int
    name: str                       # 指标名，如"白细胞计数"
    raw_name: str                   # 识别出的原始名称（可能含空格/别名）
    raw_value: str                  # 识别出的原始结果文本
    raw_unit: Optional[str]         # 识别出的原始单位
    raw_ref_range: Optional[str]    # 识别出的原始参考范围原文

    value: Optional[float] = None   # 核对后的数值
    result_text: Optional[str] = None # 核对后的定性结果，如“阴性”或“2+”
    unit: Optional[str] = None      # 核对后的单位
    ref_low: Optional[float] = None # 参考下限（解析后）
    ref_high: Optional[float] = None# 参考上限（解析后）
    ref_text: Optional[str] = None  # 核对后的定性参考值原文

    status: AnalyteStatus = AnalyteStatus.UNCHECKED
    note: Optional[str] = None      # 人工备注，如"单位待确认"
    category: str = "其他"          # 指标分类（血常规/生化全项等）

    def interpretation(self) -> Interpretation:
        """根据当前字段做规则判断，边界情况一律不强行下结论。"""
        if self.status != AnalyteStatus.CONFIRMED:
            # 未核对的不做判断——这是本项目区别于"自动报异常"的关键。
            # 返回 UNCHECKED 而不是 NO_RANGE / NOT_NUMERIC：后两者是
            # "已核对、但这份报告的原料比不了"，与"压根还没核对"是两回事。
            # （旧版本在这里返回 NO_RANGE / NOT_NUMERIC，会让绕过前端的调用方
            #   把"待核对"读成"报告没写参考范围"，属于语义错位。）
            # UNCLEAR（存疑）同属"未确认"，一并归入 UNCHECKED；
            # 二者更细的区别记在 status 字段上，interpretation 只回答"给不给判读"。
            return Interpretation.UNCHECKED
        if self.value is None:
            return Interpretation.NOT_NUMERIC
        if self.ref_low is None and self.ref_high is None:
            return Interpretation.NO_RANGE
        if self.unit is None or not self.unit.strip():
            # 有数值和范围但单位缺失时，无法确认二者是否处于同一量纲。
            # 真正无量纲的项目应由核对者明确填写“无量纲”，不能把空值当作已知。
            return Interpretation.UNCLEAR_UNIT
        from .rules import compare_value_to_reference

        direction = compare_value_to_reference(
            self.value,
            self.ref_low,
            self.ref_high,
            self.ref_text or self.raw_ref_range,
        )
        if direction == "low":
            return Interpretation.LOW
        if direction == "high":
            return Interpretation.HIGH
        return Interpretation.WITHIN

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["interpretation"] = self.interpretation().value
        return d


@dataclass
class Report:
    """一份报告，包含若干指标与报告元信息。"""
    id: int
    patient_label: str              # 去标识化的报告编号（不是真实姓名）
    exam_type: str                  # 如"血常规"
    collected_at: Optional[str] = None
    source_note: str = ""           # 数据来源说明，明确标注是否为演示数据
    hospital: str = ""              # 医院名称
    image_url: Optional[str] = None # 原报告图片 URL 或路径
    analytes: list[Analyte] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "patient_label": self.patient_label,
            "exam_type": self.exam_type,
            "collected_at": self.collected_at,
            "source_note": self.source_note,
            "hospital": self.hospital,
            "image_url": self.image_url,
            "analytes": [a.to_dict() for a in self.analytes],
        }
