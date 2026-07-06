#!/usr/bin/env python3
"""
E2E Smoke Tests for AFJ Core System
Tests critical flows: Auth, BYOK, Contracts, Agent Cancellation.

Config via env vars (nada de segredo hardcoded):
  API_BASE      default http://localhost:8000/api/v1
  TEST_EMAIL    default admin@afj.com.br
  TEST_PASSWORD default Admin@123
  GEMINI_KEY    (opcional) se setado, testa BYOK real ponta-a-ponta
  GEMINI_MODEL  default gemini-2.5-flash
"""
import os
import json
import urllib.request
import urllib.error
from datetime import datetime

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1").rstrip("/")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "admin@afj.com.br")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Admin@123")
GEMINI_KEY = os.environ.get("GEMINI_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


class TestResults:
    def __init__(self):
        self.tests = []
        self.start_time = datetime.now()

    def add(self, name, passed, error=None):
        self.tests.append({"name": name, "passed": passed, "error": error})
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"     → {str(error)[:160]}")

    def summary(self):
        total = len(self.tests)
        passed = sum(1 for t in self.tests if t["passed"])
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print(f"\n{'='*60}")
        print(f"SMOKE TEST SUMMARY: {passed}/{total} passed in {elapsed:.1f}s")
        print(f"{'='*60}")
        return passed, total


def http_request(method, url, headers=None, data=None, timeout=60):
    headers = dict(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw}


def run_tests():
    r = TestResults()

    # 1. Login
    try:
        status, data = http_request("POST", f"{API_BASE}/auth/login",
                                    data={"email": TEST_EMAIL, "password": TEST_PASSWORD})
        token = data.get("access_token") if status == 200 else None
        r.add("AUTH: Login", token is not None, None if token else f"status={status} {data}")
    except Exception as e:
        r.add("AUTH: Login", False, e)
        return r
    if not token:
        return r
    H = {"Authorization": f"Bearer {token}"}

    # 2. Get AI settings
    try:
        status, data = http_request("GET", f"{API_BASE}/users/me/ai-settings", headers=H)
        r.add("BYOK: Fetch settings", status == 200, None if status == 200 else data)
    except Exception as e:
        r.add("BYOK: Fetch settings", False, e)

    # 3. Reject invalid model format ("Gemini")
    try:
        status, data = http_request("PUT", f"{API_BASE}/users/me/ai-settings",
                                    headers=H, data={"provider": "gemini", "model": "Gemini"})
        detail = str(data.get("detail", "")).lower()
        ok = status == 422 and ("inválido" in detail or "invalid" in detail or "formato" in detail)
        r.add("BYOK: Reject invalid model format", ok, None if ok else f"status={status} {data}")
    except Exception as e:
        r.add("BYOK: Reject invalid model format", False, e)

    # 4. Accept valid model format
    try:
        status, data = http_request("PUT", f"{API_BASE}/users/me/ai-settings",
                                    headers=H, data={"provider": "gemini", "model": GEMINI_MODEL})
        r.add("BYOK: Accept valid model", status == 200, None if status == 200 else data)
    except Exception as e:
        r.add("BYOK: Accept valid model", False, e)

    # 5. BYOK real end-to-end (só se GEMINI_KEY fornecida)
    if GEMINI_KEY:
        try:
            http_request("PUT", f"{API_BASE}/users/me/ai-settings", headers=H,
                         data={"provider": "gemini", "model": GEMINI_MODEL,
                               "api_key": GEMINI_KEY, "enabled": True})
            status, data = http_request("POST", f"{API_BASE}/users/me/ai-settings/test", headers=H)
            ok = status == 200 and data.get("ok") is True
            r.add(f"BYOK: Test connection ({GEMINI_MODEL})", ok,
                  None if ok else f"status={status} {data}")
        except Exception as e:
            r.add(f"BYOK: Test connection ({GEMINI_MODEL})", False, e)
    else:
        print("ℹ️  BYOK real skipped (set GEMINI_KEY to enable)")

    # 6. List documents
    try:
        status, data = http_request("GET", f"{API_BASE}/documents", headers=H)
        r.add("DOCS: List", status == 200, None if status == 200 else data)
    except Exception as e:
        r.add("DOCS: List", False, e)

    # 7. Create contract with content
    contract_id = None
    try:
        status, data = http_request("POST", f"{API_BASE}/documents/contracts/create", headers=H,
                                    data={"titulo": "Smoke Test Contract", "tipo": "HONORARIOS",
                                          "conteudo": "Conteúdo de teste — não vazio", "valor_total": 1000.0})
        contract_id = data.get("id") if status == 201 else None
        r.add("CONTRACTS: Create with content", contract_id is not None,
              None if contract_id else f"status={status} {data}")
    except Exception as e:
        r.add("CONTRACTS: Create with content", False, e)

    # 8. Content persisted (not empty)
    if contract_id:
        try:
            status, data = http_request("GET", f"{API_BASE}/documents/{contract_id}/content", headers=H)
            content = (data.get("conteudo_texto") or "") if status == 200 else ""
            r.add("CONTRACTS: Content not empty", bool(content),
                  None if content else f"status={status} {data}")
        except Exception as e:
            r.add("CONTRACTS: Content not empty", False, e)

    # 9. Update contract
    if contract_id:
        try:
            status, data = http_request("PUT", f"{API_BASE}/documents/{contract_id}", headers=H,
                                        data={"conteudo_html": "<p>Editado</p>"})
            r.add("CONTRACTS: Update", status == 200, None if status == 200 else data)
        except Exception as e:
            r.add("CONTRACTS: Update", False, e)

    # 10. Hard delete
    if contract_id:
        try:
            status, data = http_request("DELETE",
                                        f"{API_BASE}/documents/{contract_id}?hard=true", headers=H)
            r.add("CONTRACTS: Hard delete", status == 204, None if status == 204 else data)
        except Exception as e:
            r.add("CONTRACTS: Hard delete", False, e)

    # 11. Trigger agent + cancel
    try:
        status, data = http_request("POST", f"{API_BASE}/agents/trigger", headers=H,
                                    data={"task_type": "search_jurisprudence",
                                          "task_input": {"descricao": "smoke test"}})
        run_id = data.get("run_id") if status == 202 else None
        r.add("AGENTS: Trigger", run_id is not None, None if run_id else f"status={status} {data}")
    except Exception as e:
        r.add("AGENTS: Trigger", False, e)
        run_id = None

    if run_id:
        try:
            status, data = http_request("POST", f"{API_BASE}/agents/runs/{run_id}/cancel", headers=H)
            # 200 = cancelado; 409 = já terminou (aceitável se a run foi rápida)
            ok = status in (200, 409)
            r.add("AGENTS: Cancel run", ok, None if ok else f"status={status} {data}")
        except Exception as e:
            r.add("AGENTS: Cancel run", False, e)

    return r


if __name__ == "__main__":
    print("🧪 AFJ Core System — E2E Smoke Tests\n")
    print(f"API Base: {API_BASE}")
    print(f"User:     {TEST_EMAIL}")
    print(f"BYOK:     {'ON (' + GEMINI_MODEL + ')' if GEMINI_KEY else 'OFF'}\n")
    try:
        results = run_tests()
        passed, total = results.summary()
        raise SystemExit(0 if passed == total else 1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"❌ FATAL: {e}")
        raise SystemExit(1)
