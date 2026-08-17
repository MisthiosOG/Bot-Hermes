# -*- coding: utf-8 -*-
"""Test: login → dashboard → deploy template page → interaksi UI."""
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
    co.set_user_agent(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
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
    for idx, digit in enumerate(otp):
        inp = ifr.ele(f"#pin-code-input-{idx}", timeout=3)
        if inp:
            inp.input(digit)
            time.sleep(0.15)
    did = None
    for _ in range(30):
        res = p.run_js("return window.__didResult")
        if res and res.startswith("OK:"):
            did = res[3:]
            break
        time.sleep(1)
    if not did:
        return None
    p.run_js(f"window.__did = {json.dumps(did)};")
    p.run_js(f"window.__body = {json.dumps({'referralCode': None, 'ref': None, 'posthogSessionId': None, 'turnstileToken': ts_token, 'attribution': {'referringDomain': '$direct', 'landingPath': '/login'}, 'signupSurface': 'web'})};")
    return run_async_store(p, """
        const res = await fetch('https://backboard.railway.com/login/magic', {
            method: 'POST',
            credentials: 'include',
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + window.__did},
            body: JSON.stringify(window.__body)
        });
        await res.text();
        window.__r = res.status;
    """)


def main():
    email, mail_token = new_email()
    print(f"[1] Email: {email}")
    print("[2] Solve Turnstile...")
    solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
    ts_token = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
    print(f"    Token OK ({len(ts_token)} chars)")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)
    print("[3] Login...")
    status = login(p, email, mail_token, ts_token)
    print(f"    Login status: {status}")

    # cek dashboard
    p.get("https://railway.com/dashboard")
    time.sleep(6)
    print(f"[4] Dashboard URL: {p.url}")
    txt = p.run_js("return document.body.innerText.substring(0, 150)")
    print(f"    Dashboard body: {txt}")

    # deploy page
    print("[5] Buka deploy page...")
    p.get("https://railway.app/new/template?template=https://github.com/MisthiosOG/Hermes-Gateway")
    time.sleep(10)
    print(f"    URL: {p.url}")
    txt2 = p.run_js("return document.body.innerText.substring(0, 800)")
    print(f"    Body: {txt2}")
    p.get_screenshot(path="deploy_ui.png")

    # cek elemen
    inputs = p.run_js("""
return Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
    ph: (el.placeholder || '').substring(0, 40),
    id: (el.id || '').substring(0, 40),
    type: el.type || ''
})).slice(0, 20);
""")
    print(f"    Inputs: {inputs}")

    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
