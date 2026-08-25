# 分步实现指南

> 配合 docs/project-framework.md 使用。按阶段推进，每阶段都有可运行的验收标准。
> 建议按「先跑通核心闭环 → 再补外围功能」的顺序：阶段 1–6 打通「对话 → 文书生成 → 预览 → 保存」并接入公司/个人 API 网关，阶段 7–9 补齐日程、文档库、设置，阶段 10 上线。

## 阶段 0：环境准备（半天）

```powershell
# 1. 基础工具
node -v          # 要求 >= 18
python --version # 要求 3.11
docker --version # 数据库/向量库/存储都跑容器

# 2. 安装后端依赖（在 backend/ 目录）
pip install "fastapi[standard]" uvicorn sqlalchemy alembic pydantic-settings
pip install langchain langchain-openai langgraph langchain-community
pip install qdrant-client redis celery python-docx pdfplumber cryptography
pip install python-jose passlib[bcrypt] python-multipart requests

# 3. 准备 LLM API Key（写入 backend/.env，仅供开发环境直连；生产环境由公司管理员在系统内配置，见阶段 4）
OPENAI_API_KEY=sk-xxx          # 或换成国内模型的 OpenAI 兼容接口
OPENAI_BASE_URL=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-small
CHAT_MODEL=gpt-4o-mini
```

**验收**：`uvicorn app.main:app --reload` 能启动，访问 `/docs` 看到 Swagger。

## 阶段 1：初始化项目骨架（1 天）

```powershell
# 前端
npm create vite@latest frontend -- --template react-ts
cd frontend
npm i antd @ant-design/icons axios zustand @tanstack/react-query

# 基础设施（项目根目录 docker-compose.yml）
# 服务：postgres:15 / qdrant / redis / minio，一条命令拉起
docker compose up -d
```

**验收**：前端 `npm run dev` 出现欢迎页；`docker compose ps` 四个容器 healthy。

## 阶段 2：后端基础层（2 天）

按此顺序建模块：

1. `app/core/config.py` — 从 `.env` 读配置（Pydantic Settings）
2. `app/core/database.py` — SQLAlchemy engine + session；用 Alembic 建表
3. `app/core/security.py` — JWT 签发/校验、密码哈希
4. `app/models/` — 建 users / companies / cases / case_members / conversations / messages / schedules / document_templates / case_documents（表结构见框架文档 §4）
5. `app/api/auth.py` — 注册 / 登录 / 刷新令牌
6. `app/api/cases.py` — 案件增删改查、最近 1 周打开的案件列表、新增案件（原告/被告/上诉法院/案件基本情况为必填）

```python
# app/api/cases.py 示例（简化）
@router.get("/cases/recent")
def recent_cases(user=Depends(get_current_user), db: Session = Depends(get_db)):
    week_ago = datetime.now() - timedelta(days=7)
    return db.query(Case).filter(
        Case.owner_id == user.id, Case.last_opened_at >= week_ago
    ).order_by(Case.last_opened_at.desc()).all()
```

**验收**：用 Swagger 完成注册登录 → 新建案件 → 查询最近案件的全流程。

## 阶段 3：文书撰写 Agent（核心，3–4 天）

这是整个产品的核心闭环，用 LangGraph 状态图实现，代码放在 `app/agents/drafting/`。

### 3.1 定义状态与图

```python
# app/agents/drafting/graph.py
from typing import TypedDict, Optional, Annotated, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

class DraftState(TypedDict, total=False):
    user_input: str
    doc_type: str                    # 上诉状/答辩状/起诉状...
    template_id: Optional[str]
    case_id: Optional[int]
    collected: dict                  # 已收集的信息
    missing_fields: List[str]
    draft: Optional[str]
    confirmed: bool
    file_url: Optional[str]

# 节点
async def intent_node(state):        # 识别文书类型
async def template_node(state):      # 模板选择（自有优先，收藏靠前）
async def case_node(state):          # 关联案件 / 询问案件名称
async def collect_node(state):       # LLM 判断缺失字段，输出表单问题
async def draft_node(state):         # 模板 + 案件信息 -> 生成文书
async def review_node(state):        # interrupt 等待用户确认/微调
async def finalize_node(state):      # 生成 docx、保存文档库、发送邮件

builder = StateGraph(DraftState)
builder.add_node("intent", intent_node)
builder.add_node("template", template_node)
builder.add_node("case", case_node)
builder.add_node("collect", collect_node)
builder.add_node("draft", draft_node)
builder.add_node("review", review_node)
builder.add_node("finalize", finalize_node)
builder.set_entry_point("intent")
builder.add_edge("intent", "template")
builder.add_edge("template", "case")
builder.add_edge("case", "collect")
builder.add_edge("collect", "draft")
builder.add_edge("draft", "review")
builder.add_conditional_edges("review", lambda s: "finalize" if s["confirmed"] else "draft")
builder.add_edge("finalize", END)
graph = builder.compile(checkpointer=MemorySaver())
```

### 3.2 关键实现要点

- **人工确认**：`review` 节点用 `interrupt()`（LangGraph 1.x）或 `human_review` 节点暂停执行，前端弹「文书预览 + 微调/确认」两个按钮，确认后 `Command(resume=...)` 继续。
- **工具节点**：用 `ToolNode` 注册 `search_case`（查案件档案）、`get_template`（取模板占位符）、`generate_docx`（python-docx 填充）、`save_doc`（加密存 MinIO + 登记 case_documents）。
- **模板占位符**：通用模板用 `{{上诉人}} {{被上诉人}} {{上诉请求}} {{事实与理由}}` 等占位符；自有模板上传时先解析 Word/PDF 提取占位符。
- **流式输出**：FastAPI 用 `WebSocket`/`SSE` 把 graph 的 token 流推给前端，前端打字机显示。

**验收**：对话框中输入「帮我写一份上诉状」→ 选模板 → 关联案件 → 自动补充缺失信息表单 → 生成预览 → 微调/确认 → 得到 .docx 并入库。

## 阶段 4：LLM API 管理（模型网关，2–3 天）

> 需求：开发环境用开发者 Key；上线后由公司管理员在账号中配置公司 API Key，公司全员共用、管理员可见每个员工的用量；员工也可使用自己的 Key。
> 因此需要一个「LLM 网关」统一做：密钥路由 → 额度检查 → 调用 → 用量记账。

### 4.1 新增数据库表（4 张）

| 表 | 字段要点 | 说明 |
|---|---|---|
| company_llm_configs | company_id, provider, base_url, api_key_enc, models(JSON), monthly_budget, is_active | 公司共享配置，仅管理员可读写 |
| user_llm_configs | user_id, provider, base_url, api_key_enc, models, is_active | 个人配置，员工自管 |
| llm_usage_records | user_id, company_id, source(company/personal), provider, model, prompt_tokens, completion_tokens, cost, request_id, created_at | 每次调用一条 |
| llm_quotas | company_id, user_id, period(年月), quota_limit, used, status | 员工月度额度 |

### 4.2 网关服务 app/llm/gateway.py

```python
class LLMGateway:
    """所有 Agent 只依赖这个类，不直接接触 Key"""
    def resolve_config(self, user) -> LLMConfig:
        # 优先级：个人 API(员工启用) > 公司 API(管理员配置) > 平台开发者 Key(仅内部环境)
        if user.llm_source == "personal" and user.user_llm_config:
            return user.user_llm_config
        cfg = company_llm_configs.get(user.company_id, active=True)
        if cfg: return cfg
        return DEV_LLM_CONFIG                     # 开发兜底，生产禁止

    async def chat(self, user, messages, tools=None, **kw):
        cfg = self.resolve_config(user)
        self.enforce_quota(user, cfg)             # 公司预算 + 员工限额，超限抛 QuotaExceeded
        resp = await self._call(cfg, messages, tools)   # 解密 Key 后调用，带重试/超时
        self.record_usage(user, cfg, resp)        # 写 llm_usage_records + 更新 llm_quotas.used
        return resp
```

实现要点：
- **Key 安全**：AES-256 加密落库（密钥放 KMS/环境变量），接口只返回掩码（`sk-••••••f2a`），前端永不拿到明文；
- **用量归属**：所有聊天/检索接口携带 `user_id`，网关在 `record_usage` 里写死来源（company/personal），保证公司结算准确；
- **额度控制**：管理员可为公司设月度预算、为每个员工设限额；员工用公司 API 时先扣公司预算、再扣个人配额，任一超限即降级（切个人 Key）或拒绝并提示；
- **改造存量代码**：阶段 3 里直接调 `ChatOpenAI(api_key=...)` 的地方全部换成 `gateway.chat(...)`；LangGraph 节点里通过注入的 user 上下文取配置，保证多用户并发时用量不串。

### 4.3 接口（app/api/llm.py）

| 接口 | 方法 | 角色 | 说明 |
|---|---|---|---|
| /api/llm/config/company | GET / PUT | 管理员 | 查看/修改公司 API 配置（Key 掩码展示） |
| /api/llm/config/me | GET / PUT | 员工 | 查看/修改个人 API 配置 |
| /api/llm/source | PUT | 员工 | 切换「公司 API / 个人 API」 |
| /api/llm/usage/me | GET | 员工 | 我的用量（次数 / Tokens / 费用） |
| /api/llm/usage/company | GET | 管理员 | 员工用量明细（表格数据，含额度水位） |
| /api/llm/quotas | PUT | 管理员 | 设置员工月度额度 |
| /api/llm/test | POST | 本人 | 用当前生效的 Key 发一次最小请求测试连通 |

### 4.4 前端页面

- 设置页新增「模型与 API」：使用方式切换（公司/个人）、公司 API 状态与额度条、个人 Key 配置表单、我的用量统计；
- 管理员账号自动显示「员工用量管理」卡片：用量表格（员工/使用方式/模型/调用/Tokens/费用/额度/状态）+ 配置公司密钥 + 设置员工额度 + 导出报表；
- 工作台顶栏显示当前模型与额度水位（如「公司 GPT-4o · 额度 62%」），点击跳转设置页；
- 交互已更新到原型 docs/ui-mockup/index.html 的设置页（含「切换管理员视角」演示按钮）。

**验收**：管理员配置公司 Key → 员工默认走公司 API 且用量独立记录 → 管理员看板看到每个员工的次数/Tokens/费用/额度 → 员工超限后被限制并提示 → 员工切个人 Key 后用量不再计入公司。
## 阶段 5：法律检索 Agent（3 天，RAG）

1. **数据采集**（离线脚本 `app/agents/legal_search/ingest.py`）：
   - 法条/司法解释：从政府公开数据源（如国家法律法规数据库）抓取《民法典》《刑法》等，解析为条目；
   - 司法判例：裁判文书公开数据 / 公司脱敏案例；
   - 公众号文章：订阅号列表 + 定时抓取正文。
2. **入库**：文本切块（chunk 500–800 字符）→ embedding → 写入 Qdrant，元数据存 `legal_references` 表（type 区分法条/判例/公司案例/公众号）。
3. **检索接口** `app/api/search.py`：
   - 多路并行检索（法条库 / 判例库 / 公司案例 / 公众号）→ Rerank → 过滤；
   - 强制「引用 ≤ 10 条」；
   - 输出：总分结构（先给结论与法律依据，再展开说明），观点冲突时生成对比表格，每条引用带来源链接可点击。

```python
# 检索核心（伪代码）
def search(query):
    queries = rewrite(query)                    # LLM 改写/扩展
    hits = qdrant.search_multi([q], collections=[LAW, CASE, PUB], top_k=10)
    hits = rerank(query, hits)                  # cross-encoder 重排
    refs = hits[:10]
    return build_answer(query, refs)            # LLM 组装：总分 + 表格 + 引用
```

**验收**：问「合同违约金的上限规定」，返回总分答案 + ≤10 条可点击引用，冲突观点以表格对比。

## 阶段 6：前端工作台（3–4 天）

按原型 `docs/ui-mockup/index.html` 拆组件：

| 组件 | 文件 | 说明 |
|---|---|---|
| 工作台布局 | `pages/workbench/index.tsx` | 左 224 / 中自适应 / 右 288 三栏 grid |
| 左侧列表栏 | `components/sidebar/Sidebar.tsx` | 日程/文档库入口 + 底部用户卡片 |
| 模板下拉 | `components/chat/TemplateSelect.tsx` | 通用/自有分组、⭐收藏置顶、上传 Word/PDF |
| 消息流 | `components/chat/ChatBox.tsx` | 气泡 + 打字机效果 + 工具卡片渲染 |
| 信息收集表单 | `components/chat/InfoForm.tsx` | Agent 返回的缺失字段表单，动态渲染 |
| 文书预览 | `components/chat/DocPreview.tsx` | 内嵌 Word 风格预览（docx-preview 或 iframe） |
| 案件栏 | `components/cases/CasePanel.tsx` | 最近 1 周案件、折叠/展开、新增案件弹窗 |
| 对话接入 | `api/chat.ts` | WebSocket 封装：发消息、收 token 流、收工具卡片 |

```typescript
// api/chat.ts 要点
const ws = new WebSocket(`${location.origin.replace('http','ws')}/ws/chat?token=${token}`);
ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  // msg.type: 'token' | 'form' | 'preview' | 'done'
  // 按类型追加到消息流
};
```

**验收**：工作台三栏布局与原型一致；对话全流程（含模板下拉、信息表单、文书预览）端到端跑通。

## 阶段 7：日程与提醒（2–3 天）

1. `schedules` 表 + CRUD API + 前端日历页（Ant Design `<Calendar>` 支持日/周/月）。
2. **节点抽取**：新建案件或上传判决书时，提醒 Agent 用 LLM 抽取时间节点（答辩期 15 日、举证期限、管辖权异议 15 日、判决上诉期 15 日等），计算截止日。
3. **定时任务**（Celery beat 每日扫描）：
   - 紧急事项（举证期/上诉期）提前 1 天、一般事项提前 5 天；
   - 到期 → 站内 WebSocket 推送 + 按用户设置调用飞书/微信/钉钉适配器。
4. **通知适配器**：`services/notify/` 下按渠道实现统一接口 `send(user, title, body)`；设置页可勾选渠道，公司管理员可统一接入。

**验收**：新案件自动生成「上诉期截止」日程；到点收到站内 + 飞书/微信提醒；日历页日/周/月视图切换正常。

## 阶段 8：文档库（3 天）

1. **加密存储**：上传走 `POST /cases/{id}/documents`，后端流式加密（AES-256）后存 MinIO，密钥存在 KMS/环境变量；下载时解密。
2. **密码门禁**：文档库独立密码（与登录密码分离），前端进入前校验。
3. **搜索**：关键词匹配案件标题/文件名 + 全文检索（PostgreSQL FTS 或 Qdrant 语义），结果含私库与公库。
4. **未解锁机制**：按职级过滤可见案件；未解锁案件返回脱敏版（仅上诉书/判决书，不含证据）或发起阅读申请（`doc_access_requests` 表，经手律师审核）。
5. **协作权限**：case_members 的 owner/editor/reader 控制读写；案件详情页提供「邀请协作 / 审核申请」按钮。
6. **公司库绑定**：加入公司后文档库与公司绑定，上级用本人密码可查下级文档库；判决书类文档脱敏后进参考库。

**验收**：上传加密文档 → 密码进入文档库 → 按案件浏览 → 搜索命中；未解锁案件只能看脱敏版或申请。

## 阶段 9：设置与公司（1–2 天）

- 基本信息：姓名/邮箱/手机号修改（API + 页面）。
- 界面设置：字体大小三档 + 背景色主题（浅色/米白/深色/护眼绿），本地持久化 + 服务端同步。
- 公司：邀请码申请加入 → 管理员审核 → 退出公司；管理员界面统一配置通知渠道。

## 阶段 10：测试、联调与部署（2–3 天）

```powershell
# 后端
cd backend && pytest                 # 单元 + API 集成测试（至少覆盖 Agent 图与案件 CRUD）
# 前端
cd frontend && npm run build && npx tsc --noEmit
# 部署（生产推荐）
docker compose -f docker-compose.prod.yml up -d   # 加 Nginx 反代 + HTTPS
```

- 测试要点：文书 Agent 全链路、检索引用数 ≤10、权限矩阵（上级查下级库、未解锁脱敏）、提醒调度。
- 上线清单：LLM 密钥走密钥管理、文档库密码二次验证、脱敏规则上线前审查、飞书/微信/钉钉机器人审核开通。

## 建议的开发顺序（MVP 裁剪）

| 优先级 | 功能 | 说明 |
|---|---|---|
| P0 | 工作台 + 文书撰写闭环 + 案件 CRUD | 先做出核心价值 |
| P0 | LLM 网关（公司/个人 API + 用量统计） | 上线必备，否则员工无法用公司账号计费 |
| P1 | 法律检索（法条 + 判例） | 检索价值高、实现相对独立 |
| P1 | 日程提醒（站内 + 单一渠道） | 先只接飞书 |
| P2 | 文档库加密 + 脱敏 + 协作 | 安全相关，尽早设计好权限模型 |
| P2 | 微信/钉钉、网盘备份、快递面单 | 外围集成，放最后 |
