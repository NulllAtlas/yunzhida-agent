"""
RAG 检索服务（M2）。

- 默认（无 chromadb / 未配置）使用内置法条/案例关键词检索，保证链路可用；
- 配置开启后又可用时，走 chromadb 持久化向量检索（使用轻量本地 n-gram
  embedding，无需下载模型，离线可用）。
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings
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

_KEYWORDS = ("追尾", "变道", "路口", "让行", "超速", "灯")


def _keyword_retrieve(query: str, top_k: int) -> list[RetrievedDoc]:
    """基于关键词的简单打分检索（兜底）。"""
    scored = []
    for doc in _LAW_POOL:
        score = 0.0
        for token in _KEYWORDS:
            if token in query:
                if token in doc["content"]:
                    score += 1.0
                else:
                    score += 0.2
        if score == 0 and ("事故" in query or "碰撞" in query):
            score = 0.1
        scored.append((score, doc))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        RetrievedDoc(id=d["id"], title=d["title"], content=d["content"],
                     source=d["source"], score=s)
        for s, d in scored[:top_k] if s > 0
    ]


class _NGramEmbedding:
    """轻量本地 embedding：char n-gram 哈希特征向量，无需下载模型。"""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return [self._encode(t) for t in input]

    def _encode(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        grams = set()
        norm = text.lower()
        for n in (1, 2, 3):
            for i in range(len(norm) - n + 1):
                grams.add(norm[i:i + n])
        for g in grams:
            vec[hash(g) % self.dim] += 1.0
        total = sum(vec) or 1.0
        return [v / total for v in vec]


class RagService:
    def __init__(self) -> None:
        self._pool = _LAW_POOL
        self._client: Any = None
        self._collection: Any = None
        self._try_init_chroma()

    def _try_init_chroma(self) -> None:
        """尝试初始化 chromadb（失败则保持 None，走关键词兜底）。"""
        try:
            import chromadb  # noqa: PLC0415
            from chromadb.config import Settings as ChromaSettings  # noqa: PLC0415

            self._client = chromadb.PersistentClient(
                path=settings.chroma_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name="roadmind",
                embedding_function=_NGramEmbedding(),
            )
            if self._collection.count() == 0:
                self._try_seed()
        except Exception:  # noqa: BLE001
            self._client = None
            self._collection = None

    def _try_seed(self) -> None:
        """首次使用时把内置规则库写入 chromadb（可被 index_rules.py 覆盖扩充）。"""
        try:
            self._collection.add(
                ids=[d["id"] for d in self._pool],
                documents=[d["content"] for d in self._pool],
                metadatas=[{"title": d["title"], "source": d["source"]} for d in self._pool],
            )
        except Exception:  # noqa: BLE001
            pass

    def add_docs(self, docs: list[dict]) -> int:
        """新增/覆盖文档（供 index_rules.py 调用）。id 重复会自动覆盖。"""
        if self._collection is None:
            added = 0
            known = {d["id"] for d in self._pool}
            for d in docs:
                if d["id"] not in known:
                    self._pool.append(d)
                    known.add(d["id"])
                    added += 1
            return added
        self._collection.upsert(
            ids=[d["id"] for d in docs],
            documents=[d["content"] for d in docs],
            metadatas=[{"title": d["title"], "source": d["source"]} for d in docs],
        )
        return len(docs)

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedDoc]:
        """向量检索（chromadb 可用时），否则关键词兜底。"""
        if self._collection is not None and query:
            try:
                res = self._collection.query(
                    query_texts=[query], n_results=min(top_k, 10),
                    include=["documents", "metadatas", "distances"],
                )
                docs, metas, dists = res["documents"][0], res["metadatas"][0], res["distances"][0]
                return [
                    RetrievedDoc(
                        id=str(meta.get("_id", f"doc-{i}")),
                        title=meta.get("title", ""),
                        content=text,
                        source=meta.get("source", "law"),
                        score=1.0 - float(d),
                    )
                    for i, (text, meta, d) in enumerate(zip(docs, metas, dists))
                    if text
                ]
            except Exception:  # noqa: BLE001
                pass
        return _keyword_retrieve(query, top_k)


rag_service = RagService()
