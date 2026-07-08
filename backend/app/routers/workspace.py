"""Workspace-level reads: the public canvas view, and the full graph for members."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_workspace_member
from ..models import User, Workspace
from ..serialize import edge_dict, full_graph, node_public, workspace_dict

router = APIRouter(prefix="/workspace", tags=["workspace"])


def _get_ws(db: Session, workspace_id: str) -> Workspace:
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    return ws


@router.get("/{workspace_id}/public")
def public_graph(workspace_id: str, db: Session = Depends(get_db)) -> dict:
    """No auth: enough to render the canvas. Each node is then unlocked by logging in."""
    ws = _get_ws(db, workspace_id)
    return {
        "workspace": workspace_dict(ws),
        "nodes": [node_public(n) for n in ws.nodes],
        "edges": [edge_dict(e) for e in ws.edges],
    }


@router.get("/{workspace_id}/graph")
def graph(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ws = _get_ws(db, workspace_id)
    require_workspace_member(workspace_id, user)
    return full_graph(ws)


from ..schemas import NodeCreate, EdgeCreate
from ..models import Node, Edge
import uuid

@router.post("/{workspace_id}/nodes")
def create_node(
    workspace_id: str,
    body: NodeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "admin" or user.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    
    node_key = "node_" + uuid.uuid4().hex[:8]
    n = Node(
        workspace_id=workspace_id,
        node_key=node_key,
        name=body.name,
        type=body.type,
        responsibilities=body.responsibilities,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return {"status": "ok", "node_key": n.node_key}


@router.post("/{workspace_id}/edges")
def create_edge(
    workspace_id: str,
    body: EdgeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if user.role != "admin" or user.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    
    e = Edge(
        workspace_id=workspace_id,
        edge_key="edge_" + uuid.uuid4().hex[:8],
        source_node_key=body.source_node_key,
        target_node_key=body.target_node_key,
        action_type=body.action_type,
    )
    db.add(e)
    db.commit()
    return {"status": "ok", "edge_key": e.edge_key}
