from sqlalchemy.orm import Session
from models import Posts, User

def create_new_post(db: Session, title: str, body: str, user_id: int) -> Posts:
    post = Posts(title=title, body=body, user_id=user_id)
    db.add(post)
    db.commit()
    db.refresh(post)
    return post

def get_post_by_id(db: Session, post_id: int):
    return db.query(Posts).filter(Posts.id == post_id).first()

def get_posts_for_user(db: Session, user_id: int):
    return db.query(Posts).filter(Posts.user_id == user_id).order_by(Posts.id.desc()).all()

def get_all_posts(db: Session, org_type: str = None):
    q = db.query(Posts).join(User, User.id == Posts.user_id)
    if org_type:
        q = q.filter(User.org_type == org_type)
    return q.order_by(Posts.id.desc()).all()

def delete_post(db: Session, post_id: int) -> bool:
    deleted = db.query(Posts).filter(Posts.id == post_id).delete()
    db.commit()
    return bool(deleted)

def update_post(db: Session, post_id: int, title: str, body: str) -> Posts:
    post = get_post_by_id(db, post_id)
    if not post:
        return None
    post.title = title
    post.body = body
    db.commit()
    db.refresh(post)
    return post
