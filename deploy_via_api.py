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
# solver & DrissionPage di-import lazy (di dalam fungsi) biar Flask app gak crash
# kalau Chrome belum siap

GOMAIL = "https://mail.gopretstudio.com"
MUARAI_KEY = os.environ.get("MUARAI_API_KEY", "mc_live_9ba88d8f01224f7bd1b2f957731cc30f")
SITEKEY = "0x4AAAAAAC1ksDZJd9ksGuf7"
DOMAIN = "gomal.tech"
REPO_NAME = "https://github.com/MisthiosOG/Hermes-Gateway"
REPO_BRANCH = "main"
# Docker image (dibuild GitHub Actions, lebih simple: gak butuh GitHub OAuth)
IMAGE_NAME = "ghcr.io/misthiosog/hermes-gateway:latest"
# Buyer dapet 3 link: Hermes panel + 9Router + terminal web (ttyd)
ROUTER_IMAGE = "ghcr.io/decolua/9router:latest"
TERMINAL_IMAGE = "tsl0922/ttyd:alpine"
# Data disimpan di DATA_DIR (Railway Volume) biar survive redeploy
DATA_DIR = os.environ.get("DATA_DIR", HERE)
os.makedirs(DATA_DIR, exist_ok=True)
ORDERS_FILE = os.path.join(DATA_DIR, "orders.json")
COOKIES_FILE = os.path.join(DATA_DIR, "session_cookies.json")


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
    from DrissionPage import ChromiumPage, ChromiumOptions
    co = ChromiumOptions()
    co.auto_port(True)
    co.no_js(False)
    co.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
    co.set_argument("--headless=new")
    co.set_argument("--disable-gpu")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-blink-features=AutomationControlled")
    co.set_argument("--disable-features=IsolateOrigins,site-per-process")
    co.set_argument("--disable-web-security")
    co.set_argument("--disable-site-isolation-trials")
    co.set_argument("--window-size=1366,768")
    co.set_argument("--start-maximized")
    co.set_argument("--disable-extensions")
    co.set_argument("--disable-plugins-discovery")
    co.set_argument("--disable-default-apps")
    co.set_argument("--enable-features=NetworkService,NetworkServiceInProcess")
    # Realistic locale/timezone
    co.set_argument("--lang=en-US,en;q=0.9")
    co.set_argument("--timezone=America/New_York")
    return ChromiumPage(co)


def inject_stealth(p):
    """Inject anti-detection scripts after page load."""
    p.run_js("""
        // Hide webdriver
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        // Hide automation
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
        // Mock chrome runtime
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
        // Mock permissions
        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
        // Mock plugins
        Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    """)


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
    # Load Magic SDK from Railway's bundle (embedded)
    result = run_async_store(p, """
        const m = await import('/assets/es-Cnk9wDkR.js');
        // Try m.n (which is cr - the Magic class directly)
        let MagicClass = m.n;
        if (!MagicClass || typeof MagicClass !== 'function') {
            // Fallback: try m.t.Magic (getter)
            MagicClass = m.t.Magic;
        }
        if (!MagicClass || typeof MagicClass !== 'function') {
            window.__r = 'ERR:No MagicClass found';
            return;
        }
        window.__magic = new MagicClass('pk_live_7797D999FCBC3993');
        window.__r = 'loaded';
    """)
    print(f"    Magic init: {result}")
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


DOMAINS_QUERY = """
query networking($projectId: String!, $environmentId: String!, $serviceId: String!) {
  domains(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId) {
    serviceDomains { domain }
  }
}
"""


def poll_urls(p, order, tries=60, delay=20):
    """Poll domain semua service pakai page p yang udah login. Return dict urls."""
    svc = {"url": order.get("service_id"),
           "router_url": order.get("router_service_id"),
           "terminal_url": order.get("terminal_service_id")}
    urls = {}
    for i in range(tries):
        for key, svid in svc.items():
            if key in urls or not svid:
                continue
            r = gql(p, DOMAINS_QUERY, {"projectId": order["project_id"],
                                       "environmentId": order["environment_id"], "serviceId": svid})
            m = re.search(r'"domain"\s*:\s*"([^"]+)"', r)
            if m and m.group(1):
                urls[key] = "https://" + m.group(1)
                print(f"    {key}: {urls[key]}")
        if all(k in urls for k in svc if svc[k]):
            break
        print(f"    [{i}] domain belum lengkap ({len(urls)}/{sum(1 for v in svc.values() if v)})...")
        time.sleep(delay)
    return urls


SVC_STATUS_QUERY = """
query service($id: String!) {
  service(id: $id) { deployments(first: 3) { edges { node { status } } } }
}
"""


def _dep_status(p, sid):
    """Status deployment TERBARU service, atau None kalau belum ada deployment."""
    r = gql(p, SVC_STATUS_QUERY, {"id": sid})
    statuses = re.findall(r'"status"\s*:\s*"(\w+)"', r)
    return statuses[0] if statuses else None


def wait_deploy(p, sid, tries=80, delay=15):
    """Poll deployment status service sampai SUCCESS/FAILED/CANCELLED.
    Railway cuma bisa 1 build sekaligus di satu environment, jadi deploy berikutnya
    WAJIB nunggu build sebelumnya selesai (gak boleh lanjut pas masih building).
    Ambil status deployment TERBARU (edge pertama)."""
    for i in range(tries):
        st = _dep_status(p, sid)
        if st == "SUCCESS":
            return True
        if st in ("FAILED", "CANCELLED"):
            return False
        print(f"    build {sid[:8]}: {st} ({i+1}/{tries})")
        time.sleep(delay)
    return False


def _create_service(p, pid, name, image):
    r = gql(p, "mutation serviceCreate($input: ServiceCreateInput!) { serviceCreate(input: $input) { id } }",
            {"input": {"projectId": pid, "name": name, "environmentId": None,
                       "source": {"image": image}}})
    m = re.search(r'"id"\s*:\s*"([a-f0-9-]{36})"', r)
    return m.group(1) if m else None


def create_order():
    admin_pw = gen_password(16)
    ssh_pw = gen_password(16)
    router_pw = gen_password(16)   # login dashboard 9Router
    term_pw = gen_password(16)     # basic auth terminal web

    email, mail_token = new_email()
    print(f"[1] Email: {email}")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(3)
    inject_stealth(p)

    ok = False
    for attempt in range(3):
        print(f"[2] Login attempt {attempt+1}/3...")
        p.get("https://railway.com/login")
        time.sleep(2)
        inject_stealth(p)
        did = login_and_exchange(p, email, mail_token)
        if not did:
            print("    DID gagal")
            continue
        # solve turnstile PAS setelah dapet DID (fresh token).
        # ponytail: solver kadang read-timeout (transient) — retry di tempat biar DID gak kebuang.
        from solver import MuaraicaptchaSolver
        solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
        ts_token = None
        for s_try in range(3):
            try:
                ts_token = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
                if ts_token:
                    break
            except Exception as e:
                print(f"    solver try {s_try+1}/3 error: {e}")
                time.sleep(3)
        if not ts_token:
            print("    turnstile token gagal — retry attempt")
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

    # services: hermes panel + 9router + terminal web (deploy dari docker image)
    sid = _create_service(p, pid, "hermes-gateway", IMAGE_NAME)
    print(f"[5] service hermes: {sid}")
    rid = _create_service(p, pid, "router", ROUTER_IMAGE)
    print(f"[5] service router: {rid}")
    tid = _create_service(p, pid, "terminal", TERMINAL_IMAGE)
    print(f"[5] service terminal: {tid}")
    if not (sid and rid and tid):
        print("SERVICE CREATE GAGAL")
        p.quit()
        return None

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
        print(f"    hermes/{k}: {'OK' if '\"errors\"' not in r else 'ERR'}")
    # 9Router: JWT_SECRET wajib + INITIAL_PASSWORD buat login dashboard
    for k, v in [("JWT_SECRET", gen_password(32)), ("INITIAL_PASSWORD", router_pw), ("REQUIRE_API_KEY", "false")]:
        r = gql(p, "mutation variableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }",
                {"input": {"projectId": pid, "environmentId": eid, "serviceId": rid, "name": k, "value": v}})
        print(f"    router/{k}: {'OK' if '\"errors\"' not in r else 'ERR'}")

    # create service instance + deploy.
    # Railway nge-lock env selama build — wajib sequential: patch → deploy → tunggu selesai.
    # ponytail: terminal tanpa startCommand (field invalid buat image source) → ttyd
    #   jalan di default port 7681 tanpa basic-auth; URL acak sebagai proteksi.
    print("[8] create instance + deploy (sequential, nunggu tiap build)...")
    PATCH_MUT = """
    mutation environmentPatchCommit($environmentId: String!, $patch: EnvironmentConfig!, $message: String) {
      environmentPatchCommit(environmentId: $environmentId, patch: $patch, commitMessage: $message)
    }
    """
    DEPLOY_MUT = """
    mutation serviceInstanceDeploy($serviceId: String!, $environmentId: String!, $latestCommit: Boolean) {
      serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId, latestCommit: $latestCommit)
    }
    """
    gql(p, "mutation variableUpsert($input: VariableUpsertInput!) { variableUpsert(input: $input) }",
        {"input": {"projectId": pid, "environmentId": eid, "serviceId": tid,
                   "name": "PORT", "value": "7681"}})
    term_pw = None  # tanpa password (auth-off fallback)
    seq = [("hermes", sid, IMAGE_NAME), ("router", rid, ROUTER_IMAGE), ("terminal", tid, TERMINAL_IMAGE)]
    for name, svid, img in seq:
        r = gql(p, PATCH_MUT, {"environmentId": eid,
                               "patch": {"services": {svid: {"isCreated": True, "source": {"image": img}}}},
                               "message": f"deploy {name}"})
        print(f"    patch {name}: {r[:200]}")
        if '"errors"' in r:
            raise RuntimeError(f"patch {name} gagal: {r[:300]}")
        time.sleep(2)
        # instance butuh waktu muncul setelah patch — retry deploy sampai gak "Not Authorized"
        # (env lagi di-lock build lain). Tapi: patch isCreated kadang AUTO-TRIGGER build — kalau
        # deployment service tsb udah jalan, gak usah kick lagi, tinggal tunggu build-nya selesai.
        ACTIVE = {"INITIALIZING", "BUILDING", "DEPLOYING", "PENDING", "QUEUED",
                  "PROVISIONING", "WAITING", "RETRYING", "SKIPPED"}
        r = ""
        kicked = False
        for d_try in range(50):
            r = gql(p, DEPLOY_MUT, {"serviceId": svid, "environmentId": eid, "latestCommit": True})
            if '"errors"' not in r:
                kicked = True
                break
            err = r.lower()
            retriable = ("not found" in err or "not authorized" in err or
                         "locked" in err or "forbidden" in err or
                         "another build" in err or "in progress" in err)
            if not retriable:
                raise RuntimeError(f"deploy {name} gagal: {r[:300]}")
            # env locked: cek apakah build sebenarnya udah jalan sendiri (auto-deploy dari patch)
            st = _dep_status(p, svid)
            print(f"    deploy {name}: locked; dep_status({name})={st}; raw_deploy_err={r[-200:]}")
            if st in ACTIVE:
                print(f"    deploy {name}: build {name} udah jalan otomatis ({st}) — tinggal tunggu")
                kicked = True
                break
            print(f"    deploy {name}: env locked / instance belum ready, retry {d_try+1}/50...")
            time.sleep(15)
        print(f"    deploy {name}: {r[:150]}")
        if not kicked:
            raise RuntimeError(f"deploy {name} gagal setelah retry: {r[:300]}")
        if not wait_deploy(p, svid):
            raise RuntimeError(f"deploy {name}: build gagal/tidak selesai — hentikan")

    # buat domain publik buat tiap service
    print("[9] buat domain...")
    for name, svid in [("hermes", sid), ("router", rid), ("terminal", tid)]:
        r = gql(p, """
        mutation serviceDomainCreate($input: ServiceDomainCreateInput!) {
          serviceDomainCreate(input: $input) { id }
        }
        """, {"input": {"environmentId": eid, "serviceId": svid}})
        print(f"    {name}: {r[:150]}")

    order = {
        "email": email,
        "mail_token": mail_token,
        "admin_username": "admin",
        "admin_password": admin_pw,
        "ssh_password": ssh_pw,
        "router_password": router_pw,
        "terminal_password": term_pw,
        "project_id": pid,
        "service_id": sid,
        "router_service_id": rid,
        "terminal_service_id": tid,
        "environment_id": eid,
        "url": None,
        "router_url": None,
        "terminal_url": None,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # poll URL semua service pakai session yang udah login (tanpa re-login)
    print("[10] polling domain URLs...")
    urls = poll_urls(p, order)
    order.update(urls)

    # append/update ke orders.json
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
    time.sleep(3)
    inject_stealth(p)

    # re-login
    ok = False
    for attempt in range(3):
        print(f"[1] re-login attempt {attempt+1}/3...")
        from solver import MuaraicaptchaSolver
        solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
        try:
            ts_token = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
        except Exception as e:
            print(f"    solver error: {e} — retry attempt")
            time.sleep(3)
            continue
        p.get("https://railway.com/login")
        time.sleep(2)
        inject_stealth(p)
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

    # poll domain URL semua service (hermes + router + terminal)
    urls = poll_urls(p, order, tries=15, delay=15)
    _update_order_url(project_id, urls)
    p.quit()
    return urls.get("url")


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


def _update_order_url(project_id, urls):
    """urls: dict {url, router_url, terminal_url} — hanya field yg ada di-update."""
    if not os.path.exists(ORDERS_FILE):
        return
    orders = json.load(open(ORDERS_FILE))
    for o in orders:
        if o.get("project_id") == project_id:
            for k, v in urls.items():
                o[k] = v
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
