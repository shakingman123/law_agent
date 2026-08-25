"""日程相关 Pydantic 模型。"""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

Level = Literal["urgent", "normal", "meeting"]


class ScheduleCreate(BaseModel):
    """新建日程。date 为截止日期（YYYY-MM-DD）。

    remind_advance 为提前提醒天数：0=当天，n=提前 n 天，None=不提醒。
    """

    title: str
    date: date
    level: Level = "normal"
    remind_advance: Optional[int] = None
    case_name: Optional[str] = None
    case_id: Optional[int] = None


class ScheduleOut(BaseModel):
    id: int
    user_id: int
    title: str
    date: date
    level: Level
    remind_advance: Optional[int] = None
    case_name: Optional[str] = None
    case_id: Optional[int] = None
    created_at: datetime
