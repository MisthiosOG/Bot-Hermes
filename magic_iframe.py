# -*- coding: utf-8 -*-
"""Full flow v2: Magic SDK + isi OTP di iframe."""
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


def get_otp(mail_token, tries=30):
    for i in range(tries):
        r = requests.get(f"{GOMAIL}/api/v1/emails", headers={"Authorization": f"Bearer {mail_token}"})
        for e in r.json().get("data", []):
            subject = str(e.get("subject", ""))
            body = str(e.get("text", "") or e.get("html", ""))
            # cari 6 digit di subject atau body
            m = re.search(r"\b(\d{6})\b", subject + " " + body)
            if m:
                return m.group(1)
        time.sleep(2)
    return None


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

# load SDK
p.run_js("window.__r = null;")
p.run_js("""(async () => {
    const m = await import('/assets/es-Cnk9wDkR.js');
    const { Magic } = m.t;
    window.__magic = new Magic('pk_live_7797D999FCBC3993');
    window.__r = 'loaded';
})().catch(e => { window.__r = 'ERR:' + e.message; });""")
for _ in range(20):
    if p.run_js("return window.__r"):
        break
    time.sleep(0.5)
print("SDK:", p.run_js("return window.__r"))

# kick off login (background)
p.run_js("window.__didResult = null;")
p.run_js(f"""
window.__magic.auth.loginWithEmailOTP({{ email: '{email}', showUI: true }})
    .then(did => {{ window.__didResult = 'DID:' + String(did).substring(0, 60); }})
    .catch(e => {{ window.__didResult = 'ERR:' + e.message; }});
""")

# baca OTP
print("Baca OTP...")
otp = get_otp(mail_token)
print(f"OTP: {otp}")
if not otp:
    p.quit()
    sys.exit()

# akses iframe magic
time.sleep(2)
# cari iframe magic
iframe_info = p.run_js("""
const ifr = document.querySelector('iframe#magic-iframe') || document.querySelector('iframe[src*="auth.magic.link"]');
if (!ifr) return 'NO IFRAME';
return JSON.stringify({ id: ifr.id, src: ifr.src.substring(0, 120), w: ifr.offsetWidth, h: ifr.offsetHeight });
""")
print(f"Iframe: {iframe_info}")

# DrissionPage akses iframe element
try:
    ifr_el = p.ele("#magic-iframe", timeout=3)
    if not ifr_el:
        ifr_el = p.ele("tag:iframe@src:auth.magic.link", timeout=3)
    print(f"Iframe element: {ifr_el}")
except Exception as e:
    print(f"Error cari iframe: {e}")
    ifr_el = None

# coba akses isi iframe
if ifr_el:
    try:
        inner = ifr_el.ele("tag:body")
        print(f"Iframe body: {inner}")
        # cari input
        inputs = ifr_el.eles("tag:input")
        print(f"Inputs di iframe: {len(inputs)}")
        for inp in inputs:
            print(f"  input: type={inp.attr('type')} id={inp.attr('id')} name={inp.attr('name')} maxlength={inp.attr('maxlength')}")
    except Exception as e:
        print(f"Error akses iframe: {e}")

p.get_screenshot(path="magic_iframe.png")
p.quit()
print("DONE")
