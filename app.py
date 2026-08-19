# -*- coding: utf-8 -*-
"""Web shop backend: landing page + order API + payment upload + Telegram bot trigger."""
import os, sys, json, time, threading, uuid

from flask import Flask, render_template, render_template_string, request, jsonify, send_from_directory, redirect, url_for, make_response

if hasattr(sys.stdout, "reconfigure"):
    # line_buffering: tanpa ini print dari thread worker gak nongol di Railway logs
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_via_api as dep

# DATA_DIR: lokasi persisten (Railway Volume). Fallback ke HERE buat dev lokal.
DATA_DIR = os.environ.get("DATA_DIR", HERE)
os.makedirs(DATA_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

JOBS_FILE = os.path.join(DATA_DIR, "web_jobs.json")
_jobs = {}
_lock = threading.Lock()


def _load_jobs():
    if os.path.exists(JOBS_FILE):
        try:
            return json.load(open(JOBS_FILE))
        except Exception:
            return {}
    return {}


def _save_jobs():
    with _lock:
        json.dump(_jobs, open(JOBS_FILE, "w"), indent=2)


_jobs = _load_jobs()


def _run_order(job_id):
    try:
        print(f"[deploy] Starting deploy for {job_id}...")
        _jobs[job_id]["status"] = "deploying"
        _jobs[job_id]["deploy_started_at"] = time.time()
        _save_jobs()
        # create_order() udah poll URL semua service pakai session login yang sama
        order = dep.create_order()
        print(f"[deploy] Order created: {order}")
        if not order:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = "create_order gagal (login/OTP/captcha)"
            _save_jobs()
            return
        _jobs[job_id]["order"] = order
        _jobs[job_id]["status"] = "ready" if order.get("url") else "deployed_no_url"
        _save_jobs()
        print(f"[deploy] Complete: {job_id} url={order.get('url')}")
    except Exception as e:
        print(f"[deploy] FAILED: {e}")
        import traceback
        traceback.print_exc()
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _save_jobs()


DEPLOY_TIMEOUT_SEC = 2400  # 40 menit max (login + create 3 service + poll URL)

def _worker():
    while True:
        try:
            for jid, job in list(_jobs.items()):
                st = job.get("status")
                # watchdog: kalau deploy stuck > DEPLOY_TIMEOUT_SEC, mark failed
                if st == "deploying" and job.get("deploy_started_at"):
                    if (time.time() - job["deploy_started_at"]) > DEPLOY_TIMEOUT_SEC:
                        print(f"[worker] TIMEOUT {jid} — marking failed")
                        job["status"] = "failed"
                        job["error"] = f"Deploy timeout ({DEPLOY_TIMEOUT_SEC}s)"
                        _save_jobs()
                        continue
                if st == "processing":
                    print(f"[worker] Processing {jid}...")
                    _run_order(jid)
        except Exception as e:
            print(f"[worker] Error: {e}")
            import traceback
            traceback.print_exc()
        time.sleep(5)


threading.Thread(target=_worker, daemon=True).start()


@app.route("/")
def index():
    return render_template("hermes-anim.html")


@app.route("/order")
@app.route("/order.html")
def order_page():
    return render_template("order.html")


@app.route("/api/order", methods=["POST"])
def create_order():
    name = request.form.get("name", "")
    telegram = request.form.get("telegram", "")
    pkg = request.form.get("package", "")
    price = request.form.get("price", "0")
    photo = request.files.get("payment_photo")

    job_id = uuid.uuid4().hex[:12]
    photo_path = None
    if photo and photo.filename:
        ext = photo.filename.rsplit(".", 1)[-1] if "." in photo.filename else "jpg"
        photo_path = os.path.join(UPLOAD_DIR, f"{job_id}.{ext}")
        photo.save(photo_path)

    _jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "buyer": {"name": name, "telegram": telegram, "package": pkg, "price": price},
        "payment": {"gopay": "0881022218911", "photo_path": photo_path},
        "order": None,
        "url": None,
        "error": None,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_jobs()
    return jsonify({"job_id": job_id, "status": "pending"})


@app.route("/api/order/pending")
def pending_orders():
    res = []
    for jid, job in _jobs.items():
        if job.get("status") == "pending":
            res.append({"job_id": jid, "buyer": job.get("buyer"), "created_at": job.get("created_at")})
    return jsonify(res)


@app.route("/api/order/<job_id>/deploy", methods=["POST"])
def deploy_order(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    if job["status"] != "pending":
        return jsonify({"error": f"status is {job['status']}"}), 400
    job["status"] = "processing"
    job["processing_since"] = time.time()
    _save_jobs()
    return jsonify({"status": "processing"})


@app.route("/api/order/<job_id>/delete", methods=["POST"])
def delete_order(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    job["status"] = "cancelled"
    _save_jobs()
    return jsonify({"status": "cancelled"})


@app.route("/api/order/<job_id>")
def order_status(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    resp = {
        "job_id": job_id,
        "status": job["status"],
        "buyer": job["buyer"],
        "error": job.get("error"),
    }
    if job.get("order"):
        resp["order"] = {
            "url": job["order"].get("url"),
            "router_url": job["order"].get("router_url"),
            "terminal_url": job["order"].get("terminal_url"),
            "admin_username": job["order"].get("admin_username"),
            "admin_password": job["order"].get("admin_password"),
            "ssh_password": job["order"].get("ssh_password"),
            "router_password": job["order"].get("router_password"),
            "terminal_password": job["order"].get("terminal_password"),
        }
    return jsonify(resp)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    # Simple auth: POST dengan key, simpan di cookie session
    if request.method == "POST":
        if request.form.get("key") == ADMIN_KEY:
            resp = make_response(redirect(url_for("admin")))
            resp.set_cookie("admin_key", ADMIN_KEY, httponly=True, samesite="Lax", max_age=86400*7)
            return resp
        return redirect(url_for("admin"))
    # GET: cek cookie
    if request.cookies.get("admin_key") != ADMIN_KEY:
        return render_template_string(ADMIN_LOGIN_HTML)
    return render_template("admin.html", jobs=_jobs)


ADMIN_KEY = os.environ.get("ADMIN_KEY", "change-me")

ADMIN_LOGIN_HTML = """
<!DOCTYPE html>
<html lang="id"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Admin Login — HERMES</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@500;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">
<style>
:root{--bg:#070708;--fg:#e3e3e5;--fg2:#555;--border:rgba(255,255,255,.06);--accent:#34d399}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;display:flex;justify-content:center;align-items:center;
background-image:radial-gradient(ellipse at 30% 20%,rgba(52,211,153,.04),transparent 50%)}
.card{background:rgba(18,18,22,.8);border:1px solid var(--border);border-radius:16px;padding:32px;width:min(360px,90vw)}
.logo{font-weight:800;font-size:14px;display:flex;align-items:center;gap:8px;margin-bottom:6px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px rgba(52,211,153,.4)}
.logo span{color:var(--accent)}
h3{font-size:13px;color:var(--fg2);font-weight:500;margin-bottom:18px}
input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid var(--border);background:rgba(255,255,255,.03);
color:var(--fg);font-family:'JetBrains Mono',monospace;font-size:13px;outline:none;transition:border-color .25s}
input:focus{border-color:var(--accent)}
button{width:100%;margin-top:12px;padding:12px;background:var(--accent);color:#052e16;border:none;border-radius:10px;
font-size:14px;font-weight:600;font-family:'Inter',sans-serif;cursor:pointer;transition:filter .25s}
button:hover{filter:brightness(1.1)}
</style></head><body>
<form class="card" method="post">
<div class="logo"><div class="dot"></div>HERMES <span>ADMIN</span></div>
<h3>Masuk pakai admin key</h3>
<input type="password" name="key" placeholder="Admin key" required autofocus>
<button type="submit">Login</button>
</form>
</body></html>
"""


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    resp = make_response(redirect(url_for("admin")))
    resp.delete_cookie("admin_key")
    return resp


@app.route("/health")
def health():
    return "ok"


# ── TEMPORER probe (post-mortem deploy 3-link) — hapus kalau udah fix ──
PROBE_FILE = os.path.join(DATA_DIR, "debug_probe_result.json")


@app.route("/debug/probe", methods=["POST"])
def debug_probe():
    if request.cookies.get("admin_key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    key = request.args.get("order", "").strip()
    try:
        orders = json.load(open(dep.ORDERS_FILE))
    except Exception as e:
        return jsonify({"error": f"orders load gagal: {e}"}), 500
    order = next((o for o in orders if key and (key in (o.get("email"), o.get("project_id")))), None)
    if not order:
        return jsonify({"error": "order tidak ketemu", "keys": [o.get("email") for o in orders[-5:]]}), 404
    json.dump({"status": "running", "order": key}, open(PROBE_FILE, "w"))

    def _run():
        import probe_deploy
        try:
            res = probe_deploy.run(order)
            res["status"] = "done"
        except Exception as e:
            import traceback
            res = {"status": "error", "error": str(e), "trace": traceback.format_exc()[:2000]}
        json.dump(res, open(PROBE_FILE, "w"), indent=2)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "email": order.get("email")})


@app.route("/debug/probe/result")
def debug_probe_result():
    if request.cookies.get("admin_key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403
    if not os.path.exists(PROBE_FILE):
        return jsonify({"status": "none"})
    return send_from_directory(DATA_DIR, "debug_probe_result.json")



# Bot disabled for now — will be added as separate service later
# def start_bot():
#     import bot
#     bot.main()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # start bot di thread terpisah
    try:
        import bot as bot_module
        t = threading.Thread(target=bot_module.main, daemon=True)
        t.start()
        print("Bot: started")
    except Exception as e:
        print(f"Bot: skip ({e})")

    print(f"Flask on :{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)