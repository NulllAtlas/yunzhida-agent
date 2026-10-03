"""
index_rules.py · 把法条/案例切分并入 chromadb（M2 入库脚本）。

用法（在 backend 目录下执行）：
    python scripts/index_rules.py                      # 用内置规则库入库
    python scripts/index_rules.py --dir ../data/cases  # 从指定目录读取 .md 入库

文档格式：每个 .md 文件解析为多个条目，支持两种写法：
  1. 一个文件一条：# 标题\\n内容
  2. 多个条目：# 标题\\n内容\\n\\n## 标题\\n内容 （按二级标题切分）
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.services.rag import rag_service, _LAW_POOL


def _docs_from_builtin() -> list[dict]:
    return list(_LAW_POOL)


def _docs_from_dir(src: Path) -> list[dict]:
    docs: list[dict] = []
    for md in sorted(src.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        blocks = [b for b in text.split("\n## ") if b.strip()]
        for block in blocks:
            lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]
            if not lines:
                continue
            title = lines[0].lstrip("# ").strip()
            content = " ".join(lines[1:]) if len(lines) > 1 else title
            source = "case" if "case" in str(md).lower() else "law"
            docs.append({
                "id": f"{md.stem}-{len(docs)}",
                "title": title,
                "content": content,
                "source": source,
            })
    return docs


def main() -> None:
    parser = argparse.ArgumentParser(description="法条/案例入库脚本（M2）")
    parser.add_argument("--dir", type=str, default=None, help="案例/法条目录（含 .md）")
    args = parser.parse_args()

    docs = _docs_from_dir(Path(args.dir)) if args.dir else _docs_from_builtin()
    if not docs:
        print("没有可入库的内容。")
        return
    added = rag_service.add_docs(docs)
    print(f"入库完成：本次写入 {added} 条。")
    if rag_service._collection is not None:
        print(f"chromadb 集合共 {rag_service._collection.count()} 条。")
    else:
        print("chromadb 不可用，已写入内存规则库（关键词检索）。")


if __name__ == "__main__":
    main()
