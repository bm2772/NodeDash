"""Issue a JWT for a user, carrying their scope (role, workspace, node)."""
from .config import settings
from .models import User
from .security import create_token


def issue_token(user: User) -> str:
    return create_token(
        {
            "sub": user.id,
            "role": user.role,
            "workspace_id": user.workspace_id,
            "node_key": user.node_key,
        },
        settings.jwt_secret,
        settings.jwt_exp_hours * 3600,
    )
