# -*- coding: utf-8 -*-
"""Web shop backend: landing page + order API + payment upload + Telegram bot trigger."""
import os, sys, json, time, threading, uuid

from flask import Flask, render_template, request, jsonify, send_from_directory

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import deploy_via_api as dep

UPLOAD_DIR = os.path.join(HERE, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

JOBS_FILE = os.path.join(HERE, "web_jobs.json")
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
        _jobs[job_id]["status"] = "deploying"
        _save_jobs()
        order = dep.create_order()
        _jobs[job_id]["order"] = order
        _save_jobs()
        url = dep.get_url(order["project_id"])
        order["url"] = url
        _jobs[job_id]["order"] = order
        _jobs[job_id]["status"] = "ready" if url else "deployed_no_url"
        _save_jobs()
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["error"] = str(e)
        _save_jobs()


def _worker():
    while True:
        try:
            for jid, job in list(_jobs.items()):
                if job.get("status") == "processing":
                    _run_order(jid)
        except Exception:
            pass
        time.sleep(5)


threading.Thread(target=_worker, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/order", methods=["POST"])
def create_order():
    name = request.form.get("name", "")
    telegram = request.form.get("telegram", "")
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
        "buyer": {"name": name, "telegram": telegram},
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
            "admin_username": job["order"].get("admin_username"),
            "admin_password": job["order"].get("admin_password"),
            "ssh_password": job["order"].get("ssh_password"),
        }
    return jsonify(resp)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return flask.send_from_directory(UPLOAD_DIR, filename)


@app.route("/admin")
def admin():
    return render_template("admin.html", jobs=_jobs)


@app.route("/health")
def health():
    return "ok"


# Bot disabled for now — will be added as separate service later
# def start_bot():
#     import bot
#     bot.main()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
    port = int(os.environ.get("PORT", 5000))
    # start bot di thread terpisah (gagal ga masalah)
    try:
        import bot as bot_module
        t = threading.Thread(target=bot_module.main, daemon=True)
        t.start()
        print("Bot: started")
    except Exception as e:
        print(f"Bot: skip ({e})")

    print(f"Flask on :{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)