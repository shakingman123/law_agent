"""LLM 网关：所有 Agent 统一通过它调用 LLM。

依据 docs/implementation-guide.md §4.2：
- 密钥路由：个人 API(员工启用) > 公司 API(管理员配置) > 平台开发者 Key(仅内部环境)
- 额度检查：公司月度预算 + 员工个人限额，超限抛 QuotaExceeded
- 调用：解密 Key → 构造 ChatModel（Agent 不直接接触 Key）
- 记账：写 llm_usage_records + 更新 llm_quotas.used
"""
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.core.security import decrypt_api_key, mask_api_key
from app.models.llm import (
    CompanyLlmConfig,
    LlmQuota,
    LlmUsageRecord,
    UserLlmConfig,
)
from app.models.user import User

logger = logging.getLogger("app.llm.gateway")


class QuotaExceeded(Exception):
    """超出月度额度"""


@dataclass
class ResolvedConfig:
    """解析后的 LLM 配置（含解密后的明文 Key，仅在内存中传递）。"""

    source: str  # personal / company / platform
    provider: str
    base_url: str
    api_key: str
    models: list[str]


# 平台开发者 Key（仅开发兜底，生产环境应留空以强制使用公司/个人配置）
PLATFORM_LLM_KEY = os.getenv("PLATFORM_LLM_API_KEY", "")
PLATFORM_LLM_BASE = os.getenv("PLATFORM_LLM_BASE_URL", "https://api.openai.com/v1")
PLATFORM_LLM_MODEL = os.getenv("PLATFORM_LLM_MODEL", "gpt-4o-mini")

# OpenAI 标准计费（$/1M tokens），仅用于用量估算，实际以服务商账单为准
_PRICE_TABLE = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "deepseek-chat": (0.14, 0.28),
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p_in, p_out = _PRICE_TABLE.get(model, (1.0, 2.0))
    return round((prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000, 4)


class LLMGateway:
    """所有 Agent 只依赖这个类，不直接接触 Key。"""

    def resolve_config(self, user: User, db: Session) -> ResolvedConfig:
        """按优先级解析生效的 LLM 配置。"""
        logger.info(
            "[resolve_config] 开始解析 LLM 配置: user_id=%s, llm_source=%s, company_id=%s",
            user.id, user.llm_source, user.company_id,
        )

        # 1. 个人 API（员工启用 personal 时优先）
        if user.llm_source == "personal":
            cfg = (
                db.query(UserLlmConfig)
                .filter_by(user_id=user.id, is_active=True)
                .first()
            )
            logger.debug(
                "[resolve_config] 查询个人配置: user_id=%s, 命中=%s, is_active=%s, has_key=%s",
                user.id, bool(cfg), getattr(cfg, "is_active", None), bool(getattr(cfg, "api_key_enc", None)),
            )
            if cfg and cfg.api_key_enc:
                logger.info(
                    "[resolve_config] 命中个人 API: provider=%s, models=%s",
                    cfg.provider, cfg.models,
                )
                return ResolvedConfig(
                    source="personal",
                    provider=cfg.provider,
                    base_url=cfg.base_url or "",
                    api_key=decrypt_api_key(cfg.api_key_enc),
                    models=cfg.models or [],
                )
            logger.warning("[resolve_config] 用户 llm_source=personal 但个人配置不可用，降级到公司 API")

        # 2. 公司 API（管理员配置且启用）
        if user.company_id:
            cfg = (
                db.query(CompanyLlmConfig)
                .filter_by(company_id=user.company_id, is_active=True)
                .first()
            )
            logger.debug(
                "[resolve_config] 查询公司配置: company_id=%s, 命中=%s, is_active=%s, has_key=%s",
                user.company_id, bool(cfg), getattr(cfg, "is_active", None), bool(getattr(cfg, "api_key_enc", None)),
            )
            if cfg and cfg.api_key_enc:
                logger.info(
                    "[resolve_config] 命中公司 API: provider=%s, models=%s, monthly_budget=%s",
                    cfg.provider, cfg.models, cfg.monthly_budget,
                )
                return ResolvedConfig(
                    source="company",
                    provider=cfg.provider,
                    base_url=cfg.base_url or "",
                    api_key=decrypt_api_key(cfg.api_key_enc),
                    models=cfg.models or [],
                )
            logger.warning(
                "[resolve_config] 公司 API 不可用: company_id=%s, 命中=%s",
                user.company_id, bool(cfg),
            )

        # 3. 平台开发者 Key（仅开发兜底）
        if PLATFORM_LLM_KEY:
            logger.warning(
                "[resolve_config] 降级使用平台开发者 Key（仅开发环境）: base=%s, model=%s",
                PLATFORM_LLM_BASE, PLATFORM_LLM_MODEL,
            )
            return ResolvedConfig(
                source="platform",
                provider="openai",
                base_url=PLATFORM_LLM_BASE,
                api_key=PLATFORM_LLM_KEY,
                models=[PLATFORM_LLM_MODEL],
            )

        logger.error(
            "[resolve_config] 无可用 LLM 配置: user_id=%s, company_id=%s",
            user.id, user.company_id,
        )
        raise RuntimeError(
            "无可用的 LLM 配置：请在「设置 → 模型与 API」中配置公司 API 或个人 API"
        )

    def get_chat_model(
        self,
        user: User,
        db: Session,
        model: Optional[str] = None,
        temperature: float = 0.3,
        streaming: bool = False,
    ) -> ChatOpenAI:
        """构造已注入解密 Key 的 ChatOpenAI 实例。

        Agent 节点通过此方法获取 ChatModel，不直接接触明文 Key。
        所有模型均走 OpenAI 兼容接口（DeepSeek/通义/智谱均提供）。
        """
        logger.info(
            "[get_chat_model] 构造 ChatModel: user_id=%s, 指定model=%s, temperature=%s, streaming=%s",
            user.id, model, temperature, streaming,
        )
        cfg = self.resolve_config(user, db)
        target_model = model or (cfg.models[0] if cfg.models else PLATFORM_LLM_MODEL)
        # 仅打印掩码，绝不输出明文 Key
        logger.info(
            "[get_chat_model] 解析完成: source=%s, provider=%s, model=%s, base_url=%s, key_masked=%s",
            cfg.source, cfg.provider, target_model, cfg.base_url, mask_api_key(cfg.api_key),
        )
        return ChatOpenAI(
            model=target_model,
            api_key=cfg.api_key,
            base_url=cfg.base_url or None,
            temperature=temperature,
            streaming=streaming,
        )

    def enforce_quota(self, user: User, cfg: ResolvedConfig, db: Session) -> None:
        """额度检查：公司预算 + 员工个人限额。个人 API 不计公司额度。"""
        if cfg.source == "personal":
            logger.debug("[enforce_quota] 个人 API 跳过额度检查: user_id=%s", user.id)
            return

        period = datetime.utcnow().strftime("%Y-%m")
        logger.info(
            "[enforce_quota] 检查额度: user_id=%s, source=%s, period=%s",
            user.id, cfg.source, period,
        )

        # 公司月度预算
        company_cfg = (
            db.query(CompanyLlmConfig)
            .filter_by(company_id=user.company_id)
            .first()
            if user.company_id
            else None
        )
        if company_cfg and company_cfg.monthly_budget > 0:
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            used = (
                db.query(LlmUsageRecord)
                .filter(
                    LlmUsageRecord.company_id == user.company_id,
                    LlmUsageRecord.source == "company",
                    LlmUsageRecord.created_at >= month_start,
                )
                .with_entities(LlmUsageRecord.cost)
                .all()
            )
            total = sum(r[0] for r in used)
            logger.info(
                "[enforce_quota] 公司预算: company_id=%s, 已用=$%.4f, 预算=$%.2f",
                user.company_id, total, company_cfg.monthly_budget,
            )
            if total >= company_cfg.monthly_budget:
                logger.warning(
                    "[enforce_quota] 公司预算超限: company_id=%s, 已用=$%.4f >= 预算=$%.2f",
                    user.company_id, total, company_cfg.monthly_budget,
                )
                raise QuotaExceeded(f"公司月度预算已用尽（${total:.2f}/${company_cfg.monthly_budget:.2f}）")
        else:
            logger.debug(
                "[enforce_quota] 无公司预算限制或无公司: company_id=%s",
                user.company_id,
            )

        # 员工个人限额
        quota = (
            db.query(LlmQuota)
            .filter_by(user_id=user.id, period=period)
            .first()
        )
        if quota and quota.quota_limit > 0 and quota.used >= quota.quota_limit:
            logger.warning(
                "[enforce_quota] 员工额度超限: user_id=%s, 已用=$%.4f >= 限额=$%.2f",
                user.id, quota.used, quota.quota_limit,
            )
            raise QuotaExceeded(f"你的月度额度已用尽（${quota.used:.2f}/${quota.quota_limit:.2f}）")
        elif quota:
            logger.info(
                "[enforce_quota] 员工额度: user_id=%s, 已用=$%.4f / 限额=$%.2f, status=%s",
                user.id, quota.used, quota.quota_limit, quota.status,
            )
        else:
            logger.debug("[enforce_quota] 员工无月度额度记录: user_id=%s", user.id)

    def record_usage(
        self,
        user: User,
        cfg: ResolvedConfig,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        db: Session,
    ) -> float:
        """记账：写 llm_usage_records + 更新 llm_quotas.used。返回估算费用。"""
        cost = _estimate_cost(model, prompt_tokens, completion_tokens)
        logger.info(
            "[record_usage] 记账: user_id=%s, source=%s, provider=%s, model=%s, "
            "prompt_tokens=%d, completion_tokens=%d, cost=$%.6f",
            user.id, cfg.source, cfg.provider, model,
            prompt_tokens, completion_tokens, cost,
        )

        record = LlmUsageRecord(
            user_id=user.id,
            company_id=user.company_id,
            source=cfg.source,
            provider=cfg.provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
        )
        db.add(record)

        # 公司来源累计到员工月度额度
        if cfg.source == "company":
            period = datetime.utcnow().strftime("%Y-%m")
            quota = (
                db.query(LlmQuota)
                .filter_by(user_id=user.id, period=period)
                .first()
            )
            if quota:
                before = quota.used
                quota.used = round(quota.used + cost, 4)
                logger.info(
                    "[record_usage] 累计员工额度: user_id=%s, $%.4f -> $%.4f (限额 $%.2f)",
                    user.id, before, quota.used, quota.quota_limit,
                )
                if quota.quota_limit > 0 and quota.used >= quota.quota_limit:
                    quota.status = "exceeded"
                    logger.warning(
                        "[record_usage] 员工额度达到上限，标记 exceeded: user_id=%s",
                        user.id,
                    )
            else:
                logger.debug(
                    "[record_usage] 公司来源但员工无额度记录，未累计: user_id=%s",
                    user.id,
                )

        db.commit()
        logger.debug(
            "[record_usage] 记账完成: user_id=%s, cost=$%.6f",
            user.id, cost,
        )
        return cost


gateway = LLMGateway()
