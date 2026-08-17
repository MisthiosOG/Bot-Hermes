# -*- coding: utf-8 -*-
"""
Railway auto-login via GoMail (gomal.tech) + Muaraicaptcha + kode verifikasi.
Flow: email -> turnstile -> submit email -> baca kode OTP -> masukin kode -> login.
"""
import sys, os, time, re, requests, random, string

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, r"C:\Users\LEGION\Documents\grok-maker")
from xconsole_client.muarai_solver import MuaraicaptchaSolver
from DrissionPage import ChromiumPage, ChromiumOptions

GOMAIL = "https://mail.gopretstudio.com"
SITEKEY = "0x4AAAAAAC1ksDZJd9ksGuf7"
MUARAI_KEY = "mc_live_9ba88d8f01224f7bd1b2f957731cc30f"


def new_email():
    username = "u" + "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
    r = requests.post(
        f"{GOMAIL}/api/v1/auth/signup",
        json={"username": username, "password": "Test123!", "domain": "gomal.tech"},
    )
    j = r.json()
    return j["profile"]["email_alias"], j["token"]


def get_code(mail_token, tries=30):
    """Baca kode verifikasi dari inbox GoMail."""
    for i in range(tries):
        r = requests.get(
            f"{GOMAIL}/api/v1/emails",
            headers={"Authorization": f"Bearer {mail_token}"},
        )
        for e in r.json().get("data", []):
            body = str(e.get("text", "") or e.get("html", ""))
            subject = str(e.get("subject", ""))
            # kode biasanya 6 digit di subject/body
            m = re.search(r"\b(\d{6})\b", subject + " " + body)
            if m:
                return m.group(1)
        time.sleep(3)
    return None


def main():
    # 1. email
    email, mail_token = new_email()
    print(f"[1] Email: {email}")

    # 2. turnstile
    print("[2] Solve Turnstile...")
    solver = MuaraicaptchaSolver(api_key=MUARAI_KEY)
    ts = solver.solve_turnstile(
        website_url="https://railway.com/login", website_key=SITEKEY
    )
    print(f"    Token OK ({len(ts)} chars)")

    # 3. browser headless
    print("[3] Buka Railway (headless)...")
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
    p = ChromiumPage(co)
    p.get("https://railway.com/login")
    time.sleep(5)

    # klik "Log in using email"
    p.run_js(
        "Array.from(document.querySelectorAll('button'))"
        ".find(b => b.textContent.includes('Log in using email'))?.click()"
    )
    time.sleep(4)

    # isi email
    p.run_js(
        f"""const inp = document.querySelector('input[placeholder="hello@email.com"]');
if (inp) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    ns.call(inp, '{email}');
    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
}}"""
    )
    time.sleep(1)

    # inject token turnstile
    p.run_js(
        f"""const inp = document.querySelector('input[name="cf-turnstile-response"]');
if (inp) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    ns.call(inp, '{ts}');
    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
}}"""
    )
    time.sleep(0.5)

    # submit email
    p.run_js(
        "Array.from(document.querySelectorAll('button'))"
        ".find(b => b.textContent.includes('Continue with Email'))?.click()"
    )
    print("    Email dikirim, nunggu kode OTP...")
    time.sleep(3)

    # cek form apa yang muncul
    txt = p.run_js("return document.body.innerText")
    if "code" in txt.lower() or "verif" in txt.lower():
        print("    Form input kode muncul!")

    # 4. baca kode dari inbox
    print("[4] Baca kode verifikasi...")
    code = get_code(mail_token)
    if not code:
        print("    GAGAL: kode gak ketemu")
        p.quit()
        return
    print(f"    Kode: {code}")

    # 5. isi kode ke form
    print("[5] Isi kode verifikasi...")
    # cari input untuk kode (biasanya input[inputmode=numeric] atau type=tel/text)
    p.run_js(
        f"""const inputs = Array.from(document.querySelectorAll('input'));
const inp = inputs.find(i => i.type === 'tel' || i.type === 'text' || i.inputMode === 'numeric') || inputs[0];
if (inp) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
    ns.call(inp, '{code}');
    inp.dispatchEvent(new Event('input', {{bubbles:true}}));
    inp.dispatchEvent(new Event('change', {{bubbles:true}}));
}}"""
    )
    time.sleep(1)

    # submit kode (klik submit/verify button)
    p.run_js(
        "Array.from(document.querySelectorAll('button'))"
        ".find(b => /verify|continue|submit|sign in|log in/i.test(b.textContent))?.click()"
    )
    time.sleep(6)

    print(f"[6] URL akhir: {p.url}")
    final_txt = p.run_js("return document.body.innerText.substring(0, 300)")
    print(f"    Body: {final_txt}")

    # simpan cookies
    cookies = p.run_js("return document.cookie")
    print(f"    Cookies length: {len(cookies)}")

    p.get_screenshot(path="login_result.png")
    p.quit()
    print("=== DONE ===")


if __name__ == "__main__":
    main()
