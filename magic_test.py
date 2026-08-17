# -*- coding: utf-8 -*-
"""Full flow: Magic SDK OTP login - bypass Turnstile."""
import sys, time, re, requests, random, string

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"


def new_email():
    username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    r = requests.post(f"{GOMAIL}/api/v1/auth/signup", json={"username": username, "password": "Test123!", "domain": "gomal.tech"})
    j = r.json()
    return j["profile"]["email_alias"], j["token"]


def get_otp(mail_token, tries=25):
    for i in range(tries):
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            body = str(e.get("text", "") or e.get("html", ""))
            subject = str(e.get("subject", ""))
            m = re.search(r"\b(\d{6})\b", subject + " " + body)
            if m:
                return m.group(1)
        time.sleep(3)
    return None


def js_async(p, code):
    """Run async JS, poll global __r."""
    p.run_js("window.__r = null;")
    p.run_js(f"(async () => {{\n{code}\n}})().catch(e => {{ window.__r = 'ERR:' + e.message; }});")
    for _ in range(30):
        r = p.run_js("return window.__r")
        if r and r != "null":
            return r
        time.sleep(0.5)
    return p.run_js("return window.__r")


def main():
    email, mail_token = new_email()
    print(f"[1] Email: {email}")

    co = ChromiumOptions()
    co.auto_port(True)
    co.no_js(False)
    co.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    co.set_argument("--headless=new")
    co.set_argument("--disable-gpu")
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-blink-features=AutomationControlled")
    p = ChromiumPage(co)
    p.get("https://railway.com/login")
    time.sleep(4)
    print("[2] Halaman login terbuka")

    # Load Magic SDK
    print("[3] Load Magic SDK...")
    r = js_async(p, """
        const m = await import('/assets/es-Cnk9wDkR.js');
        const { Magic } = m.t;
        window.__magic = new Magic('pk_live_7797D999FCBC3993');
        window.__r = 'Magic loaded';
    """)
    print(f"  {r}")

    # Kirim OTP
    print("[4] Kirim OTP...")
    r = js_async(p, f"""
        const res = await window.__magic.auth.loginWithEmailOTP({{ email: '{email}', showUI: false }});
        window.__r = 'OTP sent: ' + JSON.stringify(res).substring(0, 200);
    """)
    print(f"  {r}")

    # Baca OTP
    print("[5] Baca OTP...")
    otp = get_otp(mail_token)
    if not otp:
        print("  GAGAL: OTP gak ketemu")
        p.quit()
        return
    print(f"  OTP: {otp}")

    # Verify OTP
    print("[6] Verify OTP...")
    r = js_async(p, f"""
        const didToken = await window.__magic.auth.loginWithEmailOTP({{ email: '{email}', otp: '{otp}' }});
        window.__didToken = didToken;
        window.__r = 'DID: ' + String(didToken).substring(0, 60);
    """)
    print(f"  {r}")

    # Exchange DID token
    print("[7] Exchange ke /login/magic...")
    r = js_async(p, """
        const didToken = window.__didToken;
        const res = await fetch('/login/magic', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + didToken
            }
        });
        const txt = await res.text();
        window.__r = 'exchange status=' + res.status + ' body=' + txt.substring(0, 300);
    """)
    print(f"  {r}")

    # Cek session
    time.sleep(2)
    cookies = p.run_js("return document.cookie")
    print(f"[8] Cookies: {cookies[:300]}")
    print(f"  URL: {p.url}")

    p.get_screenshot(path="magic_result.png")
    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
