"""本地脱敏工具：正则规则 + spaCy NER 双重检测。

策略：规则引擎优先（结构化信息），NER 补充（非结构化实体）。
- 正则：身份证、手机号、固定电话、银行卡号、案号、地址
- NER：人名（PERSON）、机构名（ORG）、地名（GPE）
- 角色映射：上诉人/原告→甲，被上诉人/被告→乙，第三人→丙

依据 docs/project-framework.md §5.4：仅公司库入 legal_references 时脱敏。
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Optional

logger = logging.getLogger("app.agents.archive")

# ---------------------------------------------------------------------------
# 正则规则：结构化信息
# 注：中文文本里 \b 对中文字符不生效，用前后非数字断言 (?<!\d)...(?!\d) 替代。
# ---------------------------------------------------------------------------
# 身份证：18位（末位X/x或数字）或 15位纯数字
RE_ID_CARD = re.compile(r"(?<!\d)(?:[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]|[1-9]\d{5}\d{9})(?!\d)")
# 手机号：11位，1开头，第二位3-9
RE_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 固定电话：区号-号码（如 010-12345678、0755-1234567）
RE_LANDLINE = re.compile(r"(?<!\d)0\d{2,3}[-\s]?\d{7,8}(?!\d)")
# 银行卡号：16-19位连续数字（前后非数字，避免误伤短数字）
RE_BANK_CARD = re.compile(r"(?<!\d)\d{16,19}(?!\d)")
# 案号：(2024)京01民初123号、(2023)沪刑终456号 等（支持中英文括号）
RE_CASE_NO = re.compile(r"[\uff08(]\d{4}[\uff09)][\u4e00-\u9fa5]{1,6}[\u4e00-\u9fa5\d]{0,4}\d{1,5}\u53f7")
# 邮箱
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# 地址：匹配 省/市/区 县 + 详细地址。支持直辖市（北京市朝阳区）和普通省市（广东省深圳市南山区）
RE_ADDRESS = re.compile(
    r"[\u4e00-\u9fa5]{2,8}(?:\u7701|\u81ea\u6cbb\u533a|\u76f4\u8f96\u5e02|\u5e02)"
    r"[\u4e00-\u9fa5]{0,8}(?:\u5e02|\u76df|\u81ea\u6cbb\u5dde)?"
    r"[\u4e00-\u9fa5]{2,10}(?:\u533a|\u53bf|\u5e02)"
    r"[\u4e00-\u9fa5\d\u53f7\u5e84\u5f04\u53f7\u5355\u5143\u697c\u5c42\u680b\u5ba4\u53f7]{0,30}"
)

# 角色映射：把"上诉人/原告"后的姓名替换为"甲/乙/丙"
# 匹配 "上诉人张三" / "原告：张三" / "原告姓名张三" 等
#
# 修复要点（避免子串误匹配 & 贪婪吃字）：
# 1. 被告方放最前——"被上诉人"比"上诉人"长，长前缀优先匹配，避免原告正则吃掉"上诉人"子串
# 2. 原告方加 (?<!\u88ab) 负向回溯，双重保险排除"被上诉人"中的"上诉人"
# 3. 姓名用非贪婪 {2,4}?，后瞻断言确保姓名后是分隔符（标点/与/之/等/案/诉/因/起/参/合/一/上/下/于/故/经/和/被/空白/结尾），
#    防止贪婪 {2,4} 吃掉"与被""合同"等非姓名中文
# 4. group2 捕获"姓名字样 + 冒号 + 空格"并在替换时保留，避免吃掉"："或"姓名"
#    —— 如 "原告：王五" → "原告：甲"，"申请人姓名钱七" → "申请人姓名甲"
_NAME_TAIL = (r"(?=[\uff0c\uff0e\u3001\u3002\uff1b\uff1a\u3000\s"
              r"\u4e0e\u4e4b\u548c\u7b49\u56e0\u4e8e\u6545\u7ecf"
              r"\u6848\u8bc9\u53c2\u8d77\u5408\u4e00\u4e0a\u4e0b\u88ab]|$)")
ROLE_MAP = [
    # 被告方（优先匹配）
    (re.compile(r"(\u88ab\u4e0a\u8bc9\u4eba|\u88ab\u544a|\u88ab\u7533\u8bf7\u4eba|\u88ab\u8d77\u8bc9\u4eba)"
                r"((?:\u59d3\u540d)?[:\uff1a\u3000\s]*)([\u4e00-\u9fa5]{2,4}?)" + _NAME_TAIL), "\u4e59"),
    # 原告方（(?<!被) 排除"被上诉人"中的"上诉人"）
    (re.compile(r"(?<!\u88ab)(\u4e0a\u8bc9\u4eba|\u539f\u544a|\u7533\u8bf7\u4eba|\u8d77\u8bc9\u4eba)"
                r"((?:\u59d3\u540d)?[:\uff1a\u3000\s]*)([\u4e00-\u9fa5]{2,4}?)" + _NAME_TAIL), "\u7532"),
    # 第三人
    (re.compile(r"(\u7b2c\u4e09\u4eba)((?:\u59d3\u540d)?[:\uff1a\u3000\s]*)([\u4e00-\u9fa5]{2,4}?)" + _NAME_TAIL), "\u4e19"),
]


# ---------------------------------------------------------------------------
# spaCy NER 模型（惰性加载，进程内缓存）
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_nlp():
    """加载中文 NER 模型。失败时返回 None，回退到纯正则。"""
    try:
        import spacy
        nlp = spacy.load("zh_core_web_sm")
        logger.info("[desensitize] spaCy NER 模型加载成功: zh_core_web_sm")
        return nlp
    except Exception as e:  # noqa: BLE001
        logger.warning("[desensitize] spaCy 模型加载失败，回退纯正则: %s", e)
        return None


# ---------------------------------------------------------------------------
# 文件内容提取
# ---------------------------------------------------------------------------
def extract_text(file_path: str, file_type: str) -> str:
    """从 docx/pdf 提取文本。"""
    if file_type == "docx":
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs)
    if file_type == "pdf":
        import fitz  # PyMuPDF
        text_parts = []
        with fitz.open(file_path) as doc:
            for page in doc:
                text_parts.append(page.get_text())
        return "\n".join(text_parts)
    return ""


# ---------------------------------------------------------------------------
# 脱敏主流程
# ---------------------------------------------------------------------------
def desensitize_text(text: str) -> str:
    """对文本做脱敏：角色替换 → 正则结构化 → NER 补充。

    顺序说明：角色替换须先于 NER，否则 NER 把姓名替换成 [人名] 后，
    角色正则就匹配不到中文姓名了。
    """
    if not text:
        return text

    # ① 角色替换：上诉人张三 → 上诉人甲
    #   group1=角色词，group2=分隔符（姓名字样/冒号/空格，需保留），group3=姓名
    for pattern, replacement in ROLE_MAP:
        text = pattern.sub(lambda m: m.group(1) + m.group(2) + replacement, text)

    # ② 正则：结构化信息
    text = RE_ID_CARD.sub("[身份证号]", text)
    text = RE_MOBILE.sub("[手机号]", text)
    text = RE_LANDLINE.sub("[固定电话]", text)
    text = RE_BANK_CARD.sub("[银行卡号]", text)
    text = RE_CASE_NO.sub("[案号]", text)
    text = RE_EMAIL.sub("[邮箱]", text)
    text = RE_ADDRESS.sub("[地址]", text)

    # ③ spaCy NER：人名、机构名、地名（补充正则未覆盖的非结构化实体）
    nlp = _load_nlp()
    if nlp is not None:
        try:
            doc = nlp(text)
            # 从后往前替换，避免偏移错乱
            ents = sorted(doc.ents, key=lambda e: e.start_char, reverse=True)
            for ent in ents:
                if ent.label_ in ("PERSON",):
                    text = text[: ent.start_char] + "[人名]" + text[ent.end_char:]
                elif ent.label_ in ("ORG",):
                    text = text[: ent.start_char] + "[机构]" + text[ent.end_char:]
                elif ent.label_ in ("GPE", "LOC"):
                    text = text[: ent.start_char] + "[地名]" + text[ent.end_char:]
        except Exception as e:  # noqa: BLE001
            logger.warning("[desensitize] NER 处理失败，跳过实体替换: %s", e)

    return text


def desensitize_file(file_path: str) -> Optional[str]:
    """提取文件文本并脱敏，返回脱敏文本。文件不存在或格式不支持返回 None。"""
    if not os.path.isfile(file_path):
        logger.warning("[desensitize] 文件不存在: %s", file_path)
        return None
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    if ext not in ("docx", "pdf"):
        logger.info("[desensitize] 暂不支持的格式: %s", ext)
        return None
    text = extract_text(file_path, ext)
    if not text.strip():
        logger.info("[desensitize] 文件内容为空: %s", file_path)
        return None
    return desensitize_text(text)
