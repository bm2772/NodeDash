"""Quick RAG semantic-cache check against a running backend (needs Ollama + embed model).

Asks a node's agent three prompts:
  Q1 — a question (nothing cached yet)
  Q2 — semantically SIMILAR to Q1 (should retrieve Q1 as memory)
  Q3 — UNRELATED (should retrieve nothing)
"""
import httpx

B = "http://127.0.0.1:8000"
H = None


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


def main():
    global H
    tok = httpx.post(B + "/auth/login", json={"email": "admin@acme.test", "password": "admin123"}).json()["access_token"]
    H = hdr(tok)
    me = httpx.get(B + "/auth/me", headers=H).json()
    ws = me["workspace_id"]
    graph = httpx.get(B + f"/workspace/{ws}/graph", headers=H).json()
    node = next(n["node_id"] for n in graph["nodes"] if "finance" in n["node_id"])
    print(f"workspace={ws} node={node}\n")

    def ask(msg):
        r = httpx.post(
            B + f"/workspace/{ws}/nodes/{node}/agent/invoke",
            headers=H, json={"message": msg}, timeout=180,
        ).json()
        return r["reply"]["body"], r.get("used_memory", [])

    q1 = "A lumber vendor will be 3 days late. What should we do?"
    q2 = "What do we do if a timber supplier is delayed by a couple of days?"   # similar to q1
    q3 = "What is our standard invoice approval turnaround time?"               # unrelated

    r1, m1 = ask(q1)
    print(f"Q1: {q1}\n  reply: {r1[:120]}...\n  used_memory: {len(m1)} (expect 0)\n")

    r2, m2 = ask(q2)
    print(f"Q2 (similar): {q2}\n  used_memory: {len(m2)} (expect >=1)")
    for m in m2:
        print(f"    ↳ score={m['score']} matched Q: {m['query']}")
    print()

    r3, m3 = ask(q3)
    print(f"Q3 (unrelated): {q3}\n  used_memory: {len(m3)} (expect 0)")
    for m in m3:
        print(f"    ↳ score={m['score']} matched Q: {m['query']}")

    print("\nRESULT:", "PASS" if (len(m1) == 0 and len(m2) >= 1) else "CHECK — similar query did not retrieve prior exchange")


if __name__ == "__main__":
    main()
