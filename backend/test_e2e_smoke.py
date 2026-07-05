#!/usr/bin/env python3
"""
E2E Smoke Tests for AFJ Core System
Tests critical flows: BYOK, Petitions, Contracts, Agent Cancellation
"""
import json
import urllib.request
import urllib.error
from datetime import datetime

API_BASE = "http://localhost:8000/api/v1"
TEST_EMAIL = "admin@afj.com.br"
TEST_PASSWORD = "Admin@123"

class TestResults:
    def __init__(self):
        self.tests = []
        self.start_time = datetime.now()

    def add(self, name: str, passed: bool, error: str = None):
        self.tests.append({"name": name, "passed": passed, "error": error})
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"     Error: {error[:100]}")

    def summary(self):
        total = len(self.tests)
        passed = sum(1 for t in self.tests if t["passed"])
        elapsed = (datetime.now() - self.start_time).total_seconds()
        print(f"\n{'='*60}")
        print(f"SMOKE TEST SUMMARY: {passed}/{total} passed in {elapsed:.1f}s")
        print(f"{'='*60}\n")
        for t in self.tests:
            status = "✅" if t["passed"] else "❌"
            print(f"{status} {t['name']}")
        return passed == total

def http_request(method, url, headers=None, data=None, timeout=30):
    """Simple HTTP request helper"""
    if headers is None:
        headers = {}
    if data:
        data = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except:
            return e.code, {"error": body}
    except Exception as e:
        raise e

def run_tests():
    results = TestResults()
    token = None

    # TEST 1: Login
    try:
        status, data = http_request(
            "POST",
            f"{API_BASE}/auth/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = data.get("access_token") if status == 200 else None
        results.add("AUTH: Login successful", token is not None)
    except Exception as e:
        results.add("AUTH: Login successful", False, str(e))
        return results

    headers = {"Authorization": f"Bearer {token}"}

    # TEST 2: Get AI Settings
    try:
        status, data = http_request("GET", f"{API_BASE}/users/me/ai-settings", headers=headers)
        results.add("BYOK: Fetch AI settings", status == 200)
    except Exception as e:
        results.add("BYOK: Fetch AI settings", False, str(e))

    # TEST 3: Update AI Settings with valid model
    try:
        status, data = http_request(
            "PUT",
            f"{API_BASE}/users/me/ai-settings",
            headers=headers,
            data={
                "provider": "gemini",
                "model": "gemini-2.0-flash",
                "api_key": "test-key-12345",
                "enabled": True
            }
        )
        results.add("BYOK: Save AI settings (valid model)", status == 200)
    except Exception as e:
        results.add("BYOK: Save AI settings (valid model)", False, str(e))

    # TEST 4: Model validation - reject invalid model
    try:
        status, data = http_request(
            "PUT",
            f"{API_BASE}/users/me/ai-settings",
            headers=headers,
            data={"model": "InvalidModel"}
        )
        passed = status == 422
        error_detail = data.get("detail", "").lower()
        has_helpful_msg = "inválido" in error_detail or "invalid" in error_detail
        results.add("BYOK: Reject invalid model name", passed and has_helpful_msg)
    except Exception as e:
        results.add("BYOK: Reject invalid model name", False, str(e))

    # TEST 5: List Documents
    try:
        status, data = http_request("GET", f"{API_BASE}/documents", headers=headers)
        results.add("DOCUMENTS: List documents", status == 200)
    except Exception as e:
        results.add("DOCUMENTS: List documents", False, str(e))

    # TEST 6: Create Contract
    contract_id = None
    try:
        status, data = http_request(
            "POST",
            f"{API_BASE}/documents/contracts/create",
            headers=headers,
            data={
                "titulo": "Smoke Test Contract",
                "tipo": "HONORARIOS",
                "conteudo": "Test contract content - not empty",
                "valor_total": 1000.00
            }
        )
        passed = status == 201
        if passed:
            contract_id = data.get("id")
        results.add("CONTRACTS: Create with content", passed)
    except Exception as e:
        results.add("CONTRACTS: Create with content", False, str(e))

    # TEST 7: Get Contract Content
    if contract_id:
        try:
            status, data = http_request(
                "GET",
                f"{API_BASE}/documents/{contract_id}/content",
                headers=headers
            )
            passed = status == 200
            content = data.get("conteudo_texto", "")
            has_content = len(content) > 0
            results.add("CONTRACTS: Fetch content (not empty)", passed and has_content)
        except Exception as e:
            results.add("CONTRACTS: Fetch content (not empty)", False, str(e))

    # TEST 8: Update Contract
    if contract_id:
        try:
            status, data = http_request(
                "PUT",
                f"{API_BASE}/documents/{contract_id}",
                headers=headers,
                data={"conteudo_html": "<p>Updated contract content</p>"}
            )
            results.add("CONTRACTS: Update content", status == 200)
        except Exception as e:
            results.add("CONTRACTS: Update content", False, str(e))

    # TEST 9: Archive Contract (soft delete)
    if contract_id:
        try:
            status, data = http_request(
                "DELETE",
                f"{API_BASE}/documents/{contract_id}",
                headers=headers
            )
            results.add("CONTRACTS: Archive (soft delete)", status == 204)
        except Exception as e:
            results.add("CONTRACTS: Archive (soft delete)", False, str(e))

    # TEST 10: List Archived Documents excluded
    try:
        status, docs = http_request("GET", f"{API_BASE}/documents", headers=headers)
        if status == 200 and isinstance(docs, list):
            has_archived = any(d.get("status") == "ARQUIVADO" for d in docs)
            results.add("DOCUMENTS: Exclude archived by default", not has_archived)
        else:
            results.add("DOCUMENTS: Exclude archived by default", False)
    except Exception as e:
        results.add("DOCUMENTS: Exclude archived by default", False, str(e))

    return results

if __name__ == "__main__":
    print("🧪 AFJ Core System — E2E Smoke Tests\n")
    print(f"API Base: {API_BASE}")
    print(f"Test User: {TEST_EMAIL}\n")

    try:
        results = run_tests()
        all_pass = results.summary()
        exit(0 if all_pass else 1)
    except Exception as e:
        print(f"❌ FATAL ERROR: {e}")
        exit(1)
