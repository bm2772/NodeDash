"""Model/GPU status + manual wake (for pre-warming before a demo)."""
from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..gpu_manager import manager
from ..models import User

router = APIRouter(prefix="/model", tags=["model"])


@router.get("/status")
def model_status() -> dict:
    """Public: current GPU state (off/warming/ready/disabled) + which models are wired."""
    return manager.status()


@router.post("/wake")
def model_wake(user: User = Depends(get_current_user)) -> dict:
    """Kick off a GPU warm-up (no-op if already up or GPU management is off)."""
    manager.request_wake()
    return manager.status()
