import json as _json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import schemas
from crud import assignments as crud
from crud import classes as crud_classes
from db import get_db
from deps import get_current_user, get_current_teacher
from models import Class as ClassModel
from services.ai_grader import grade_submission as _ai_grade
from routers.ai import _check_rate_limit

router = APIRouter(tags=["Assignments"])


def _check_assignment_org(db: Session, assignment, current_user):
    """404 если задание принадлежит классу другой организации."""
    cls = db.query(ClassModel).filter(ClassModel.id == assignment.class_id).first()
    if cls and cls.org_type != current_user.org_type:
        raise HTTPException(status_code=404, detail="Assignment not found")


def _check_submission_org(db: Session, submission, current_user):
    """404 если submission принадлежит классу другой организации."""
    from models import Assignment
    assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
    if assignment:
        cls = db.query(ClassModel).filter(ClassModel.id == assignment.class_id).first()
        if cls and cls.org_type != current_user.org_type:
            raise HTTPException(status_code=404, detail="Submission not found")


# ════════════════════════════════════════════════════════
#  ЗАДАНИЯ
# ════════════════════════════════════════════════════════

@router.post(
    "/assignments/",
    response_model=schemas.AssignmentResponseFull,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    body: schemas.AssignmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    criteria_list = [c.model_dump() for c in body.criteria]
    obj = crud.create_assignment(
        db=db,
        class_id=body.class_id,
        title=body.title,
        description=body.description,
        criteria=criteria_list,
        max_score=body.max_score,
        deadline=body.deadline,
        created_by=current_user.id,
        reference_solution_url=body.reference_solution_url,
    )
    return obj


@router.get("/assignments/", response_model=List[schemas.AssignmentResponseFull])
def list_assignments(
    class_id: Optional[int] = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if class_id is not None:
        cls = db.query(ClassModel).filter(ClassModel.id == class_id).first()
        if cls and cls.org_type != current_user.org_type:
            raise HTTPException(status_code=404, detail="Assignment not found")
    return crud.get_all_assignments(db, class_id=class_id, active_only=active_only)


# NOTE: Must be before /assignments/{assignment_id}
@router.get("/assignments/student/my-submissions", response_model=List[schemas.SubmissionWithGrade])
def my_submissions(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return crud.get_submissions_for_student(db, current_user.id)


@router.get("/assignments/student/my-rating")
def my_rating(
    class_id: int = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the student's average score (0-100 scale) based on graded submissions."""
    from sqlalchemy import text as sqlt
    try:
        if class_id:
            rows = db.execute(sqlt("""
                SELECT g.score, a.max_score
                FROM grades g
                JOIN submissions s ON s.id = g.submission_id
                JOIN assignments a ON a.id = s.assignment_id
                WHERE s.student_id = :uid AND a.class_id = :cid
            """), {"uid": current_user.id, "cid": class_id}).fetchall()
        else:
            rows = db.execute(sqlt("""
                SELECT g.score, a.max_score
                FROM grades g
                JOIN submissions s ON s.id = g.submission_id
                JOIN assignments a ON a.id = s.assignment_id
                WHERE s.student_id = :uid
            """), {"uid": current_user.id}).fetchall()

        if not rows:
            return {"avg_score": 0, "avg_percent": 0, "graded_count": 0, "total_score": 0, "max_possible": 0}

        total_score = sum(r[0] or 0 for r in rows)
        max_possible = sum(r[1] or 100 for r in rows)
        avg_score = round(total_score / len(rows), 1)
        avg_percent = round((total_score / max_possible * 100) if max_possible > 0 else 0, 1)

        return {
            "avg_score": avg_score,
            "avg_percent": avg_percent,
            "graded_count": len(rows),
            "total_score": total_score,
            "max_possible": max_possible,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assignments/{assignment_id}", response_model=schemas.AssignmentResponseFull)
def get_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    obj = crud.get_assignment(db, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, obj, current_user)
    return obj


@router.put("/assignments/{assignment_id}", response_model=schemas.AssignmentResponseFull)
def update_assignment(
    assignment_id: int,
    body: schemas.AssignmentUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    obj = crud.get_assignment(db, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, obj, current_user)
    data = body.model_dump(exclude_none=True)
    obj = crud.update_assignment(db, assignment_id, data)
    return obj


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    obj = crud.get_assignment(db, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, obj, current_user)
    crud.delete_assignment(db, assignment_id)


# ════════════════════════════════════════════════════════
#  ВАРИАНТЫ ЗАДАНИЙ
# ════════════════════════════════════════════════════════

@router.get(
    "/assignments/{assignment_id}/variants",
    response_model=List[schemas.VariantResponse],
)
def list_variants(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Список всех вариантов задания с эталонными решениями."""
    obj = crud.get_assignment(db, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, obj, current_user)
    return crud_classes.get_variants(db, assignment_id)


@router.post(
    "/assignments/{assignment_id}/variants",
    response_model=schemas.VariantResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_variant(
    assignment_id: int,
    body: schemas.VariantCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    obj = crud.get_assignment(db, assignment_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, obj, current_user)
    return crud_classes.add_variant(
        db=db,
        assignment_id=assignment_id,
        variant_number=body.variant_number,
        reference_solution_url=body.reference_solution_url,
        title=body.title,
    )


@router.delete(
    "/assignments/{assignment_id}/variants/{variant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_variant(
    assignment_id: int,
    variant_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    """Удалить вариант задания."""
    if not crud_classes.delete_variant(db, variant_id):
        raise HTTPException(status_code=404, detail="Variant not found")




@router.post(
    "/assignments/{assignment_id}/submit",
    response_model=schemas.SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_assignment(
    assignment_id: int,
    body: schemas.SubmissionCreateV2,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    assignment = crud.get_assignment(db, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, assignment, current_user)
    if not assignment.is_active:
        raise HTTPException(status_code=400, detail="Assignment is closed")

    if crud.student_already_submitted(db, assignment_id, current_user.id):
        raise HTTPException(status_code=409, detail="You already submitted this assignment")

    if not body.text_content and not body.file_url and not body.file_urls:
        raise HTTPException(status_code=422, detail="Provide text_content, file_url or file_urls")

    # Validate variant_number if variants exist
    variants = crud_classes.get_variants(db, assignment_id)
    if variants and body.variant_number is None:
        raise HTTPException(
            status_code=422,
            detail=f"Это задание имеет варианты ({len(variants)} шт.). Укажите variant_number.",
        )
    if body.variant_number and variants:
        valid_numbers = [v.variant_number for v in variants]
        if body.variant_number not in valid_numbers:
            raise HTTPException(
                status_code=422,
                detail=f"Вариант {body.variant_number} не найден. Доступные: {valid_numbers}",
            )

    is_late = bool(assignment.deadline and datetime.utcnow() > assignment.deadline)

    all_file_urls: list = []
    if body.file_url:
        all_file_urls.append(body.file_url)
    if body.file_urls:
        all_file_urls.extend(body.file_urls)

    from models import Submission
    import json
    sub_obj = Submission(
        assignment_id=assignment_id,
        student_id=current_user.id,
        text_content=body.text_content,
        file_url=all_file_urls[0] if all_file_urls else None,
        file_urls=json.dumps(all_file_urls) if all_file_urls else None,
        variant_number=body.variant_number,
        status="late" if is_late else "submitted",
    )
    db.add(sub_obj)
    db.commit()
    db.refresh(sub_obj)
    return sub_obj


@router.get(
    "/assignments/{assignment_id}/submissions",
    response_model=List[schemas.SubmissionWithGrade],
)
def get_submissions(
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    assignment = crud.get_assignment(db, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _check_assignment_org(db, assignment, current_user)
    subs = crud.get_submissions_for_assignment(db, assignment_id)

    # Enrich with student ФИО
    from models import User
    for sub in subs:
        user = db.query(User).filter(User.id == sub.student_id).first()
        if user:
            sub.student_name = user.full_name or user.email
    return subs




@router.get("/submissions/{submission_id}", response_model=schemas.SubmissionWithGrade)
def get_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    obj = crud.get_submission(db, submission_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Submission not found")
    _check_submission_org(db, obj, current_user)
    if current_user.role == "student" and obj.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Enrich with student ФИО для учителя
    if current_user.role in ("teacher", "admin"):
        from models import User
        user = db.query(User).filter(User.id == obj.student_id).first()
        if user:
            obj.student_name = user.full_name or user.email
    return obj


@router.delete(
    "/submissions/{submission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    obj = crud.get_submission(db, submission_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Submission not found")
    _check_submission_org(db, obj, current_user)

    if current_user.role == "student":
        if obj.student_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
        if obj.status == "graded":
            raise HTTPException(status_code=400, detail="Нельзя удалить уже проверенную сдачу")
    elif current_user.role not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")

    from models import Grade
    db.query(Grade).filter(Grade.submission_id == submission_id).delete()
    db.delete(obj)
    db.commit()


@router.post(
    "/submissions/{submission_id}/grade",
    response_model=schemas.GradeResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_grade(
    submission_id: int,
    body: schemas.GradeCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    sub = crud.get_submission(db, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    _check_submission_org(db, sub, current_user)

    crud.set_submission_status(db, submission_id, "graded")
    return crud.create_or_update_grade(
        db=db,
        submission_id=submission_id,
        score=body.score,
        feedback=body.feedback,
        criteria_scores=body.criteria_scores,
        graded_by=body.graded_by,
    )


@router.get("/submissions/{submission_id}/grade", response_model=schemas.GradeResponse)
def get_grade(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    grade = crud.get_grade_by_submission(db, submission_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Grade not found yet")

    sub = crud.get_submission(db, submission_id)
    if sub:
        _check_submission_org(db, sub, current_user)
    if current_user.role == "student" and sub.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return grade


@router.patch("/submissions/{submission_id}/status")
def update_status(
    submission_id: int,
    new_status: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    allowed = {"submitted", "grading", "graded", "late"}
    if new_status not in allowed:
        raise HTTPException(status_code=422, detail=f"Status must be one of {allowed}")
    sub = crud.get_submission(db, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    _check_submission_org(db, sub, current_user)
    obj = crud.set_submission_status(db, submission_id, new_status)
    return {"id": obj.id, "status": obj.status}





@router.post(
    "/submissions/{submission_id}/ai-grade",
    response_model=schemas.GradeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ai_grade_submission(
    submission_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    sub = crud.get_submission(db, submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    _check_submission_org(db, sub, current_user)

    _check_rate_limit(current_user.id)

    assignment = crud.get_assignment(db, sub.assignment_id)
    criteria = _json.loads(assignment.criteria) if assignment.criteria else []

    if not criteria:
        raise HTTPException(
            status_code=400,
            detail="Нет критериев оценивания. Добавьте критерии в задание.",
        )

    crud.set_submission_status(db, submission_id, "grading")


    full_text = sub.text_content or ""

    all_urls: list = []
    if sub.file_urls:
        try:
            all_urls = _json.loads(sub.file_urls)
        except Exception:
            pass
    if not all_urls and sub.file_url:
        all_urls = [sub.file_url]

    from services.ai_grader import _fetch_file_text
    for i, url in enumerate(all_urls):
        file_text = await _fetch_file_text(url)
        if file_text.strip():
            label = f"ФАЙЛ {i+1}" if len(all_urls) > 1 else "СОДЕРЖИМОЕ ФАЙЛА"
            full_text = (
                (full_text + f"\n\n{label}:\n" + file_text).strip()
                if full_text
                else f"{label}:\n{file_text}"
            )

    if not full_text:
        full_text = f"[Студент сдал файл(ы), но прочитать не удалось: {', '.join(all_urls)}]"


    reference_urls: list = []

    if sub.variant_number:
        variant = crud_classes.get_variant_by_number(db, sub.assignment_id, sub.variant_number)
        if variant:
            try:
                import json as _json2
                var_urls = _json2.loads(variant.reference_solution_url) if variant.reference_solution_url.startswith('[') else None
                if isinstance(var_urls, list):
                    reference_urls.extend(var_urls)
                else:
                    reference_urls.append(variant.reference_solution_url)
            except Exception:
                reference_urls.append(variant.reference_solution_url)
        else:
            if assignment.reference_solution_url:
                try:
                    import json as _json2
                    urls = _json2.loads(assignment.reference_solution_url) if assignment.reference_solution_url.startswith('[') else None
                    if isinstance(urls, list):
                        reference_urls.extend(urls)
                    else:
                        reference_urls.append(assignment.reference_solution_url)
                except Exception:
                    reference_urls.append(assignment.reference_solution_url)
    else:
        if assignment.reference_solution_url:
            try:
                import json as _json2
                urls = _json2.loads(assignment.reference_solution_url) if assignment.reference_solution_url.startswith('[') else None
                if isinstance(urls, list):
                    reference_urls.extend(urls)
                else:
                    reference_urls.append(assignment.reference_solution_url)
            except Exception:
                reference_urls.append(assignment.reference_solution_url)


    # Собираем контекст лекций класса
    lecture_context = ""
    try:
        from models import Posts
        posts = db.query(Posts).filter(Posts.user_id != None).all()
        parts = []
        for p in posts:
            try:
                b = _json.loads(p.body)
                ptype = b.get("type", "")
                if ptype not in ("lecture", "material"):
                    continue
                # Проверяем что пост относится к нужному классу
                class_id_in_body = b.get("class_id")
                if class_id_in_body and int(class_id_in_body) != assignment.class_id:
                    continue
                content = (b.get("content") or b.get("description") or "")[:2000]
                block = f"### {p.title}\n{content}"
                parts.append(block)
            except Exception:
                continue
        lecture_context = "\n\n".join(parts[:5])
    except Exception:
        pass

    try:
        result = await _ai_grade(
            text=full_text,
            file_url=None,
            criteria=criteria,
            max_score=assignment.max_score,
            reference_solution_url=None,
            reference_solution_urls=reference_urls if reference_urls else None,
            lecture_context=lecture_context if lecture_context else None,
        )
    except RuntimeError as e:
        crud.set_submission_status(db, submission_id, "submitted")
        raise HTTPException(status_code=502, detail=str(e))


    try:
        usage = result.pop("_usage", {})
        from models import AiUsageLog
        log = AiUsageLog(
            user_id=current_user.id,
            class_id=assignment.class_id,
            endpoint="ai-grade",
            org_type=current_user.org_type,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )
        db.add(log)
        db.commit()
    except Exception:
        pass

    crud.set_submission_status(db, submission_id, "graded")
    return crud.create_or_update_grade(
        db=db,
        submission_id=submission_id,
        score=result["score"],
        feedback=result.get("feedback"),
        criteria_scores=result.get("criteria_scores"),
        graded_by="ai",
    )