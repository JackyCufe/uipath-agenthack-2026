"""
EmbeddingSearch —语义检索服务。

三阶段管线：keyword过滤 → embedding匹配 →返回TopK。

不直接依赖 Bitable，而是通过 IndexReader 协议解耦。
"""

from __future__ import annotations

import json
import os
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


# -- 数据结构 ------------------------------------------------------------------

@dataclass
class SearchResult:
    """单条检索结果。"""
    req_id: str
    similarity: float                # 0.0-1.0 cosine
    stage_label: str = ""            # 当前所处阶段
    verdict: str = ""                # 最近一次判定
    reject_reason: str = ""          # 如果被拒过
    keyword_tags: list[str] = field(default_factory=list)
    wiki_link: str = ""
    summary: str = ""                # 一句话摘要


# -- 索引读取协议（解耦 Bitable）------------------------------------------------


class IndexReader(Protocol):
    """检索层只需要这个接口，不关心底层是 Bitable还是其他。"""

    def keyword_filter(self, keywords: list[str], limit: int = 20) -> list[dict[str, Any]]:
        """根据关键词过滤，返回候选行列表。每行至少含：
        req_id, stage_label, verdict, reject_reason,
        keyword_tags, searchable_text, embedding_vector (JSON string), wiki_link
        """
        ...


# -- 嵌入生成 ----------------------------------------------------------------


class Embedder:
    """用 LLM 生成文本嵌入向量 + 提取关键词。"""

    def __init__(self, llm_client: Any, model: str = "claude-sonnet-4-20250514"):
        self._client = llm_client
        self._model = model
        # Auto-detect client type
        self._is_openai = hasattr(llm_client, 'chat') and hasattr(llm_client.chat, 'completions')

    def _call_llm(self, prompt: str, max_tokens: int) -> str:
        """统一 LLM 调用，兼容 Anthropic 和 OpenAI/DeepSeek。"""
        if self._client is None:
            return ""
        if self._is_openai:
            resp = self._client.chat.completions.create(
                model=self._model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content or ""
        else:
            resp = self._client.messages.create(
                model=self._model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text

    def embed(self, text: str) -> list[float]:
        """用智谱GLM embedding-3生成真实向量。"""
        try:
            import requests as _req
            # 智谱GLM embedding API
            api_key = os.environ.get("ZHIPU_API_KEY", "")
            if not api_key:
                # 从config读取
                try:
                    from config import ZHIPU_API_KEY as _zk
                    api_key = _zk
                except (ImportError, AttributeError):
                    pass
            if not api_key:
                # DEEPV.md中记录的key
                api_key = "20746b76dc8c41efab48bfc6f4fa1b88.cqOfA4BCLr6VZzHE"

            resp = _req.post(
                "https://open.bigmodel.cn/api/paas/v4/embeddings",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": "embedding-3", "input": text[:2000]},
                timeout=10,
            )
            data = resp.json()
            if data.get("code") == 200 or "data" in data:
                vec = data.get("data", [{}])[0].get("embedding", [])
                if vec:
                    return [float(v) for v in vec]
            # fallback: 尝试OpenAI兼容格式
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                vec = data["data"][0].get("embedding", [])
                if vec:
                    return [float(v) for v in vec]
            print(f"[Embedder] GLM embedding返回异常: {str(data)[:200]}")
        except Exception as e:
            print(f"[Embedder] GLM embedding调用失败: {e}")
        return [0.0] * 1024

    def extract_keywords(self, text: str) -> list[str]:
        """从文本中提取检索关键词。"""
        raw = self._call_llm(
            "从以下需求文本中提取 3-8 个检索关键词（中文+英文均可）。"
            "优先提取：功能模块名、技术栈、问题类型、客户名。"
            "用 JSON 字符串数组返回，只需要数组。\n\n"
            f"文本：{text[:2000]}",
            max_tokens=512,
        ).strip()
        try:
            kw = json.loads(raw)
            if isinstance(kw, list):
                return [str(k) for k in kw][:8]
        except json.JSONDecodeError:
            pass

        import re
        match = re.search(r'\[([^\]]+)\]', raw)
        if match:
            try:
                items = json.loads(f'[{match.group(1)}]')
                return [str(k) for k in items][:8]
            except (json.JSONDecodeError, ValueError):
                pass

        # fallback: 简单分词（LLM失败时）
        import re
        # 提取2-4字的中文词和英文单词
        words = re.findall(r'[\u4e00-\u9fa5]{2,4}|[a-zA-Z]{3,}', text)
        return words[:8] if words else [text[:4]]


# -- 检索服务 ------------------------------------------------------------------


class EmbeddingSearch:
    """语义检索主入口。

    用法：
        search = EmbeddingSearch(llm_client, index_reader)
        results = search.find_similar("首页加载慢")
    """

    def __init__(self, llm_client: Any, index_reader: IndexReader, model: str = ""):
        self._embedder = Embedder(llm_client, model=model or "deepseek-v4-flash")
        self._index = index_reader

    def find_similar(self, query_text: str, top_k: int = 3) -> list[SearchResult]:
        """查相似需求历史。无 LLM 时返回空。"""
        if self._embedder._client is None:
            return []

        # Phase 1: 关键词过滤 → 缩到候选 ≤20
        keywords = self._embedder.extract_keywords(query_text)
        candidates = self._index.keyword_filter(keywords, limit=20)

        if not candidates:
            return []

        # Phase 2: GLM embedding + cosine相似度
        query_vec = self._embedder.embed(query_text)
        if all(v == 0 for v in query_vec):
            # embedding失败，fallback到关键词匹配
            scored = []
            for row in candidates[:20]:
                cand_text = row.get("searchable_text", "") or row.get("summary", "")
                sim = 0.0
                for kw in keywords:
                    if kw.lower() in cand_text.lower():
                        sim += 0.3
                if sim > 0:
                    scored.append((sim, row))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:top_k]
        else:
            scored = []
            for row in candidates[:20]:
                cand_text = row.get("searchable_text", "") or row.get("summary", "")
                if not cand_text:
                    continue
                cand_vec = self._embedder.embed(cand_text[:500])
                if all(v == 0 for v in cand_vec):
                    continue
                sim = self._cosine_similarity(query_vec, cand_vec)
                scored.append((sim, row))
            scored.sort(key=lambda x: x[0], reverse=True)
            top = scored[:top_k]

        return [
            SearchResult(
                req_id=row.get("req_id", ""),
                similarity=round(sim, 4),
                stage_label=row.get("stage_label", ""),
                verdict=row.get("verdict", ""),
                reject_reason=row.get("reject_reason", ""),
                keyword_tags=row.get("keyword_tags", []),
                wiki_link=row.get("wiki_link", ""),
                summary=row.get("searchable_text", "")[:200],
            )
            for sim, row in top
        ]

    # -- 内部工具 -------------------------------------------------------------

    @staticmethod
    def _parse_vector(raw: str | list | None) -> list[float]:
        """解析 embedding_vector 字段（可能是 JSON string 或 list）。"""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [float(v) for v in raw]
        if isinstance(raw, str) and raw.strip():
            try:
                return [float(v) for v in json.loads(raw)]
            except (json.JSONDecodeError, ValueError):
                pass
        return []

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine 相似度。维度不对齐时截断。"""
        n = min(len(a), len(b))
        if n == 0:
            return 0.0
        dot = sum(a[i] * b[i] for i in range(n))
        norm_a = math.sqrt(sum(x * x for x in a[:n]))
        norm_b = math.sqrt(sum(x * x for x in b[:n]))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
