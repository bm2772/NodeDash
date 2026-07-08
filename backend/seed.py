"""Provision the committed Acme seed graph directly (no interview / no LLM).

Useful for the frontend and demos: gives you a workspace_id, an admin login, and
the per-node access codes for the login-gated node windows.

Run:  python seed.py
"""
import json

from app.config import settings
from app.database import SessionLocal, init_db
from app.graph_spec import normalize_spec, validate_spec
from app.provisioning import create_admin, provision_workspace
from app.security import hash_password

ADMIN_EMAIL = "admin@acme.test"
ADMIN_PASSWORD = "admin123"


def main() -> None:
    init_db()
    with open(settings.seed_path, "r", encoding="utf-8") as f:
        spec = normalize_spec(json.load(f))
    errors = validate_spec(spec)
    if errors:
        raise SystemExit(f"Seed spec invalid: {errors}")

    db = SessionLocal()
    try:
        ws = provision_workspace(db, spec)
        create_admin(db, ws.id, ADMIN_EMAIL, hash_password(ADMIN_PASSWORD))
        print(f"\nProvisioned workspace: {ws.workspace_name}")
        print(f"  workspace_id : {ws.id}")
        print(f"  admin login  : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print("\n  Node access codes (for POST /auth/node-login):")
        for n in ws.nodes:
            print(f"    - {n.name:<28} node_key={n.node_key:<32} access_code={n.access_code}")
        print("\nStart the API with:  uvicorn app.main:app --reload\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
