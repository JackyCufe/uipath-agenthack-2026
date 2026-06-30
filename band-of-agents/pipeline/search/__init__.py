from .embedding_search import EmbeddingSearch, Embedder, IndexReader, SearchResult

# SearchService 是公开别名 — 调用者不需要知道内部是 embedding 实现
SearchService = EmbeddingSearch

__all__ = ["EmbeddingSearch", "Embedder", "IndexReader", "SearchResult", "SearchService"]
