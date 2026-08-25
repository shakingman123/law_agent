"""日程提醒 Agent — LangGraph 状态图。

依据 docs/project-framework.md §5.3：
    新案件建档/更新 → 抽取时间节点(答辩期/管辖权异议/举证期/上诉期)
    → 依据文书类型计算截止日 → 生成 schedules(提前5天/提前1天)

骨架实现：时间节点抽取用 LLM，截止日计算与 schedule 入库待接入。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.llm.gateway import gateway
from app.models.user import User


class ReminderState(TypedDict, total=False):
    case_text: str                # 案件/文书文本
    case_id: int
    time_nodes: list[dict]        # 抽取出的时间节点
    deadlines: list[dict]         # 计算后的截止日
    schedules: list[dict]         # 生成的日程项


def build_reminder_graph(user: User, db: Session):
    llm = gateway.get_chat_model(user, db, temperature=0.1)

    async def extract_node(state: ReminderState) -> dict:
        """抽取时间节点：答辩期(15日)/管辖权异议(15日)/举证期/上诉期(15日)。"""
        resp = await llm.ainvoke([
            SystemMessage(
                content=(
                    "从法律文书中抽取时间节点，返回 JSON 数组，"
                    "每项含 {type, base_date(YYYY-MM-DD), days}。"
                    "常见：答辩期15日、上诉期15日、举证期限。只返回 JSON。"
                )
            ),
            HumanMessage(content=state["case_text"]),
        ])
        try:
            nodes = json.loads(resp.content.strip().removeprefix("```json").removesuffix("```").strip())
        except Exception:  # noqa: BLE001
            nodes = []
        return {"time_nodes": nodes}

    def calc_node(state: ReminderState) -> dict:
        """依据文书类型计算截止日。"""
        deadlines = []
        for n in state.get("time_nodes", []):
            try:
                base = datetime.strptime(n["base_date"], "%Y-%m-%d")
                deadline = base + timedelta(days=n["days"])
                deadlines.append({
                    "type": n["type"],
                    "deadline": deadline.strftime("%Y-%m-%d"),
                    "case_id": state.get("case_id"),
                })
            except Exception:  # noqa: BLE001
                continue
        return {"deadlines": deadlines}

    def schedule_node(state: ReminderState) -> dict:
        """生成日程：紧急(上诉期)提前1天，一般提前5天。"""
        schedules = []
        for d in state.get("deadlines", []):
            deadline = datetime.strptime(d["deadline"], "%Y-%m-%d")
            is_urgent = "上诉" in d["type"]
            ahead = 1 if is_urgent else 5
            schedules.append({
                "title": f"{d['type']}截止提醒",
                "start_at": (deadline - timedelta(days=ahead)).strftime("%Y-%m-%d"),
                "level": "urgent" if is_urgent else "normal",
                "case_id": d.get("case_id"),
            })
        return {"schedules": schedules}

    builder = StateGraph(ReminderState)
    builder.add_node("extract", extract_node)
    builder.add_node("calc", calc_node)
    builder.add_node("schedule", schedule_node)
    builder.set_entry_point("extract")
    builder.add_edge("extract", "calc")
    builder.add_edge("calc", "schedule")
    builder.add_edge("schedule", END)

    return builder.compile()
