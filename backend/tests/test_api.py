"""API 端到端测试，验证核对接口的边界处理。"""
from fastapi.testclient import TestClient

from app import vision_import
from app.ingest import make_report
from app.main import app

client = TestClient(app)


def test_list_reports():
    resp = client.get("/api/reports")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2
    assert data[0]["exam_type"] == "血常规"


def test_get_report_has_analytes():
    resp = client.get("/api/reports/1")
    assert resp.status_code == 200
    analytes = resp.json()["analytes"]
    assert len(analytes) >= 5


def test_unchecked_analyte_reports_unchecked_interpretation():
    """接口层回归：未核对的指标，interpretation 必须是 unchecked。

    "还没核对"（流程没走完）≠ "no_range / not_numeric"（已核对但原料比不了）。
    这条断言守的是绕过前端的调用方 —— 导出、其它客户端、对接方。
    """
    reports = client.get("/api/reports").json()
    pending = [a for r in reports for a in r["analytes"] if a["status"] != "confirmed"]
    assert pending, "演示数据里应至少有一条未核对指标"
    for a in pending:
        assert a["interpretation"] == "unchecked", (
            f'{a["name"]} 的 status={a["status"]}，'
            f'interpretation 却是 {a["interpretation"]}'
        )


def test_get_missing_report_404():
    assert client.get("/api/reports/999").status_code == 404


def test_update_analyte_confirm():
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": "70", "unit": "%", "ref_range": "40-75", "status": "confirmed"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["value"] == 70.0
    assert body["interpretation"] == "within"


def test_update_analyte_bad_value_rejected():
    # 任意文本不能伪装成定性结果被静默接受
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": "疑似阴性结果", "status": "confirmed"},
    )
    assert resp.status_code == 400


def test_update_analyte_confirms_qualitative_result_without_unit():
    resp = client.put(
        "/api/reports/1/analytes/106",
        json={"value": "阴性", "unit": None, "ref_range": "阴性", "status": "confirmed"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "confirmed"
    assert body["value"] is None
    assert body["result_text"] == "阴性"
    assert body["ref_text"] == "阴性"
    assert body["unit"] is None
    assert body["interpretation"] == "not_numeric"


def test_update_analyte_missing_value_cannot_be_confirmed():
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": None, "unit": "%", "ref_range": "40-75", "status": "confirmed"},
    )
    assert resp.status_code == 400


def test_update_analyte_bad_range_rejected():
    # 解析不了的参考范围要报错，不猜
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": "70", "ref_range": "3-5 / 6-8", "status": "confirmed"},
    )
    assert resp.status_code == 400


def test_update_analyte_bad_status_rejected():
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": "70", "status": "not-a-real-status"},
    )
    assert resp.status_code == 400


def test_update_analyte_mark_unclear():
    # 非数值结果可以标记为存疑，不报错
    resp = client.put(
        "/api/reports/1/analytes/106",
        json={"value": None, "status": "unclear", "note": "定性结果，规则不适用"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "unclear"


def test_confirmed_range_without_unit_is_reported_unclear():
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": "70", "unit": None, "ref_range": "40-75", "status": "confirmed"},
    )
    assert resp.status_code == 200
    assert resp.json()["interpretation"] == "unclear_unit"


def test_confirmed_strict_range_preserves_operator_and_boundary_meaning():
    resp = client.put(
        "/api/reports/1/analytes/104",
        json={"value": "5.2", "unit": "mmol/L", "ref_range": "<5.2", "status": "confirmed"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ref_text"] == "<5.2"
    assert body["interpretation"] == "high"


def test_table_import_requires_date_and_keeps_metadata():
    missing = client.post(
        "/api/import/table",
        json={"csv_text": "白细胞计数,9.2,10^9/L,3.5-9.5"},
    )
    assert missing.status_code == 422

    response = client.post(
        "/api/import/table",
        json={
            "csv_text": "白细胞计数,9.2,10^9/L,3.5-9.5",
            "patient_label": "导入测试",
            "exam_type": "血常规",
            "collected_at": "2026-10-14",
            "hospital": "测试医院",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["collected_at"] == "2026-10-14"
    assert body["hospital"] == "测试医院"
    assert body["analytes"][0]["status"] == "unchecked"
    assert body["analytes"][0]["value"] is None


def test_update_report_metadata_preserves_analytes_and_rejects_blank_required_fields():
    imported = client.post(
        "/api/import/table",
        json={
            "csv_text": "尿胆红素,阴性,,阴性",
            "patient_label": "导入报告",
            "exam_type": "血常规",
            "collected_at": "2026-10-14",
        },
    ).json()
    report_id = imported["id"]

    response = client.put(
        f"/api/reports/{report_id}",
        json={
            "patient_label": "  尿检复查  ",
            "exam_type": " 尿常规 ",
            "collected_at": "2026-07-13",
            "hospital": " 市中心医院 ",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["patient_label"] == "尿检复查"
    assert updated["exam_type"] == "尿常规"
    assert updated["collected_at"] == "2026-07-13"
    assert updated["hospital"] == "市中心医院"
    assert updated["analytes"] == imported["analytes"]

    rejected = client.put(
        f"/api/reports/{report_id}",
        json={
            "patient_label": "   ",
            "exam_type": "尿常规",
            "collected_at": "2026-07-13",
            "hospital": "另一家医院",
        },
    )
    assert rejected.status_code == 400
    persisted = client.get(f"/api/reports/{report_id}").json()
    assert persisted["patient_label"] == "尿检复查"
    assert persisted["hospital"] == "市中心医院"


def test_update_missing_report_metadata_returns_404():
    response = client.put(
        "/api/reports/999999",
        json={
            "patient_label": "不存在的报告",
            "exam_type": "其他",
            "collected_at": "2026-10-14",
            "hospital": "",
        },
    )
    assert response.status_code == 404


def test_ocr_import_persists_private_original(tmp_path, monkeypatch):
    monkeypatch.setenv("LAB_REPORT_UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(vision_import, "is_configured", lambda: True)

    def fake_ingest(**kwargs):
        return make_report(
            report_id=kwargs["report_id"],
            patient_label=kwargs["patient_label"],
            exam_type=kwargs["exam_type"],
            collected_at=kwargs["collected_at"],
            hospital=kwargs["hospital"],
            source_note="测试图片识别",
            rows=[{"name": "白细胞计数", "value": "9.2", "unit": "10^9/L", "ref_range": "3.5-9.5"}],
        )

    monkeypatch.setattr(vision_import, "ingest_image_as_report", fake_ingest)
    png = b"\x89PNG\r\n\x1a\nminimal-test-image"
    response = client.post(
        "/api/import/ocr",
        data={"patient_label": "图片测试", "exam_type": "血常规", "collected_at": "2026-10-14", "hospital": "测试医院"},
        files={"file": ("report.png", png, "image/png")},
    )
    assert response.status_code == 200
    image_url = response.json()["image_url"]
    assert image_url.startswith("/api/uploads/")
    fetched = client.get(image_url)
    assert fetched.status_code == 200
    assert fetched.content == png
    assert fetched.headers["cache-control"].startswith("private")


def test_batch_confirm_uses_source_values_and_rejects_invalid_group_atomically():
    imported = client.post(
        "/api/import/table",
        json={
            "csv_text": "项目,结果,单位,参考范围\n白细胞计数,9.2,10^9/L,3.5-9.5\n自定义指标,2.0,U,复杂范围",
            "patient_label": "批量核对测试",
            "exam_type": "血常规",
            "collected_at": "2026-10-14",
        },
    ).json()
    report_id = imported["id"]
    first_id, second_id = [item["id"] for item in imported["analytes"]]

    rejected = client.post(
        f"/api/reports/{report_id}/batch-confirm",
        json={"analyte_ids": [first_id, second_id]},
    )
    assert rejected.status_code == 400
    unchanged = client.get(f"/api/reports/{report_id}").json()
    assert [item["status"] for item in unchanged["analytes"]] == ["unchecked", "unchecked"]

    accepted = client.post(
        f"/api/reports/{report_id}/batch-confirm",
        json={"analyte_ids": [first_id]},
    )
    assert accepted.status_code == 200
    items = accepted.json()["analytes"]
    assert items[0]["status"] == "confirmed"
    assert items[0]["value"] == 9.2
    assert items[0]["unit"] == "10^9/L"
    assert items[1]["status"] == "unchecked"


def test_batch_confirm_rejects_missing_source_unit():
    imported = client.post(
        "/api/import/table",
        json={
            "csv_text": "无单位指标,2.0,,1-3",
            "patient_label": "缺单位批量测试",
            "exam_type": "其他",
            "collected_at": "2026-10-14",
        },
    ).json()
    response = client.post(
        f"/api/reports/{imported['id']}/batch-confirm",
        json={"analyte_ids": [imported["analytes"][0]["id"]]},
    )
    assert response.status_code == 400
    assert "单位" in response.json()["detail"]


def test_batch_confirm_accepts_explicit_qualitative_result_without_unit():
    imported = client.post(
        "/api/import/table",
        json={
            "csv_text": "项目,结果,单位,参考范围\n尿胆红素,阴性,,阴性\n尿蛋白,2+,,阴性",
            "patient_label": "定性批量核对测试",
            "exam_type": "尿常规",
            "collected_at": "2026-10-14",
        },
    ).json()
    ids = [item["id"] for item in imported["analytes"]]

    response = client.post(
        f"/api/reports/{imported['id']}/batch-confirm",
        json={"analyte_ids": ids},
    )
    assert response.status_code == 200
    items = response.json()["analytes"]
    assert [item["status"] for item in items] == ["confirmed", "confirmed"]
    assert [item["result_text"] for item in items] == ["阴性", "2+"]
    assert all(item["value"] is None for item in items)
    assert all(item["unit"] is None for item in items)
    assert all(item["interpretation"] == "not_numeric" for item in items)
