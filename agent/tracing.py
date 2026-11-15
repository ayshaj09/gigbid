"""Tracing (E3): one trace per job run, carrying the same trace id the MCP audit log records.

* Langfuse (self-hostable, open source): set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
  LANGFUSE_HOST. A CallbackHandler is attached to every graph run.
* LangSmith: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY; LangChain picks it up itself.
Nothing is attached when neither is configured.
"""
from __future__ import annotations

import os


def callbacks(trace_id: str, user_id: str, thread_id: str) -> list:
    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return []
    try:
        from langfuse.langchain import CallbackHandler
    except ImportError:
        return []
    return [CallbackHandler()]


def run_metadata(trace_id: str, user_id: str, thread_id: str) -> dict:
    return {"trace_id": trace_id, "langfuse_user_id": user_id, "langfuse_session_id": thread_id,
            "langfuse_tags": ["gigbid"]}
