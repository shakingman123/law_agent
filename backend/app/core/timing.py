"""分段计时诊断工具。

用法：在请求入口创建 StageReport，各分段用 report.stage("名称") 包裹，
请求结束时调用 report.finish() 输出单行汇总日志：

    [耗时诊断] total=38.2s | 历史加载=0.15s | RAG检索=4.2s | LLM生成=25.3s

- report.stage() 返回同步/异步双模式上下文（with / async with 均可）
- report.child("父段", "子段") 用于嵌套细分（如 RAG 内的 embed/search）
- 线上可凭 TIMING_DISABLED=1 环境变量一键关闭，零开销
"""
from __future__ import annotations

import os
import time
from typing import Optional

_DISABLED = os.getenv("TIMING_DISABLED") == "1"


class _Stage:
    """同步/异步双模式计时上下文。"""

    def __init__(self, sink: list, name: str):
        self._sink = sink
        self._name = name
        self._t = 0.0

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._sink.append((self._name, time.perf_counter() - self._t))
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return self.__exit__(exc_type, exc, tb)


class _DisabledStage:
    """TIMING_DISABLED=1 时的直通占位。"""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class StageReport:
    """收集一次请求内所有分段的耗时，结束时输出单行诊断日志。"""

    def __init__(self, label: str, msg_id: Optional[str] = None):
        self.label = label
        self.msg_id = msg_id
        self._t0 = time.perf_counter()
        self._stages: list[tuple[str, float]] = []
        # 嵌套子段：{父段: [(子段, 耗时), ...]}
        self._children: dict[str, list[tuple[str, float]]] = {}

    @staticmethod
    def _fmt(seconds: float) -> str:
        return f"{seconds:.2f}s" if seconds >= 0.1 else f"{seconds * 1000:.0f}ms"

    def stage(self, name: str):
        """同步/异步通用分段计时。with / async with 均可。"""
        if _DISABLED:
            return _DisabledStage()
        return _Stage(self._stages, name)

    def child(self, parent: str, name: str):
        """父段内的子段计时，汇总时以 RAG检索(embed=3.8s,search=0.4s) 形式附加。"""
        if _DISABLED:
            return _DisabledStage()
        return _Stage(self._children.setdefault(parent, []), name)

    def finish(self, extra: Optional[str] = None) -> float:
        """输出诊断日志并返回总耗时。"""
        total = time.perf_counter() - self._t0
        if _DISABLED:
            return total
        parts = []
        for name, cost in self._stages:
            seg = f"{name}={self._fmt(cost)}"
            kids = self._children.get(name)
            if kids:
                seg += "(" + ",".join(f"{k}={self._fmt(c)}" for k, c in kids) + ")"
            parts.append(seg)
        # 子段父段名不在主列表时（如按检索源细分），附加到末尾
        for parent, kids in self._children.items():
            if parent not in dict(self._stages) and kids:
                parts.append(parent + "(" + ",".join(f"{k}={self._fmt(c)}" for k, c in kids) + ")")
        line = f"[耗时诊断] {self.label}" + (f" msg_id={self.msg_id}" if self.msg_id else "")
        line += f" total={self._fmt(total)}"
        if parts:
            line += " | " + " | ".join(parts)
        if extra:
            line += f" | {extra}"
        print(line, flush=True)
        return total
