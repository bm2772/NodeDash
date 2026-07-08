"""ORM models. The DB mirrors the graph-spec: workspace / nodes / edges,
plus users (scoped seats), documents (per-node gated data), messages (agent bus),
and interview sessions (the questionnaire in progress)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=_uuid)
    workspace_name = Column(String, nullable=False)
    industry = Column(String, nullable=False, default="")
    global_objective = Column(Text, nullable=False, default="")
    trigger_event = Column(String, nullable=False, default="")
    standard_sla_days = Column(Integer, nullable=False, default=14)
    agent_guardrails = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=_now)

    nodes = relationship("Node", back_populates="workspace", cascade="all, delete-orphan")
    edges = relationship("Edge", back_populates="workspace", cascade="all, delete-orphan")


class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (UniqueConstraint("workspace_id", "node_key", name="uq_node_key"),)

    id = Column(String, primary_key=True, default=_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    node_key = Column(String, nullable=False)            # e.g. node_finance_internal
    name = Column(String, nullable=False)
    type = Column(String, nullable=False, default="internal")  # internal | external
    responsibilities = Column(JSON, nullable=False, default=list)
    constraints = Column(JSON, nullable=False, default=list)
    autonomy_level = Column(String, nullable=False, default="suggest_only")
    agent_system_prompt = Column(Text, nullable=False, default="")
    access_code = Column(String, nullable=False, default="")  # seat claim code for this node

    workspace = relationship("Workspace", back_populates="nodes")


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (UniqueConstraint("workspace_id", "edge_key", name="uq_edge_key"),)

    id = Column(String, primary_key=True, default=_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    edge_key = Column(String, nullable=False)
    source_node_key = Column(String, nullable=False)
    target_node_key = Column(String, nullable=False)
    action_type = Column(String, nullable=False, default="")
    required_data_payload = Column(JSON, nullable=False, default=list)

    workspace = relationship("Workspace", back_populates="edges")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="member")     # admin | member
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True, index=True)
    node_key = Column(String, nullable=True)  # the single node this seat may access (None for admin)
    created_at = Column(DateTime, default=_now)


class Document(Base):
    """Node-scoped data. This is what login gates: a Finance seat sees Finance docs only."""

    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    node_key = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    doc_type = Column(String, nullable=False, default="record")
    content = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=_now)


class Message(Base):
    """Agent message bus: cross-node coordination along edges."""

    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False, index=True)
    edge_key = Column(String, nullable=True)
    from_node_key = Column(String, nullable=True)
    to_node_key = Column(String, nullable=True)
    action_type = Column(String, nullable=False, default="message")
    body = Column(Text, nullable=False, default="")
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=_now)


class InterviewSession(Base):
    """A questionnaire in progress. Answers compile into a Workspace on generate."""

    __tablename__ = "interview_sessions"

    id = Column(String, primary_key=True, default=_uuid)
    status = Column(String, nullable=False, default="in_progress")  # in_progress | generated
    admin_email = Column(String, nullable=True)
    admin_hashed_password = Column(String, nullable=True)
    answers = Column(JSON, nullable=False, default=dict)  # {question_id: answer}
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    created_at = Column(DateTime, default=_now)
