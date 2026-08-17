# -*- coding: utf-8 -*-
"""Diagnostic domain: cek staticUrl + suggestAddServiceDomain + coba generate."""
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

ORDER = None  # diisi dari orders.json


def load_order(project_id):
    orders = json.load(open(r"C:\Users\LEGION\Documents\OBSIDIAN\Projects\railway-auto\orders.json"))
    return next((o for o in orders if o.get("project_id") == project_id), None)


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
    # baca OTP terbaru
    newest = ""
    try:
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            ra = str(e.get("received_at", ""))
            if ra > newest:
                newest = ra
    except Exception:
        pass
    otp = None
    for i in range(40):
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            if str(e.get("received_at", "")) > newest:
                m = re.search(r"\b(\d{6})\b", str(e.get("subject", "")) + " " + str(e.get("text", "") or e.get("html", "")))
                if m:
                    otp = m.group(1)
                    break
        if otp:
            break
        time.sleep(2)
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
    order = load_order("52763a82-d127-416d-bc7d-d31876d68659")
    print(f"order: {order['email']}")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)

    for attempt in range(3):
        solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
        ts = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
        p.get("https://railway.com/login")
        time.sleep(3)
        did = login(p, order["email"], order["mail_token"], ts)
        if not did:
            continue
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
        if "200" in str(st):
            break

    # cek deployment + staticUrl + suggestAddServiceDomain
    print("[1] cek deployment detail...")
    r = gql(p, """
    query service($id: String!) {
      service(id: $id) {
        id
        deployments(first: 1) {
          edges { node { id status staticUrl suggestAddServiceDomain } }
        }
        serviceInstances {
          edges { node { id activeDeployments { status staticUrl } } }
        }
      }
    }
    """, {"id": order["service_id"]})
    print(f"    {r[:1200]}")

    # coba serviceDomainCreate berbagai shape
    print("[2] serviceDomainCreate shapes...")
    sid = order["service_id"]
    eid = order["environment_id"]
    pid = order["project_id"]
    shapes = [
        {"projectId": pid, "environmentId": eid, "serviceId": sid},
        {"environmentId": eid, "serviceId": sid},
        {"serviceId": sid},
    ]
    for i, shape in enumerate(shapes):
        r = gql(p, "mutation serviceDomainCreate($input: ServiceDomainCreateInput!) { serviceDomainCreate(input: $input) { id } }", {"input": shape})
        ok = '"errors"' not in r
        print(f"    [{i}] {list(shape.keys())}: {'OK' if ok else 'ERR'} {r[:250]}")

    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
