"""End-to-end smoke test of the backend, offline (LLM_PROVIDER=mock).

Exercises: interview -> generate graph -> render canvas -> node-scoped login ->
scoped access is enforced -> agent invoke + message bus.

Run:  python smoke_test.py     (uses a throwaway sqlite file)
"""
import os
import tempfile

# Configure BEFORE importing the app.
_db_fd, _db_path = tempfile.mkstemp(suffix=".db")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["JWT_SECRET"] = "smoke-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()  # startup event only fires under a context-managed client; be explicit here
client = TestClient(app)

ANSWERS = {
    "q_industry_output": "Custom Furniture Manufacturing",
    "q_global_objective": "Deliver custom furniture within 14 days.",
    "q_operational_stages": "sourcing, assembly, quality assurance, distribution",
    "q_bottlenecks": "vendor delays on raw materials",
    "q_internal_teams": "Procurement, Finance",
    "q_external_partners": "Oakline Timber",
    "q_capacity_constraints": "Finance needs 48h to approve; vendors juggle multiple clients",
    "q_people_to_seats": "alice@acme.test, bob@acme.test",
    "q_trigger": "New Client Contract Signed",
    "q_approval_chains": "Procurement proposes, Finance approves, Vendor executes",
    "q_data_handoffs": "Purchase Order, Vendor Details",
    "q_autonomy_level": "Finance can execute standard; Procurement suggests only",
    "q_external_visibility": "strict isolation - only assigned deadlines",
    "q_exception_handling": "auto-renegotiate then alert the human",
    "q_communication_tone": "professional and concise",
}

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((PASS if cond else FAIL, name, detail))
    print(f"  [{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail and not cond else ""))


def main() -> int:
    print("health:")
    r = client.get("/health")
    check("health ok", r.status_code == 200 and r.json()["status"] == "ok", r.text)
    check("mock mode (llm disabled)", r.json().get("llm_enabled") is False, r.text)

    print("interview:")
    r = client.post("/interview/start", json={"admin_email": "admin@acme.test", "admin_password": "admin123"})
    check("start interview", r.status_code == 201, r.text)
    sid = r.json()["session_id"]
    check("first question returned", r.json().get("next_question") is not None)

    for qid, ans in ANSWERS.items():
        r = client.post(f"/interview/{sid}/answer", json={"question_id": qid, "answer": ans})
        check(f"answer {qid}", r.status_code == 200, r.text)
    check("interview complete", client.get(f"/interview/{sid}").json()["progress"]["complete"])

    print("generate:")
    r = client.post(f"/interview/{sid}/generate")
    check("generate workspace", r.status_code == 200, r.text)
    data = r.json()
    ws_id = data["workspace_id"]
    admin_token = data["admin_token"]
    graph = data["graph"]
    node_access = {n["name"]: n for n in data["node_access"]}
    check("generation valid", data["generation"]["valid"], str(data.get("generation")))
    check(">=3 nodes generated", len(graph["nodes"]) >= 3, str([n["node_id"] for n in graph["nodes"]]))
    check(">=1 edge generated", len(graph["edges"]) >= 1)
    check("every node has agent prompt",
          all(n["agent_system_prompt"].strip() for n in graph["nodes"]))
    check("guardrails compiled from answers",
          graph["agent_guardrails"]["communication_tone"] == "professional_and_concise",
          str(graph["agent_guardrails"]))

    print("canvas + admin graph:")
    r = client.get(f"/workspace/{ws_id}/public")
    check("public canvas (no auth)", r.status_code == 200 and "nodes" in r.json())
    check("public view hides prompts", all("agent_system_prompt" not in n for n in r.json()["nodes"]))
    r = client.get(f"/workspace/{ws_id}/graph", headers={"Authorization": f"Bearer {admin_token}"})
    check("admin reads full graph", r.status_code == 200)

    print("node-scoped login + access control:")
    finance = next((v for k, v in node_access.items() if "finance" in k.lower()), None) \
        or list(node_access.values())[0]
    other = next((v for v in node_access.values() if v["node_key"] != finance["node_key"]), None)

    r = client.post("/auth/node-login", json={
        "workspace_id": ws_id, "node_key": finance["node_key"],
        "access_code": finance["access_code"],
        "email": "finance.member@acme.test", "password": "member123",
    })
    check("seat login with access code", r.status_code == 200, r.text)
    member_token = r.json()["access_token"]
    check("token scoped to node", r.json()["node_key"] == finance["node_key"])

    r = client.post("/auth/node-login", json={
        "workspace_id": ws_id, "node_key": finance["node_key"],
        "access_code": "wrong-code",
        "email": "intruder@acme.test", "password": "member123",
    })
    check("wrong access code rejected", r.status_code == 401, r.text)

    hdr = {"Authorization": f"Bearer {member_token}"}
    r = client.get(f"/workspace/{ws_id}/nodes/{finance['node_key']}", headers=hdr)
    check("seat reads OWN node window", r.status_code == 200, r.text)
    check("own window includes documents", len(r.json().get("documents", [])) > 0)

    if other:
        r = client.get(f"/workspace/{ws_id}/nodes/{other['node_key']}", headers=hdr)
        check("seat BLOCKED from other node (403)", r.status_code == 403, r.text)

    r = client.get(f"/workspace/{ws_id}/nodes/{other['node_key']}",
                   headers={"Authorization": f"Bearer {admin_token}"}) if other else None
    if r is not None:
        check("admin reads any node window", r.status_code == 200, r.text)

    print("agent runtime + message bus:")
    r = client.post(
        f"/workspace/{ws_id}/nodes/{finance['node_key']}/agent/invoke",
        headers=hdr, json={"message": "A vendor slipped a checkpoint by 3 days.", "emit_handoffs": True},
    )
    check("agent invoke", r.status_code == 200, r.text)
    check("agent replied", bool(r.json()["reply"]["body"]))
    r = client.get(f"/workspace/{ws_id}/messages", headers={"Authorization": f"Bearer {admin_token}"})
    check("message bus has entries", r.status_code == 200 and len(r.json()["messages"]) >= 1)

    print()
    failed = [x for x in results if x[0] == FAIL]
    print(f"{'='*50}\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILURES:")
        for _, name, detail in failed:
            print(f"  - {name}: {detail[:300]}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        try:
            os.remove(_db_path)
        except OSError:
            pass
