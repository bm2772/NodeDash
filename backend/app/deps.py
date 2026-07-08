"""Auth dependencies, including node-scoped access control.

The core rule: a member token carries a single node_key. That seat may read/act
on exactly that node. Admins (node_key = None) may access the whole workspace.
"""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import decode_token


def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    claims = decode_token(token, settings.jwt_secret)
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, claims.get("sub"))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def require_workspace_member(workspace_id: str, user: User) -> None:
    if user.role == "admin" and user.workspace_id == workspace_id:
        return
    if user.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")


def require_node_access(workspace_id: str, node_key: str, user: User) -> None:
    """Gate a node 'window': admin of the workspace, or the seat scoped to this node."""
    if user.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this workspace")
    if user.role == "admin":
        return
    if user.node_key != node_key:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Your seat is scoped to '{user.node_key}', not '{node_key}'",
        )
