"""V4 outcome-aware ranking on top of V3: boost evidence from proposals that won or got replies."""
from rag.pipeline import Flags, Pipeline, RetrievalQuery

FLAGS = Flags(decompose=True, hybrid=True, rerank=True, outcome_aware=True)


def build(index, cfg, reranker=None, grader=None) -> Pipeline:
    return Pipeline(index, cfg, FLAGS, reranker=reranker, grader=grader)


def retrieve(query: RetrievalQuery, index, cfg, k: int = 5, reranker=None):
    return build(index, cfg, reranker).retrieve(query, k)
