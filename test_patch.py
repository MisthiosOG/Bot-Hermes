# -*- coding: utf-8 -*-
"""Test: full flow + environmentPatchCommit untuk create service instance."""
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
    return r.json()["profile"]["email_alias"], r.json()["token"]


def get_otp(mail_token, tries=40):
    newest = ""
    try:
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            ra = str(e.get("received_at", ""))
            if ra > newest:
                newest = ra
    except Exception:
        pass
    for i in range(tries):
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            if str(e.get("received_at", "")) > newest:
                m = re.search(r"\b(\d{6})\b", str(e.get("subject", "")) + " " + str(e.get("text", "") or e.get("html", "")))
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


def run_async_store(p, code, key="__r", wait=60):
    p.run_js(f"window['{key}'] = null;")
    p.run_js(f"(async () => {{\n{code}\n}})().catch(e => {{ window['{key}'] = 'ERR:' + e.message; }});")
    for _ in range(wait * 2):
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
        return None
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
        return None
    for idx, digit in enumerate(otp):
        inp = ifr.ele(f"#pin-code-input-{idx}", timeout=3)
        if inp:
            inp.input(digit)
            time.sleep(0.15)
    for _ in range(40):
        res = p.run_js("return window.__didResult")
        if res and res.startswith("OK:"):
            return res[3:]
        time.sleep(1)
    return None


def main():
    email, mail_token = new_email()
    print(f"[1] {email}")
    solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
    ts = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
    print("[2] turnstile OK")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)

    # login + exchange
    for attempt in range(3):
        did = login(p, email, mail_token, ts)
        if did:
            break
        print(f"    login retry {attempt+1}")
        ts = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
        p.get("https://railway.com/login")
        time.sleep(3)
    if not did:
        print("LOGIN GAGAL")
        return
    p.run_js(f"window.__did = {json.dumps(did)};")
    body = {"referralCode": None, "ref": None, "posthogSessionId": None, "turnstileToken": ts, "attribution": {"referringDomain": "$direct", "landingPath": "/login"}, "signupSurface": "web"}
    p.run_js(f"window.__body = {json.dumps(body)};")
    st = run_async_store(p, """
        const res = await fetch('https://backboard.railway.com/login/magic', {
            method: 'POST', credentials: 'include',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + window.__did},
            body: JSON.stringify(window.__body)
        });
        await res.text();
        window.__r = res.status;
    """)
    print(f"[3] exchange: {st}")

    # setup
    r = gql(p, "query { me { id workspaces { id name } } }")
    ws = re.search(r'"workspaces"\s*:\s*\[\s*\{\s*"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    r = gql(p, "mutation projectCreate($input: ProjectCreateInput!) { projectCreate(input: $input) { id } }", {"input": {"name": "Hermes-Gateway", "workspaceId": ws}})
    pid = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    r = gql(p, "mutation serviceCreate($input: ServiceCreateInput!) { serviceCreate(input: $input) { id } }", {"input": {"projectId": pid, "name": "hermes-gateway", "environmentId": None, "source": {"repo": REPO_NAME}, "branch": "main"}})
    sid = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    r = gql(p, "query environments($projectId: String!) { environments(projectId: $projectId) { edges { node { id name } } } }", {"projectId": pid})
    eid = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r).group(1)
    print(f"[4] project={pid} service={sid} env={eid}")

    # set env var
    r = gql(p, "mutation variableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }", {"input": {"projectId": pid, "environmentId": eid, "name": "ADMIN_PASSWORD", "value": "test123"}})
    print(f"[5] var: {'OK' if '\"errors\"' not in r else 'ERR'}")

    # ==== KUNCI: environmentPatchCommit untuk create instance ====
    print("[6] environmentPatchCommit (isCreated=true)...")
    patch = {"services": {sid: {"isCreated": True, "source": {"repo": REPO_NAME, "branch": "main"}}}}
    r = gql(p, """
    mutation environmentPatchCommit($environmentId: String!, $patch: EnvironmentConfig!, $message: String) {
      environmentPatchCommit(environmentId: $environmentId, patch: $patch, commitMessage: $message)
    }
    """, {"environmentId": eid, "patch": patch, "message": "deploy hermes"})
    print(f"    {r[:300]}")

    # trigger deploy
    print("[7] serviceInstanceDeploy...")
    r = gql(p, """
    mutation serviceInstanceDeploy($serviceId: String!, $environmentId: String!, $latestCommit: Boolean) {
      serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId, latestCommit: $latestCommit)
    }
    """, {"serviceId": sid, "environmentId": eid, "latestCommit": True})
    print(f"    {r[:300]}")

    # cek status deployment via service(id)
    print("[8] cek status deployment...")
    r = gql(p, """
    query service($id: String!) {
      service(id: $id) {
        deployments(first: 3) {
          edges { node { id status staticUrl } }
        }
      }
    }
    """, {"id": sid})
    print(f"    {r[:600]}")

    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
