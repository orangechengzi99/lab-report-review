"""规则判断的单元测试。

重点覆盖本项目最强调的边界情况：
- 不同部位/字段不因数值相同而误判（对应 ASTAR 的去重教训）
- 缺范围不判"正常"
- 非数值不套规则
- 未核对不判异常
- 参考范围解析保守，解析不了不猜
"""
from app.models import Analyte, AnalyteStatus, Interpretation
from app.rules import (
    is_numeric_value,
    is_qualitative_value,
    parse_qualitative_value,
    parse_ref_range,
    parse_value,
)


def _a(**kw):
    base = dict(id=1, name="x", raw_name="x", raw_value="0", raw_unit=None,
                raw_ref_range=None, unit="U")
    base.update(kw)
    return Analyte(**base)


# ---- 参考范围解析 ----

def test_parse_simple_range():
    assert parse_ref_range("3.5-9.5") == (3.5, 9.5)
    assert parse_ref_range("3.5～9.5") == (3.5, 9.5)
    assert parse_ref_range(" 3.5 - 9.5 ") == (3.5, 9.5)


def test_parse_single_sided_range():
    # 单边范围（真实检验单常见）：≤ 给上限，> 给下限
    assert parse_ref_range("<5.2") == (None, 5.2)
    assert parse_ref_range("≤26") == (None, 26.0)
    assert parse_ref_range(">10") == (10.0, None)
    assert parse_ref_range("≥1.0") == (1.0, None)


def test_strict_single_sided_range_excludes_boundary_value():
    strict_upper = _a(
        value=5.2, ref_low=None, ref_high=5.2, raw_ref_range="<5.2",
        status=AnalyteStatus.CONFIRMED,
    )
    inclusive_upper = _a(
        value=5.2, ref_low=None, ref_high=5.2, raw_ref_range="≤5.2",
        status=AnalyteStatus.CONFIRMED,
    )
    strict_lower = _a(
        value=10.0, ref_low=10.0, ref_high=None, raw_ref_range=">10",
        status=AnalyteStatus.CONFIRMED,
    )
    inclusive_lower = _a(
        value=10.0, ref_low=10.0, ref_high=None, raw_ref_range="≥10",
        status=AnalyteStatus.CONFIRMED,
    )

    assert strict_upper.interpretation() == Interpretation.HIGH
    assert inclusive_upper.interpretation() == Interpretation.WITHIN
    assert strict_lower.interpretation() == Interpretation.LOW
    assert inclusive_lower.interpretation() == Interpretation.WITHIN


def test_parse_double_dash_range():
    # 真实报告常见双横线（长破折号被转成 --），应归一解析
    assert parse_ref_range("0.5--10") == (0.5, 10.0)
    assert parse_ref_range("59--104") == (59.0, 104.0)


def test_parse_rejects_complex_range():
    assert parse_ref_range("3.5~9.5 ×10^9/L") == (None, None)
    assert parse_ref_range("3-5 / 6-8") == (None, None)
    assert parse_ref_range("") == (None, None)
    assert parse_ref_range(None) == (None, None)


def test_parse_rejects_inverted_range():
    assert parse_ref_range("9.5-3.5") == (None, None)


# ---- 数值解析 ----

def test_parse_value_numeric():
    assert parse_value("9.2") == 9.2
    assert parse_value(" 98 ") == 98.0
    assert parse_value("20.2 ↑") == 20.2
    assert parse_value("0.07↓") == 0.07


def test_parse_value_non_numeric():
    assert parse_value("阴性") is None
    assert parse_value("阳性") is None
    assert parse_value("") is None
    assert parse_value(None) is None


def test_is_numeric_value():
    assert is_numeric_value("72.5") is True
    assert is_numeric_value("72.5 ↑") is True
    assert is_numeric_value("阴性") is False
    assert is_numeric_value("弱阳性") is False
    assert is_numeric_value("约 72.5") is False


def test_parse_qualitative_value_is_explicit_and_conservative():
    assert parse_qualitative_value(" 阴性 ") == "阴性"
    assert parse_qualitative_value("弱阳性") == "弱阳性"
    assert parse_qualitative_value("2+") == "2+"
    assert parse_qualitative_value("±") == "±"
    assert parse_qualitative_value("阴性（-）") == "阴性（-）"
    assert parse_qualitative_value("疑似阴性结果") is None
    assert parse_qualitative_value("约 2+") is None
    assert is_qualitative_value("阳性") is True
    assert is_qualitative_value("9.2") is False


# ---- 判断逻辑（核心边界） ----

def test_confirmed_high():
    a = _a(value=456.0, ref_low=125.0, ref_high=350.0, status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.HIGH


def test_confirmed_low():
    a = _a(value=98.0, ref_low=115.0, ref_high=150.0, status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.LOW


def test_confirmed_within():
    a = _a(value=9.2, ref_low=3.5, ref_high=9.5, status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.WITHIN


def test_no_range_not_judged_as_normal():
    # 缺参考范围：绝不能判"正常"，只能判"无法比较"
    a = _a(value=88.0, ref_low=None, ref_high=None, status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.NO_RANGE
    assert a.interpretation() != Interpretation.WITHIN


def test_missing_unit_with_range_is_unclear():
    a = _a(value=88.0, unit=None, ref_low=80.0, ref_high=100.0,
           status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.UNCLEAR_UNIT


def test_non_numeric_not_judged():
    a = _a(value=None, status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.NOT_NUMERIC


def test_unchecked_not_judged_as_abnormal():
    # 未核对：即使 value 为空，也不得判为异常/正常
    a = _a(value=None, ref_low=3.9, ref_high=6.1, status=AnalyteStatus.UNCHECKED)
    assert a.interpretation() not in (Interpretation.HIGH, Interpretation.LOW, Interpretation.WITHIN)


def test_unchecked_returns_unchecked_not_no_range():
    """未核对必须报 UNCHECKED —— 不能复用 NO_RANGE / NOT_NUMERIC。

    回归用例：旧实现按"有没有参考范围"二选一，
    - 有范围 → NOT_NUMERIC、"没范围" → NO_RANGE，
    于是"还没核对"被说成了"这份报告比不了"。
    绕过前端的调用方（导出、别的客户端、对接方）会把待核对项读成
    "报告未提供参考范围"——对一个主打证据可追溯的产品是硬伤。
    """
    # 有范围且已填值，只是没核对 —— 旧实现会返回 NOT_NUMERIC
    a = _a(value=5.9, ref_low=3.9, ref_high=6.1, status=AnalyteStatus.UNCHECKED)
    assert a.interpretation() is Interpretation.UNCHECKED

    # 没有范围、也没核对 —— 旧实现会返回 NO_RANGE
    b = _a(value=None, ref_low=None, ref_high=None, status=AnalyteStatus.UNCHECKED)
    assert b.interpretation() is Interpretation.UNCHECKED

    # 未核对的 interpretation 与 status 语义一致，都表示"还没看"
    assert a.interpretation().value == a.status.value == "unchecked"


def test_unclear_also_not_judged():
    # 存疑同属"未确认"：记录本身不可靠，谈不上判读
    a = _a(value=5.9, ref_low=3.9, ref_high=6.1, status=AnalyteStatus.UNCLEAR)
    assert a.interpretation() is Interpretation.UNCHECKED


def test_confirmed_still_gets_real_verdict():
    # 修 UNCHECKED 不能误伤"已核对"分支：三种真实结论必须照旧
    assert _a(value=5.9, ref_low=3.9, ref_high=6.1,
              status=AnalyteStatus.CONFIRMED).interpretation() is Interpretation.WITHIN
    assert _a(value=9.9, ref_low=3.9, ref_high=6.1,
              status=AnalyteStatus.CONFIRMED).interpretation() is Interpretation.HIGH
    assert _a(value=2.1, ref_low=3.9, ref_high=6.1,
              status=AnalyteStatus.CONFIRMED).interpretation() is Interpretation.LOW
    # 已核对但报告确实没给范围 → 这才是 NO_RANGE 该出现的地方
    assert _a(value=5.9, ref_low=None, ref_high=None,
              status=AnalyteStatus.CONFIRMED).interpretation() is Interpretation.NO_RANGE


def test_different_fields_same_value_not_merged():
    # 呼应 ASTAR 去重教训：两个不同指标数值相同，也必须各自独立判断
    a = _a(id=1, name="白细胞", value=9.2, ref_low=3.5, ref_high=9.5,
           status=AnalyteStatus.CONFIRMED)
    b = _a(id=2, name="血红蛋白", value=9.2, ref_low=115.0, ref_high=150.0,
           status=AnalyteStatus.CONFIRMED)
    assert a.interpretation() == Interpretation.WITHIN
    assert b.interpretation() == Interpretation.LOW
    assert a.id != b.id
