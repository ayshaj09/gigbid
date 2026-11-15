"""Tests always use the hand-made fixtures, even after `datapipe.build` has produced real personas."""
import os

os.environ.setdefault("GIGBID_PERSONA_SOURCE", "fixtures")
# Tests use the cheap stand-ins (no model download, deterministic); the shipped config uses open
# models (agent/config.yaml retrieval.embedder / reranker).
os.environ.setdefault("EMBEDDER_PROVIDER", "hashing")
os.environ.setdefault("RERANKER_PROVIDER", "lexical")
