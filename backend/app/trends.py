"""趋势聚合：把多份报告里的同一指标串成时间序列。

核心原则（与项目整体一致）：
- 只用「已核对 + 有数值」的点画线，未核对的点不进入趋势，避免用未确认数据下结论。
- 指标按名称归一化后分组（去空格、统一大小写），展示名取最近一次的名称。
- 每个指标至少需要 2 个时间点才有"趋势"意义，单点不展示。
- 趋势方向只描述数值变化（上升/下降/平稳），不给出任何医学解读。
"""
from __future__ import annotations

from .models import Report

# 变化幅度小于此比例视为"平稳"
_FLAT_THRESHOLD = 0.05


def _norm_key(name: str) -> str:
    """指标名归一化，用于跨报告匹配。"""
    return "".join(name.split()).upper()


def _direction(values: list[float]) -> str:
    """比较首尾值判断趋势方向，幅度过小算平稳。"""
    if len(values) < 2:
        return "flat"
    first, last = values[0], values[-1]
    if first == 0:
        return "up" if last > 0 else ("down" if last < 0 else "flat")
    change = (last - first) / abs(first)
    if change > _FLAT_THRESHOLD:
        return "up"
    if change < -_FLAT_THRESHOLD:
        return "down"
    return "flat"


def build_trends(reports: list[Report]) -> list[dict]:
    """把报告列表聚合成指标趋势序列。

    返回按「最新点是否异常」优先、其次按分类+名称排序的列表。
    """
    groups: dict[str, dict] = {}

    for r in reports:
        # 没有真实检查日期的报告不能进入时间序列，避免把空日期画成伪时间点。
        if not r.collected_at:
            continue
        date = r.collected_at
        for a in r.analytes:
            # 只用已核对且有数值的点
            if a.status.value != "confirmed" or a.value is None:
                continue
            key = _norm_key(a.name)
            g = groups.setdefault(key, {"points": []})
            g["points"].append({
                "date": date,
                "value": a.value,
                "ref_low": a.ref_low,
                "ref_high": a.ref_high,
                "interpretation": a.interpretation().value,
                "report_id": r.id,
                "_name": a.name,
                "_unit": a.unit or "",
                "_category": a.category or "其他",
            })

    trends = []
    for g in groups.values():
        points = sorted(g["points"], key=lambda p: p["date"])
        if len(points) < 2:
            continue  # 单点无趋势意义
        values = [p["value"] for p in points]
        latest = points[-1]

        # 展示名用最近一次；分类/单位用众数（避免个别报告漏填导致漂移）
        name = latest["_name"]
        category = _mode([p["_category"] for p in points])
        unit = _mode([p["_unit"] for p in points if p["_unit"]])

        clean_points = [
            {k: v for k, v in p.items() if not k.startswith("_")} for p in points
        ]
        trends.append({
            "name": name,
            "unit": unit,
            "category": category,
            "points": clean_points,
            "trend": _direction(values),
            "latest_value": latest["value"],
            "latest_date": latest["date"],
            "latest_interpretation": latest["interpretation"],
            "ref_low": latest["ref_low"],
            "ref_high": latest["ref_high"],
            "abnormal": latest["interpretation"] in ("high", "low"),
        })

    # 异常优先，其次按分类+名称
    trends.sort(key=lambda t: (not t["abnormal"], t["category"], t["name"]))
    return trends


def _mode(values: list[str]) -> str:
    """取出现次数最多的值（众数），空列表返回空串。"""
    if not values:
        return ""
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def group_by_category(trends: list[dict]) -> dict[str, list[dict]]:
    """按分类分组，便于前端分区块展示。"""
    out: dict[str, list[dict]] = {}
    for t in trends:
        out.setdefault(t["category"], []).append(t)
    return out
