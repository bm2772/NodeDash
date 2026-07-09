"""Per-node agent runtime + the cross-node message bus.

An agent is that node's system prompt (from provisioning) plus the guardrails,
invoked against a real LLM when configured, or a deterministic stub otherwise.
When emit_handoffs is set, the agent also posts messages down its outgoing edges
— the beginnings of the edge-negotiation loop from the spec.
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import gpu_manager, llm, rag
from ..bus import manager
from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import get_current_user, require_node_access, require_workspace_member
from ..models import Edge, Message, Node, User, Workspace

router = APIRouter(prefix="/workspace/{workspace_id}", tags=["agents"])


def _pick_target() -> tuple[str, object, object, object]:
    """Choose where this turn runs. Returns (served_by, base_url, api_key, model);
    None values mean 'use the default fallback endpoint'. Wakes the GPU in the
    background when it's cold so the *next* turn can use it."""
    if gpu_manager.manager.is_ready():
        gpu_manager.manager.touch()
        return "amd-mi300x", gpu_manager.manager.target_base_url(), (settings.gpu_api_key or None), settings.gpu_model
    gpu_manager.manager.request_wake()  # no-op unless GPU management is enabled
    return "fallback", None, None, None


def _agent_reply(node: Node, guardrails: dict, user_message: str, memory_context: str = "") -> tuple[str, str]:
    """Returns (reply_text, served_by). served_by ∈ {amd-mi300x, fallback, mock}."""
    system = (
        node.agent_system_prompt
        + f"\n\nGuardrails: {guardrails}. Respond concisely as this node's Chief of Staff."
    )
    if memory_context:
        system += "\n\n" + memory_context
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_message}]

    served_by, base_url, api_key, model = _pick_target()
    if settings.llm_enabled or served_by == "amd-mi300x":
        try:
            text = llm.chat(
                messages, temperature=0.3, max_tokens=600,
                base_url=base_url, api_key=api_key, model=model,
            ).strip()
            return text, served_by
        except llm.LLMError as exc:
            # GPU hiccup → fall back to the always-on endpoint if we have one
            if served_by == "amd-mi300x" and settings.llm_enabled:
                try:
                    return llm.chat(messages, temperature=0.3, max_tokens=600).strip(), "fallback"
                except llm.LLMError as exc2:
                    exc = exc2
            return f"[agent offline: {exc}] Acknowledged: {user_message}", served_by
    # Deterministic offline stub so the demo works without an endpoint.
    stub = (
        f"[{node.name} agent] Acknowledged: '{user_message}'. "
        f"Per my '{node.autonomy_level}' autonomy and the "
        f"'{guardrails.get('delay_handling_protocol', 'auto-renegotiate-then-alert')}' protocol, "
        f"I will update my plan and notify affected neighbours."
    )
    return stub, "mock"


def _rag_answer(db: Session, workspace_id: str, node: Node, guardrails: dict, user_message: str):
    """RAG-wrapped agent turn: retrieve similar past exchanges → inject → answer → cache."""
    qvec = rag.embed_query(user_message)
    scored = rag.retrieve(db, workspace_id, node.node_key, qvec)
    context = rag.build_context(scored)
    reply, served_by = _agent_reply(node, guardrails, user_message, context)
    rag.store(db, workspace_id, node.node_key, user_message, reply, qvec)
    used = [
        {"query": r.query, "response": r.response, "score": round(s, 3)} for s, r in scored
    ]
    return reply, used, served_by


@router.post("/nodes/{node_key}/agent/invoke")
async def invoke_agent(
    workspace_id: str,
    node_key: str,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_node_access(workspace_id, node_key, user)
    node = db.query(Node).filter(
        Node.workspace_id == workspace_id, Node.node_key == node_key
    ).first()
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found")
    ws = db.get(Workspace, workspace_id)
    guardrails = ws.agent_guardrails if ws else {}
    user_message = str(body.get("message", "")).strip()
    if not user_message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "message is required")
    emit_handoffs = bool(body.get("emit_handoffs", False))

    reply_text, used_memory, served_by = await run_in_threadpool(
        _rag_answer, db, workspace_id, node, guardrails, user_message
    )

    reply = Message(
        workspace_id=workspace_id, from_node_key=node_key, to_node_key=None,
        action_type="agent_reply", body=reply_text,
        payload={"prompt": user_message, "used_memory": used_memory, "served_by": served_by},
    )
    db.add(reply)

    emitted = []
    if emit_handoffs:
        out_edges = db.query(Edge).filter(
            Edge.workspace_id == workspace_id, Edge.source_node_key == node_key
        ).all()
        for e in out_edges:
            msg = Message(
                workspace_id=workspace_id, edge_key=e.edge_key,
                from_node_key=node_key, to_node_key=e.target_node_key,
                action_type=e.action_type,
                body=f"{node.name} → {e.target_node_key}: {e.action_type}",
                payload={"required_data_payload": e.required_data_payload},
            )
            db.add(msg)
            emitted.append(msg)

    db.commit()
    db.refresh(reply)

    def _ser(m: Message) -> dict:
        return {
            "id": m.id, "edge_key": m.edge_key, "from": m.from_node_key,
            "to": m.to_node_key, "action_type": m.action_type,
            "body": m.body, "payload": m.payload,
        }

    for m in [reply, *emitted]:
        db.refresh(m)
        await manager.broadcast(workspace_id, _ser(m))

    return {
        "reply": _ser(reply),
        "handoffs": [_ser(m) for m in emitted],
        "used_memory": used_memory,
        "served_by": served_by,
    }


@router.get("/messages")
def list_messages(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_workspace_member(workspace_id, user)
    msgs = (
        db.query(Message)
        .filter(Message.workspace_id == workspace_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return {
        "messages": [
            {
                "id": m.id, "edge_key": m.edge_key, "from": m.from_node_key,
                "to": m.to_node_key, "action_type": m.action_type,
                "body": m.body, "payload": m.payload,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ]
    }


@router.websocket("/ws")
async def workspace_ws(websocket: WebSocket, workspace_id: str) -> None:
    """Live feed of the message bus. Token passed as ?token= query param."""
    token = websocket.query_params.get("token", "")
    from ..security import decode_token

    claims = decode_token(token, settings.jwt_secret) if token else None
    if not claims or claims.get("workspace_id") != workspace_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    # verify the user still exists
    db = SessionLocal()
    try:
        if not db.get(User, claims.get("sub")):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    finally:
        db.close()

    await manager.connect(workspace_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive / ignore inbound
    except WebSocketDisconnect:
        manager.disconnect(workspace_id, websocket)
