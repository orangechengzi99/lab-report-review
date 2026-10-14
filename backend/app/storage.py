"""本地原报告图片存储。

上传文件只保存在运行时目录 ``data/uploads``，该目录必须被 Git 忽略。
文件名使用随机 UUID，不包含患者标签或原始文件名，避免在路径中泄露信息。
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Optional


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_UPLOAD_DIR = _PROJECT_ROOT / "data" / "uploads"
_SAFE_FILENAME = re.compile(r"^[0-9a-f]{32}\.(?:png|jpg|gif|webp)$")


class InvalidImage(ValueError):
    """图片为空、过大或格式不受支持。"""


def upload_dir() -> Path:
    configured = os.environ.get("LAB_REPORT_UPLOAD_DIR")
    return Path(configured).expanduser().resolve() if configured else _DEFAULT_UPLOAD_DIR


def max_image_bytes() -> int:
    raw = os.environ.get("LAB_REPORT_MAX_IMAGE_BYTES", str(10 * 1024 * 1024))
    try:
        return max(1, int(raw))
    except ValueError:
        return 10 * 1024 * 1024


def detect_image(data: bytes) -> tuple[str, str]:
    """根据文件魔数识别 MIME 与扩展名，不信任上传文件名或 Content-Type。"""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise InvalidImage("仅支持 JPEG、PNG、GIF 或 WebP 图片")


def validate_image(data: bytes) -> tuple[str, str]:
    if not data:
        raise InvalidImage("图片为空")
    if len(data) > max_image_bytes():
        limit_mb = max_image_bytes() / (1024 * 1024)
        raise InvalidImage(f"图片不能超过 {limit_mb:g} MB")
    return detect_image(data)


def save_original_image(data: bytes) -> tuple[str, str]:
    """原子写入原图，返回前端可访问 URL 与 MIME。"""
    mime, ext = validate_image(data)
    target_dir = upload_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    target = target_dir / filename
    temporary = target.with_suffix(f"{target.suffix}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return f"/api/uploads/{filename}", mime


def resolve_original_image(filename: str) -> tuple[Optional[Path], Optional[str]]:
    if not _SAFE_FILENAME.fullmatch(filename or ""):
        return None, None
    path = upload_dir() / filename
    if not path.is_file():
        return None, None
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    return path, mime


def delete_original_image(image_url: Optional[str]) -> None:
    """数据库保存失败时清理刚写入的孤立文件。"""
    if not image_url:
        return
    filename = image_url.rsplit("/", 1)[-1]
    path, _ = resolve_original_image(filename)
    if path is not None:
        path.unlink()
