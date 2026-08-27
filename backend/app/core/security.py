"""安全相关：密码哈希、JWT 签发/校验、API Key 加解密与掩码。"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ---- 密码哈希（passlib bcrypt）----
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt 算法硬限制：输入最长 72 字节（UTF-8 下一个汉字占 3 字节，即约 24 个汉字）
# 新版 bcrypt 超限直接抛 ValueError 导致 500，故统一按字节安全截断后再哈希/校验，
# 保证哈希与校验使用同一截断逻辑、互相一致。
_BCRYPT_MAX_BYTES = 72


def _bcrypt_safe(password: str) -> str:
    """将密码截断到 UTF-8 编码不超过 72 字节（按整字符截断，不切半个字）。"""
    if len(password.encode("utf-8")) <= _BCRYPT_MAX_BYTES:
        return password
    while len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        password = password[:-1]
    return password


def hash_password(password: str) -> str:
    return pwd_context.hash(_bcrypt_safe(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_bcrypt_safe(plain), hashed)


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
