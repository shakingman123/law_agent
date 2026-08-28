"""诊断开发者账户登录问题。

在 backend 目录运行：
    python diagnose_dev.py

会输出：
1. .env 实际读到的 DEVELOPER_EMAIL / DEVELOPER_PASSWORD（用 repr 显示隐藏字符）
2. 数据库中开发者账户的 password_hash
3. 用多个候选密码逐个测试 bcrypt 匹配结果
"""
import sys
import bcrypt

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User


def main():
    print("=" * 60)
    print("1. .env 实际读取到的配置（repr 可见隐藏字符）")
    print("=" * 60)
    print(f"DEVELOPER_EMAIL    = {settings.DEVELOPER_EMAIL!r}")
    print(f"DEVELOPER_PASSWORD = {settings.DEVELOPER_PASSWORD!r}")
    print(f"密码字节数: {len(settings.DEVELOPER_PASSWORD.encode('utf-8'))}")

    print()
    print("=" * 60)
    print("2. 数据库中开发者账户的存储信息")
    print("=" * 60)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.is_developer == True).first()  # noqa: E712
        if not user:
            print("!! 数据库中没有 is_developer=True 的账户")
            print("!! 说明账户从未被播种，或 is_developer 字段未填充")
            # 顺便查一下所有邮箱里带 dev/test/lawagent 的账户
            print("\n-- 模糊匹配可能的开发者账户 --")
            candidates = (
                db.query(User)
                .filter(
                    User.email.like("%dev%")
                    | User.email.like("%test%")
                    | User.email.like("%lawagent%")
                )
                .all()
            )
            for u in candidates:
                print(f"  id={u.id} email={u.email!r} is_developer={u.is_developer}")
            return
        print(f"id            = {user.id}")
        print(f"email         = {user.email!r}")
        print(f"name          = {user.name!r}")
        print(f"is_developer  = {user.is_developer}")
        print(f"password_hash = {user.password_hash!r}")
    finally:
        db.close()

    print()
    print("=" * 60)
    print("3. 候选密码逐个测试 bcrypt 匹配")
    print("=" * 60)
    candidates = [
        "dev123456",
        "LawTest@2026#8x42",
        "LawTest@2026",
        "LawTest@2026#8x42\n",
        "LawTest@2026#8x42\r",
        " LawTest@2026#8x42",
        "LawTest@2026#8x42 ",
        settings.DEVELOPER_PASSWORD,
    ]
    stored = user.password_hash.encode("utf-8")
    matched = False
    for pwd in candidates:
        try:
            ok = bcrypt.checkpw(pwd.encode("utf-8"), stored)
        except Exception as e:
            ok = f"ERROR: {e}"
        flag = "<<<< 匹配!" if ok is True else ""
        print(f"  {pwd!r:40s} -> {ok} {flag}")
        if ok is True:
            matched = True

    print()
    if matched:
        print("结论：已找到匹配密码（见上方 <<<< 标记），用该密码登录即可。")
    else:
        print("结论：所有候选密码都不匹配。")
        print("可能原因：")
        print("  a) 账户是用一个已被修改/遗忘的密码播种的")
        print("  b) 哈希格式损坏（可看上方 password_hash 是否以 $2b$ 开头）")
        print("  c) 数据库连接指向了错误的库/表")
        print("建议：直接用脚本重置密码——见下方第 4 步")

    print()
    print("=" * 60)
    print("4. （可选）直接重置开发者密码")
    print("=" * 60)
    print("如需重置，取消下面几行注释后重新运行：")
    print("""
# import bcrypt as _bc
# new_pwd = settings.DEVELOPER_PASSWORD  # 或直接写 "LawTest@2026#8x42"
# new_hash = _bc.hashpw(new_pwd.encode("utf-8"), _bc.gensalt()).decode()
# db = SessionLocal()
# u = db.query(User).filter(User.email == settings.DEVELOPER_EMAIL).first()
# if u:
#     u.password_hash = new_hash
#     db.commit()
#     print(f"已将 {u.email} 的密码重置为 {new_pwd!r}")
# db.close()
""")


if __name__ == "__main__":
    sys.exit(main() or 0)
