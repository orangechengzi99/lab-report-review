"""趋势聚合测试：验证只统计已核对点、分组、方向判断与边界。"""
from app.models import Report, Analyte, AnalyteStatus
from app import trends as trends_mod


def _mk_report(rid, date, items):
    """items: [(name, value, low, high, status)]"""
    return Report(
        id=rid, patient_label=f"R{rid}", exam_type="血常规", collected_at=date,
        analytes=[
            Analyte(id=rid * 100 + i, name=n, raw_name=n, raw_value=str(v),
                    raw_unit="U", raw_ref_range=None, value=v, unit="U",
                    ref_low=lo, ref_high=hi, status=st)
            for i, (n, v, lo, hi, st) in enumerate(items)
        ],
    )


def test_trends_requires_two_points():
    # 只有 1 个时间点 → 不返回
    r = _mk_report(1, "2026-01-01", [("血红蛋白", 100, 115, 150, AnalyteStatus.CONFIRMED)])
    assert trends_mod.build_trends([r]) == []


def test_trends_ignores_report_without_collection_date():
    r1 = _mk_report(1, None, [("血红蛋白", 132, 115, 150, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("血红蛋白", 98, 115, 150, AnalyteStatus.CONFIRMED)])
    assert trends_mod.build_trends([r1, r2]) == []


def test_trends_groups_same_metric_across_reports():
    r1 = _mk_report(1, "2026-01-01", [("血红蛋白", 132, 115, 150, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("血红蛋白", 98, 115, 150, AnalyteStatus.CONFIRMED)])
    out = trends_mod.build_trends([r1, r2])
    assert len(out) == 1
    t = out[0]
    assert t["name"] == "血红蛋白"
    assert len(t["points"]) == 2
    assert t["trend"] == "down"
    assert t["latest_interpretation"] == "low"
    assert t["abnormal"] is True


def test_trends_excludes_unchecked_points():
    # 未核对的点不进入趋势（避免用未确认数据下结论）
    r1 = _mk_report(1, "2026-01-01", [("空腹血糖", 5.1, 3.9, 6.1, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("空腹血糖", 9.9, 3.9, 6.1, AnalyteStatus.UNCHECKED)])
    out = trends_mod.build_trends([r1, r2])
    # 只剩 1 个已核对点 → 不构成趋势
    assert out == []


def test_trends_excludes_null_value():
    r1 = _mk_report(1, "2026-01-01", [("白细胞计数", 6.0, 3.5, 9.5, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("白细胞计数", None, 3.5, 9.5, AnalyteStatus.CONFIRMED)])
    assert trends_mod.build_trends([r1, r2]) == []


def test_trends_direction_up():
    r1 = _mk_report(1, "2026-01-01", [("空腹血糖", 5.0, 3.9, 6.1, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("空腹血糖", 6.9, 3.9, 6.1, AnalyteStatus.CONFIRMED)])
    out = trends_mod.build_trends([r1, r2])
    assert out[0]["trend"] == "up"
    assert out[0]["latest_interpretation"] == "high"


def test_trends_direction_flat_within_threshold():
    # 变化 < 5% 视为平稳
    r1 = _mk_report(1, "2026-01-01", [("促甲状腺激素", 2.0, 0.27, 4.2, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("促甲状腺激素", 2.05, 0.27, 4.2, AnalyteStatus.CONFIRMED)])
    assert trends_mod.build_trends([r1, r2])[0]["trend"] == "flat"


def test_trends_points_sorted_by_date():
    # 传入顺序打乱，输出必须按日期升序
    r_late = _mk_report(2, "2026-06-01", [("血红蛋白", 98, 115, 150, AnalyteStatus.CONFIRMED)])
    r_early = _mk_report(1, "2026-01-01", [("血红蛋白", 132, 115, 150, AnalyteStatus.CONFIRMED)])
    out = trends_mod.build_trends([r_late, r_early])
    dates = [p["date"] for p in out[0]["points"]]
    assert dates == ["2026-01-01", "2026-06-01"]


def test_trends_abnormal_sorted_first():
    r1 = _mk_report(1, "2026-01-01", [
        ("白细胞计数", 6.0, 3.5, 9.5, AnalyteStatus.CONFIRMED),
        ("血红蛋白", 130, 115, 150, AnalyteStatus.CONFIRMED),
    ])
    r2 = _mk_report(2, "2026-06-01", [
        ("白细胞计数", 6.0, 3.5, 9.5, AnalyteStatus.CONFIRMED),
        ("血红蛋白", 90, 115, 150, AnalyteStatus.CONFIRMED),   # 异常
    ])
    out = trends_mod.build_trends([r1, r2])
    assert out[0]["name"] == "血红蛋白"   # 异常项排前
    assert out[0]["abnormal"] is True
    assert out[1]["abnormal"] is False


def test_trends_no_range_gives_no_range_interpretation():
    r1 = _mk_report(1, "2026-01-01", [("平均红细胞体积", 88, None, None, AnalyteStatus.CONFIRMED)])
    r2 = _mk_report(2, "2026-06-01", [("平均红细胞体积", 88, None, None, AnalyteStatus.CONFIRMED)])
    out = trends_mod.build_trends([r1, r2])
    assert out[0]["latest_interpretation"] == "no_range"
    assert out[0]["abnormal"] is False
