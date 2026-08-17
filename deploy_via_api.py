# -*- coding: utf-8 -*-
"""
Railway auto-order: buat akun + deploy Hermes-Gateway.

Usage:
  python deploy_via_api.py create          # buat order baru (~1 menit)
  python deploy_via_api.py url <project_id>  # ambil URL publik (nunggu build)

Hasil create disimpan ke orders.json.
"""
import sys, os, time, re, requests, random, string, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from solver import MuaraicaptchaSolver
from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"
MUARAI_KEY = "mc_live_9ba88d8f01224f7bd1b2f957731cc30f"
SITEKEY = "0x4AAAAAAC1ksDZJd9ksGuf7"
DOMAIN = "gomal.tech"
REPO_NAME = "https://github.com/MisthiosOG/Hermes-Gateway"
REPO_BRANCH = "main"
# Docker image (dibuild GitHub Actions, lebih simple: gak butuh GitHub OAuth)
IMAGE_NAME = "ghcr.io/misthiosog/hermes-gateway:latest"
ORDERS_FILE = os.path.join(HERE, "orders.json")
COOKIES_FILE = os.path.join(HERE, "session_cookies.json")


def gen_password(n=16):
    return "".join(random.choices(string.ascii_letters + string.digits, k=n))


def new_email():
    username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    r = requests.post(f"{GOMAIL}/api/v1/auth/signup",
                      json={"username": username, "password": "Test123!", "domain": DOMAIN})
    j = r.json()
    return j["profile"]["email_alias"], j["token"]


def get_otp(mail_token, tries=40):
    # catat email terbaru dulu (received_at)
    newest = ""
    try:
        r = requests.get(f"{GOMAIL}/api/v1/emails",
                         headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            ra = str(e.get("received_at", ""))
            if ra > newest:
                newest = ra
    except Exception:
        pass

    # tunggu email BARU (received_at > newest)
    for i in range(tries):
        r = requests.get(f"{GOMAIL}/api/v1/emails",
                         headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            ra = str(e.get("received_at", ""))
            if ra > newest:
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
        window.__r = 'status=' + res.status + ' body=' + txt.substring(0, 3000);
    """)


def save_cookies(p):
    try:
        # kunjungi backboard biar session cookie (domain backboard) ke-capture
        p.get("https://backboard.railway.com/graphql/internal")
        time.sleep(2)
        cl = p.cookies()
        cookies = cl.as_dict() if hasattr(cl, "as_dict") else list(cl)
        with open(COOKIES_FILE, "w") as f:
            json.dump(cookies, f)
    except Exception as e:
        print(f"    warn: save cookies gagal: {e}")


def restore_cookies(p):
    if not os.path.exists(COOKIES_FILE):
        return False
    try:
        with open(COOKIES_FILE) as f:
            cookies = json.load(f)
        p.get("https://backboard.railway.com/graphql/internal")
        time.sleep(2)
        p.set.cookies(cookies)
        return True
    except Exception as e:
        print(f"    warn: restore cookies gagal: {e}")
        return False


def login_and_exchange(p, email, mail_token):
    """Login Magic OTP + exchange. Return True kalau sukses."""
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
    did = None
    for _ in range(40):
        res = p.run_js("return window.__didResult")
        if res and res.startswith("OK:"):
            did = res[3:]
            break
        if res and res.startswith("ERR:"):
            return None
        time.sleep(1)
    if not did:
        return None
    return did


def create_order():
    admin_pw = gen_password(16)
    ssh_pw = gen_password(16)

    email, mail_token = new_email()
    print(f"[1] Email: {email}")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)

    ok = False
    for attempt in range(3):
        print(f"[2] Login attempt {attempt+1}/3...")
        p.get("https://railway.com/login")
        time.sleep(3)
        did = login_and_exchange(p, email, mail_token)
        if not did:
            print("    DID gagal")
            continue
        # solve turnstile PAS setelah dapet DID (fresh token)
        solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
        ts_token = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
        p.run_js(f"window.__did = {json.dumps(did)};")
        body = {"referralCode": None, "ref": None, "posthogSessionId": None,
                "turnstileToken": ts_token,
                "attribution": {"referringDomain": "$direct", "landingPath": "/login"},
                "signupSurface": "web"}
        p.run_js(f"window.__body = {json.dumps(body)};")
        st = run_async_store(p, """
            const res = await fetch('https://backboard.railway.com/login/magic', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + window.__did},
                body: JSON.stringify(window.__body)
            });
            const txt = await res.text();
            window.__r = res.status + '|' + txt.substring(0, 200);
        """)
        print(f"    exchange: {st}")
        if "200" in str(st):
            ok = True
            break
    if not ok:
        print("LOGIN GAGAL")
        p.quit()
        return None

    # workspace
    r = gql(p, "query { me { id workspaces { id name } } }")
    m = re.search(r'"workspaces"\s*:\s*\[\s*\{\s*"id"\s*:\s*"([a-f0-9-]{36})"', r)
    ws_id = m.group(1) if m else None
    print(f"[3] workspace: {ws_id}")

    # project
    r = gql(p, "mutation projectCreate($input: ProjectCreateInput!) { projectCreate(input: $input) { id } }",
            {"input": {"name": "Hermes-Gateway", "workspaceId": ws_id}})
    m = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r)
    pid = m.group(1) if m else None
    print(f"[4] project: {pid}")

    # service (deploy dari docker image - gak butuh GitHub OAuth)
    r = gql(p, "mutation serviceCreate($input: ServiceCreateInput!) { serviceCreate(input: $input) { id } }",
            {"input": {"projectId": pid, "name": "hermes-gateway", "environmentId": None,
                       "source": {"image": IMAGE_NAME}}})
    m = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r)
    sid = m.group(1) if m else None
    print(f"[5] service: {sid}")

    # environment
    r = gql(p, "query environments($projectId: String!) { environments(projectId: $projectId) { edges { node { id name } } } }",
            {"projectId": pid})
    m = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r)
    eid = m.group(1) if m else None
    print(f"[6] env: {eid}")

    # env vars (setelah serviceId dapet)
    print("[7] set env vars (via config patch)...")
    # variable dimasukin langsung ke config service, bukan via variableUpsert
    for k, v in [("ADMIN_PASSWORD", admin_pw), ("SSH_ROOT_PASSWORD", ssh_pw)]:
        r = gql(p, "mutation variableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }",
                {"input": {"projectId": pid, "environmentId": eid, "serviceId": sid, "name": k, "value": v}})
        print(f"    {k}: {'OK' if '\"errors\"' not in r else 'ERR'}")

    # create service instance (isCreated=true) + trigger build
    print("[8] create instance + deploy...")
    patch = {"services": {sid: {"isCreated": True, "source": {"image": IMAGE_NAME}}}}
    r = gql(p, """
    mutation environmentPatchCommit($environmentId: String!, $patch: EnvironmentConfig!, $message: String) {
      environmentPatchCommit(environmentId: $environmentId, patch: $patch, commitMessage: $message)
    }
    """, {"environmentId": eid, "patch": patch, "message": "deploy hermes-gateway"})
    print(f"    patch: {r[:200]}")
    time.sleep(3)
    r = gql(p, """
    mutation serviceInstanceDeploy($serviceId: String!, $environmentId: String!, $latestCommit: Boolean) {
      serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId, latestCommit: $latestCommit)
    }
    """, {"serviceId": sid, "environmentId": eid, "latestCommit": True})
    print(f"    deploy: {r[:200]}")

    # buat domain publik
    print("[9] buat domain...")
    r = gql(p, """
    mutation serviceDomainCreate($input: ServiceDomainCreateInput!) {
      serviceDomainCreate(input: $input) { id }
    }
    """, {"input": {"environmentId": eid, "serviceId": sid}})
    print(f"    {r[:200]}")

    order = {
        "email": email,
        "mail_token": mail_token,
        "admin_username": "admin",
        "admin_password": admin_pw,
        "ssh_password": ssh_pw,
        "project_id": pid,
        "service_id": sid,
        "environment_id": eid,
        "url": None,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # append ke orders.json
    orders = []
    if os.path.exists(ORDERS_FILE):
        try:
            orders = json.load(open(ORDERS_FILE))
        except Exception:
            orders = []
    orders.append(order)
    json.dump(orders, open(ORDERS_FILE, "w"), indent=2)

    p.quit()
    print("\n=== ORDER DIBUAT ===")
    print(json.dumps(order, indent=2))
    print(f"\nURL belum siap (build ~5-10 menit). Cek nanti:")
    print(f"  python deploy_via_api.py url {pid}")
    return order


def get_url(project_id):
    """Re-login pakai email + mail_token tersimpan, lalu poll staticUrl."""
    # cari order
    orders = json.load(open(ORDERS_FILE)) if os.path.exists(ORDERS_FILE) else []
    order = next((o for o in orders if o.get("project_id") == project_id), None)
    if not order:
        print("Order tidak ditemukan di orders.json")
        return None

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)

    # re-login
    ok = False
    for attempt in range(3):
        print(f"[1] re-login attempt {attempt+1}/3...")
        solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
        ts_token = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
        p.get("https://railway.com/login")
        time.sleep(3)
        did = login_and_exchange(p, order["email"], order["mail_token"])
        if not did:
            continue
        p.run_js(f"window.__did = {json.dumps(did)};")
        body = {"referralCode": None, "ref": None, "posthogSessionId": None,
                "turnstileToken": ts_token,
                "attribution": {"referringDomain": "$direct", "landingPath": "/login"},
                "signupSurface": "web"}
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
        if "200" in str(st):
            ok = True
            break
    if not ok:
        print("re-login GAGAL")
        p.quit()
        return None

    # poll domain URL
    for i in range(15):
        r = gql(p, """
        query networking($projectId: String!, $environmentId: String!, $serviceId: String!) {
          domains(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId) {
            serviceDomains { domain }
          }
        }
        """, {"projectId": order["project_id"], "environmentId": order["environment_id"], "serviceId": order["service_id"]})
        m = re.search(r'"domain"\s*:\s*"([^"]+)"', r)
        if m and m.group(1):
            url = "https://" + m.group(1)
            print(f"[2] URL: {url}")
            _update_order_url(project_id, url)
            p.quit()
            return url
        print(f"    [{i}] domain belum siap: {r[:150]}")
        time.sleep(15)
    p.quit()
    return None


def _find_service_id(p, project_id):
    """Dari project_id, cari service_id di orders.json."""
    orders = []
    if os.path.exists(ORDERS_FILE):
        try:
            orders = json.load(open(ORDERS_FILE))
        except Exception:
            pass
    for o in orders:
        if o.get("project_id") == project_id:
            return o.get("service_id")
    return None


def _update_order_url(project_id, url):
    if not os.path.exists(ORDERS_FILE):
        return
    orders = json.load(open(ORDERS_FILE))
    for o in orders:
        if o.get("project_id") == project_id:
            o["url"] = url
    json.dump(orders, open(ORDERS_FILE, "w"), indent=2)


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 1 and args[0] == "create":
        create_order()
    elif len(args) >= 2 and args[0] == "url":
        get_url(args[1])
    else:
        print("Usage:")
        print("  python deploy_via_api.py create")
        print("  python deploy_via_api.py url <project_id>")
