import os
import io
from uuid import uuid4
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from deps import get_current_user
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.file_service import read_file

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx",
    "txt", "md", "csv", "rtf",
    "png", "jpg", "jpeg", "gif", "webp",
    "zip", "rar", "sm",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


MAGIC_BYTES: dict = {
    b"\x25\x50\x44\x46": "pdf",
    b"\x50\x4b\x03\x04": "zip/docx/xlsx/pptx",
    b"\xd0\xcf\x11\xe0": "doc/xls/ppt",
    b"\x89\x50\x4e\x47": "png",
    b"\xff\xd8\xff":     "jpg",
    b"\x47\x49\x46\x38": "gif",
    b"\x52\x49\x46\x46": "webp",
    b"\x52\x61\x72\x21": "rar",
    b"\x1f\x8b":         "gz",
}


TEXT_EXTENSIONS = {"txt", "md", "csv", "rtf", "sm"}

def _validate_file_content(content: bytes, ext: str) -> bool:

    if ext in TEXT_EXTENSIONS:

        try:
            content[:1024].decode("utf-8", errors="strict")
            return True
        except UnicodeDecodeError:
            try:
                content[:1024].decode("cp1251", errors="strict")
                return True
            except Exception:
                return False
    if ext == "pdf":
        return content[:4] == b"\x25\x50\x44\x46"
    if ext in ("png",):
        return content[:4] == b"\x89\x50\x4e\x47"
    if ext in ("jpg", "jpeg"):
        return content[:3] == b"\xff\xd8\xff"
    if ext == "gif":
        return content[:4] == b"\x47\x49\x46\x38"
    if ext == "webp":
        return content[:4] == b"\x52\x49\x46\x46"
    if ext == "rar":
        return content[:4] == b"\x52\x61\x72\x21"
    if ext in ("zip",):
        return content[:4] == b"\x50\x4b\x03\x04"
    if ext in ("docx", "xlsx", "pptx"):
        return content[:4] == b"\x50\x4b\x03\x04"
    if ext in ("doc", "xls", "ppt"):
        return content[:4] == b"\xd0\xcf\x11\xe0"
    # Для остальных форматов не проверяем magic bytes
    return True


@router.get("/utils/file-text")
async def get_file_text(
    url: str,
    current_user=Depends(get_current_user),
):
    from services.ai_grader import _fetch_file_text
    text = await _fetch_file_text(url)
    return {"text": text}


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    ext = os.path.splitext(file.filename)[1].lstrip(".").lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Тип файла '.{ext}' не разрешён. Допустимые: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Файл слишком большой (максимум 50 МБ)")


    if not _validate_file_content(content, ext):
        raise HTTPException(
            status_code=415,
            detail=f"Содержимое файла не соответствует расширению .{ext}. Загрузите настоящий {ext.upper()} файл.",
        )

    unique_filename = f"{uuid4().hex}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    try:
        with open(file_path, "wb") as buffer:
            buffer.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    parsed = read_file(file_path)
    file_url = f"{APP_BASE_URL.rstrip('/')}/uploads/{unique_filename}"
    return JSONResponse(content={"file_url": file_url, "filename": file.filename, "parsed": parsed})
