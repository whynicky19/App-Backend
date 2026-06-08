from sqlalchemy.orm import Session
from sqlalchemy import select
import models


def get_user_by_email(db: Session, email: str, org_type: str = "university"):
    smth = select(models.User).where(
        models.User.email == email,
        models.User.org_type == org_type,
    )
    result = db.execute(smth)
    return result.scalar_one_or_none()


def get_user_by_id(db: Session, user_id: int):
    smth = select(models.User).where(models.User.id == user_id)
    result = db.execute(smth)
    return result.scalar_one_or_none()


def create_user(db: Session, email: str, hashed_password: str, role: str = "employee",
                full_name: str = None, group: str = None, org_type: str = "university"):
    user = models.User(
        email=email,
        hashed_password=hashed_password,
        role=role,
        full_name=full_name,
        group=group,
        org_type=org_type,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_by_admin(db: Session, user_id: int, update_data: dict):
    user = db.query(models.User).filter(models.User.id == user_id).first()

    if not user:
        return None

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    return user