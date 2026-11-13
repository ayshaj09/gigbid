"""V2 hybrid: V1 + BM25 and dense fused with reciprocal rank fusion (exact names like Celery, dbt)."""
from rag.pipeline import Flags, Pipeline, RetrievalQuery

FLAGS = Flags(decompose=True, hybrid=True)


def build(index, cfg, reranker=None, grader=None) -> Pipeline:
    return Pipeline(index, cfg, FLAGS, reranker=reranker, grader=grader)


def retrieve(query: RetrievalQuery, index, cfg, k: int = 5, reranker=None):
    return build(index, cfg, reranker).retrieve(query, k)
