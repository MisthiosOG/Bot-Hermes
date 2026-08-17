# -*- coding: utf-8 -*-
"""Telegram bot: notifikasi order + bukti TF + approve/delete + kirim kredensial ke buyer."""
import os, sys, json, time, asyncio

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("BOT_TOKEN") or "8921396573:AAEG6fWTCXylJWB1nW8pPuvHx0CfSK0dLAU"
ADMIN_ID = int(os.environ.get("ADMIN_ID") or "861901986")
FLASK = "http://localhost:5000"

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler
import httpx

bot = Bot(token=TOKEN)
_seen_status = {}  # job_id -> last_status yang udah diproses

def j():
    f = os.path.join(HERE, "web_jobs.json")
    if os.path.exists(f):
        try: return json.load(open(f))
        except: return {}
    return {}

def sj(jobs):
    json.dump(jobs, open(os.path.join(HERE, "web_jobs.json"), "w"), indent=2)

async def tell(text, kb=None):
    if ADMIN_ID:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="HTML", reply_markup=kb)

async def send_photo_to_admin(photo_path, caption, kb=None):
    if ADMIN_ID and photo_path and os.path.exists(photo_path):
        with open(photo_path, "rb") as f:
            await bot.send_photo(chat_id=ADMIN_ID, photo=f, caption=caption, parse_mode="HTML", reply_markup=kb)

async def dm_user(username, text):
    """Kirim pesan ke user via @username. Gagal kalau user belum /start bot."""
    if not username:
        return False, "no username"
    try:
        u = username.strip()
        if u.startswith("@"): u = u[1:]
        await bot.send_message(chat_id="@"+u, text=text, parse_mode="HTML")
        return True, "ok"
    except Exception as e:
        err = str(e)
        if "chat not found" in err.lower():
            return False, "user belum /start bot"
        return False, err

async def poll():
    while True:
        try:
            jobs = j()
            for jid, job in jobs.items():
                s = job.get("status")
                if _seen_status.get(jid) == s: continue
                _seen_status[jid] = s

                # ── order baru ──
                if s == "pending":
                    b = job.get("buyer", {})
                    pay = job.get("payment", {})
                    msg = (f"<b>🆕 Order Baru</b>\n"
                           f"Nama: {b.get('name','—')}\n"
                           f"Telegram: {b.get('telegram','—')}\n"
                           f"GoPay: {pay.get('gopay','—')}\n"
                           f"Waktu: {job.get('created_at','—')}\n"
                           f"ID: <code>{jid}</code>")
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Approve", callback_data=f"app|{jid}"),
                        InlineKeyboardButton("❌ Delete", callback_data=f"del|{jid}"),
                    ]])
                    # kirim teks + foto bukti TF
                    photo_path = pay.get("photo_path")
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, "rb") as f:
                            await bot.send_photo(chat_id=ADMIN_ID, photo=f, caption=msg, parse_mode="HTML", reply_markup=kb)
                    else:
                        await tell(msg, kb)

                # ── order selesai ──
                elif s == "ready":
                    o = job.get("order") or {}
                    b = job.get("buyer", {})
                    creds = (f"<b>✅ Panel Siap!</b>\n\n"
                             f"URL: <code>{o.get('url','—')}</code>\n"
                             f"Username: <code>{o.get('admin_username','admin')}</code>\n"
                             f"Password: <code>{o.get('admin_password','—')}</code>\n"
                             f"SSH: <code>{o.get('ssh_password','—')}</code>\n\n"
                             f"Simpan baik-baik. Login di URL di atas.")
                    # kirim ke buyer
                    buyer_tg = b.get("telegram", "")
                    dm_ok, dm_note = await dm_user(buyer_tg, creds)
                    # kirim ke admin
                    note = f"Sudah dikirim ke {buyer_tg}" if dm_ok else f"GAGAL kirim ke {buyer_tg}: {dm_note}"
                    await tell(f"{creds}\n\n<i>{note}</i>")
                    # update status DM
                    job["dm_sent"] = dm_ok
                    sj(jobs)

        except Exception as e:
            print(f"[bot] {e}")
        await asyncio.sleep(8)

async def cb(update, ctx):
    data = update.callback_query.data
    act, jid = data.split("|", 1)
    jobs = j()
    job = jobs.get(jid)
    if act == "del":
        if job: job["status"] = "cancelled"; sj(jobs)
        await tell(f"❌ Order <code>{jid}</code> dibatalkan.")
    elif act == "app":
        if not job or job.get("status") != "pending":
            await update.callback_query.answer("Status sudah berubah")
            return
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{FLASK}/api/order/{jid}/deploy")
            if r.status_code == 200:
                job["status"] = "processing"; sj(jobs)
                await tell(f"⏳ Deploy <code>{jid}</code> dimulai...")
            else:
                await tell(f"❌ Gagal: {r.text}")
    await update.callback_query.answer()
    try: await update.callback_query.edit_message_reply_markup(reply_markup=None)
    except: pass

async def run_bot():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CallbackQueryHandler(cb))
    async def startup(app):
        asyncio.create_task(poll())
    app.post_init = startup
    print("[bot] Jalan.")
    await app.run_polling(stop_signals=None)

def main():
    if "ISI_BOT" in TOKEN:
        print("[bot] Ganti BOT_TOKEN"); return
    if not ADMIN_ID:
        print("[bot] Isi ADMIN_ID"); return
    asyncio.run(run_bot())

if __name__ == "__main__":
    asyncio.run(run_bot())