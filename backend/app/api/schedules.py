"""日程接口：列表 / 新建 / 删除。

依据 docs/figma-design-spec.md §4 日程列表页：
- GET    /api/schedules           列出当前用户的全部日程（按日期升序）
- POST   /api/schedules           新建日程（标题/日期/紧急程度/关联案件）
- DELETE /api/schedules/{id}      删除日程
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.schedule import Schedule
from app.models.user import User
from app.schemas.schedule import ScheduleCreate, ScheduleOut

router = APIRouter(prefix="/api/schedules", tags=["schedules"])


@router.get("", response_model=list[ScheduleOut])
def list_schedules(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出当前用户的全部日程，按日期升序。"""
    return (
        db.query(Schedule)
        .filter(Schedule.user_id == user.id)
        .order_by(Schedule.date.asc())
        .all()
    )


@router.post("", response_model=ScheduleOut)
def create_schedule(
    payload: ScheduleCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建日程。"""
    schedule = Schedule(
        user_id=user.id,
        title=payload.title.strip(),
        date=payload.date,
        level=payload.level,
        remind_advance=payload.remind_advance,
        case_name=payload.case_name,
        case_id=payload.case_id,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除日程（仅本人）。"""
    schedule = db.get(Schedule, schedule_id)
    if not schedule or schedule.user_id != user.id:
        raise HTTPException(status_code=404, detail="日程不存在")
    db.delete(schedule)
    db.commit()
    return {"ok": True}
