# -*- coding: utf-8 -*-
"""FULL WORKING FLOW: Railway auto-login via Magic SDK + OTP.

Alur:
1. Bikin email GoMail (gomal.tech)
2. Load Magic SDK di halaman Railway
3. loginWithEmailOTP (background) -> kirim OTP + buka iframe
4. Baca OTP 6 digit dari subject email GoMail
5. Isi OTP ke 6 input pin-code di iframe Magic
6. Dapet DID token
7. Exchange DID token ke POST /login/magic -> session cookie
"""
import sys, time, re, requests, random, string

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"
MAGIC_KEY = "pk_live_7797D999FCBC3993"
DOMAIN = "gomal.tech"


def new_email():
    username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    r = requests.post(f"{GOMAIL}/api/v1/auth/signup", json={"username": username, "password": "Test123!", "domain": DOMAIN})
    j = r.json()
    return j["profile"]["email_alias"], j["token"]


def get_otp(mail_token, tries=40):
    """Baca OTP 6 digit dari subject/body email."""
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
    """Run async JS, hasil disimpan di window[key]."""
    p.run_js(f"window['{key}'] = null;")
    p.run_js(f"(async () => {{\n{code}\n}})().catch(e => {{ window['{key}'] = 'ERR:' + e.message; }});")
    for _ in range(60):
        r = p.run_js(f"return window['{key}']")
        if r and r != "null":
            return r
        time.sleep(0.5)
    return p.run_js(f"return window['{key}']")


def main():
    email, mail_token = new_email()
    print(f"[1] Email: {email}")

    p = make_browser()
    p.get("https://railway.com/login")
    time.sleep(4)
    print("[2] Halaman login terbuka")

    # Load Magic SDK
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

    # Kick off login (background, simpan hasil di __didResult)
    p.run_js("window.__didResult = null;")
    p.run_js(
        f"""
        window.__magic.auth.loginWithEmailOTP({{ email: '{email}', showUI: true }})
            .then(did => {{ window.__didResult = 'OK:' + String(did); }})
            .catch(e => {{ window.__didResult = 'ERR:' + e.message; }});
        """
    )

    # Baca OTP
    print("[4] Baca OTP...")
    otp = get_otp(mail_token)
    if not otp:
        print("  GAGAL: OTP gak ketemu")
        p.quit()
        return
    print(f"  OTP: {otp}")

    # Tunggu iframe muncul
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
        print("  GAGAL: iframe Magic gak muncul")
        p.quit()
        return
    print(f"  Iframe OK: {ifr.attr('class')}")

    # Isi 6 digit OTP ke 6 input pin-code
    for idx, digit in enumerate(otp):
        inp = ifr.ele(f"#pin-code-input-{idx}", timeout=3)
        if inp:
            inp.input(digit)
            time.sleep(0.15)

    print("  OTP terisi, nunggu DID token...")

    # Tunggu DID token
    did = None
    for _ in range(30):
        res = p.run_js("return window.__didResult")
        if res and res.startswith("OK:"):
            did = res[3:]
            break
        if res and res.startswith("ERR:"):
            print(f"  Error: {res}")
            break
        time.sleep(1)
    
    if not did:
        print("  GAGAL: DID token gak dapet")
        p.get_screenshot(path="otp_failed.png")
        p.quit()
        return
    print(f"[6] DID token dapet: {did[:60]}...")

    # Exchange DID token ke /login/magic
    print("[7] Exchange ke /login/magic...")
    r = run_async_store(
        p,
        """
        const res = await fetch('/login/magic', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': 'Bearer ' + window.__didResult.substring(3)
            }
        });
        const txt = await res.text();
        window.__r = 'status=' + res.status + ' body=' + txt.substring(0, 200);
        """,
    )
    print(f"  {r}")

    # Cek session
    time.sleep(3)
    cookies = p.run_js("return document.cookie")
    print(f"[8] Cookies: {cookies[:400]}")
    print(f"  URL: {p.url}")

    # Cek apakah udah login (ada railway session)
    has_session = p.run_js(
        "return document.cookie.includes('railway_session') || document.cookie.includes('connect.sid')"
    )
    print(f"  Ada session? {has_session}")

    p.get_screenshot(path="login_success.png")
    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
