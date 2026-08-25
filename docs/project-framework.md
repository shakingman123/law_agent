# 法律文书 Agent — 项目框架

> 依据 readme.md 需求整理，技术栈：React 前端 + Python(LangChain/LangGraph) 后端 + Web 交互。

## 1. 总体架构

```text
┌────────────────────────────────────────────────────────────┐
│  前端 React (Vite + TypeScript + Ant Design)               │
│  工作台(对话) │ 日程列表 │ 文档库 │ 设置                    │
│  REST API + WebSocket(流式对话/提醒推送)                   │
└────────────────────────┬───────────────────────────────────┘
                         │ HTTPS / WSS
┌────────────────────────▼───────────────────────────────────┐
│  后端 FastAPI (Python 3.11)                                 │
│  ├─ REST 路由层：认证/案件/文档/日程/公司                   │
│  ├─ WebSocket 网关：Agent 流式输出、实时提醒                │
│  └─ Agent 编排层 (LangGraph)                               │
│      ├─ 文书撰写 Agent  ── 模板+案件信息→草稿→预览→定稿     │
│      ├─ 法律检索 Agent  ── 多源RAG→总分结构输出(≤10条)      │
│      ├─ 日程提醒 Agent  ── 提取时间节点→日程→多渠道通知     │
│      ├─ 案件归档 Agent  ── 加密存储+脱敏入库                │
│      └─ LLM 网关 ── 公司/个人密钥路由 + 用量统计与限额      │
└───────┬──────────────┬──────────────┬──────────────┬───────┘
        │              │              │              │
   PostgreSQL    向量库 Qdrant   对象存储 MinIO   Redis/Celery
   (用户/案件/     (法条/判例/      (Word/PDF/      (缓存/任务/
    日程/模板)      公司案例/公众号)  照片/视频)       提醒调度)
```

## 2. 技术选型

| 层次 | 技术 | 用途 |
|---|---|---|
| 前端框架 | React 18 + TypeScript + Vite | 页面与应用壳 |
| UI 组件库 | Ant Design 5 | 表格、表单、日历、对话框等企业级组件 |
| 状态管理 | Zustand + TanStack Query | 全局状态 / 服务端缓存 |
| 对话流 | WebSocket + 事件流(SSE) | Agent 打字机式输出 |
| 后端框架 | Python 3.11 + FastAPI | REST + WebSocket 网关 |
| Agent 框架 | LangChain + LangGraph | 状态图编排、工具调用、记忆 |
| ORM / 迁移 | SQLAlchemy 2 + Alembic | 数据模型与迁移 |
| 主数据库 | PostgreSQL 15 | 用户、公司、案件、日程、模板 |
| 向量库 | Qdrant(或 pgvector) | 法条/判例/公众号文章语义检索 |
| 缓存/异步 | Redis + Celery | 提醒调度、文件处理、邮件/快递任务 |
| 对象存储 | MinIO(兼容S3) | 案件电子资料、生成的文书 |
| 文档处理 | python-docx / pdfplumber | Word/PDF 解析与生成 |
| LLM | OpenAI 兼容 API(或国内模型) + Embedding | 对话生成与向量化 |
| LLM 网关 | 自研(services/llm) | 公司/个人 Key 路由、用量统计、额度限制 |
| 认证 | JWT + OAuth2 | 登录与会话 |

## 3. 仓库目录结构

```text
law_agent/
├── frontend/                     # React 前端
│   ├── src/
│   │   ├── pages/
│   │   │   ├── workbench/        # 工作台(对话框+案件栏)
│   │   │   ├── calendar/         # 日程列表(日/周/月)
│   │   │   ├── doclib/           # 文档库(私库/公库/搜索/解锁)
│   │   │   └── settings/         # 设置(基本信息/界面/公司)
│   │   ├── components/
│   │   │   ├── chat/             # ChatBox、消息气泡、模板下拉、文书预览
│   │   │   ├── cases/            # 案件栏、新增案件表单
│   │   │   ├── sidebar/          # 左侧列表栏、用户卡片
│   │   │   └── common/           # 上传、富文本、图标等
│   │   ├── api/                  # axios + ws 客户端封装
│   │   ├── stores/               # zustand stores
│   │   └── types/                # 与后端对齐的 TS 类型
│   └── package.json
│
├── backend/                      # Python 后端
│   ├── app/
│   │   ├── main.py               # FastAPI 入口
│   │   ├── core/                 # 配置/安全/数据库/日志
│   │   ├── api/                  # 路由(按模块)
│   │   │   ├── auth.py  users.py  cases.py  llm.py
│   │   │   ├── templates.py  docs.py  schedules.py
│   │   │   └── chat.py  ws.py
│   │   ├── agents/               # LangGraph 各 Agent
│   │   │   ├── drafting/         # 文书撰写
│   │   │   ├── legal_search/     # 法律检索 RAG
│   │   │   ├── reminder/         # 时间节点提醒
│   │   │   └── archive/          # 案件归档/脱敏
│   │   ├── services/             # 业务服务(文件加密、网盘、通知)
│   │   ├── models/               # SQLAlchemy ORM
│   │   ├── schemas/              # Pydantic 模型
│   │   ├── llm/                  # LLM 网关(模型路由/密钥管理/用量计费)
│   │   └── tasks/                # Celery 任务(提醒/导出/邮件)
│   ├── tests/
│   ├── requirements.txt
│   └── pyproject.toml
│
├── docs/                         # 需求、设计文档(本目录)
├── docker-compose.yml            # PG/Qdrant/Redis/MinIO
└── readme.md
```

## 4. 数据库核心表设计

| 表 | 关键字段 | 说明 |
|---|---|---|
| users | id, name, email, phone, avatar, company_id, role, password_hash | 用户与职级 |
| companies | id, name, invite_code, admin_id | 公司与邀请码 |
| cases | id, title, plaintiff, defendant, court, case_no, stage(一审/二审), created_by, updated_at | 案件基本信息 |
| case_members | case_id, user_id, role(owner/editor/reader), status | 协作与权限 |
| case_documents | id, case_id, file_name, file_type, storage_key, encrypted, uploader_id, created_at | 案件电子资料 |
| document_templates | id, name, type(generic/private), file_url, owner_id, is_favorite | 文书模板 |
| conversations | id, user_id, case_id, title | 对话会话 |
| messages | id, conversation_id, role, content, meta(工具调用/预览) | 聊天记录 |
| schedules | id, user_id, case_id, title, start_at, end_at, remind_days, channel | 日程/提醒 |
| legal_references | id, type(法条/判例/公司案例/公众号), title, content, embedding_id, is_desensitized, source_url | 检索库 |
| company_llm_configs | id, company_id, provider, base_url, api_key_enc, models, monthly_budget, is_active | 公司共享 LLM 配置(仅管理员可改) |
| user_llm_configs | id, user_id, provider, base_url, api_key_enc, models, is_active | 个人 LLM 配置(员工自管) |
| llm_usage_records | id, user_id, company_id, source(company/personal), provider, model, prompt_tokens, completion_tokens, cost, created_at | 每次 LLM 调用用量明细 |
| llm_quotas | id, company_id, user_id, period(年月), quota_limit, used, status | 员工月度额度 |
| doc_access_requests | id, case_id, applicant_id, status | 解锁申请 |

## 5. Agent 工作流（LangGraph 状态图）

所有 Agent 统一使用 StateGraph，节点之间传递 State（案件信息、缺失字段、草稿），支持人工确认(interrupt)实现「生成预览→用户确认」。

### 5.1 文书撰写 Agent（核心）

```text
用户输入「帮我写一份上诉状」
  → ① 意图识别: doc_type=上诉状
  → ② 模板选择: 下拉中「自有模板优先(收藏靠前)/通用模板」
  → ③ 案件关联: 从右侧当前案件 / 询问案件名称
  → ④ 信息收集: LLM 对比模板所需字段与案件已有信息，只问缺失项(表单)
  → ⑤ 生成草稿: 调用模板 + 案件信息 → 生成文书预览
  → ⑥ 用户微调 → 重新生成
  → ⑦ 确认定稿: 生成 .docx → 保存本地 + 写入文档库(加密)
  → ⑧ (可选)发送法院邮箱 / 快递面单
```

关键点：用 interrupt 暂停在「预览确认」节点；工具节点 search_case、get_template、load_case_info、generate_docx、save_doc。

### 5.2 法律检索 Agent（RAG）

```text
问题 → 查询改写 → 多路检索(并行):
  ├─ 法条库(民法典/刑法/司法解释)  — Qdrant 向量检索
  ├─ 判例库(公司脱敏案例)          — Qdrant 向量检索
  └─ 公众号观点                    — 爬取索引 + 向量检索
→ 重排(Rerank) → 过滤: 引用 ≤ 10 条
→ 输出: 总分结构(先结论后展开) + 对比观点用表格 + 每条引用可点击跳转
```

### 5.3 日程提醒 Agent

```text
新案件建档/更新 → 抽取时间节点(答辩期/管辖权异议/举证期/上诉期)
→ 依据文书类型计算截止日(如判决书送达后15日上诉期)
→ 生成 schedules(提前5天/提前1天按紧急程度)
→ Celery 定时扫描 → 站内推送(WebSocket) + 飞书/微信/钉钉消息
→ 日历界面(日/周/月)展示
```

### 5.4 案件归档 Agent

```text
上传 Word/PDF/照片/视频 → 病毒扫描 → AES 加密 → MinIO
→ 按案件归档 → (公司库) 脱敏处理 → 写入 legal_references
→ 权限: 案件协作成员可读/改；上级可用自己密码查看下级文档库
```

### 5.5 LLM 网关与 API 配置（公司共享 + 个人自备）

开发环境使用开发者自己的 Key；上线后由公司管理员在账号中配置公司 API Key，公司全员共用并按员工独立统计用量，员工也可配置并使用自己的 Key。

```text
LLM 调用路由（LLMGateway 统一入口，所有 Agent 只依赖它）:
  ├─ 优先级: 个人 API(员工启用) > 公司 API(管理员配置) > 平台开发者 Key(仅内部环境)
  ├─ 额度检查: 公司月度预算 + 员工个人限额(llm_quotas)，超限自动降级/拒绝
  ├─ 调用: 解密 Key → 请求模型 → 记录 llm_usage_records
  └─ 统计: 按 公司/员工/模型/时间 维度汇总，供管理员看板与导出
```

关键设计：
- API Key AES 加密存储，接口仅返回掩码（sk-••••f2a），永不回传明文；
- 管理员可查看每个员工的使用量（次数 / Tokens / 费用 / 额度水位）并设置月度限额；
- 员工可在设置页切换「公司 API / 个人 API」，个人调用不计入公司额度；
- 所有聊天/检索请求携带 user_id，由网关统一归属用量，保证公司结算准确。
## 6. 前端页面结构（与 readme 布局对应）

| 页面 | 布局 | 对应需求 |
|---|---|---|
| 工作台 | 左侧列表栏(日程/文档库) + 中央对话框 + 右侧案件栏(可折叠) + 左下用户卡片 | 撰写文书、检索、提醒入口 |
| 日程列表 | 日/周/月视图 + 新建日程 + 通知渠道设置(飞书/微信/钉钉) | 时间节点提醒 |
| 文档库 | 密码门禁 → 搜索栏 → 案件卡片(按更新时间) → 未解锁案件(脱敏版/申请) | 加密文档库、协作 |
| 设置 | 基本信息 / 界面(字体、背景) / 公司(邀请码加入/退出) | 设置界面 |

## 7. 外部集成清单

| 集成 | 用途 | 实现方式 |
|---|---|---|
| 飞书 | 日程同步、消息提醒 | 飞书开放平台 API / Webhook |
| 微信 | 消息提醒 | 企业微信应用消息 / 公众号模板 |
| 钉钉 | 消息提醒 | 钉钉机器人 Webhook |
| 百度网盘/夸克网盘 | 云文档备份 | 官方开放 API(OAuth) |
| 邮件 | 发到法院邮箱 | SMTP / 企业邮箱 API |
| 快递 | 寄出文书 | 快递100 / 菜鸟 API(打印面单) |

## 8. 安全设计

- 登录 JWT + 刷新令牌；文档库独立密码(二次校验)
- 文档上传后 AES-256 加密再入库，访问时解密
- 公司库脱敏：姓名/身份证/住址等替换后再进参考库
- LLM API Key AES 加密存储、接口只回掩码；用量按员工独立计费，公司预算与员工限额双重控制
- 权限模型：案件 owner/editor/reader 三级；上级可查下级库(用本人密码)；未解锁案件默认隐藏
