# -*- coding: utf-8 -*-
"""Diagnostic: lihat apa yang muncul pas loginWithEmailOTP showUI=true."""
import sys, time, requests, random, string

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"


def new_email():
    username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    r = requests.post(f"{GOMAIL}/api/v1/auth/signup", json={"username": username, "password": "Test123!", "domain": "gomal.tech"})
    j = r.json()
    return j["profile"]["email_alias"], j["token"]


email, mail_token = new_email()
print(f"Email: {email}")

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

# load Magic SDK
p.run_js("window.__r = null;")
p.run_js("""
(async () => {
    const m = await import('/assets/es-Cnk9wDkR.js');
    const { Magic } = m.t;
    window.__magic = new Magic('pk_live_7797D999FCBC3993');
    window.__r = 'loaded';
})().catch(e => { window.__r = 'ERR:' + e.message; });
""")
for _ in range(20):
    if p.run_js("return window.__r"):
        break
    time.sleep(0.5)
print("SDK:", p.run_js("return window.__r"))

# kick off loginWithEmailOTP showUI=true (background, don't await)
p.run_js("window.__didResult = null;")
p.run_js(f"""
window.__magic.auth.loginWithEmailOTP({{ email: '{email}', showUI: true }})
    .then(did => {{ window.__didResult = 'DID:' + String(did).substring(0, 60); }})
    .catch(e => {{ window.__didResult = 'ERR:' + e.message; }});
""")

# poll DOM buat iframe/modal
for i in range(12):
    time.sleep(2)
    info = p.run_js("""
const iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src.substring(0, 100));
const magicEls = Array.from(document.querySelectorAll('[class*="magic"], [id*="magic"]')).map(e => e.id || e.className).filter(x => x).slice(0, 5);
return JSON.stringify({ iframes, magicEls, did: window.__didResult });
""")
    print(f"[{i}] {info}")
    if p.run_js("return window.__didResult"):
        break

p.get_screenshot(path="magic_modal.png")

# cek OTP di inbox
print("Cek inbox...")
for i in range(15):
    r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
    for e in r.json().get("data", []):
        body = str(e.get("text", "") or e.get("html", ""))
        subject = str(e.get("subject", ""))
        print(f"  Email: subject='{subject}' body='{body[:200]}'")
    if r.json().get("data"):
        break
    time.sleep(3)

p.quit()
print("DONE")
