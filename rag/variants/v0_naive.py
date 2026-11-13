"""V0 baseline (required): naive dense top-k cosine on the whole job post."""
from rag.pipeline import Flags, Pipeline, RetrievalQuery

FLAGS = Flags()


def build(index, cfg, reranker=None, grader=None) -> Pipeline:
    return Pipeline(index, cfg, FLAGS, reranker=reranker, grader=grader)


def retrieve(query: RetrievalQuery, index, cfg, k: int = 5, reranker=None):
    return build(index, cfg, reranker).retrieve(query, k)
