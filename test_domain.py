# -*- coding: utf-8 -*-
"""Test: query service(id) deployments + serviceDomainCreate shapes."""
import sys, time, re, requests, random, string, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, r"C:\Users\LEGION\Documents\grok-maker")
from xconsole_client.muarai_solver import MuaraicaptchaSolver
from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"
MUARAI_KEY = "mc_live_9ba88d8f01224f7bd1b2f957731cc30f"
SITEKEY = "0x4AAAAAAC1ksDZJd9ksGuf7"
DOMAIN = "gomal.tech"
REPO_NAME = "https://github.com/MisthiosOG/Hermes-Gateway"


def new_email():
    username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    r = requests.post(f"{GOMAIL}/api/v1/auth/signup", json={"username": username, "password": "Test123!", "domain": DOMAIN})
    j = r.json()
    return j["profile"]["email_alias"], j["token"]


def get_otp(mail_token, tries=40):
    for i in range(tries):
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            subject = str(e.get("subject", ""))
            body = str(e.get("text", "") or e.get("html", ""))
            m = re.search(r"\b(\d{6})\b", subject + " " + body)
            if m:
                return m.group(1)
        time.sleep(2)
    return None


def make_browser():
    co = ChromiumOptions()
    co.auto_port(True)
    co.no_js(False)
    co.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    co.set_argument("--headless=new")
    co.set_argument("--disable-gpu")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-blink-features=AutomationControlled")
    return ChromiumPage(co)


def run_async_store(p, code, key="__r"):
    p.run_js(f"window['{key}'] = null;")
    p.run_js(f"(async () => {{\n{code}\n}})().catch(e => {{ window['{key}'] = 'ERR:' + e.message; }});")
    for _ in range(60):
        r = p.run_js(f"return window['{key}']")
        if r and r != "null":
            return r
        time.sleep(0.5)
    return p.run_js(f"return window['{key}']")


def gql(p, query, variables=None):
    p.run_js(f"window.__gql_vars = {json.dumps(variables or {})};")
    p.run_js(f"window.__gql_query = {json.dumps(query)};")
    return run_async_store(p, """
        const res = await fetch('https://backboard.railway.com/graphql/internal', {
            method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ query: window.__gql_query, variables: window.__gql_vars })
        });
        const txt = await res.text();
        window.__r = 'status=' + res.status + ' body=' + txt.substring(0, 2500);
    """)


def login(p, email, mail_token, ts_token):
    run_async_store(p, """
        const m = await import('/assets/es-Cnk9wDkR.js');
        const { Magic } = m.t;
        window.__magic = new Magic('pk_live_7797D999FCBC3993');
        window.__r = 'loaded';
    """)
    p.run_js("window.__didResult = null;")
    p.run_js(f"""
        window.__magic.auth.loginWithEmailOTP({{ email: '{email}', showUI: true }})
            .then(did => {{ window.__didResult = 'OK:' + String(did); }})
            .catch(e => {{ window.__didResult = 'ERR:' + e.message; }});
    """)
    otp = get_otp(mail_token)
    if not otp:
        return "OTP_NOT_FOUND"
    ifr = None
    for _ in range(20):
        try:
            ifr = p.ele("tag:iframe@src:auth.magic.link", timeout=2)
            if ifr:
                break
        except Exception:
            pass
        time.sleep(1)
    if not ifr:
        return "IFRAME_NOT_FOUND"
    for idx, digit in enumerate(otp):
        inp = ifr.ele(f"#pin-code-input-{idx}", timeout=3)
        if inp:
            inp.input(digit)
            time.sleep(0.15)
    did = None
    for _ in range(40):
        res = p.run_js("return window.__didResult")
        if res and res.startswith("OK:"):
            did = res[3:]
            break
        time.sleep(1)
    if not did:
        return "DID_NOT_FOUND"
    p.run_js(f"window.__did = {json.dumps(did)};")
    body = {"referralCode": None, "ref": None, "posthogSessionId": None, "turnstileToken": ts_token, "attribution": {"referringDomain": "$direct", "landingPath": "/login"}, "signupSurface": "web"}
    p.run_js(f"window.__body = {json.dumps(body)};")
    return run_async_store(p, """
        const res = await fetch('https://backboard.railway.com/login/magic', {
            method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + window.__did},
            body: JSON.stringify(window.__body)
        });
        await res.text();
        window.__r = res.status;
    """)


def main():
    email, mail_token = new_email()
    print(f"[1] {email}")
    solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
    ts = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
    print("[2] turnstile OK")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)
    st = login(p, email, mail_token, ts)
    print(f"[2.5] login status: {st}")

    # setup
    r = gql(p, "query { me { id workspaces { id name } } }")
    print(f"    me query: {r[:200]}")
    m = re.search(r'"workspaces"\s*:\s*\[\s*\{\s*"id"\s*:\s*"([a-f0-9-]{36})"', r)
    if not m:
        print("    GAGAL parse workspace")
        p.quit()
        return
    ws = m.group(1)
    r = gql(p, "mutation projectCreate($input: ProjectCreateInput!) { projectCreate(input: $input) { id } }", {"input": {"name": "Hermes-Gateway", "workspaceId": ws}})
    pid = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    r = gql(p, "mutation serviceCreate($input: ServiceCreateInput!) { serviceCreate(input: $input) { id } }", {"input": {"projectId": pid, "name": "hermes-gateway", "environmentId": None, "source": {"repo": REPO_NAME}, "branch": "main"}})
    sid = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    r = gql(p, "query environments($projectId: String!) { environments(projectId: $projectId) { edges { node { id name } } } }", {"projectId": pid})
    eid = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    print(f"[3] project={pid} service={sid} env={eid}")

    # set env var
    r = gql(p, "mutation variableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }", {"input": {"projectId": pid, "environmentId": eid, "name": "ADMIN_PASSWORD", "value": "test123"}})
    print(f"[4] var: {'OK' if '\"errors\"' not in r else 'ERR'}")

    # query service(id) deployments
    print("[5] query service(id) deployments...")
    r = gql(p, """
    query service($id: String!) {
      service(id: $id) {
        id
        name
        deployments(first: 1) {
          edges {
            node {
              id
              status
              staticUrl
              suggestAddServiceDomain
            }
          }
        }
      }
    }
    """, {"id": sid})
    print(f"    {r}")

    # coba serviceDomainCreate berbagai shape
    print("[6] serviceDomainCreate shapes...")
    shapes = [
        {"projectId": pid, "environmentId": eid, "serviceId": sid},
        {"environmentId": eid, "serviceId": sid},
        {"serviceId": sid},
        {"projectId": pid, "environmentId": eid, "serviceId": sid, "domain": ""},
        {"projectId": pid, "environmentId": eid, "serviceId": sid, "targetPort": 8080},
    ]
    for i, shape in enumerate(shapes):
        r = gql(p, "mutation serviceDomainCreate($input: ServiceDomainCreateInput!) { serviceDomainCreate(input: $input) { id } }", {"input": shape})
        ok = '"errors"' not in r
        print(f"    [{i}] {list(shape.keys())}: {'OK' if ok else 'ERR'} {r[:180]}")

    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
