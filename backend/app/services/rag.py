"""
RAG 检索服务（M2）。

MVP 阶段：返回内置法条/案例模板（纯内存），保证链路可用；
迭代阶段：接入 chromadb 向量库做真实检索。
"""
from __future__ import annotations

from app.schemas.models import RetrievedDoc

# 内置规则库（法条要件 + 少量案例种子）
_LAW_POOL: list[dict] = [
    {"id": "law-043", "title": "道交法 第43条", "source": "law",
     "content": "同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离；前车正在左转弯、掉头、超车时不得超车。"},
    {"id": "law-044", "title": "实施条例 第44条", "source": "law",
     "content": "在道路同方向划有2条以上机动车道的，变更车道的机动车不得影响相关车道内行驶的机动车的正常行驶。"},
    {"id": "law-047", "title": "道交法 第47条", "source": "law",
     "content": "机动车通过没有交通信号灯、交通标志、交通标线或者交通警察指挥的交叉路口时，应当减速慢行，并让行人和优先通行的车辆先行。"},
    {"id": "law-051", "title": "实施条例 第51条", "source": "law",
     "content": "机动车通过有交通信号灯控制的交叉路口，应当按照规定通行；转弯的机动车让直行的车辆先行。"},
    {"id": "case-001", "title": "案例：追尾事故", "source": "case",
     "content": "后车未保持安全距离追尾，责任认定为后车全责。依据道交法第43条。"},
    {"id": "case-002", "title": "案例：路口转弯未让行", "source": "case",
     "content": "转弯车辆未让直行车辆导致碰撞，转弯车负主要责任，直行车辆未尽注意义务负次要责任。"},
]


class RagService:
    def __init__(self) -> None:
        self._pool = _LAW_POOL

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedDoc]:
        """MVP：基于关键词的简单打分检索。迭代阶段替换为向量检索。"""
        q = query
        scored = []
        for doc in self._pool:
            # 简单字符串包含打分
            score = 0.0
            for token in ("追尾", "变道", "路口", "让行", "超速", "灯"):
                if token in q:
                    if token in doc["content"]:
                        score += 1.0
                    else:
                        score += 0.2
            if score == 0 and ("事故" in q or "碰撞" in q):
                score = 0.1
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            RetrievedDoc(
                id=d["id"], title=d["title"], content=d["content"],
                source=d["source"], score=s,
            )
            for s, d in scored[:top_k] if s > 0
        ]


rag_service = RagService()
