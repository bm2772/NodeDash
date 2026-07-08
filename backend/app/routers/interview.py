"""The admin-facing onboarding interview: start -> answer questions -> generate."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..database import get_db
from ..generation import generate_graph_spec
from ..models import InterviewSession, Node, User
from ..provisioning import create_admin, provision_workspace
from ..questionnaire import flat_questions, load_questionnaire, next_question, progress
from ..schemas import AnswerIn, InterviewStart
from ..security import hash_password
from ..serialize import full_graph
from ..tokens import issue_token

router = APIRouter(prefix="/interview", tags=["interview"])


def _question_payload(q: dict | None) -> dict | None:
    if q is None:
        return None
    return {
        "question_id": q["question_id"],
        "question": q["question"],
        "tier_id": q.get("tier_id"),
        "tier_title": q.get("tier_title"),
        "generates": q.get("generates"),
        "allowed_values": q.get("allowed_values"),
    }


@router.get("/questionnaire")
def get_questionnaire() -> dict:
    """The raw questionnaire definition (tiers + questions)."""
    return load_questionnaire()


@router.post("/start", status_code=status.HTTP_201_CREATED)
def start(body: InterviewStart, db: Session = Depends(get_db)) -> dict:
    session = InterviewSession(
        admin_email=body.admin_email,
        admin_hashed_password=hash_password(body.admin_password),
        answers={},
        status="in_progress",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id,
        "total_questions": len(flat_questions()),
        "next_question": _question_payload(next_question(session.answers)),
    }


def _get_session(db: Session, session_id: str) -> InterviewSession:
    session = db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Interview session not found")
    return session


@router.get("/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = _get_session(db, session_id)
    return {
        "session_id": session.id,
        "status": session.status,
        "answers": session.answers,
        "progress": progress(session.answers),
        "next_question": _question_payload(next_question(session.answers)),
        "workspace_id": session.workspace_id,
    }


@router.post("/{session_id}/answer")
def answer(session_id: str, body: AnswerIn, db: Session = Depends(get_db)) -> dict:
    session = _get_session(db, session_id)
    if session.status != "in_progress":
        raise HTTPException(status.HTTP_409_CONFLICT, "Interview already generated")
    valid_ids = {q["question_id"] for q in flat_questions()}
    if body.question_id not in valid_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown question_id '{body.question_id}'")
    # reassign so SQLAlchemy detects the JSON mutation
    session.answers = {**session.answers, body.question_id: body.answer}
    db.commit()
    return {
        "progress": progress(session.answers),
        "next_question": _question_payload(next_question(session.answers)),
    }


@router.post("/{session_id}/generate")
async def generate(session_id: str, db: Session = Depends(get_db)) -> dict:
    session = _get_session(db, session_id)
    if session.status == "generated" and session.workspace_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workspace already generated for this session")
    if not session.answers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No answers to compile")

    # Admin email is globally unique — check before provisioning so we don't leave
    # an orphan workspace behind and so the client gets a clean error (not a 500).
    if db.query(User).filter(User.email == session.admin_email).first():
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Admin email '{session.admin_email}' already has a workspace — use a different email.",
        )

    # LLM generation can block; keep the event loop free.
    spec, meta = await run_in_threadpool(generate_graph_spec, session.answers)
    if not meta.get("valid"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Generated graph failed validation", "meta": meta},
        )

    workspace = provision_workspace(db, spec)
    admin = create_admin(db, workspace.id, session.admin_email, session.admin_hashed_password)

    session.status = "generated"
    session.workspace_id = workspace.id
    db.commit()

    nodes = db.query(Node).filter(Node.workspace_id == workspace.id).all()
    return {
        "workspace_id": workspace.id,
        "generation": meta,
        "admin_token": issue_token(admin),
        "graph": full_graph(workspace),
        # Seat access codes so the admin can distribute node logins.
        "node_access": [
            {"node_key": n.node_key, "name": n.name, "type": n.type, "access_code": n.access_code}
            for n in nodes
        ],
    }
