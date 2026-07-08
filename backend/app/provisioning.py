"""Turn a validated graph spec into a live workspace in the DB:
   - one Workspace row
   - one Node row per node (+ a per-node access code seats use to log in)
   - one Edge row per edge
   - a few per-node Documents (the gated data each node's window reveals)

This is the runtime 'provisioning' step from the spec: seed the DB and create the
scoped surface each employee logs into.
"""
import secrets

from sqlalchemy.orm import Session

from .models import Document, Edge, Node, User, Workspace
from .security import hash_password


def _access_code() -> str:
    return secrets.token_hex(4)  # 8 hex chars, e.g. 'a1b2c3d4'


def _seed_documents(node: Node) -> list[Document]:
    """Generic, node-scoped sample data so login-gating is demonstrable for any graph."""
    docs = [
        Document(
            workspace_id=node.workspace_id,
            node_key=node.node_key,
            title=f"{node.name} — Responsibilities & Constraints",
            doc_type="overview",
            content={
                "responsibilities": node.responsibilities,
                "constraints": node.constraints,
                "autonomy_level": node.autonomy_level,
            },
        ),
        Document(
            workspace_id=node.workspace_id,
            node_key=node.node_key,
            title=f"{node.name} — Active Jobs",
            doc_type="task_board",
            content={
                "open_items": [
                    {"ref": "JOB-1001", "status": "in_progress", "owner": node.name},
                    {"ref": "JOB-1002", "status": "blocked", "owner": node.name},
                ]
            },
        ),
    ]
    # A 'sensitive records' doc to make the access boundary concrete.
    sensitive = {
        "internal": {
            "title": f"{node.name} — Internal Records (confidential)",
            "content": {"note": "Internal-only figures", "budget_context": "REDACTED unless seat-scoped"},
        },
        "external": {
            "title": f"{node.name} — Assigned Deliveries",
            "content": {"note": "Only your assigned deadlines are visible here", "master_schedule": "hidden"},
        },
    }[node.type]
    docs.append(
        Document(
            workspace_id=node.workspace_id,
            node_key=node.node_key,
            title=sensitive["title"],
            doc_type="records",
            content=sensitive["content"],
        )
    )
    return docs


def provision_workspace(db: Session, spec: dict) -> Workspace:
    ws_in = spec["workspace"]
    workspace = Workspace(
        workspace_name=ws_in["workspace_name"],
        industry=ws_in.get("industry", ""),
        global_objective=ws_in.get("global_objective", ""),
        trigger_event=ws_in.get("trigger_event", ""),
        standard_sla_days=int(ws_in.get("standard_sla_days", 14)),
        agent_guardrails=spec.get("agent_guardrails", {}),
    )
    db.add(workspace)
    db.flush()  # assign workspace.id

    for n in spec["nodes"]:
        node = Node(
            workspace_id=workspace.id,
            node_key=n["node_id"],
            name=n["name"],
            type=n["type"],
            responsibilities=n.get("responsibilities", []),
            constraints=n.get("constraints", []),
            autonomy_level=n["autonomy_level"],
            agent_system_prompt=n.get("agent_system_prompt", ""),
            access_code=_access_code(),
        )
        db.add(node)
        db.flush()
        for doc in _seed_documents(node):
            db.add(doc)

    for e in spec["edges"]:
        db.add(
            Edge(
                workspace_id=workspace.id,
                edge_key=e["edge_id"],
                source_node_key=e["source_node_id"],
                target_node_key=e["target_node_id"],
                action_type=e.get("action_type", "handoff"),
                required_data_payload=e.get("required_data_payload", []),
            )
        )

    db.commit()
    db.refresh(workspace)
    return workspace


def create_admin(db: Session, workspace_id: str, email: str, hashed_password: str) -> User:
    admin = User(
        email=email,
        hashed_password=hashed_password,
        role="admin",
        workspace_id=workspace_id,
        node_key=None,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def create_seat(db: Session, workspace_id: str, node_key: str, email: str, password: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        role="member",
        workspace_id=workspace_id,
        node_key=node_key,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
