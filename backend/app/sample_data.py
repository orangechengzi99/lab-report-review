"""存储层：内存 dict 存储（演示项目）。

演示项目用内存存储，避免引入外部数据库复杂度；真实项目应换 SQLite，
见 README「局限说明」。这里在原有示例数据基础上，支持动态新增报告
（来自表格导入 / OCR 识别）。
"""
from __future__ import annotations

from .models import Report, Analyte, AnalyteStatus


def build_demo_reports() -> list[Report]:
    """构造 2 份演示报告（明确标注虚构），覆盖正常/异常/缺范围/非数值等边界。"""
    r1 = Report(
        id=1,
        patient_label="DEMO-001（虚构）",
        exam_type="血常规",
        collected_at="2026-10-01",
        source_note="手工构造的演示数据，非真实患者报告",
        analytes=[
            Analyte(
                id=101, name="白细胞计数", raw_name="白细胞计数 WBC",
                raw_value="9.2", raw_unit="10^9/L", raw_ref_range="3.5-9.5",
                value=9.2, unit="10^9/L", ref_low=3.5, ref_high=9.5,
                status=AnalyteStatus.CONFIRMED,
            ),
            Analyte(
                id=102, name="血红蛋白", raw_name="血红蛋白 HGB",
                raw_value="98", raw_unit="g/L", raw_ref_range="115-150",
                value=98.0, unit="g/L", ref_low=115.0, ref_high=150.0,
                status=AnalyteStatus.CONFIRMED,
            ),
            Analyte(
                id=103, name="血小板计数", raw_name="血小板 PLT",
                raw_value="456", raw_unit="10^9/L", raw_ref_range="125-350",
                value=456.0, unit="10^9/L", ref_low=125.0, ref_high=350.0,
                status=AnalyteStatus.CONFIRMED,
            ),
            Analyte(
                id=104, name="中性粒细胞百分比", raw_name="中性粒 %",
                raw_value="72.5", raw_unit="%", raw_ref_range="40-75",
                value=None, unit=None, ref_low=None, ref_high=None,
                status=AnalyteStatus.UNCHECKED,
            ),
            Analyte(
                id=105, name="平均红细胞体积", raw_name="MCV",
                raw_value="88", raw_unit="fL", raw_ref_range=None,
                value=88.0, unit="fL", ref_low=None, ref_high=None,
                status=AnalyteStatus.CONFIRMED,
            ),
            Analyte(
                id=106, name="抗环瓜氨酸肽抗体", raw_name="抗CCP抗体",
                raw_value="阴性", raw_unit=None, raw_ref_range=None,
                value=None, result_text="阴性", unit=None, ref_low=None, ref_high=None,
                status=AnalyteStatus.CONFIRMED,
            ),
        ],
    )

    r2 = Report(
        id=2,
        patient_label="DEMO-002（虚构）",
        exam_type="生化全项",
        collected_at="2026-10-08",
        source_note="手工构造的演示数据，非真实患者报告",
        analytes=[
            Analyte(
                id=201, name="空腹血糖", raw_name="GLU 空腹",
                raw_value="6.8", raw_unit="mmol/L", raw_ref_range="3.9-6.1",
                value=None, unit=None, ref_low=None, ref_high=None,
                status=AnalyteStatus.UNCHECKED,
            ),
            Analyte(
                id=202, name="总胆固醇", raw_name="TC",
                raw_value="5.4", raw_unit="mmol/L", raw_ref_range="<5.2",
                value=None, unit=None, ref_low=None, ref_high=None,
                status=AnalyteStatus.UNCHECKED,
            ),
            Analyte(
                id=203, name="谷丙转氨酶", raw_name="ALT",
                raw_value="45", raw_unit="U/L", raw_ref_range="9-50",
                value=None, unit=None, ref_low=None, ref_high=None,
                status=AnalyteStatus.UNCHECKED,
            ),
        ],
    )

    return [r1, r2]


_STORE: dict[int, Report] = {}
_next_id: int = 1000  # 动态导入的报告从 1000 起，避免与示例数据冲突


def get_all_reports() -> list[Report]:
    if not _STORE:
        for r in build_demo_reports():
            _STORE[r.id] = r
    return list(_STORE.values())


def get_report(report_id: int) -> Report | None:
    get_all_reports()
    return _STORE.get(report_id)


def add_report(report: Report) -> Report:
    """新增一份报告（来自导入/识别）。"""
    global _next_id
    get_all_reports()
    if report.id in _STORE:
        # 分配一个不冲突的 id
        while report.id in _STORE:
            report.id = _next_id
            _next_id += 1
    _STORE[report.id] = report
    return report
