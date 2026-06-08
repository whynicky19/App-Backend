import json
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

import schemas
from db import get_db
from deps import get_current_user, get_current_teacher
from models import ProcessedDocument, RagChunk, RagDocument
from services.chunker import chunk_text, count_tokens
from services.document_processor import doc_to_prompt_text, process_document
from services.embedder import embed_texts_sync
from services.retriever import retrieve_and_answer

router = APIRouter(prefix="/rag", tags=["RAG"])
logger = logging.getLogger(__name__)

_ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "text/plain",
    "text/markdown",
    "text/csv",
}

_EXT_FALLBACK = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".txt": "text/plain",
    ".md": "text/markdown",
}

_MAX_BYTES = 50 * 1024 * 1024

def _resolve_mime(file: UploadFile) -> str:
    from pathlib import Path
    ct = file.content_type or ""
    if ct in _ALLOWED_MIME:
        return ct
    ext = Path(file.filename or "").suffix.lower()
    return _EXT_FALLBACK.get(ext, ct)

@router.post(
    "/ingest",
    response_model=schemas.RagIngestResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingest_file(
    file: UploadFile,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
) -> schemas.RagIngestResponse:
    mime = _resolve_mime(file)
    if mime not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"Неподдерживаемый тип '{file.content_type}'. Допустимые: DOCX, PDF, PNG, JPG, TXT, MD",
        )

    data = file.file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Файл превышает 50 МБ")

    fname = file.filename or "upload"

    try:
        doc_json = process_document(data, fname)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except Exception as exc:
        logger.exception("Ошибка парсинга '%s'", fname)
        raise HTTPException(status_code=422, detail=f"Не удалось распарсить файл: {exc}")

    full_text = doc_json.get("full_text", "").strip()
    if not full_text:
        raise HTTPException(status_code=422, detail="Из файла не удалось извлечь текст.")

    token_count = count_tokens(full_text)
    logger.info("'%s': распарсен, %d токенов", fname, token_count)

    rag_doc = RagDocument(filename=fname, mime_type=mime, org_type=current_user.org_type)
    db.add(rag_doc)
    db.flush()

    proc_doc = ProcessedDocument(
        rag_document_id=rag_doc.id,
        filename=fname,
        format=doc_json.get("format", "unknown"),
        content_json=json.dumps(doc_json, ensure_ascii=False),
        token_count=token_count,
    )
    db.add(proc_doc)

    chunks = chunk_text(full_text)
    if not chunks:
        raise HTTPException(status_code=422, detail="Текст не разбился на чанки.")

    embeddings = embed_texts_sync([c.text for c in chunks])

    db.add_all([
        RagChunk(
            document_id=rag_doc.id,
            chunk_index=chunk.index,
            text=chunk.text,
            token_count=chunk.token_count,
            embedding=json.dumps(embedding),
        )
        for chunk, embedding in zip(chunks, embeddings)
    ])

    db.commit()
    logger.info("Сохранён doc #%d, %d чанков, JSON кэш %d токенов", rag_doc.id, len(chunks), token_count)

    return schemas.RagIngestResponse(
        document_id=rag_doc.id,
        filename=fname,
        chunks_created=len(chunks),
    )

@router.post("/query", response_model=schemas.RagQueryResponse)
def query_rag(
    body: schemas.RagQueryRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> schemas.RagQueryResponse:
    try:
        result = retrieve_and_answer(
            question=body.question,
            db=db,
            top_k=body.top_k,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return schemas.RagQueryResponse(
        answer=result["answer"],
        sources=[schemas.RagChunkSource(**s) for s in result["sources"]],
        context_tokens=result["context_tokens"],
    )

@router.get("/documents", response_model=List[schemas.RagIngestResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    docs = db.query(RagDocument).filter(RagDocument.org_type == current_user.org_type).order_by(RagDocument.created_at.desc()).all()
    return [
        schemas.RagIngestResponse(
            document_id=d.id,
            filename=d.filename,
            chunks_created=len(d.chunks),
        )
        for d in docs
    ]

@router.get("/documents/{doc_id}/content", response_model=dict)
def get_document_json(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc or doc.org_type != current_user.org_type:
        raise HTTPException(status_code=404, detail="Документ не найден")
    proc = db.query(ProcessedDocument).filter(
        ProcessedDocument.rag_document_id == doc_id
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="JSON-кэш не найден")
    return json.loads(proc.content_json)

@router.delete("/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc or doc.org_type != current_user.org_type:
        raise HTTPException(status_code=404, detail="Документ не найден")
    db.delete(doc)
    db.commit()
