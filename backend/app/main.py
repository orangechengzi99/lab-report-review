"""FastAPI 后端：检验报告管理（lab-report-review）。

三组接口：

- 报告与核对
  - GET  /api/reports            列出报告
  - GET  /api/reports/{id}       单份报告详情（含每个指标的判读状态）
  - PUT  /api/reports/{id}       修改报告标签、类型、日期和医院
  - PUT  /api/reports/{id}/analytes/{aid}  人工核对某条指标
- 趋势聚合
  - GET  /api/trends             跨报告时间序列（只含已核对的数据点）
- 数据导入（结果一律是"待核对草稿"，不自动入档）
  - POST /api/import/table、/table-file、/deepseek、/ocr
  - GET  /api/import/deepseek-status、/ocr-status

核对接口是本项目的核心：它允许用户确认数值、单位、参考范围，
并明确区分"确认"与"存疑"。任何未经核对的指标不会被判为异常。
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import database
from . import table_import, deepseek_import, vision_import, storage
from . import trends as trends_mod
from .models import Analyte, AnalyteStatus
from .rules import parse_qualitative_value, parse_ref_range, parse_value

app = FastAPI(
    title="检验报告管理 API",
    description=(
        "检验报告的结构化导入、人工核对、参考范围规则判断与跨报告趋势聚合。"
        "所有判读只依据报告自带的参考范围，不跨报告套用统一阈值，不产出诊断结论。"
    ),
    version="0.1.0",
)

# 开发阶段允许跨域（前端 Vite 默认 5173 端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyteUpdate(BaseModel):
    """人工核对提交的内容。

    value/unit/ref_range 均为用户核对后填入的字符串；value 可以是数值，
    也可以是明确的定性结果（如“阴性”“弱阳性”“2+”）。
    后端负责解析并在解析失败时返回明确错误，不静默接受。
    """
    name: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=50)
    value: Optional[str] = Field(default=None, max_length=100)
    unit: Optional[str] = Field(default=None, max_length=50)
    ref_range: Optional[str] = Field(default=None, max_length=100)
    status: str  # "confirmed" | "unclear"
    note: Optional[str] = Field(default=None, max_length=500)


class BatchConfirmBody(BaseModel):
    """批量确认只提交待核对指标 ID，字段值始终取报告识别原文。"""
    analyte_ids: list[int] = Field(min_length=1, max_length=200)


class ReportUpdate(BaseModel):
    """导入后允许更正的报告基本信息；指标和原图不在此接口中改动。"""
    patient_label: str = Field(min_length=1, max_length=100)
    exam_type: str = Field(min_length=1, max_length=50)
    collected_at: date
    hospital: str = Field(default="", max_length=200)


def _validated_analyte_update(
    payload: AnalyteUpdate,
    new_status: AnalyteStatus,
    *,
    batch_mode: bool = False,
) -> dict:
    """把核对表单转换为数据库字段；批量模式只要求定量结果单位完整。"""
    update_kwargs: dict = {"status": new_status}

    value_text = payload.value.strip() if payload.value is not None else ""
    parsed_value = None
    result_text = None
    if value_text:
        parsed_value = parse_value(value_text)
        if parsed_value is None:
            result_text = parse_qualitative_value(value_text)
        if parsed_value is None and result_text is None and new_status == AnalyteStatus.CONFIRMED:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"无法识别结果：{payload.value!r}。"
                    "请输入数值，或明确的定性结果（如阴性、阳性、弱阳性、1+）"
                ),
            )
        if parsed_value is None and result_text is None:
            # “存疑”允许保留人工输入的原文，但不会把它判为已核对。
            result_text = value_text
    else:
        if new_status == AnalyteStatus.CONFIRMED:
            raise HTTPException(status_code=400, detail="确认指标前必须填写并核对结果")

    update_kwargs["value"] = parsed_value
    update_kwargs["result_text"] = result_text
    is_qualitative = result_text is not None and parse_qualitative_value(result_text) is not None

    clean_unit = payload.unit.strip() if payload.unit and payload.unit.strip() else None
    if batch_mode and parsed_value is not None and clean_unit is None:
        raise HTTPException(status_code=400, detail="批量核对中的定量结果要求报告原文包含单位")
    update_kwargs["unit"] = clean_unit
    update_kwargs["note"] = payload.note.strip() if payload.note and payload.note.strip() else None

    if payload.ref_range is not None and payload.ref_range.strip() != "":
        clean_ref = payload.ref_range.strip()
        if is_qualitative or (new_status != AnalyteStatus.CONFIRMED and parsed_value is None):
            if batch_mode and parse_qualitative_value(clean_ref) is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"定性参考值 {clean_ref!r} 需要单独核对",
                )
            update_kwargs["ref_low"] = None
            update_kwargs["ref_high"] = None
            update_kwargs["ref_text"] = clean_ref
        else:
            low, high = parse_ref_range(clean_ref)
            if low is None and high is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"无法解析参考范围：{payload.ref_range!r}（仅支持 'a-b' 形式）",
                )
            update_kwargs["ref_low"] = low
            update_kwargs["ref_high"] = high
            # 保留核对后的参考范围原文，避免把 “<” 重写成 “<=” 并丢失临界值语义。
            update_kwargs["ref_text"] = clean_ref
    else:
        update_kwargs["ref_low"] = None
        update_kwargs["ref_high"] = None
        update_kwargs["ref_text"] = None

    if payload.name is not None:
        clean_name = payload.name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="指标名称不能为空")
        update_kwargs["name"] = clean_name
    if payload.category is not None:
        update_kwargs["category"] = payload.category.strip() or "其他"
    return update_kwargs


@app.get("/api/reports")
def list_reports():
    return [r.to_dict() for r in database.get_all_reports()]


@app.get("/api/reports/{report_id}")
def get_report(report_id: int):
    r = database.get_report(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return r.to_dict()


@app.put("/api/reports/{report_id}")
def update_report(report_id: int, payload: ReportUpdate):
    """更正报告基本信息，不触碰原图、指标值或核对状态。"""
    if database.get_report(report_id) is None:
        raise HTTPException(status_code=404, detail="报告不存在")

    patient_label = payload.patient_label.strip()
    exam_type = payload.exam_type.strip()
    if not patient_label:
        raise HTTPException(status_code=400, detail="报告标签不能为空")
    if not exam_type:
        raise HTTPException(status_code=400, detail="检查类型不能为空")

    updated = database.update_report(
        report_id,
        patient_label=patient_label,
        exam_type=exam_type,
        collected_at=payload.collected_at.isoformat(),
        hospital=payload.hospital.strip(),
    )
    if updated is None:
        raise HTTPException(status_code=500, detail="报告信息更新失败")
    return updated.to_dict()


@app.put("/api/reports/{report_id}/analytes/{analyte_id}")
def update_analyte(report_id: int, analyte_id: int, payload: AnalyteUpdate):
    # 先确认报告和指标存在
    r = database.get_report(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    a = next((x for x in r.analytes if x.id == analyte_id), None)
    if a is None:
        raise HTTPException(status_code=404, detail="指标不存在")

    # 校验 status 合法性
    try:
        new_status = AnalyteStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"非法状态：{payload.status}")

    update_kwargs = _validated_analyte_update(payload, new_status)

    updated = database.update_analyte(analyte_id, **update_kwargs)
    if updated is None:
        raise HTTPException(status_code=500, detail="更新失败")
    return updated.to_dict()


@app.post("/api/reports/{report_id}/batch-confirm")
def batch_confirm_analytes(report_id: int, body: BatchConfirmBody):
    """一次确认多条明确草稿；支持定量和常见定性结果，并使用识别原文。"""
    report = database.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    if len(set(body.analyte_ids)) != len(body.analyte_ids):
        raise HTTPException(status_code=400, detail="批量核对包含重复指标")

    by_id = {analyte.id: analyte for analyte in report.analytes}
    updates: list[tuple[int, dict]] = []
    for analyte_id in body.analyte_ids:
        analyte = by_id.get(analyte_id)
        if analyte is None:
            raise HTTPException(status_code=404, detail=f"指标 {analyte_id} 不存在")
        if analyte.status != AnalyteStatus.UNCHECKED:
            raise HTTPException(status_code=400, detail=f"「{analyte.name}」不是待核对状态")
        payload = AnalyteUpdate(
            name=analyte.name,
            category=analyte.category,
            value=analyte.raw_value,
            unit=analyte.raw_unit,
            ref_range=analyte.raw_ref_range,
            status=AnalyteStatus.CONFIRMED.value,
        )
        updates.append((analyte_id, _validated_analyte_update(
            payload,
            AnalyteStatus.CONFIRMED,
            batch_mode=True,
        )))

    try:
        updated = database.update_analytes_batch(report_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if updated is None:
        raise HTTPException(status_code=500, detail="批量核对失败")
    return updated.to_dict()


@app.get("/api/trends")
def get_trends():
    """跨报告聚合的指标趋势序列。

    只统计「已核对 + 有数值」的点；每个指标至少 2 个时间点才返回。
    趋势方向仅描述数值变化，不含任何医学解读。
    """
    reports = database.get_all_reports()
    items = trends_mod.build_trends(reports)
    return {"count": len(items), "items": items}


# ---------------------------------------------------------------------------
# 导入入口
# ---------------------------------------------------------------------------

class TableImportBody(BaseModel):
    """表格导入请求体（CSV 文本直接放在请求里，也可用文件上传）。"""
    csv_text: str = Field(min_length=1, max_length=2_000_000)
    patient_label: str = Field(default="导入报告", min_length=1, max_length=100)
    exam_type: str = Field(default="血常规", min_length=1, max_length=50)
    collected_at: date
    hospital: str = Field(default="", max_length=100)


@app.post("/api/import/table")
def import_table(body: TableImportBody):
    """电子版表格导入：CSV 文本 → 待核对报告草稿。"""
    report = table_import.ingest_csv_as_report(
        report_id=database.get_next_id(),
        text=body.csv_text,
        patient_label=body.patient_label,
        exam_type=body.exam_type,
        collected_at=body.collected_at.isoformat(),
        hospital=body.hospital.strip(),
    )
    if report is None:
        raise HTTPException(
            status_code=400,
            detail="无法解析表格：请确认包含「名称/结果」两列，或使用简单的「指标名,结果」两列格式",
        )
    saved = database.add_report(report)
    return saved.to_dict()


@app.post("/api/import/table-file")
async def import_table_file(
    file: UploadFile = File(...),
    patient_label: str = Form("导入报告"),
    exam_type: str = Form("血常规"),
    collected_at: date = Form(...),
    hospital: str = Form(""),
):
    """电子版表格导入：上传 CSV 文件。"""
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="CSV 文件不能超过 2 MB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="文件编码无法识别，请转为 UTF-8 或 GBK 的 CSV")
    report = table_import.ingest_csv_as_report(
        report_id=database.get_next_id(),
        text=text,
        patient_label=patient_label,
        exam_type=exam_type,
        collected_at=collected_at.isoformat(),
        hospital=hospital.strip(),
    )
    if report is None:
        raise HTTPException(status_code=400, detail="无法解析表格内容")
    saved = database.add_report(report)
    return saved.to_dict()


@app.post("/api/import/ocr")
async def import_ocr(
    file: UploadFile = File(...),
    patient_label: str = Form("导入报告"),
    exam_type: str = Form("血常规"),
    collected_at: date = Form(...),
    hospital: str = Form(""),
):
    """图像识别导入：上传检验单图片，用 DeepSeek deepseek-flash 识别为待核对草稿。

    未配置 DEEPSEEK_API_KEY 时返回 503 + 明确提示，前端据此降级。
    """
    if not vision_import.is_configured():
        raise HTTPException(
            status_code=503,
            detail="图片识别未配置（需设置 DEEPSEEK_API_KEY）。可先用文本解析或表格导入。",
        )
    image_bytes = await file.read(storage.max_image_bytes() + 1)
    try:
        mime_type, _ = storage.validate_image(image_bytes)
        report = await run_in_threadpool(
            vision_import.ingest_image_as_report,
            report_id=database.get_next_id(),
            image_bytes=image_bytes,
            filename=file.filename or "image.png",
            patient_label=patient_label,
            exam_type=exam_type,
            collected_at=collected_at.isoformat(),
            hospital=hospital.strip(),
            mime_type=mime_type,
        )
    except storage.InvalidImage as e:
        raise HTTPException(status_code=400, detail=str(e))
    except vision_import.VisionNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"图片识别失败：{e}")
    image_url = None
    try:
        image_url, _ = storage.save_original_image(image_bytes)
        report.image_url = image_url
        saved = database.add_report(report)
    except Exception:
        storage.delete_original_image(image_url)
        raise
    return saved.to_dict()


@app.get("/api/import/ocr-status")
def ocr_status():
    """查询图片识别入口是否已配置（现在走 DeepSeek deepseek-flash）。"""
    return {"configured": vision_import.is_configured()}


@app.get("/api/uploads/{filename}", include_in_schema=False)
def uploaded_image(filename: str):
    """仅提供由本应用保存的随机命名原图；拒绝任意路径访问。"""
    path, mime = storage.resolve_original_image(filename)
    if path is None or mime is None:
        raise HTTPException(status_code=404, detail="原图不存在")
    return FileResponse(
        path,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


class DeepseekImportBody(BaseModel):
    """DeepSeek 文本解析请求体。"""
    text: str = Field(min_length=1, max_length=200_000)
    patient_label: str = Field(default="导入报告", min_length=1, max_length=100)
    exam_type: str = Field(default="血常规", min_length=1, max_length=50)
    collected_at: date
    hospital: str = Field(default="", max_length=100)


@app.post("/api/import/deepseek")
def import_deepseek(body: DeepseekImportBody):
    """DeepSeek 文本解析：报告文字 → 待核对草稿。"""
    if not deepseek_import.is_configured():
        raise HTTPException(
            status_code=503,
            detail="文本解析未配置（需设置 DEEPSEEK_API_KEY）。可先用表格导入。",
        )
    try:
        report = deepseek_import.ingest_text_as_report(
            report_id=database.get_next_id(),
            text=body.text,
            patient_label=body.patient_label,
            exam_type=body.exam_type,
            collected_at=body.collected_at.isoformat(),
            hospital=body.hospital.strip(),
        )
    except deepseek_import.DeepseekNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"文本解析失败：{e}")
    saved = database.add_report(report)
    return saved.to_dict()


@app.get("/api/import/deepseek-status")
def deepseek_status():
    """查询 DeepSeek 入口是否已配置。"""
    return {"configured": deepseek_import.is_configured()}
