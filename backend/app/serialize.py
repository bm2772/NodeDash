"""DB rows -> API/spec dicts."""
from .models import Edge, Node, Workspace


def node_public(n: Node) -> dict:
    """Safe to render on the canvas before login — no responsibilities/prompt."""
    return {"node_key": n.node_key, "name": n.name, "type": n.type, "autonomy_level": n.autonomy_level}


def node_full(n: Node) -> dict:
    return {
        "node_id": n.node_key,
        "name": n.name,
        "type": n.type,
        "responsibilities": n.responsibilities,
        "constraints": n.constraints,
        "autonomy_level": n.autonomy_level,
        "agent_system_prompt": n.agent_system_prompt,
    }


def edge_dict(e: Edge) -> dict:
    return {
        "edge_id": e.edge_key,
        "source_node_id": e.source_node_key,
        "target_node_id": e.target_node_key,
        "action_type": e.action_type,
        "required_data_payload": e.required_data_payload,
    }


def workspace_dict(ws: Workspace) -> dict:
    return {
        "workspace_id": ws.id,
        "workspace_name": ws.workspace_name,
        "industry": ws.industry,
        "global_objective": ws.global_objective,
        "trigger_event": ws.trigger_event,
        "standard_sla_days": ws.standard_sla_days,
    }


def full_graph(ws: Workspace) -> dict:
    return {
        "workspace": workspace_dict(ws),
        "nodes": [node_full(n) for n in ws.nodes],
        "edges": [edge_dict(e) for e in ws.edges],
        "agent_guardrails": ws.agent_guardrails,
    }
