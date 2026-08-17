# -*- coding: utf-8 -*-
"""Debug v2: bypass disabled button, force submit form."""
import sys, time, requests, random, string

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
p.get("https://railway.com/login")
time.sleep(5)

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

# Cari form & coba requestSubmit / dispatch submit event
result = p.run_js("""
const form = document.querySelector('form');
if (!form) return 'NO FORM';

// cara 1: requestSubmit (validasi + submit)
try {
    form.requestSubmit();
    return 'requestSubmit called';
} catch(e) {
    // cara 2: dispatch submit event manual
    try {
        form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
        return 'submit event dispatched';
    } catch(e2) {
        return 'both failed: ' + e.message + ' / ' + e2.message;
    }
}
""")
print(f"Submit result: {result}")
time.sleep(5)

# Cek apa yang terjadi
txt = p.run_js("return document.body.innerText.substring(0, 600)")
print(f"Setelah submit: {txt}")

# cek inbox
for i in range(15):
    r2 = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
    emails = r2.json().get("data", [])
    if emails:
        print(f"EMAIL DAPET! (cek ke-{i+1})")
        for e in emails:
            print(f"  From: {e.get('from')}")
            print(f"  Subject: {e.get('subject')}")
            body = str(e.get("text", "") or e.get("html", ""))
            print(f"  Body: {body[:300]}")
        break
    print(f"  Kosong... ({i+1}/15)")
    time.sleep(3)

p.quit()
print("=== DEBUG V2 DONE ===")
