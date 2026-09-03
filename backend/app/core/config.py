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
    # 关闭 DeepSeek 推理模型的深度思考（thinking），首 token 延迟 3.1s → 1.2s
    # 仅对 deepseek 供应商生效；设为 false 可恢复思考以提升复杂任务质量
    LLM_THINKING_DISABLED: bool = True
    # CORS 允许来源（逗号分隔）
    CORS_ORIGINS: str = "http://localhost:5173"
    # 文件上传目录（开发环境本地磁盘）
    UPLOAD_DIR: str = "uploads"
    # Chroma 向量库持久化目录
    CHROMA_DIR: str = "chroma_db"
    # 检索相关性阈值：余弦距离超过该值的命中视为不相关并丢弃
    # （0.4 很严格 / 0.55 均衡 / 0.7 宽松；设为 1.0 等于不过滤）
    # RAG 检索相关性阈值（向量粗召回 + 关键词精过滤）
    # 法律领域用英文优先的 embedding 模型（all-MiniLM-L6-v2），中文语义区分度不够，
    # 需要两级阈值：放宽阈值做粗召回，严格阈值以内信任向量，中间区间用关键词重叠率过滤
    RAG_MAX_DISTANCE: float = 0.60       # 放宽阈值：超过则直接丢弃（完全不相关）
    RAG_STRICT_DISTANCE: float = 0.45    # 严格阈值：以内的结果直接信任向量相关性
    RAG_MIN_KEYWORD_OVERLAP: float = 0.4  # 中间区间的关键词重叠率门槛（query 的 n-gram 至少 40% 出现在 content 里）
    # Qdrant 向量库（法律检索多源 RAG）
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    # Qdrant 客户端超时（秒）
    QDRANT_TIMEOUT: float = 5.0
    # Qdrant 集合名（统一使用 knowledge_base 单一集合，分类用 metadata.category 区分）
    # 保留旧变量名做兼容，值全部指向 knowledge_base
    QDRANT_COLLECTION_LAW: str = "knowledge_base"
    QDRANT_COLLECTION_CASE: str = "knowledge_base"
    QDRANT_COLLECTION_WECHAT: str = "knowledge_base"
    # RAG 检索默认返回条数
    RAG_TOP_K: int = 5
    # 检索时每个分类单独取多少条再合并（每路 top_k，合并后再截一次 RAG_TOP_K）
    RAG_PER_CATEGORY_K: int = 5
    # 知识库分类检索权重（法条=权威依据，判例=参考，公众号=一家之言）
    RAG_CATEGORY_WEIGHTS: dict = {
        "law": 1.0,
        "case": 0.8,
        "wechat": 0.5,
    }
    # 对话上下文：拼进 LLM 的最近消息轮数（1 轮 = 1 条 user + 1 条 agent）
    CHAT_HISTORY_ROUNDS: int = 5
    # ClamAV 病毒扫描（留空则使用 TCP；填写路径则用 Unix socket）
    CLAMAV_SOCKET: str = ""
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    # LibreOffice 命令路径（用于 .doc → .docx 格式转换）
    # Windows 默认：C:/Program Files/LibreOffice/program/soffice.exe
    # Linux  默认：/usr/bin/soffice
    # 留空则自动查找 PATH；找不到 ole 格式直接降级为提示下载
    LIBREOFFICE_BIN: str = ""
    LIBREOFFICE_TIMEOUT: int = 30  # 单次转换超时（秒）
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
