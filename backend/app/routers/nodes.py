"""The node 'window'. Everything here is gated by require_node_access: only the
seat scoped to this node (or the workspace admin) sees its config, neighbours,
and documents. This is what makes a Finance login reveal Finance data only.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_node_access
from ..models import Document, Edge, Node, User, Workspace

router = APIRouter(prefix="/workspace/{workspace_id}/nodes", tags=["node-window"])


def _get_node(db: Session, workspace_id: str, node_key: str) -> Node:
    node = (
        db.query(Node)
        .filter(Node.workspace_id == workspace_id, Node.node_key == node_key)
        .first()
    )
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found")
    return node


def _neighbours(db: Session, workspace_id: str, node_key: str) -> dict:
    edges = db.query(Edge).filter(Edge.workspace_id == workspace_id).all()
    names = {
        n.node_key: n.name
        for n in db.query(Node).filter(Node.workspace_id == workspace_id).all()
    }
    downstream, upstream = [], []
    for e in edges:
        if e.source_node_key == node_key:
            downstream.append({
                "edge_key": e.edge_key, "node_key": e.target_node_key,
                "name": names.get(e.target_node_key), "action_type": e.action_type,
                "required_data_payload": e.required_data_payload,
            })
        if e.target_node_key == node_key:
            upstream.append({
                "edge_key": e.edge_key, "node_key": e.source_node_key,
                "name": names.get(e.source_node_key), "action_type": e.action_type,
                "required_data_payload": e.required_data_payload,
            })
    return {"upstream": upstream, "downstream": downstream}


@router.get("/{node_key}")
def node_window(
    workspace_id: str,
    node_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_node_access(workspace_id, node_key, user)
    node = _get_node(db, workspace_id, node_key)
    ws = db.get(Workspace, workspace_id)
    docs = db.query(Document).filter(
        Document.workspace_id == workspace_id, Document.node_key == node_key
    ).all()
    return {
        "workspace_id": workspace_id,
        "node": {
            "node_key": node.node_key,
            "name": node.name,
            "type": node.type,
            "responsibilities": node.responsibilities,
            "constraints": node.constraints,
            "autonomy_level": node.autonomy_level,
            "agent_system_prompt": node.agent_system_prompt,
        },
        "guardrails": ws.agent_guardrails if ws else {},
        "neighbours": _neighbours(db, workspace_id, node_key),
        "documents": [
            {"id": d.id, "title": d.title, "doc_type": d.doc_type, "content": d.content}
            for d in docs
        ],
    }


@router.get("/{node_key}/documents")
def node_documents(
    workspace_id: str,
    node_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    require_node_access(workspace_id, node_key, user)
    _get_node(db, workspace_id, node_key)
    docs = db.query(Document).filter(
        Document.workspace_id == workspace_id, Document.node_key == node_key
    ).all()
    return {
        "node_key": node_key,
        "documents": [
            {"id": d.id, "title": d.title, "doc_type": d.doc_type, "content": d.content}
            for d in docs
        ],
    }


from ..schemas import EmployeeCreate
from ..security import hash_password

@router.post("/{node_key}/users")
def create_employee(
    workspace_id: str,
    node_key: str,
    body: EmployeeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "admin" or user.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    
    _get_node(db, workspace_id, node_key) # ensure node exists
    
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already in use")
    
    u = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role="member",
        workspace_id=workspace_id,
        node_key=node_key,
    )
    db.add(u)
    db.commit()
    return {"status": "ok", "user_id": u.id}
