from typing import Optional, List
from sqlalchemy.orm import Session
from models import Class, User, AssignmentVariant, Assignment, Submission, Grade, class_members
from sqlalchemy import func

def create_class(db: Session, name: str, description: Optional[str], created_by: int,
                 group: Optional[str] = None, org_type: str = "university") -> Class:
    obj = Class(name=name, description=description, created_by=created_by, group=group, org_type=org_type)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def get_class(db: Session, class_id: int) -> Optional[Class]:
    return db.query(Class).filter(Class.id == class_id).first()

def get_all_classes(db: Session, teacher_id: Optional[int] = None,
                    org_type: Optional[str] = None) -> List[Class]:
    q = db.query(Class)
    if org_type is not None:
        q = q.filter(Class.org_type == org_type)
    if teacher_id is not None:
        q = q.filter(Class.created_by == teacher_id)
    return q.order_by(Class.created_at.desc()).all()

def update_class(db: Session, class_id: int, data: dict) -> Optional[Class]:
    obj = get_class(db, class_id)
    if not obj:
        return None
    for k, v in data.items():
        if v is not None:
            setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj

def delete_class(db: Session, class_id: int) -> bool:
    obj = get_class(db, class_id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

def add_member(db: Session, class_id: int, user_id: int) -> bool:
    obj = get_class(db, class_id)
    if not obj:
        return False
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False
    if user not in obj.members:
        obj.members.append(user)
        db.commit()
    return True

def remove_member(db: Session, class_id: int, user_id: int) -> bool:
    obj = get_class(db, class_id)
    if not obj:
        return False
    user = db.query(User).filter(User.id == user_id).first()
    if user and user in obj.members:
        obj.members.remove(user)
        db.commit()
    return True

def get_members(db: Session, class_id: int) -> List[User]:
    obj = get_class(db, class_id)
    if not obj:
        return []
    return obj.members

def add_variant(
    db: Session,
    assignment_id: int,
    variant_number: int,
    reference_solution_url: str,
    title: Optional[str] = None,
) -> AssignmentVariant:
    existing = db.query(AssignmentVariant).filter(
        AssignmentVariant.assignment_id == assignment_id,
        AssignmentVariant.variant_number == variant_number,
    ).first()
    if existing:
        db.delete(existing)
        db.flush()

    obj = AssignmentVariant(
        assignment_id=assignment_id,
        variant_number=variant_number,
        title=title or f"Вариант {variant_number}",
        reference_solution_url=reference_solution_url,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def get_variants(db: Session, assignment_id: int) -> List[AssignmentVariant]:
    return (
        db.query(AssignmentVariant)
        .filter(AssignmentVariant.assignment_id == assignment_id)
        .order_by(AssignmentVariant.variant_number)
        .all()
    )

def delete_variant(db: Session, variant_id: int) -> bool:
    obj = db.query(AssignmentVariant).filter(AssignmentVariant.id == variant_id).first()
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

def get_variant_by_number(db: Session, assignment_id: int, variant_number: int) -> Optional[AssignmentVariant]:
    return db.query(AssignmentVariant).filter(
        AssignmentVariant.assignment_id == assignment_id,
        AssignmentVariant.variant_number == variant_number,
    ).first()

def get_student_rating(db: Session, class_id: Optional[int] = None,
                       org_type: Optional[str] = None) -> list:
    q = (
        db.query(
            User.id.label("student_id"),
            User.email.label("email"),
            func.sum(Grade.score).label("total_score"),
            func.count(Grade.id).label("graded_count"),
            func.avg(Grade.score).label("avg_score"),
        )
        .join(Submission, Submission.student_id == User.id)
        .join(Grade, Grade.submission_id == Submission.id)
        .filter(User.role == "student")
    )

    if org_type is not None:
        q = q.filter(User.org_type == org_type)

    if class_id is not None:
        q = q.filter(
            Submission.assignment_id.in_(
                db.query(Assignment.id).filter(Assignment.class_id == class_id)
            )
        )

    rows = q.group_by(User.id, User.email).order_by(func.sum(Grade.score).desc()).all()

    return [
        {
            "student_id": r.student_id,
            "email": r.email,
            "total_score": int(r.total_score or 0),
            "graded_count": int(r.graded_count or 0),
            "avg_score": round(float(r.avg_score or 0), 1),
        }
        for r in rows
    ]
