# -*- coding: utf-8 -*-
"""FULL WORKING: Railway auto-login (Magic OTP + Turnstile) → session cookie.

Alur:
1. Bikin email GoMail (gomal.tech)
2. Solve Turnstile via Muaraicaptcha -> turnstileToken
3. Load Magic SDK -> loginWithEmailOTP -> kirim OTP + buka iframe
4. Baca OTP dari subject email
5. Isi OTP ke 6 input pin-code iframe -> DID token
6. Exchange: POST https://backboard.railway.com/login/magic
   body { turnstileToken, referralCode, ref, posthogSessionId, attribution, signupSurface }
   header Authorization: Bearer <DID>
7. Dapet session cookie
"""
import sys, time, re, requests, random, string

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


def main():
    # 1. Email
    email, mail_token = new_email()
    print(f"[1] Email: {email}")

    # 2. Turnstile token via Muaraicaptcha
    print("[2] Solve Turnstile (Muaraicaptcha)...")
    solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
    ts_token = solver.solve_turnstile(
        website_url="https://railway.com/login", website_key=SITEKEY
    )
    print(f"    Turnstile token OK ({len(ts_token)} chars)")

    # 3. Browser + Magic SDK
    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)

    r = run_async_store(
        p,
        """
        const m = await import('/assets/es-Cnk9wDkR.js');
        const { Magic } = m.t;
        window.__magic = new Magic('pk_live_7797D999FCBC3993');
        window.__r = 'loaded';
        """,
    )
    print(f"[3] Magic SDK: {r}")

    # 4. Kick off login (background)
    p.run_js("window.__didResult = null;")
    p.run_js(
        f"""
        window.__magic.auth.loginWithEmailOTP({{ email: '{email}', showUI: true }})
            .then(did => {{ window.__didResult = 'OK:' + String(did); }})
            .catch(e => {{ window.__didResult = 'ERR:' + e.message; }});
        """
    )

    # 5. Baca OTP
    print("[4] Baca OTP...")
    otp = get_otp(mail_token)
    if not otp:
        print("    GAGAL: OTP gak ketemu")
        p.quit()
        return
    print(f"    OTP: {otp}")

    # 6. Isi OTP ke iframe
    print("[5] Isi OTP ke iframe Magic...")
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
        print("    GAGAL: iframe Magic gak muncul")
        p.quit()
        return

    for idx, digit in enumerate(otp):
        inp = ifr.ele(f"#pin-code-input-{idx}", timeout=3)
        if inp:
            inp.input(digit)
            time.sleep(0.15)

    # 7. Tunggu DID token
    print("[6] Nunggu DID token...")
    did = None
    for _ in range(30):
        res = p.run_js("return window.__didResult")
        if res and res.startswith("OK:"):
            did = res[3:]
            break
        if res and res.startswith("ERR:"):
            print(f"    Error: {res}")
            break
        time.sleep(1)
    if not did:
        print("    GAGAL: DID token gak dapet")
        p.get_screenshot(path="otp_failed.png")
        p.quit()
        return
    print(f"    DID token: {did[:60]}...")

    # 8. Exchange
    print("[7] Exchange DID + Turnstile ke /login/magic...")
    body = {
        "referralCode": None,
        "ref": None,
        "posthogSessionId": None,
        "turnstileToken": ts_token,
        "attribution": {"referringDomain": "$direct", "landingPath": "/login"},
        "signupSurface": "web",
    }
    # simpan body + did ke window biar fetch dari browser (same-origin cookies/headers)
    p.run_js(f"window.__did = {json.dumps(did)};")
    p.run_js(f"window.__body = {json.dumps(body)};")
    r = run_async_store(
        p,
        """
        const res = await fetch('https://backboard.railway.com/login/magic', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + window.__did
            },
            body: JSON.stringify(window.__body)
        });
        const txt = await res.text();
        window.__r = 'status=' + res.status + ' body=' + txt.substring(0, 400);
        """,
    )
    print(f"    {r}")

    # 9. Cek session
    time.sleep(3)
    cookies = p.run_js("return document.cookie")
    print(f"[8] Cookies: {cookies[:400]}")

    # coba akses dashboard
    p.get("https://railway.com/dashboard")
    time.sleep(5)
    print(f"    Dashboard URL: {p.url}")
    dash_text = p.run_js("return document.body.innerText.substring(0, 200)")
    print(f"    Dashboard text: {dash_text}")

    p.get_screenshot(path="final_state.png")
    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    import json
    main()
