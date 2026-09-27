from typing import List, Dict, Any


class RAGService:
    def __init__(self) -> None:
        self._built = False

    async def index_rules(self, items: List[Dict[str, Any]]) -> None:
        """把法条/案例切分 → embedding → 入库（D3 起接 chromadb）。"""
        self._built = True

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """检索相关法条/案例，骨架阶段返回空列表。"""
        return []
