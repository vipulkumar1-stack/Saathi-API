"""
THROWAWAY spike — verifies the auth chain before any real suite code is written.

Checks, in order:
  1. GET /hmac-token — does it return a usable secret, unauthenticated?
  2. Try several HMAC signing payloads against one cheap GraphQL read
     (finex -> BankList) until one returns HTTP 200.
  3. POST send_otp then validate_otp with the fixed test credentials
     from the collection, to confirm the OTP login flow still works
     and to find where the JWT lives in the response.

Run: python3 tools/probe/probe_auth.py
Not part of the suite — delete or fold findings into src/auth/* once verified.
"""
import hashlib
import hmac
import json
import time
import uuid

import requests

BASE = "https://pre-apis.ambak.com"
ORIGIN = "https://pre-saathi.ambak.com"
COMMON_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": ORIGIN,
    "referer": ORIGIN + "/",
}

MOBILE = "9990511718"
OTP = "987789"

BANK_LIST_BODY = {
    "query": "query BankList { BankList { id name } }",
    "variables": {},
    "operationName": "BankList",
}


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def dump_response(resp):
    print(f"status={resp.status_code}  content-type={resp.headers.get('content-type')}")
    body_preview = resp.text[:1500]
    print(f"body[:1500]=\n{body_preview}")
    return resp


def step1_hmac_token():
    section("STEP 1: GET /hmac-token")
    try:
        resp = requests.get(f"{BASE}/hmac-token", headers=COMMON_HEADERS, timeout=20)
    except requests.RequestException as e:
        print(f"REQUEST FAILED: {e!r}")
        return None
    dump_response(resp)
    if resp.status_code != 200:
        print("-> /hmac-token did NOT return 200. Cannot assume a secret is issued here.")
        return None
    try:
        data = resp.json()
    except ValueError:
        print("-> response is not JSON.")
        return None
    print(f"-> parsed JSON keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
    return data


def sign_meta_only(meta: str, secret: str) -> str:
    return hmac.new(secret.encode(), meta.encode(), hashlib.sha256).hexdigest()


def sign_meta_plus_body(meta: str, secret: str, body: str) -> str:
    return hmac.new(secret.encode(), (meta + body).encode(), hashlib.sha256).hexdigest()


def sign_method_path_meta(meta: str, secret: str, method: str, path: str) -> str:
    payload = f"{method}{path}{meta}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_method_path_body_meta(meta: str, secret: str, method: str, path: str, body: str) -> str:
    payload = f"{method}{path}{body}{meta}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def step2_try_signing_variants(secret: str, bearer_token: str = None):
    section("STEP 2: try HMAC signing variants against finex GraphQL (BankList)")
    if not secret:
        print("-> No secret available from step 1. Skipping signed attempts, "
              "but still trying an UNSIGNED call for comparison.")

    path = "/finex/api/v1/graphql"
    url = BASE + path
    body_str = json.dumps(BANK_LIST_BODY)

    variants = []
    if secret:
        ts = int(time.time())
        nonce = uuid.uuid4().hex[:16]
        meta = f"ts={ts};nonce={nonce}"
        variants = [
            ("meta-only (collection's guess)", sign_meta_only(meta, secret), meta),
            ("meta+body", sign_meta_plus_body(meta, secret, body_str), meta),
            ("method+path+meta", sign_method_path_meta(meta, secret, "POST", path), meta),
            ("method+path+body+meta", sign_method_path_body_meta(meta, secret, "POST", path, body_str), meta),
        ]

    results = []
    for label, signature, meta in variants:
        headers = dict(COMMON_HEADERS)
        headers.update({
            "content-type": "application/json",
            "x-hmac-meta": meta,
            "x-hmac-signature": signature,
        })
        if bearer_token:
            headers["authorization"] = f"Bearer {bearer_token}"
        try:
            resp = requests.post(url, headers=headers, data=body_str, timeout=20)
        except requests.RequestException as e:
            print(f"[{label}] REQUEST FAILED: {e!r}")
            continue
        print(f"\n-- variant: {label} --")
        dump_response(resp)
        results.append((label, resp.status_code))

    # Unsigned baseline for comparison
    headers = dict(COMMON_HEADERS)
    headers["content-type"] = "application/json"
    if bearer_token:
        headers["authorization"] = f"Bearer {bearer_token}"
    try:
        resp = requests.post(url, headers=headers, data=body_str, timeout=20)
        print("\n-- variant: UNSIGNED (baseline) --")
        dump_response(resp)
        results.append(("unsigned", resp.status_code))
    except requests.RequestException as e:
        print(f"[unsigned] REQUEST FAILED: {e!r}")

    print("\nSummary:", results)
    return results


def step3_otp_login():
    section("STEP 3: send_otp -> validate_otp with fixed test credentials")
    send_url = f"{BASE}/account/user/send_otp"
    send_body = {"source": "onboarding", "mobile": MOBILE}
    headers = dict(COMMON_HEADERS)
    headers["content-type"] = "application/json"
    try:
        resp = requests.post(send_url, headers=headers, json=send_body, timeout=20)
    except requests.RequestException as e:
        print(f"send_otp REQUEST FAILED: {e!r}")
        return None
    print("-- send_otp --")
    dump_response(resp)

    validate_url = f"{BASE}/account/user/validate_otp"
    validate_headers = dict(headers)
    validate_headers["source"] = "onboarding"
    validate_body = {"otp": OTP, "kind": "1", "mobile": MOBILE}
    try:
        resp = requests.post(validate_url, headers=validate_headers, json=validate_body, timeout=20)
    except requests.RequestException as e:
        print(f"validate_otp REQUEST FAILED: {e!r}")
        return None
    print("-- validate_otp --")
    dump_response(resp)

    token = None
    if resp.status_code == 200:
        try:
            data = resp.json()
            print(f"-> parsed JSON top-level keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        except ValueError:
            print("-> validate_otp response not JSON.")
    return token


if __name__ == "__main__":
    hmac_data = step1_hmac_token()
    secret = None
    if isinstance(hmac_data, dict):
        for key in ("secret", "hmac_secret", "token", "key", "data"):
            if key in hmac_data:
                candidate = hmac_data[key]
                if isinstance(candidate, str):
                    secret = candidate
                    print(f"-> using hmac_data['{key}'] as secret candidate")
                    break
    step2_try_signing_variants(secret)
    step3_otp_login()
    section("DONE — review output above before writing any real suite code")
