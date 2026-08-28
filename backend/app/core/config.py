"""应用配置：通过 pydantic-settings 从 .env 读取。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 数据库连接串（开发环境默认 SQLite；生产多用户建议 PostgreSQL，在 .env 中覆盖即可）
    DATABASE_URL: str = "sqlite:///./law_agent.db"
    # JWT
    SECRET_KEY: str = "change-me-to-a-random-secret-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    # LLM API Key 加密密钥（Fernet；非法时自动派生，仅开发环境安全）
    LLM_ENCRYPTION_KEY: str = "replace-with-fernet-key-please"
    # LLM 调用超时（秒）与最大重试次数
    # 默认 120s 与前端 chat.ts 的 LLM_TIMEOUT 对齐，避免文书撰写（draft_node 润色长文本）超时
    LLM_TIMEOUT: float = 120.0
    LLM_MAX_RETRIES: int = 2
    # CORS 允许来源（逗号分隔）
    CORS_ORIGINS: str = "http://localhost:5173"
    # 文件上传目录（开发环境本地磁盘）
    UPLOAD_DIR: str = "uploads"
    # Chroma 向量库持久化目录
    CHROMA_DIR: str = "chroma_db"
    # Qdrant 向量库（法律检索多源 RAG）
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    # Qdrant 客户端超时（秒）
    QDRANT_TIMEOUT: float = 5.0
    # Qdrant 集合名
    QDRANT_COLLECTION_LAW: str = "law_articles"          # 法条库
    QDRANT_COLLECTION_CASE: str = "case_precedents"      # 判例库（公司脱敏案例）
    QDRANT_COLLECTION_WECHAT: str = "wechat_articles"   # 公众号观点
    # RAG 检索默认返回条数
    RAG_TOP_K: int = 5
    # 对话上下文：拼进 LLM 的最近消息轮数（1 轮 = 1 条 user + 1 条 agent）
    CHAT_HISTORY_ROUNDS: int = 5
    # ClamAV 病毒扫描（留空则使用 TCP；填写路径则用 Unix socket）
    CLAMAV_SOCKET: str = ""
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    # MinIO 对象存储（兼容 S3）
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "law-agent"
    MINIO_SECURE: bool = False
    # LangGraph 检查点保存器类型：memory(默认,开发)/sqlite/postgres(生产)
    CHECKPOINTER_TYPE: str = "memory"
    # SQLite 检查点文件路径（CHECKPOINTER_TYPE=sqlite 时生效）
    CHECKPOINTER_SQLITE_PATH: str = "checkpoints.db"
    # PostgreSQL 检查点连接串（CHECKPOINTER_TYPE=postgres 时生效，留空则复用 DATABASE_URL）
    CHECKPOINTER_PG_URL: str = ""
    # 平台开发者账号（启动时自动播种，可在 .env 覆盖）
    DEVELOPER_EMAIL: str = "dev@lawagent.com"
    DEVELOPER_PASSWORD: str = "dev123456"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
