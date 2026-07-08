"""Validate & normalize a graph spec against questionnaire/graph-spec.schema.json.

Kept dependency-free (no jsonschema) and, importantly, *forgiving on input*: LLMs
routinely return slightly-off JSON (missing prefixes, a string where a list is
expected, an unknown enum). normalize_spec() coerces those into a schema-valid
object where it safely can; validate_spec() then reports anything still wrong.
"""
import re
from typing import Any

AUTONOMY_LEVELS = {"suggest_only", "execute", "restricted"}
NODE_TYPES = {"internal", "external"}
DELAY_PROTOCOLS = {"auto-renegotiate-then-alert", "alert-human-only", "halt-downstream"}
TRANSPARENCY = {"strict_isolation", "shared_deadlines", "full_transparency"}
TONES = {"professional_and_concise", "friendly_and_detailed", "formal"}

DEFAULT_GUARDRAILS = {
    "delay_handling_protocol": "auto-renegotiate-then-alert",
    "vendor_data_transparency": "strict_isolation",
    "communication_tone": "professional_and_concise",
}


def _slug(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return s or "unnamed"


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str):
        # accept comma / newline / semicolon separated strings
        parts = re.split(r"[\n;,]+", value)
        return [p.strip() for p in parts if p.strip()]
    return [str(value)]


def normalize_spec(raw: dict) -> dict:
    """Best-effort coercion of an LLM/raw dict into the canonical graph spec."""
    raw = dict(raw or {})
    ws = dict(raw.get("workspace") or {})
    try:
        sla = int(ws.get("standard_sla_days", 14))
    except (TypeError, ValueError):
        sla = 14
    workspace = {
        "workspace_name": str(ws.get("workspace_name") or ws.get("name") or "Untitled Workspace"),
        "industry": str(ws.get("industry") or ""),
        "global_objective": str(ws.get("global_objective") or ws.get("objective") or ""),
        "trigger_event": str(ws.get("trigger_event") or ws.get("trigger") or ""),
        "standard_sla_days": sla,
    }

    nodes = []
    seen_nodes: set[str] = set()
    for n in raw.get("nodes") or []:
        n = dict(n)
        key = str(n.get("node_id") or n.get("id") or n.get("name") or "node")
        if not key.startswith("node_"):
            key = "node_" + _slug(key)
        else:
            key = "node_" + _slug(key[len("node_"):])
        # de-dupe keys
        base, i = key, 2
        while key in seen_nodes:
            key = f"{base}_{i}"
            i += 1
        seen_nodes.add(key)

        node_type = str(n.get("type", "internal")).lower()
        if node_type not in NODE_TYPES:
            node_type = "external" if "extern" in node_type else "internal"
        autonomy = str(n.get("autonomy_level", "suggest_only"))
        if autonomy not in AUTONOMY_LEVELS:
            autonomy = "restricted" if node_type == "external" else "suggest_only"

        nodes.append(
            {
                "node_id": key,
                "name": str(n.get("name") or n.get("label") or key),
                "type": node_type,
                "responsibilities": _as_list(n.get("responsibilities")),
                "constraints": _as_list(n.get("constraints")),
                "autonomy_level": autonomy,
                "agent_system_prompt": str(n.get("agent_system_prompt") or ""),
            }
        )

    valid_keys = {n["node_id"] for n in nodes}
    name_to_key = {n["name"].lower(): n["node_id"] for n in nodes}

    def resolve(ref: str) -> str:
        ref = str(ref)
        cand = ref if ref.startswith("node_") else "node_" + _slug(ref)
        if cand in valid_keys:
            return cand
        if ref.lower() in name_to_key:
            return name_to_key[ref.lower()]
        return cand

    edges = []
    seen_edges: set[str] = set()
    for e in raw.get("edges") or []:
        e = dict(e)
        src = resolve(e.get("source_node_id") or e.get("from") or e.get("source") or "")
        tgt = resolve(e.get("target_node_id") or e.get("to") or e.get("target") or "")
        key = str(e.get("edge_id") or e.get("id") or f"{src}_to_{tgt}")
        if not key.startswith("edge_"):
            key = "edge_" + _slug(key)
        base, i = key, 2
        while key in seen_edges:
            key = f"{base}_{i}"
            i += 1
        seen_edges.add(key)
        edges.append(
            {
                "edge_id": key,
                "source_node_id": src,
                "target_node_id": tgt,
                "action_type": str(e.get("action_type") or e.get("type") or "handoff"),
                "required_data_payload": _as_list(e.get("required_data_payload") or e.get("payload")),
            }
        )

    guardrails = dict(DEFAULT_GUARDRAILS)
    g = raw.get("agent_guardrails") or {}
    if isinstance(g, dict):
        if g.get("delay_handling_protocol") in DELAY_PROTOCOLS:
            guardrails["delay_handling_protocol"] = g["delay_handling_protocol"]
        if g.get("vendor_data_transparency") in TRANSPARENCY:
            guardrails["vendor_data_transparency"] = g["vendor_data_transparency"]
        if g.get("communication_tone") in TONES:
            guardrails["communication_tone"] = g["communication_tone"]

    return {
        "workspace": workspace,
        "nodes": nodes,
        "edges": edges,
        "agent_guardrails": guardrails,
    }


def validate_spec(spec: dict) -> list[str]:
    """Return a list of human-readable errors. Empty list == valid."""
    errors: list[str] = []

    if not isinstance(spec, dict):
        return ["spec must be a JSON object"]

    ws = spec.get("workspace")
    if not isinstance(ws, dict):
        errors.append("workspace: missing or not an object")
    else:
        for f in ("workspace_name", "industry", "global_objective", "trigger_event"):
            if not str(ws.get(f, "")).strip():
                errors.append(f"workspace.{f}: required, non-empty")
        if not isinstance(ws.get("standard_sla_days"), int) or ws.get("standard_sla_days", 0) < 1:
            errors.append("workspace.standard_sla_days: must be a positive integer")

    nodes = spec.get("nodes")
    node_keys: set[str] = set()
    if not isinstance(nodes, list) or len(nodes) < 2:
        errors.append("nodes: need at least 2")
    else:
        for idx, n in enumerate(nodes):
            loc = f"nodes[{idx}]"
            if not isinstance(n, dict):
                errors.append(f"{loc}: not an object")
                continue
            key = n.get("node_id", "")
            if not re.match(r"^node_[a-z0-9_]+$", str(key)):
                errors.append(f"{loc}.node_id '{key}': must match ^node_[a-z0-9_]+$")
            if key in node_keys:
                errors.append(f"{loc}.node_id '{key}': duplicate")
            node_keys.add(key)
            if not str(n.get("name", "")).strip():
                errors.append(f"{loc}.name: required")
            if n.get("type") not in NODE_TYPES:
                errors.append(f"{loc}.type: must be internal|external")
            if n.get("autonomy_level") not in AUTONOMY_LEVELS:
                errors.append(f"{loc}.autonomy_level: must be one of {sorted(AUTONOMY_LEVELS)}")
            if not isinstance(n.get("responsibilities"), list) or not n.get("responsibilities"):
                errors.append(f"{loc}.responsibilities: non-empty list required")
            if not str(n.get("agent_system_prompt", "")).strip():
                errors.append(f"{loc}.agent_system_prompt: required")

    edges = spec.get("edges")
    if not isinstance(edges, list) or len(edges) < 1:
        errors.append("edges: need at least 1")
    else:
        for idx, e in enumerate(edges):
            loc = f"edges[{idx}]"
            if not isinstance(e, dict):
                errors.append(f"{loc}: not an object")
                continue
            if not re.match(r"^edge_[a-z0-9_]+$", str(e.get("edge_id", ""))):
                errors.append(f"{loc}.edge_id: must match ^edge_[a-z0-9_]+$")
            for ref in ("source_node_id", "target_node_id"):
                if e.get(ref) not in node_keys:
                    errors.append(f"{loc}.{ref} '{e.get(ref)}': not a known node")
            if not str(e.get("action_type", "")).strip():
                errors.append(f"{loc}.action_type: required")
            if not isinstance(e.get("required_data_payload"), list) or not e.get("required_data_payload"):
                errors.append(f"{loc}.required_data_payload: non-empty list required")

    g = spec.get("agent_guardrails")
    if not isinstance(g, dict):
        errors.append("agent_guardrails: missing or not an object")
    else:
        if g.get("delay_handling_protocol") not in DELAY_PROTOCOLS:
            errors.append("agent_guardrails.delay_handling_protocol: invalid")
        if g.get("vendor_data_transparency") not in TRANSPARENCY:
            errors.append("agent_guardrails.vendor_data_transparency: invalid")
        if g.get("communication_tone") not in TONES:
            errors.append("agent_guardrails.communication_tone: invalid")

    return errors
