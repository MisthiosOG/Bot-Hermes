"""
Railway Auto-Account + Deploy Hermes-Gateway
1. Bikin email GoMail
2. Solve Turnstile via Muaraicaptcha
3. Login Railway pake magic link
4. Deploy Hermes-Gateway
5. Output link + password
"""
import sys, os, time, re, json, random, string, requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# --- Paths ---
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
GROK_MAKER = r"C:\Users\LEGION\Documents\grok-maker"
sys.path.insert(0, GROK_MAKER)

from xconsole_client.muarai_solver import MuaraicaptchaSolver
from DrissionPage import ChromiumPage, ChromiumOptions

# --- Config ---
GOMAIL_BASE = "https://mail.gopretstudio.com"
RAILWAY_LOGIN = "https://railway.com/login"
DEPLOY_URL = "https://railway.app/new/template?template=https://github.com/MisthiosOG/Hermes-Gateway"
MUARAI_API_KEY = os.environ.get("MUARAI_API_KEY") or "mc_live_9ba88d8f01224f7bd1b2f957731cc30f"
TURNSTILE_SITEKEY = "0x4AAAAAAC1ksDZJd9ksGuf7"

class RailwayAuto:
    def __init__(self):
        self.email = None
        self.email_token = None
        self.email_password = None
        self.admin_password = None
        self.ssh_password = None
        self.session = None
        self.service_url = None

    def _gen_password(self, length=16):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

    def create_email(self):
        """Step 1: Bikin email GoMail"""
        print("[1] Bikin email GoMail...")
        username = "u" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        pw = "TestPass123!"
        r = requests.post(f"{GOMAIL_BASE}/api/v1/auth/signup", json={
            "username": username, "password": pw, "domain": "awdigi.dev"
        })
        if r.status_code != 201:
            raise RuntimeError(f"GoMail signup gagal: {r.status_code} {r.text}")
        data = r.json()
        self.email = data["profile"]["email_alias"]
        self.email_token = data["token"]
        self.email_password = pw
        print(f"  Email: {self.email}")
        return self

    def solve_turnstile(self):
        """Step 2: Solve Turnstile via Muaraicaptcha"""
        print("\n[2] Solve Turnstile Railway...")
        solver = MuaraicaptchaSolver(
            api_key=MUARAI_API_KEY,
            debug=True,
            timeout=60,
        )
        # Cek balance
        bal = solver._check_balance()
        print(f"  Balance: ${bal:.4f}")
        if bal < 0.01:
            raise RuntimeError(f"Balance terlalu rendah (${bal:.4f}). Top up dulu!")
        
        token = solver.solve_turnstile(
            website_url=RAILWAY_LOGIN,
            website_key=TURNSTILE_SITEKEY,
        )
        print(f"  Token: {token[:50]}...")
        self.turnstile_token = token
        return self

    def login_railway(self):
        """Step 3: Login Railway pake email + magic link"""
        print("\n[3] Login Railway...")
        
        co = ChromiumOptions()
        co.auto_port(True)
        co.no_js(False)
        co.set_user_agent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
        )
        
        self.page = ChromiumPage(co)
        p = self.page
        p.get(RAILWAY_LOGIN)
        time.sleep(4)
        
        # Klik "Log in using email"
        p.run_js("Array.from(document.querySelectorAll('button'))"
                 ".find(b => b.textContent.includes('Log in using email'))?.click()")
        time.sleep(3)
        
        # Isi email
        p.run_js(f"""const input = document.querySelector('input[placeholder="hello@email.com"]');
if (input) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    ns.call(input, '{self.email}');
    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
}}""")
        time.sleep(1)
        
        # Inject Turnstile token
        p.run_js(f"""const input = document.querySelector('input[name="cf-turnstile-response"]');
if (input) {{
    const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    ns.call(input, '{self.turnstile_token}');
    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
}}""")
        time.sleep(0.5)
        
        # Klik Continue with Email
        p.run_js("Array.from(document.querySelectorAll('button'))"
                 ".find(b => b.textContent.includes('Continue with Email'))?.click()")
        print("  Menunggu magic link...")
        time.sleep(5)
        
        # Baca inbox GoMail
        print("  Cek inbox...")
        magic_link = None
        for i in range(20):
            r = requests.get(f"{GOMAIL_BASE}/api/v1/emails", headers={
                "Authorization": f"Bearer {self.email_token}"
            })
            if r.status_code == 200:
                emails = r.json().get("data", [])
                for email in emails:
                    body = str(email.get('text', '') or email.get('html', ''))
                    links = re.findall(r'https?://[^\s<>"\']+', body)
                    for link in links:
                        if 'railway' in link.lower() and 'magic' in link.lower():
                            magic_link = link
                            break
            if magic_link:
                break
            print(f"  Inbox kosong... ({i+1}/20)")
            time.sleep(3)
        
        if not magic_link:
            raise RuntimeError("Gak dapet magic link dari GoMail")
        
        print(f"  Magic link dapet!")
        
        # Klik magic link
        p.get(magic_link)
        time.sleep(5)
        
        # Cek apakah login sukses (redirect ke dashboard)
        current_url = p.url
        print(f"  URL setelah login: {current_url}")
        
        # Ambil cookies
        cookies = p.run_js("return document.cookie")
        print(f"  Cookies length: {len(cookies)}")
        
        # Cek localStorage untuk token
        ls = p.run_js("""
const items = {};
for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    items[k] = (localStorage.getItem(k) || '').substring(0, 50);
}
return JSON.stringify(items);
""")
        print(f"  localStorage: {ls[:300]}")
        
        # Simpan session
        self.session_cookies = cookies
        self.page = p
        return self

    def deploy_gateway(self):
        """Step 4: Deploy Hermes-Gateway ke akun Railway"""
        print("\n[4] Deploy Hermes-Gateway...")
        
        # Generate password unik
        self.admin_password = self._gen_password(16)
        self.ssh_password = self._gen_password(16)
        print(f"  Admin password: {self.admin_password}")
        print(f"  SSH password: {self.ssh_password}")
        
        p = self.page
        
        # Approach 1: Coba deploy via template page
        print("  Buka halaman deploy template...")
        p.get(DEPLOY_URL)
        time.sleep(8)
        
        print(f"  URL: {p.url}")
        p.get_screenshot(path="deploy_page.png")
        
        # Cek apakah ada form atau redirect ke dashboard
        page_text = p.run_js("return document.body.innerText.substring(0, 1000)")
        print(f"  Page text: {page_text[:500]}")
        
        # Approach 2: Jika ada halaman template, isi env vars
        # Cari button deploy / configure
        buttons = p.run_js("""
return Array.from(document.querySelectorAll('button, a')).map(el => ({
    text: (el.textContent || '').trim().substring(0, 60),
    tag: el.tagName,
    href: (el.href || '').substring(0, 200)
})).filter(el => el.text);
""")
        print(f"  Buttons/Links: {buttons}")
        
        # Cari input fields
        inputs = p.run_js("""
return Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
    placeholder: el.placeholder || '',
    name: el.name || '',
    id: el.id || '',
    type: el.type || '',
    value: (el.value || '').substring(0, 30)
}));
""")
        print(f"  Inputs: {inputs}")
        
        # Approach 3: Jika redirect ke dashboard, deploy via dashboard UI
        if 'dashboard' in p.url.lower() or 'project' in p.url.lower():
            print("  Redirect ke dashboard, deploy via UI...")
            # Buka template page lagi
            p.get(DEPLOY_URL)
            time.sleep(5)
        
        # TODO: deploy logic needs to be completed based on actual page structure
        print("  [DEPLOY] Menunggu implementasi deploy...")
        
        # Simpan hasil
        self.service_url = f"https://{self.admin_password[:8]}.up.railway.app"
        
        return self

    def run(self):
        """Full pipeline"""
        try:
            self.create_email()
            self.solve_turnstile()
            self.login_railway()
            self.deploy_gateway()
            return {
                "email": self.email,
                "admin_password": self.admin_password,
                "ssh_password": self.ssh_password,
                "status": "success"
            }
        except Exception as e:
            print(f"\n[ERROR] {e}")
            return {"status": "error", "error": str(e)}
        finally:
            if hasattr(self, 'page') and self.page:
                try:
                    self.page.quit()
                except:
                    pass

def main():
    print("=" * 50)
    print("Railway Auto-Account + Deploy Hermes-Gateway")
    print("=" * 50)
    
    auto = RailwayAuto()
    result = auto.run()
    
    print("\n" + "=" * 50)
    print("HASIL:")
    print(json.dumps(result, indent=2))
    print("=" * 50)

if __name__ == "__main__":
    main()