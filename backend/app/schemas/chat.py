"""对话相关 Pydantic 模型。"""
from typing import Optional

from pydantic import BaseModel


class DraftRequest(BaseModel):
    """启动文书撰写流程。"""

    user_input: str
    case_id: Optional[int] = None
    case_name: Optional[str] = None
    template_id: Optional[int] = None  # 指定模板（公共/私有）


class ResumeRequest(BaseModel):
    """用户确认/微调后恢复执行。"""

    confirmed: bool
    feedback: Optional[str] = None


class DraftResponse(BaseModel):
    """文书撰写流程的响应。"""

    thread_id: str
    doc_type: str = ""
    draft: str = ""
    missing_fields: list[str] = []
    awaiting_review: bool = False  # 是否停在预览确认节点
    done: bool = False             # 是否已定稿
    file_url: str = ""            # 定稿 docx 下载 URL
    pdf_url: str = ""             # 定稿 pdf 下载 URL
    error: str = ""


class ChatMessageRequest(BaseModel):
    """通用对话消息（接入 LLM + RAG）。"""

    message: str
    conversation_id: Optional[int] = None  # 指定会话；不传则用最近会话
    case_id: Optional[int] = None
    case_name: Optional[str] = None
    attachments: list[str] = []    # 已上传文件 URL 列表
    use_rag: bool = True           # 是否检索知识库


class ChatMessageResponse(BaseModel):
    """通用对话响应。"""

    reply: str
    rag_sources: list[dict] = []   # 命中的知识库引用 [{index, title, source, content}]
    conversation_id: int = 0       # 本次消息所属会话
    message_id: int = 0           # agent 回复消息 id
    error: str = ""
