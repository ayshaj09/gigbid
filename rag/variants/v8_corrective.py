"""V8 corrective RAG on top of V3: grade evidence per requirement, re-query when weak, refuse to claim when none."""
from rag.pipeline import Flags, Pipeline, RetrievalQuery

FLAGS = Flags(decompose=True, hybrid=True, rerank=True, corrective=True)


def build(index, cfg, reranker=None, grader=None) -> Pipeline:
    return Pipeline(index, cfg, FLAGS, reranker=reranker, grader=grader)


def retrieve(query: RetrievalQuery, index, cfg, k: int = 5, reranker=None):
    return build(index, cfg, reranker).retrieve(query, k)
