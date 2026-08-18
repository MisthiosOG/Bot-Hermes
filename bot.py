# -*- coding: utf-8 -*-
"""Telegram bot: notifikasi order + bukti TF + approve/delete + kirim kredensial ke buyer."""
import os, sys, json, time, asyncio, html

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("BOT_TOKEN") or "8921396573:AAEG6fWTCXylJWB1nW8pPuvHx0CfSK0dLAU"
ADMIN_ID = int(os.environ.get("ADMIN_ID") or "861901986")
FLASK = f"http://localhost:{os.environ.get('PORT', 8080)}"
# DATA_DIR: lokasi persisten (Railway Volume). Fallback ke HERE buat dev lokal.
DATA_DIR = os.environ.get("DATA_DIR", HERE)

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
import httpx

bot = Bot(token=TOKEN)
_seen_status = {}  # job_id -> last_status yang udah diproses
SEEN_FILE = os.path.join(DATA_DIR, "bot_seen.json")

def _load_seen():
    global _seen_status
    if os.path.exists(SEEN_FILE):
        try: _seen_status = json.load(open(SEEN_FILE))
        except: _seen_status = {}

def _save_seen():
    try: json.dump(_seen_status, open(SEEN_FILE, "w"))
    except Exception as e: print(f"[bot] seen save err: {e}")

_load_seen()

def esc(s):
    return html.escape(str(s if s is not None else "—"))

def rupiah(v):
    """Format angka jadi Rupiah: 15000 -> 15.000. Tahan input string/non-angka."""
    try:
        n = int(str(v).replace("Rp", "").replace("rp", "").replace(".", "").replace(",", "").strip())
        return f"{n:,}".replace(",", ".")
    except Exception:
        return esc(v)

def styled_kb(*rows):
    """Inline keyboard dengan warna (Bot API 9.4 / PTB 22.8):
    style = "danger" (merah) | "primary" (biru) | "success" (hijau)."""
    return InlineKeyboardMarkup([[b for b in r] for r in rows])

def btn(text, data, style=None):
    return InlineKeyboardButton(text, callback_data=data, style=style)

def invoice_block(job_id, job):
    """Teks invoice rapi dalam blok monospace (pre) biar gak berantakan.
    Nominal ditonjolkan biar admin bisa cocokan sama bukti TF."""
    b = job.get("buyer", {})
    pay = job.get("payment", {})
    price = rupiah(b.get("price"))
    lines = [
        f"Nama     : {esc(b.get('name'))}",
        f"Telegram : {esc(b.get('telegram'))}",
        f"Paket    : {esc(b.get('package'))}",
        f"Waktu    : {esc(job.get('created_at'))}",
        f"GoPay    : {esc(pay.get('gopay'))}",
    ]
    return (
        "<b>ORDER BARU</b>\n"
        "<pre>" + "\n".join(lines) + "\nID       : " + esc(job_id) + "</pre>\n\n"
        f"<b>NOMINAL TF : Rp {price}</b>\n"
        f"<i>Cocokin angka di bukti transfer = Rp {price}</i>"
    )

def creds_block(job):
    o = job.get("order") or {}
    lines = [
        f"Hermes Panel : {esc(o.get('url'))}",
        f"  login admin / {esc(o.get('admin_password'))}",
        f"9Router      : {esc(o.get('router_url'))}",
        f"  password   : {esc(o.get('router_password'))}",
        f"Terminal Web : {esc(o.get('terminal_url'))}",
        f"  login admin / {esc(o.get('terminal_password'))}",
        f"SSH pass     : {esc(o.get('ssh_password'))}",
    ]
    return (
        "<b>PANEL SIAP — 3 LINK AKTIF</b>\n"
        "<pre>" + "\n".join(lines) + "</pre>"
        "Simpan baik-baik. Langganan aktif 30 hari."
    )

def j():
    f = os.path.join(DATA_DIR, "web_jobs.json")
    if os.path.exists(f):
        try: return json.load(open(f))
        except: return {}
    return {}

def sj(jobs):
    json.dump(jobs, open(os.path.join(DATA_DIR, "web_jobs.json"), "w"), indent=2)

async def tell(text, kb=None):
    if ADMIN_ID:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML", reply_markup=kb)

async def send_photo_to_admin(photo_path, caption, kb=None):
    if ADMIN_ID and photo_path and os.path.exists(photo_path):
        with open(photo_path, "rb") as f:
            await bot.send_photo(chat_id=ADMIN_ID, photo=f, caption=caption, parse_mode="HTML", reply_markup=kb)

async def poll():
    while True:
        try:
            jobs = j()
            for jid, job in jobs.items():
                s = job.get("status")
                if _seen_status.get(jid) == s: continue
                _seen_status[jid] = s
                _save_seen()

                # ── order baru ──
                if s == "pending":
                    b = job.get("buyer", {})
                    pay = job.get("payment", {})
                    msg = invoice_block(jid, job)
                    kb = styled_kb(
                        [btn("Approve", f"app|{jid}", style="success"),
                         btn("Delete", f"del|{jid}", style="danger")],
                    )
                    # kirim teks + foto bukti TF
                    photo_path = pay.get("photo_path")
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, "rb") as f:
                            await bot.send_photo(chat_id=ADMIN_ID, photo=f, caption=msg, parse_mode="HTML", reply_markup=kb)
                    else:
                        await tell(msg, kb)

                # ── order selesai ──
                elif s == "ready":
                    creds = creds_block(job)
                    await tell(creds)

        except Exception as e:
            print(f"[bot] {e}")
        await asyncio.sleep(8)

async def cb(update, ctx):
    data = update.callback_query.data
    act, jid = data.split("|", 1)
    jobs = j()
    job = jobs.get(jid)
    answer_text = ""
    if act == "del":
        if job: job["status"] = "cancelled"; sj(jobs)
        await tell(f"Order <code>{jid}</code> dibatalkan.")
    elif act == "resend":
        await update.callback_query.answer("Resend disabled")
    elif act == "app":
        if not job or job.get("status") != "pending":
            await update.callback_query.answer("Status sudah berubah")
            return
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{FLASK}/api/order/{jid}/deploy")
            if r.status_code == 200:
                job["status"] = "processing"; sj(jobs)
                await tell(f"Deploy <code>{jid}</code> dimulai...")
            else:
                await tell(f"Gagal: {r.text}")
    await update.callback_query.answer(answer_text)
    try: await update.callback_query.edit_message_reply_markup(reply_markup=None)
    except: pass

def main():
    if "ISI_BOT" in TOKEN:
        print("[bot] Ganti BOT_TOKEN"); return
    if not ADMIN_ID:
        print("[bot] Isi ADMIN_ID"); return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CallbackQueryHandler(cb))
    # poll task berjalan dalam loop yang sama dengan bot
    async def startup(app):
        asyncio.create_task(poll())
    app.post_init = startup
    print("[bot] Jalan.")
    app.run_polling(stop_signals=None, drop_pending_updates=True)

if __name__ == "__main__":
    main()