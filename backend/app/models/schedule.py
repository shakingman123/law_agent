"""日程 ORM。

依据 docs/figma-design-spec.md §4：日程列表页（日/周/月切换 + 待办提醒）。
schedules 记录用户的期限/会议等日程，按 user_id 隔离。
"""
from datetime import datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String

from app.core.database import Base


class Schedule(Base):
    """用户日程（期限/会议等）。level: urgent 紧急 / normal 一般 / meeting 会议。

    remind_advance 为提前提醒天数（相对 date）：0=当天提醒，n=提前 n 天，None=不提醒。
    与 level 解耦：level 决定颜色分类，remind_advance 决定实际提醒时机。
    """

    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(128), nullable=False)
    date = Column(Date, nullable=False, index=True)
    level = Column(String(16), default="normal")  # urgent / normal / meeting
    remind_advance = Column(Integer, nullable=True)  # 0=当天, n=提前n天, None=不提醒
    case_name = Column(String(128), nullable=True)
    case_id = Column(Integer, ForeignKey("cases.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
