"""Compile questionnaire answers into a validated graph spec.

Two strategies:
  * LLM  — prompt an OpenAI-compatible model (Fireworks / AMD vLLM) to emit JSON
           constrained to the schema, with one repair round if validation fails.
  * mock — build the graph heuristically from the answers, no network. Used when
           no endpoint is configured, and as a last-resort fallback so a demo
           never dies on a flaky generator.

Either way the output goes through normalize_spec + validate_spec before return.
"""
import json
import re
from typing import Optional

from . import llm
from .graph_spec import (
    DELAY_PROTOCOLS,
    TONES,
    TRANSPARENCY,
    normalize_spec,
    validate_spec,
)
from .config import settings
from .questionnaire import flat_questions

# --------------------------------------------------------------------------- #
# Shared: agent system-prompt template (bridges Tier 4 -> a running agent)
# --------------------------------------------------------------------------- #
def build_agent_prompt(node: dict, workspace: dict, upstream: list[str],
                       downstream: list[str], guardrails: dict) -> str:
    autonomy_help = {
        "suggest_only": "draft actions and wait for human confirmation before anything is sent",
        "execute": "auto-approve/act on standard requests, escalating non-standard ones to your human",
        "restricted": "operate with limited scope and see only your assigned deadlines",
    }.get(node["autonomy_level"], "draft actions for human confirmation")
    visibility = (
        "restricted to your own assigned deadlines — you cannot see internal master deadlines"
        if node["type"] == "external"
        else "full internal visibility"
    )
    resp = "; ".join(node.get("responsibilities") or []) or "coordinate your node's work"
    up = ", ".join(upstream) or "(none)"
    down = ", ".join(downstream) or "(none)"
    return (
        f"You are the AI Chief of Staff for {node['name']} in the "
        f"'{workspace.get('workspace_name','')}' workspace "
        f"(industry: {workspace.get('industry','')}). "
        f"Global objective: {workspace.get('global_objective','')}. "
        f"Your responsibilities: {resp}. "
        f"You coordinate upstream with: {up}; downstream with: {down}. "
        f"Your autonomy is '{node['autonomy_level']}' — you {autonomy_help}. "
        f"Your data visibility is {visibility}. "
        f"Communication tone: {guardrails.get('communication_tone','professional_and_concise')}. "
        f"On a missed deadline or blocked handoff, follow the "
        f"'{guardrails.get('delay_handling_protocol','auto-renegotiate-then-alert')}' protocol. "
        f"When a neighbouring agent's timeline shifts, update your plan, rebalance your "
        f"role's other active jobs, and notify affected downstream agents."
    )


def _fill_missing_prompts(spec: dict) -> dict:
    """Guarantee every node has an agent_system_prompt (LLMs sometimes skip them)."""
    ws = spec["workspace"]
    guardrails = spec["agent_guardrails"]
    up_map: dict[str, list[str]] = {n["node_id"]: [] for n in spec["nodes"]}
    down_map: dict[str, list[str]] = {n["node_id"]: [] for n in spec["nodes"]}
    name = {n["node_id"]: n["name"] for n in spec["nodes"]}
    for e in spec["edges"]:
        s, t = e["source_node_id"], e["target_node_id"]
        if t in name and name[t] not in down_map.get(s, []):
            down_map.setdefault(s, []).append(name[t])
        if s in name and name[s] not in up_map.get(t, []):
            up_map.setdefault(t, []).append(name[s])
    for n in spec["nodes"]:
        if not str(n.get("agent_system_prompt", "")).strip():
            n["agent_system_prompt"] = build_agent_prompt(
                n, ws, up_map.get(n["node_id"], []), down_map.get(n["node_id"], []), guardrails
            )
    return spec


# --------------------------------------------------------------------------- #
# LLM strategy
# --------------------------------------------------------------------------- #
_SYSTEM = (
    "You are AgentGraph's onboarding compiler. You turn an admin's interview answers "
    "into a workspace operating graph. Output ONLY a single JSON object, no prose, no "
    "markdown fences. It must have exactly these top-level keys: workspace, nodes, edges, "
    "agent_guardrails.\n\n"
    "Rules:\n"
    "- workspace: {workspace_name, industry, global_objective, trigger_event, standard_sla_days(int)}.\n"
    "- nodes[]: {node_id, name, type, responsibilities[], constraints[], autonomy_level, agent_system_prompt}.\n"
    "    node_id matches ^node_[a-z0-9_]+$. type is 'internal' or 'external'.\n"
    "    autonomy_level is 'suggest_only', 'execute', or 'restricted' (external partners are usually 'restricted').\n"
    "    agent_system_prompt is a detailed 'AI Chief of Staff' prompt for that node: its role, responsibilities, "
    "who it coordinates with upstream/downstream, its autonomy, its data visibility, and its delay protocol.\n"
    "- edges[]: {edge_id, source_node_id, target_node_id, action_type, required_data_payload[]}.\n"
    "    edge_id matches ^edge_[a-z0-9_]+$. source/target must be existing node_ids.\n"
    "- agent_guardrails: {delay_handling_protocol, vendor_data_transparency, communication_tone}.\n"
    f"    delay_handling_protocol in {sorted(DELAY_PROTOCOLS)}.\n"
    f"    vendor_data_transparency in {sorted(TRANSPARENCY)}.\n"
    f"    communication_tone in {sorted(TONES)}.\n"
    "Create one node per internal team and one per external partner. Wire directed edges for the "
    "approval chains and data handoffs described. Keep it to the actors the admin named."
)


def _answers_as_prompt(answers: dict) -> str:
    label = {q["question_id"]: q["question"] for q in flat_questions()}
    lines = []
    for qid, ans in answers.items():
        if ans in (None, "", []):
            continue
        val = ans if isinstance(ans, str) else json.dumps(ans)
        lines.append(f"- [{qid}] {label.get(qid, qid)}\n  ANSWER: {val}")
    return "The admin's interview answers:\n" + "\n".join(lines)


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def generate_via_llm(answers: dict) -> tuple[dict, list[str]]:
    """Returns (normalized_spec, errors). errors empty == valid."""
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _answers_as_prompt(answers)},
    ]
    raw = llm.chat(messages, json_mode=True, temperature=0.2, max_tokens=3000)
    parsed = _extract_json(raw) or {}
    spec = _fill_missing_prompts(normalize_spec(parsed))
    errors = validate_spec(spec)
    if not errors:
        return spec, []

    # One repair round: hand the model its output + the specific validation errors.
    repair = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _answers_as_prompt(answers)},
        {"role": "assistant", "content": json.dumps(parsed)},
        {
            "role": "user",
            "content": "That JSON failed validation with these errors:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\nReturn a corrected JSON object only.",
        },
    ]
    raw2 = llm.chat(repair, json_mode=True, temperature=0.0, max_tokens=3000)
    spec2 = _fill_missing_prompts(normalize_spec(_extract_json(raw2) or {}))
    return spec2, validate_spec(spec2)


# --------------------------------------------------------------------------- #
# Mock strategy (offline, deterministic, answer-driven)
# --------------------------------------------------------------------------- #
def _split_items(text) -> list[str]:
    if isinstance(text, list):
        return [str(t).strip() for t in text if str(t).strip()]
    if not text:
        return []
    return [p.strip() for p in re.split(r"[\n;,]+", str(text)) if p.strip()]


def _match_enum(text, options: set[str], default: str) -> str:
    t = str(text or "").lower()
    for opt in options:
        if opt.lower() in t:
            return opt
    keys = {
        "renegot": "auto-renegotiate-then-alert",
        "alert": "alert-human-only",
        "halt": "halt-downstream",
        "isolat": "strict_isolation",
        "shared": "shared_deadlines",
        "full": "full_transparency",
        "concise": "professional_and_concise",
        "friendly": "friendly_and_detailed",
        "formal": "formal",
    }
    for frag, val in keys.items():
        if frag in t and val in options:
            return val
    return default


def generate_via_mock(answers: dict) -> dict:
    a = answers
    industry = str(a.get("q_industry_output") or "Operations")
    ws_name = industry if len(industry) < 60 else "Operations"
    try:
        sla_match = re.search(r"\d+", str(a.get("q_global_objective", "")))
        sla = int(sla_match.group()) if sla_match else 14
    except Exception:
        sla = 14

    internal = _split_items(a.get("q_internal_teams")) or ["Operations", "Finance"]
    external = _split_items(a.get("q_external_partners")) or ["External Partner"]
    constraints_pool = _split_items(a.get("q_capacity_constraints"))
    payloads = _split_items(a.get("q_data_handoffs")) or ["Handoff Document", "Details"]

    workspace = {
        "workspace_name": f"{ws_name} Operations".replace("Operations Operations", "Operations"),
        "industry": industry,
        "global_objective": str(a.get("q_global_objective") or "Deliver on time and within budget."),
        "trigger_event": str(a.get("q_trigger") or "New Operational Cycle Started"),
        "standard_sla_days": sla,
    }
    guardrails = {
        "delay_handling_protocol": _match_enum(
            a.get("q_exception_handling"), DELAY_PROTOCOLS, "auto-renegotiate-then-alert"
        ),
        "vendor_data_transparency": _match_enum(
            a.get("q_external_visibility"), TRANSPARENCY, "strict_isolation"
        ),
        "communication_tone": _match_enum(
            a.get("q_communication_tone"), TONES, "professional_and_concise"
        ),
    }

    nodes: list[dict] = []
    for name in internal:
        nodes.append({"name": name, "type": "internal", "autonomy_level": "suggest_only"})
    for name in external:
        nodes.append({"name": name, "type": "external", "autonomy_level": "restricted"})

    # normalize first to get canonical node_ids, then attach responsibilities/prompts
    partial = {"workspace": workspace, "nodes": nodes, "edges": [], "agent_guardrails": guardrails}
    spec = normalize_spec(partial)
    for i, n in enumerate(spec["nodes"]):
        n["responsibilities"] = [f"Own {n['name']} tasks in the operational cycle",
                                 "Coordinate handoffs with neighbouring nodes"]
        n["constraints"] = ([constraints_pool[i]] if i < len(constraints_pool) else
                            (["Serves multiple concurrent clients"] if n["type"] == "external" else []))

    # linear approval chain + one status update back to the first node
    keys = [n["node_id"] for n in spec["nodes"]]
    edges = []
    for i in range(len(keys) - 1):
        edges.append({
            "source_node_id": keys[i],
            "target_node_id": keys[i + 1],
            "action_type": "request_approval" if i == 0 else "send_order",
            "required_data_payload": payloads[:2] or ["Handoff Document"],
        })
    if len(keys) >= 2:
        edges.append({
            "source_node_id": keys[-1],
            "target_node_id": keys[0],
            "action_type": "status_update",
            "required_data_payload": ["Status", "Revised ETA"],
        })
    spec["edges"] = edges
    spec = normalize_spec(spec)  # re-key edges canonically
    return _fill_missing_prompts(spec)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def generate_graph_spec(answers: dict) -> tuple[dict, dict]:
    """Returns (spec, meta). meta = {strategy, warnings, valid}."""
    warnings: list[str] = []

    if settings.llm_enabled:
        try:
            spec, errors = generate_via_llm(answers)
            if not errors:
                return spec, {"strategy": "llm", "warnings": [], "valid": True}
            warnings.append(f"LLM output failed validation: {errors}")
        except llm.LLMError as exc:
            warnings.append(f"LLM call failed: {exc}")
        warnings.append("Fell back to offline mock generator.")

    spec = generate_via_mock(answers)
    errors = validate_spec(spec)
    return spec, {"strategy": "mock", "warnings": warnings, "valid": not errors, "errors": errors}
