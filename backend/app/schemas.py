"""Pydantic request/response models for the API surface."""
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Interview ---
class InterviewStart(BaseModel):
    admin_email: str
    admin_password: str = Field(min_length=6)


class AnswerIn(BaseModel):
    question_id: str
    answer: Any  # free text, or a structured value for list-type questions


# --- Auth ---
class LoginIn(BaseModel):
    email: str
    password: str


class NodeLoginIn(BaseModel):
    """Claim/authenticate a seat scoped to a single node via its access code."""

    workspace_id: str
    node_key: str
    access_code: str
    email: str
    password: str = Field(min_length=6)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    workspace_id: Optional[str] = None
    node_key: Optional[str] = None


# --- Agent ---
class AgentInvokeIn(BaseModel):
    message: str
    emit_handoffs: bool = False  # if true, agent may post messages to neighbor nodes

# --- Admin Operations ---
class NodeCreate(BaseModel):
    name: str
    type: str = "internal"
    responsibilities: list[str] = []

class EdgeCreate(BaseModel):
    source_node_key: str
    target_node_key: str
    action_type: str = ""

class EmployeeCreate(BaseModel):
    email: str
    password: str = Field(min_length=6)
