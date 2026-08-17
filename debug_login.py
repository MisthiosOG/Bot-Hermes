# -*- coding: utf-8 -*-
"""Debug: cek kenapa form Railway gak submit."""
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

# Cek state setelah isi email
state1 = p.run_js("""return JSON.stringify({
    emailValue: document.querySelector('input[placeholder="hello@email.com"]')?.value,
    turnstileInput: document.querySelector('input[name="cf-turnstile-response"]') ? 'exists' : 'missing',
    continueDisabled: (() => { const b = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Continue with Email')); return b ? b.disabled : 'notfound'; })()
});""")
print(f"State setelah isi email: {state1}")

# inject token
p.run_js(f"""const inp = document.querySelector('input[name="cf-turnstile-response"]');
if (inp) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    ns.call(inp, '{ts}');
    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
}}""")
time.sleep(1)

# Cek state setelah inject token
state2 = p.run_js("""return JSON.stringify({
    turnstileValue: document.querySelector('input[name="cf-turnstile-response"]')?.value?.substring(0, 30),
    continueDisabled: (() => { const b = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Continue with Email')); return b ? b.disabled : 'notfound'; })()
});""")
print(f"State setelah inject token: {state2}")

# screenshot
p.get_screenshot(path="debug_state.png")

# coba klik submit
p.run_js("Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Continue with Email'))?.click()")
time.sleep(3)

# cek apa yang terjadi
final = p.run_js("return document.body.innerText.substring(0, 800)")
print(f"Setelah klik: {final}")

p.quit()
print("=== DEBUG DONE ===")
