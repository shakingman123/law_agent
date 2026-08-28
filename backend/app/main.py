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


from app.api import auth, cases, chat, conversations, dev, files, llm, prompts, rag, schedules, templates
from app.core.config import settings
from app.core.database import Base, engine, SessionLocal
from app.core.security import hash_password
from app.models.user import User

# 启动时自动建表（开发环境）。导入 models 以确保所有表注册到 Base.metadata。
import app.models  # noqa: F401

Base.metadata.create_all(bind=engine)

# 轻量迁移：create_all 只建新表，不会给已存在的表补新列，这里手动补齐
from sqlalchemy import inspect, text

with engine.connect() as conn:
    _insp = inspect(engine)

    def _ensure_column(table: str, column: str, ddl: str):
        if conn.dialect.has_table(conn, table):
            cols = {c["name"] for c in _insp.get_columns(table)}
            if column not in cols:
                conn.execute(text(ddl))

    # BOOLEAN DEFAULT FALSE 兼容 PostgreSQL 与 SQLite（PG 的 BOOLEAN 不接受整数 0）
    _ensure_column("users", "is_developer", "ALTER TABLE users ADD COLUMN is_developer BOOLEAN DEFAULT FALSE")
    _ensure_column("admin_requests", "company_id", "ALTER TABLE admin_requests ADD COLUMN company_id INTEGER")
    # 直属上级（用户对用户外键，SQLite 不强制检查 FK，PG 也兼容）
    _ensure_column("users", "supervisor_id", "ALTER TABLE users ADD COLUMN supervisor_id INTEGER")
    conn.commit()

# 播种默认 prompts + 公共模板（幂等）
with SessionLocal() as db:
    prompts.seed_default_prompts(db)
    templates.seed_templates(db)

    # 播种平台开发者账号（幂等；账号密码可在 .env 用 DEVELOPER_EMAIL/DEVELOPER_PASSWORD 覆盖）
    if not db.query(User).filter(User.email == settings.DEVELOPER_EMAIL).first():
        db.add(
            User(
                name="平台开发者",
                email=settings.DEVELOPER_EMAIL,
                role="开发者",
                password_hash=hash_password(settings.DEVELOPER_PASSWORD),
                is_developer=True,
                llm_source="company",
            )
        )
        db.commit()

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
app.include_router(dev.router)


@app.get("/")
def root():
    return {"name": "Law Agent Backend", "status": "ok"}
