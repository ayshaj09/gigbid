"""V1 requirement decomposition: one dense retrieval per extracted requirement, merged by RRF."""
from rag.pipeline import Flags, Pipeline, RetrievalQuery

FLAGS = Flags(decompose=True)


def build(index, cfg, reranker=None, grader=None) -> Pipeline:
    return Pipeline(index, cfg, FLAGS, reranker=reranker, grader=grader)


def retrieve(query: RetrievalQuery, index, cfg, k: int = 5, reranker=None):
    return build(index, cfg, reranker).retrieve(query, k)
