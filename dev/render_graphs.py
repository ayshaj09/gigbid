"""Render both graphs from code (C deliverable): docs/images/*.mmd (Mermaid source)."""
from pathlib import Path

from agent.graphs.bid_graph import compile_bid_graph
from agent.graphs.conversation_graph import compile_conversation_graph

out = Path(__file__).resolve().parent.parent / "docs" / "images"
out.mkdir(parents=True, exist_ok=True)
for name, g in (("bid_graph", compile_bid_graph()), ("conversation_graph", compile_conversation_graph())):
    (out / f"{name}.mmd").write_text(g.get_graph().draw_mermaid())
    print("wrote", out / f"{name}.mmd")
