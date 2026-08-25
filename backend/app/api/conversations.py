"""会话接口：会话列表 / 新建 / 详情(含历史消息) / 删除。

对话历史持久化依据：切换页面/刷新不丢；前端进入工作台时拉取最近会话。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    ConversationWithMessages,
    MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _ensure_default_conversation(user: User, db: Session) -> Conversation:
    """每个用户至少有一个默认会话；没有则创建。"""
    conv = (
        db.query(Conversation)
        .filter_by(user_id=user.id)
        .order_by(Conversation.last_message_at.desc())
        .first()
    )
    if conv:
        return conv
    conv = Conversation(user_id=user.id, title="新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("", response_model=list[ConversationOut])
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户的会话列表（按最近消息时间倒序）。"""
    return (
        db.query(Conversation)
        .filter_by(user_id=user.id)
        .order_by(Conversation.last_message_at.desc())
        .all()
    )


@router.post("", response_model=ConversationOut)
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = Conversation(
        user_id=user.id,
        title=payload.title,
        case_id=payload.case_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """会话详情 + 全部历史消息。"""
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return ConversationWithMessages(
        id=conv.id,
        title=conv.title,
        user_id=conv.user_id,
        case_id=conv.case_id,
        last_message_at=conv.last_message_at,
        created_at=conv.created_at,
        messages=msgs,
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """会话历史消息（分页可选，当前全量返回）。"""
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return (
        db.query(Message)
        .filter_by(conversation_id=conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    db.query(Message).filter_by(conversation_id=conversation_id).delete()
    db.delete(conv)
    db.commit()
    return {"ok": True}
