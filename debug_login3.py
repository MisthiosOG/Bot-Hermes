# -*- coding: utf-8 -*-
"""Debug v3: remove disabled + klik, dan intercept network."""
import sys, time, requests, random, string, json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, r"C:\Users\LEGION\Documents\grok-maker")
from xconsole_client.muarai_solver import MuaraicaptchaSolver
from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"
SITEKEY = "0x4AAAAAAC1ksDZJd9ksGuf7"
MUARAI_KEY = "mc_live_9ba88d8f01224f7bd1b2f957731cc30f"

username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
r = requests.post(f"{GOMAIL}/api/v1/auth/signup", json={"username": username, "password": "Test123!", "domain": "gomal.tech"})
email = r.json()["profile"]["email_alias"]
mail_token = r.json()["token"]
print(f"Email: {email}")

solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
ts = solver.solve_turnstile(website_url="https://railway.com/login", website_key=SITEKEY)
print(f"Token OK ({len(ts)} chars)")

co = ChromiumOptions()
co.auto_port(True)
co.no_js(False)
co.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
co.set_argument("--headless=new")
co.set_argument("--disable-gpu")
co.set_argument("--no-sandbox")
co.set_argument("--disable-blink-features=AutomationControlled")
p = ChromiumPage(co)

# pasang listener XHR/fetch
p.listen.start("https://backboard.railway.com")

p.get("https://railway.com/login")
time.sleep(5)

# klik email login
p.run_js("Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Log in using email'))?.click()")
time.sleep(4)

# isi email
p.run_js(f"""const inp = document.querySelector('input[placeholder="hello@email.com"]');
if (inp) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    ns.call(inp, '{email}');
    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
}}""")
time.sleep(1)

# inject token
p.run_js(f"""const inp = document.querySelector('input[name="cf-turnstile-response"]');
if (inp) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    ns.call(inp, '{ts}');
    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
}}""")
time.sleep(1)

# HAPUS disabled + klik button
res = p.run_js("""
const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Continue with Email'));
if (!btn) return 'NO BUTTON';
btn.removeAttribute('disabled');
btn.disabled = false;
btn.click();
return 'clicked, disabled=' + btn.disabled;
""")
print(f"Klik result: {res}")
time.sleep(5)

# cek network requests
try:
    reqs = p.listen.steps()
    print(f"Network requests: {len(reqs)}")
    for rq in reqs[-5:]:
        print(f"  {rq.method} {rq.url[:120]}")
except Exception as e:
    print(f"listen error: {e}")

# cek page state
txt = p.run_js("return document.body.innerText.substring(0, 500)")
print(f"Page: {txt}")

# cek inbox
for i in range(12):
    r2 = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
    emails = r2.json().get("data", [])
    if emails:
        print(f"EMAIL DAPET! (cek ke-{i+1})")
        for e in emails:
            print(f"  Subject: {e.get('subject')}")
            body = str(e.get("text", "") or e.get("html", ""))
            print(f"  Body: {body[:400]}")
        break
    print(f"  Kosong... ({i+1}/12)")
    time.sleep(3)

p.quit()
print("=== DEBUG V3 DONE ===")
