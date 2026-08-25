"""FastAPI 入口：建表、CORS、挂载路由。

启动开发服务器：
    cd backend
    uvicorn app.main:app --reload --port 8000
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 配置日志：开发环境输出 INFO 及以上，含时间/模块/级别
# 排查问题时可将 level 改为 logging.DEBUG 查看更详细的节点流程
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


from app.api import auth, cases, chat, conversations, files, llm, prompts, rag, schedules, templates
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal

# 启动时自动建表（开发环境）。导入 models 以确保所有表注册到 Base.metadata。
import app.models  # noqa: F401

Base.metadata.create_all(bind=engine)

# 播种默认 prompts + 公共模板（幂等）
with SessionLocal() as db:
    prompts.seed_default_prompts(db)
    templates.seed_templates(db)

app = FastAPI(title="Law Agent Backend", version="0.1.0")

# CORS：开发环境允许 Vite 默认端口
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(llm.router)
app.include_router(chat.router)
app.include_router(cases.router)
app.include_router(prompts.router)
app.include_router(rag.router)
app.include_router(files.router)
app.include_router(conversations.router)
app.include_router(templates.router)
app.include_router(schedules.router)


@app.get("/")
def root():
    return {"name": "Law Agent Backend", "status": "ok"}
