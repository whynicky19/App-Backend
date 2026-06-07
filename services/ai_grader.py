import json
import os
import io
import zipfile
import re
import httpx
from typing import Optional

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o"

def _build_system_prompt(has_reference: bool) -> str:
    ref_block = ""
    if has_reference:
        ref_block = """
ЭТАЛОННОЕ РЕШЕНИЕ:
Эталон показывает ожидаемый уровень ответа — используй его чтобы понять глубину темы.
НЕ требуй дословного совпадения. Студент мог объяснить иначе но правильно — это полный балл.
Снижай балл только если студент упустил ключевые смысловые элементы, не за другие формулировки.
"""
    return f"""Ты справедливый преподаватель. Оценивай работу студента по критериям — ни занижая ни завышая.

{ref_block}
Шкала для каждого критерия:
- Критерий полностью раскрыт, всё верно → 100% балла
- Раскрыт хорошо, есть суть, мелкие пробелы → 75–90%
- Раскрыт частично, половина темы присутствует → 40–65%
- Упомянуто поверхностно, без понимания → 15–35%
- Отсутствует или полностью неверно → 0–10%

Важно:
- Оценивай что реально написано, не додумывай за студента
- Если файл не прочитался и нет текста → 0 за содержание файла
- Пустой ответ → 0
- Сумма по критериям = итоговый score
- Комментарий: 2-3 предложения, конкретно — что верно, что не так, что добавить

ОТВЕЧАЙ ТОЛЬКО JSON.

Формат:
{{
  "score": <целое число 0..max_score>,
  "feedback": "<общий комментарий>",
  "criteria_scores": [
    {{"name": "...", "score": <int>, "max": <int>, "comment": "..."}}
  ]
}}"""

def _build_user_prompt(
    text: str,
    criteria: list,
    max_score: int,
    has_file: bool,
    reference_text: Optional[str] = None,
    lecture_context: Optional[str] = None,
) -> str:
    criteria_text = "\n".join(
        f"- {c['name']} (вес: {c['weight']} баллов)"
        + (f": {c['description']}" if c.get("description") else "")
        for c in criteria
    )

    file_note = ""
    if has_file:
        file_note = "\n[ПРИМЕЧАНИЕ: Студент также прикрепил файл. Содержимое файла включено выше если удалось прочитать.]"

    ref_block = ""
    if reference_text:
        ref_block = f"""
ЭТАЛОННОЕ РЕШЕНИЕ (для понимания ожидаемого уровня, не для дословного сравнения):
\"\"\"
{reference_text[:8000]}
\"\"\"

Используй эталон чтобы понять: какие ключевые идеи и факты должны быть в ответе.
Если студент раскрыл те же идеи своими словами — это засчитывается полностью.
Снижай балл только за реально пропущенные смысловые элементы.

"""

    lecture_block = ""
    if lecture_context and lecture_context.strip():
        lecture_block = f"""
МАТЕРИАЛЫ КУРСА:
\"\"\"
{lecture_context[:6000]}
\"\"\"

"""

    return f"""Оцени работу студента по критериям ниже. Оценивай строго по содержанию.

КРИТЕРИИ ОЦЕНКИ (максимальный балл = {max_score}):
{criteria_text}
{ref_block}{lecture_block}
РАБОТА СТУДЕНТА:
\"\"\"\n{text}
\"\"\"{file_note}

ИНСТРУКЦИИ:
- Оцени каждый критерий строго по содержанию: полное раскрытие = полный балл, частичное = пропорциональный балл, отсутствие = 0
{'- Сравни с эталонным решением: укажи что совпадает и что упущено' if reference_text else ''}
- Сумма баллов по критериям должна точно равняться итоговому score
- Итоговый score не может превышать {max_score}
- Комментарий: конкретно что сделано верно и что именно не так (без общих фраз)

Верни ТОЛЬКО JSON без лишних слов."""

async def _fetch_file_text(url: str) -> str:
    if not url or not url.startswith("http"):
        return ""
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(url)
            if not resp.is_success:
                return ""

            raw_ext = url.split("?")[0].rsplit(".", 1)
            ext = raw_ext[-1].lower() if len(raw_ext) > 1 else ""
            content_type = resp.headers.get("content-type", "").lower()

            if ext == "pdf" or "pdf" in content_type:
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(resp.content)) as pdf:
                        pages = [p.extract_text(layout=True) or "" for p in pdf.pages[:40]]
                    text = "\n\n".join(p for p in pages if p.strip())
                    return text[:25000] if text.strip() else ""
                except Exception as e:
                    return f"[PDF — не удалось извлечь текст: {e}]"

            elif ext in ("docx", "pptx", "xlsx"):
                try:
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                        texts = []
                        for name in z.namelist():
                            if not name.endswith(".xml"):
                                continue
                            if not any(p in name for p in ("word/", "ppt/slides/", "xl/worksheets/")):
                                continue
                            try:
                                xml = z.read(name).decode("utf-8", errors="ignore")
                                found = re.findall(
                                    r"<(?:w:t|a:t|t)[^>]*>([^<]+)</(?:w:t|a:t|t)>", xml
                                )
                                if found:
                                    texts.append(" ".join(found))
                            except Exception:
                                pass
                    result = " ".join(texts).replace("  ", " ")
                    return result[:20000] if result.strip() else ""
                except Exception as e:
                    return f"[Office файл — не удалось прочитать: {e}]"

            elif ext in ("txt", "md", "csv", "tsv", "log", "json", "xml", "yaml", "yml"):
                return resp.content.decode("utf-8", errors="ignore")[:20000]

            elif ext in ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"):
                return "[Изображение — текстовое содержимое недоступно]"

            else:
                try:
                    decoded = resp.content.decode("utf-8", errors="ignore")
                    if decoded.strip():
                        return decoded[:15000]
                    return ""
                except Exception:
                    return ""

    except Exception:
        return ""

async def grade_submission(
    text: str,
    criteria: list,
    max_score: int = 100,
    file_url: Optional[str] = None,
    reference_solution_url: Optional[str] = None,
    reference_solution_urls: Optional[list] = None,
    lecture_context: Optional[str] = None,
) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Please add it to your .env file: OPENAI_API_KEY=sk-..."
        )

    full_text = (text or "").strip()
    has_file = False

    if file_url:
        has_file = True
        file_content = await _fetch_file_text(file_url)
        if file_content.strip():
            if full_text:
                full_text = f"ТЕКСТОВЫЙ ОТВЕТ:\n{full_text}\n\nСОДЕРЖИМОЕ ФАЙЛА:\n{file_content}"
            else:
                full_text = f"СОДЕРЖИМОЕ ФАЙЛА:\n{file_content}"
        elif full_text:
            full_text = f"{full_text}\n\n[Файл прикреплён но не удалось прочитать: {file_url}]"
        else:
            full_text = f"[Студент сдал только файл: {file_url}, но прочитать его не удалось]"

    if not full_text:
        full_text = "[Студент не предоставил ответа]"

    reference_text: Optional[str] = None

    all_ref_urls: list = []
    if reference_solution_urls:
        all_ref_urls.extend(reference_solution_urls)
    if reference_solution_url and reference_solution_url not in all_ref_urls:
        all_ref_urls.append(reference_solution_url)

    if all_ref_urls:
        ref_parts = []
        for idx, ref_url in enumerate(all_ref_urls):
            ref_content = await _fetch_file_text(ref_url)
            if ref_content.strip():
                label = f"ЭТАЛОННЫЙ ФАЙЛ {idx+1}" if len(all_ref_urls) > 1 else "ЭТАЛОННОЕ РЕШЕНИЕ"
                ref_parts.append(f"{label}:\n{ref_content[:8000]}")
        if ref_parts:
            reference_text = "\n\n".join(ref_parts)

    has_reference = reference_text is not None
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": _build_system_prompt(has_reference)},
            {"role": "user", "content": _build_user_prompt(
                full_text, criteria, max_score, has_file, reference_text, lecture_context
            )},
        ],
        "max_tokens": 2500,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            OPENAI_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json=payload,
        )

    if not resp.is_success:
        try:
            err = resp.json()
            msg = err.get("error", {}).get("message", f"OpenAI error {resp.status_code}")
        except Exception:
            msg = f"OpenAI error {resp.status_code}"
        raise RuntimeError(msg)

    raw = resp.json()["choices"][0]["message"]["content"].strip()

    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except Exception:
                raise RuntimeError(f"ИИ вернул невалидный JSON: {e}\nОтвет: {raw[:400]}")
        else:
            raise RuntimeError(f"ИИ вернул невалидный JSON: {e}\nОтвет: {raw[:400]}")

    result["score"] = max(0, min(int(result.get("score", 0)), max_score))
    if not isinstance(result.get("criteria_scores"), list):
        result["criteria_scores"] = []

    usage = resp.json().get("usage", {})
    result["_usage"] = usage

    return result

def get_cached_text_for_url(file_url: str, db) -> str:
    try:
        from models import ProcessedDocument
        filename = file_url.rstrip("/").split("/")[-1].split("?")[0]
        proc = db.query(ProcessedDocument).filter(
            ProcessedDocument.filename == filename
        ).order_by(ProcessedDocument.id.desc()).first()
        if proc:
            import json as _json
            doc = _json.loads(proc.content_json)
            return doc.get("full_text", "")[:20000]
    except Exception:
        pass
    return ""
