"""Authentication: admin login, and node-scoped seat login/claim.

The node-login flow is the 'open a node window and verify' interaction: a Finance
team member presents the Finance node's access code, and gets a token that unlocks
Finance data only.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Node, User
from ..provisioning import create_seat
from ..schemas import LoginIn, NodeLoginIn, TokenOut
from ..security import verify_password
from ..tokens import issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_out(user: User) -> TokenOut:
    return TokenOut(
        access_token=issue_token(user),
        role=user.role,
        workspace_id=user.workspace_id,
        node_key=user.node_key,
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return _token_out(user)


@router.post("/node-login", response_model=TokenOut)
def node_login(body: NodeLoginIn, db: Session = Depends(get_db)) -> TokenOut:
    node = (
        db.query(Node)
        .filter(Node.workspace_id == body.workspace_id, Node.node_key == body.node_key)
        .first()
    )
    if not node:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Node not found")

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        # Returning seat: verify password and that they are scoped to this node.
        if not verify_password(body.password, existing.hashed_password):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
        if existing.role != "admin" and (
            existing.workspace_id != body.workspace_id or existing.node_key != body.node_key
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "This account is not authorised for that node"
            )
        return _token_out(existing)

    # New seat: the access code proves authorisation for this node.
    if body.access_code != node.access_code:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access code for this node")
    user = create_seat(db, body.workspace_id, body.node_key, body.email, body.password)
    return _token_out(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "workspace_id": user.workspace_id,
        "node_key": user.node_key,
    }
