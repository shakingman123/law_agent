"""文书撰写 Agent — 工具节点。

依据 docs/implementation-guide.md §3.2：
- get_template: 按模板 id 从 DB 取模板（公共/私有），无 id 时按文书类型取公共模板
- render_template: 用已收集信息填充占位符
- generate_files: 生成真实 .docx + .pdf，返回下载 URL
"""
import os
import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.template import DocumentTemplate


def get_template_by_id(db: Session, template_id: Optional[int]) -> Optional[DocumentTemplate]:
    """按 id 取模板。"""
    if not template_id:
        return None
    return db.get(DocumentTemplate, template_id)


def get_template_by_type(db: Session, doc_type: str) -> Optional[DocumentTemplate]:
    """按文书类型取首个公共模板。"""
    return (
        db.query(DocumentTemplate)
        .filter_by(doc_type=doc_type, scope="public")
        .order_by(DocumentTemplate.id)
        .first()
    )


def template_to_dict(tpl: Optional[DocumentTemplate]) -> Optional[dict]:
    """把 ORM 模板转成 {content, placeholders}。"""
    if not tpl:
        return None
    return {"content": tpl.content, "placeholders": list(tpl.placeholders or [])}


def render_template(template_content: str, collected: dict) -> str:
    """用已收集信息填充模板占位符。"""
    rendered = template_content
    for key, val in collected.items():
        rendered = rendered.replace("{{" + key + "}}", str(val))
    rendered = rendered.replace("{{date}}", datetime.utcnow().strftime("%Y年%m月%d日"))
    # 剩余未填充的占位符标记为待补充，避免后续由 LLM 编造缺失的事实、理由等真实信息。
    rendered = re.sub(r"\{\{.*?\}\}", "（此处待补充）", rendered)
    return rendered


def _ensure_upload_dir() -> None:
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


def generate_docx(doc_type: str, content: str, case_id: Optional[int] = None) -> str:
    """生成真实 .docx 文件，返回下载 URL。"""
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    _ensure_upload_dir()
    doc = Document()
    # 默认正文字体
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(12)

    lines = content.split("\n")
    for i, line in enumerate(lines):
        p = doc.add_paragraph(line)
        # 标题（第一行）居中加粗
        if i == 0 and line.strip():
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in p.runs:
                run.bold = True
                run.font.size = Pt(16)

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"{doc_type}_{case_id or 'draft'}_{stamp}.docx"
    fpath = os.path.join(settings.UPLOAD_DIR, fname)
    doc.save(fpath)
    return f"/api/files/{fname}"


def generate_pdf(doc_type: str, content: str, case_id: Optional[int] = None) -> str:
    """生成 .pdf 文件，返回下载 URL。

    使用 reportlab，注册系统中文字体（宋体）以支持中文。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    _ensure_upload_dir()

    # 注册中文字体：优先微软雅黑，回退宋体
    font_name = "SimSun"
    candidates = [
        ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
        ("MSYH", r"C:\Windows\Fonts\msyh.ttc"),
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
    ]
    for name, path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                font_name = name
                break
            except Exception:  # noqa: BLE001
                continue

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    fname = f"{doc_type}_{case_id or 'draft'}_{stamp}.pdf"
    fpath = os.path.join(settings.UPLOAD_DIR, fname)

    doc = SimpleDocTemplate(
        fpath, pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm,
    )

    title_style = ParagraphStyle(
        "Title", fontName=font_name, fontSize=16, alignment=TA_CENTER,
        spaceAfter=18, leading=22,
    )
    body_style = ParagraphStyle(
        "Body", fontName=font_name, fontSize=12, alignment=TA_LEFT,
        leading=20, firstLineIndent=24,
    )
    sign_style = ParagraphStyle(
        "Sign", fontName=font_name, fontSize=12, alignment=TA_LEFT,
        leading=20,
    )

    story = []
    lines = content.split("\n")
    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            story.append(Spacer(1, 6))
            continue
        # 转义 XML 特殊字符
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if i == 0:
            story.append(Paragraph(safe, title_style))
        else:
            # 落款/此致行不缩进
            no_indent = text.startswith("此致") or text.startswith("日期") or "：\n" not in line and (
                "上诉人：" in text or "答辩人：" in text or "起诉人：" in text
                or "代理人" in text or "委托人：" in text
            )
            story.append(Paragraph(safe, sign_style if no_indent else body_style))

    doc.build(story)
    return f"/api/files/{fname}"
