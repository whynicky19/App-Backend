from typing import List

from fastapi import APIRouter, status, Depends, HTTPException
from sqlalchemy.orm import Session

import schemas
from db import get_db
from crud import posts as crud_posts
from deps import get_current_user
from models import post_enrollments

router = APIRouter(prefix="/posts", tags=["posts"])

@router.post("/create", response_model=schemas.PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(post: schemas.PostCreate, db: Session = Depends(get_db),
                current_user=Depends(get_current_user)
                ):
    created = crud_posts.create_new_post(
        db=db,
        title=post.title,
        body=post.body,
        user_id=current_user.id,
    )
    return created

@router.get("/", response_model=List[schemas.PostResponse])
def get_posts_for_user(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return crud_posts.get_all_posts(db=db)

@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    post = crud_posts.get_post_by_id(db=db, post_id=post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")

    crud_posts.delete_post(db=db, post_id=post_id)
    return None

@router.post("/{post_id}/join", status_code=200)
def join_post_class(post_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    exists = db.execute(
        post_enrollments.select().where(
            post_enrollments.c.post_id == post_id,
            post_enrollments.c.user_id == current_user.id,
        )
    ).first()
    if not exists:
        db.execute(post_enrollments.insert().values(post_id=post_id, user_id=current_user.id))
        db.commit()
    return {"ok": True}

@router.delete("/{post_id}/leave", status_code=200)
def leave_post_class(post_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    db.execute(
        post_enrollments.delete().where(
            post_enrollments.c.post_id == post_id,
            post_enrollments.c.user_id == current_user.id,
        )
    )
    db.commit()
    return {"ok": True}

@router.put("/{post_id}", response_model=schemas.PostResponse)
def update_post(
    post_id: int,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    existing = crud_posts.get_post_by_id(db=db, post_id=post_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Post not found")
    if existing.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    updated = crud_posts.update_post(db=db, post_id=post_id, title=post.title, body=post.body)
    return updated
