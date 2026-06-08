from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models import User
from schemas import UserResponse
from deps import get_current_user
from db import get_db

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/", response_model=list[UserResponse])
def get_all_users(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return db.query(User).filter(User.is_active == True, User.org_type == current_user.org_type).all()
