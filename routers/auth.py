from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from db import get_db
import schemas
from crud import users as crud_users
from security import hash_password, verify_password, create_access_token, create_refresh_token, decode_refresh_token
from jose import JWTError
from deps import get_current_user
from utils.groups import search_groups

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/groups/search")
def get_groups(q: str = ""):

    return search_groups(q)


@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud_users.get_user_by_email(db, user.email)
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")


    if user.group and user.group not in search_groups(""):
        raise HTTPException(status_code=400, detail="Такой группы не существует")

    hashed = hash_password(user.password)
    created = crud_users.create_user(
        db,
        user.email,
        hashed,
        user.role,
        full_name=user.full_name,
        group=user.group
    )
    return created


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = crud_users.get_user_by_email(db, form_data.username)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}


@router.post("/refresh", response_model=schemas.Token)
def refresh_token(body: schemas.RefreshRequest, db: Session = Depends(get_db)):
    try:
        payload = decode_refresh_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    from crud import users as crud_users
    user = crud_users.get_user_by_id(db, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(subject=str(user.id))
    new_refresh_token = create_refresh_token(subject=str(user.id))
    return {"access_token": access_token, "refresh_token": new_refresh_token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserResponse)
def me(current_user=Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserResponse)
def update_me(
    body: schemas.UpdateMe,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if body.full_name is not None:
        current_user.full_name = body.full_name.strip() or None

    if body.group is not None:

        if body.group not in search_groups(""):
            raise HTTPException(status_code=400, detail="Такой группы не существует")
        current_user.group = body.group

    db.commit()
    db.refresh(current_user)
    return current_user


def admin_required(current_user=Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admin allowed")
    return current_user