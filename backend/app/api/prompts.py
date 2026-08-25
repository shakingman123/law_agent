"""Prompt 模板库接口 + 默认数据播种。

集中管理 Agent 系统提示词，取代硬编码。
默认 prompts 在应用启动时播种（幂等）。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db
from app.models.prompt import PromptTemplate
from app.schemas.prompt import PromptCreate, PromptOut, PromptUpdate

router = APIRouter(prefix="/api/prompts", tags=["prompts"])


# 默认系统 prompts（与 drafting Agent 原硬编码一致 + 通用对话）
DEFAULT_PROMPTS = [
    {
        "name": "意图识别",
        "category": "drafting",
        "key": "intent",
        "content": (
            "你是法律文书助手。根据用户输入，识别要写的文书类型，"
            "只能从以下选项中选：起诉状/答辩状/反诉状/上诉状/代理词/"
            "再审申请书/申请书/异议书/授权委托书/身份证明书。"
            "只返回类型名，不要其他内容。若无法判断返回 unknown。"
        ),
        "variables": [],
    },
    {
        "name": "字段提取",
        "category": "drafting",
        "key": "collect",
        "content": (
            "用户要写一份《{{doc_type}}》，模板需要的字段有：{{missing}}。\n"
            "用户输入：{{user_input}}\n"
            "案件名称：{{case_name}}\n"
            "请从用户输入中尽量提取这些字段，以 JSON 返回，"
            "键为字段名，值为提取到的内容（提取不到的不要写）。只返回 JSON。"
        ),
        "variables": ["doc_type", "missing", "user_input", "case_name"],
    },
    {
        "name": "文书生成",
        "category": "drafting",
        "key": "draft",
        "content": (
            "你是资深律师。请仅对已提供的文书内容进行格式规范、"
            "语言润色与结构整理，使表达专业、通顺。"
            "严禁编造、补充或猜测任何缺失的事实、理由、当事人、日期等案件信息；"
            "文中标注“（此处待补充）”的内容保持原样，不得自行填写。"
            "直接返回完整文书内容，不要解释。"
        ),
        "variables": [],
    },
    {
        "name": "草稿微调",
        "category": "drafting",
        "key": "refine",
        "content": "根据用户反馈修改文书草稿，直接返回修改后的完整文书。",
        "variables": [],
    },
    {
        "name": "通用法律助手",
        "category": "chat",
        "key": "system",
        "content": (
            "你是一位专业的法律助手。请基于已知信息和知识库内容回答用户问题，"
            "回答需准确、专业。若知识库提供了相关资料，请优先参考。"
            "{{context}}"
        ),
        "variables": ["context"],
    },
]


def seed_default_prompts(db: Session) -> None:
    """幂等播种默认 prompts（应用启动时调用）。"""
    for item in DEFAULT_PROMPTS:
        existing = (
            db.query(PromptTemplate)
            .filter_by(category=item["category"], key=item["key"])
            .first()
        )
        if existing:
            continue
        db.add(
            PromptTemplate(
                name=item["name"],
                category=item["category"],
                key=item["key"],
                content=item["content"],
                variables=item["variables"],
                is_system=True,
            )
        )
    db.commit()


def get_prompt(db: Session, category: str, key: str) -> str | None:
    """供 Agent 调用：按 category+key 取 prompt 内容，找不到返回 None。"""
    p = db.query(PromptTemplate).filter_by(category=category, key=key).first()
    return p.content if p else None


@router.get("", response_model=list[PromptOut])
def list_prompts(
    category: str | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(PromptTemplate)
    if category:
        q = q.filter_by(category=category)
    return q.order_by(PromptTemplate.category, PromptTemplate.key).all()


@router.get("/{category}/{key}", response_model=PromptOut)
def get_prompt_by_key(
    category: str,
    key: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.query(PromptTemplate).filter_by(category=category, key=key).first()
    if not p:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    return p


@router.post("", response_model=PromptOut)
def create_prompt(
    payload: PromptCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = PromptTemplate(
        name=payload.name,
        category=payload.category,
        key=payload.key,
        content=payload.content,
        variables=payload.variables,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.put("/{prompt_id}", response_model=PromptOut)
def update_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    if payload.name is not None:
        p.name = payload.name
    if payload.content is not None:
        p.content = payload.content
    if payload.variables is not None:
        p.variables = payload.variables
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{prompt_id}")
def delete_prompt(
    prompt_id: int,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prompt 不存在")
    if p.is_system:
        raise HTTPException(status_code=400, detail="系统内置 prompt 不可删除")
    db.delete(p)
    db.commit()
    return {"ok": True}
