"""安全相关：密码哈希、JWT 签发/校验、API Key 加解密与掩码。"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
import bcrypt

from app.core.config import settings

# ---- 密码哈希（直接使用 bcrypt 库，弃用 passlib）----
# 弃用原因：passlib 1.7.4 已停止维护，其初始化自检（detect_wrap_bug）向 bcrypt 库
# 传入 100 字节固定测试串，bcrypt >= 4.0 对超 72 字节输入直接抛 ValueError，
# 导致后端初始化失败、所有密码哈希/校验 500（与用户密码长短无关）。

# bcrypt 算法硬限制：输入最长 72 字节（UTF-8 下一个汉字占 3 字节，即约 24 个汉字）。
# 哈希与校验前统一按整字符截断，保证两侧逻辑一致、且永不超限。
_BCRYPT_MAX_BYTES = 72


def _bcrypt_safe(password: str) -> bytes:
    """将密码截断到 UTF-8 编码不超过 72 字节（按整字符截断，不切半个字），返回字节串。"""
    if len(password.encode("utf-8")) <= _BCRYPT_MAX_BYTES:
        return password.encode("utf-8")
    while len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        password = password[:-1]
    return password.encode("utf-8")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_safe(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_safe(plain), hashed.encode("utf-8"))
    except ValueError:
        # 库中哈希格式非法等情况一律视为校验失败
        return False


# ---- JWT（python-jose）----
def create_access_token(subject: str | int, expires_minutes: Optional[int] = None) -> str:
    minutes = expires_minutes if expires_minutes is not None else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    to_encode = {"exp": expire, "sub": str(subject)}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


# ---- LLM API Key 加解密（cryptography Fernet，AES）----
def _fernet_key() -> bytes:
    """返回合法的 Fernet key。

    若配置项本身已是合法 Fernet key 则直接使用；否则基于其 SHA256 派生 32 字节
    url-safe base64 key（保证开发环境任意字符串均可运行）。
    """
    raw = settings.LLM_ENCRYPTION_KEY.encode()
    try:
        Fernet(raw)
        return raw
    except (ValueError, TypeError):
        digest = hashlib.sha256(raw).digest()
        return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_fernet_key())


def encrypt_api_key(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def mask_api_key(plaintext: str) -> str:
    """生成掩码：sk-••••f2a（前缀 + 4 个圆点 + 末 3 位）。

    - 以 'sk-' 开头的 key 保留 3 位前缀；
    - 其它 key 保留 2 位前缀；
    - 长度不足 7 位时统一返回 '••••'。
    """
    if not plaintext:
        return ""
    if len(plaintext) <= 6:
        return "••••"
    prefix = plaintext[:3] if plaintext.startswith("sk-") else plaintext[:2]
    suffix = plaintext[-3:]
    return f"{prefix}••••{suffix}"
