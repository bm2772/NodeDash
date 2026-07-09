"""Per-node semantic cache (RAG).

When a department agent is prompted, we embed the query, find the most similar
past exchanges for that node, and inject them into the agent's context so it
answers consistently with what it said before. Everything degrades gracefully:
if embeddings are unavailable (mock mode, no embed model), retrieval returns
nothing and storage is skipped, so the agent still works.

Vectors are stored as JSON in SQLite and compared with brute-force cosine
similarity — fine for the modest number of exchanges a node accumulates.
"""
import math
from typing import Optional

from sqlalchemy.orm import Session

from . import llm
from .config import settings
from .models import AgentMemory


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def embed_query(text: str) -> Optional[list[float]]:
    """Embed a query, or None if embeddings aren't configured/available."""
    if not settings.embeddings_enabled:
        return None
    try:
        return llm.embed(text)
    except llm.LLMError:
        return None


def retrieve(
    db: Session,
    workspace_id: str,
    node_key: str,
    query_vec: Optional[list[float]],
    *,
    top_k: Optional[int] = None,
    threshold: Optional[float] = None,
) -> list[tuple[float, AgentMemory]]:
    """Top-k past exchanges for this node above the similarity threshold."""
    if not query_vec:
        return []
    top_k = top_k or settings.rag_top_k
    threshold = settings.rag_threshold if threshold is None else threshold
    rows = (
        db.query(AgentMemory)
        .filter(AgentMemory.workspace_id == workspace_id, AgentMemory.node_key == node_key)
        .all()
    )
    scored = [
        (_cosine(query_vec, r.embedding), r) for r in rows if r.embedding
    ]
    scored = [pair for pair in scored if pair[0] >= threshold]
    scored.sort(key=lambda p: p[0], reverse=True)
    return scored[:top_k]


def build_context(scored: list[tuple[float, AgentMemory]]) -> str:
    """Render retrieved exchanges as a context block for the system prompt."""
    if not scored:
        return ""
    lines = [
        "Relevant past exchanges for this department (stay consistent with them; "
        "do not contradict prior commitments):"
    ]
    for _score, r in scored:
        lines.append(f"- Q: {r.query}\n  A: {r.response}")
    return "\n".join(lines)


def store(
    db: Session,
    workspace_id: str,
    node_key: str,
    query: str,
    response: str,
    query_vec: Optional[list[float]],
) -> Optional[AgentMemory]:
    """Cache a new exchange (added to the session; caller commits). No-op without a vector."""
    if not query_vec:
        return None
    mem = AgentMemory(
        workspace_id=workspace_id,
        node_key=node_key,
        query=query,
        response=response,
        embedding=query_vec,
    )
    db.add(mem)
    return mem
