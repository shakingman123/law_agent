"""一次性迁移：用显式 ONNXMiniLM_L6_V2 重新嵌入所有 Chroma 集合。

背景：历史文档向量由 chroma "default" embedding function 生成，该 EF 在不同进程
可能解析到不同模型，导致查询向量与入库向量不一致（参考资料错误/漏检）。
store.py 现已显式使用 ONNXMiniLM_L6_V2，本脚本把存量文档全部按新 EF 重嵌入。

用法（在 backend 目录、激活 venv 后执行）：
    python migrate_reembed.py           # 仅重嵌入
    python migrate_reembed.py --check   # 只检查是否需要重嵌入，不做改动

幂等：可重复执行；全程不修改文档原文与元数据，仅重建向量。
"""
import sys

from app.rag.store import EMBEDDING_FN, _get_client


def check_only(client) -> bool:
    """自洽性检查：任一集合用原文查询距离应≈0。返回是否全部一致。"""
    all_ok = True
    for info in client.list_collections():
        col = client.get_collection(info.name)
        if col.count() == 0:
            print(f"[检查] {info.name}: 空集合，跳过")
            continue
        sample = col.get(limit=min(3, col.count()), include=["documents"])
        for doc in sample["documents"]:
            res = col.query(query_texts=[doc], n_results=1, include=["distances"])
            dist = res["distances"][0][0]
            ok = dist < 0.01
            all_ok = all_ok and ok
            print(f"[检查] {info.name}: 原文查询距离={dist:.4f} {'OK' if ok else '不一致!'}")
            if not ok:
                break
    return all_ok


def reembed(client) -> None:
    for info in client.list_collections():
        name = info.name
        old = client.get_collection(name)
        data = old.get(include=["documents", "metadatas"])
        docs = data.get("documents") or []
        metas = data.get("metadatas") or []
        ids = data.get("ids") or []
        client.delete_collection(name)
        new = client.get_or_create_collection(
            name=name,
            embedding_function=EMBEDDING_FN,
            configuration={"hnsw": {"space": "cosine"}},
        )
        if docs:
            # 分批写入，避免大集合单次请求过大
            batch = 256
            for i in range(0, len(docs), batch):
                new.add(
                    documents=docs[i : i + batch],
                    metadatas=metas[i : i + batch],
                    ids=ids[i : i + batch],
                )
        print(f"[迁移] {name}: 重嵌入完成 count={new.count()}")


def main() -> None:
    client = _get_client()
    if "--check" in sys.argv:
        ok = check_only(client)
        print("\n结论:", "向量一致，无需迁移" if ok else "存在向量不一致，请执行: python migrate_reembed.py")
    else:
        reembed(client)
        print("\n自洽性验证:")
        check_only(client)


if __name__ == "__main__":
    main()
