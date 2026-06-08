from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from deps import get_current_user
from models import Chat, chat_members, Message
from schemas import ChatCreate, ChatResponse
from models import User

router = APIRouter(prefix="/chats", tags=["Chats"])

@router.post("/", response_model=ChatResponse)
def create_chat(chat: ChatCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    db_chat = Chat(name=chat.name)
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    db.execute(chat_members.insert().values(chat_id=db_chat.id, user_id=current_user.id))
    db.commit()
    return db_chat

@router.get("/", response_model=list[ChatResponse])
def get_chats(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    chats = (
        db.query(Chat)
        .join(chat_members)
        .filter(chat_members.c.user_id == current_user.id)
        .all()
    )
    return chats

@router.get("/{chat_id}/users")
def get_chat_users(chat_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    users = (
        db.query(User)
        .join(chat_members)
        .filter(chat_members.c.chat_id == chat_id)
        .all()
    )
    return [{"id": u.id, "email": u.email, "role": u.role, "is_active": u.is_active} for u in users]

@router.post("/{chat_id}/users/{user_id}")
def add_user_to_chat(chat_id: int, user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.org_type != current_user.org_type:
        raise HTTPException(status_code=403, detail="Нельзя добавить пользователя из другой организации")
    existing = db.execute(
        chat_members.select().where(
            chat_members.c.chat_id == chat_id,
            chat_members.c.user_id == user_id
        )
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="User already in chat")
    db.execute(chat_members.insert().values(chat_id=chat_id, user_id=user_id))
    db.commit()
    return {"message": "User added"}

@router.delete("/{chat_id}")
def delete_chat(chat_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    # Check the user is a member of this chat
    member = db.execute(
        chat_members.select().where(
            chat_members.c.chat_id == chat_id,
            chat_members.c.user_id == current_user.id
        )
    ).fetchone()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this chat")
    # Delete messages, members, then the chat
    db.query(Message).filter(Message.chat_id == chat_id).delete()
    db.execute(chat_members.delete().where(chat_members.c.chat_id == chat_id))
    db.delete(chat)
    db.commit()
    return {"message": "Chat deleted"}

@router.delete("/{chat_id}/users/{user_id}")
def remove_user_from_chat(chat_id: int, user_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    db.execute(
        chat_members.delete().where(
            chat_members.c.chat_id == chat_id,
            chat_members.c.user_id == user_id
        )
    )
    db.commit()
    return {"message": "User removed"}
