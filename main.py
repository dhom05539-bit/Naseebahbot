
import os, sqlite3, threading, asyncio
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN") or "8457960212:AAE3x99-YGJI8MtAKVBPp-0f-GRvovIvO4c"

flask_app = Flask(__name__)
@flask_app.route('/')
def home(): return "✅ بوت نُسيبه شغال 24/7 - @Naseebah_bot"
@flask_app.route('/health')
def health(): return "OK", 200

BRANCHES = {
    "فرع ساحة دان": {"lat": 21.311746875, "lon": 39.51455625, "radius": 80},
    "فرع درايف ثرو العوالي": {"lat": 21.311863594, "lon": 39.51664031, "radius": 80},
    "فرع درايف ثرو الشوقيه": {"lat": 21.312759375, "lon": 39.39463125, "radius": 80},
}
EMPLOYEES = {
    "احمد": "فرع ساحة دان", "محمود": "فرع ساحة دان", "عبدالعزيز": "فرع ساحة دان",
    "نواف": "فرع درايف ثرو العوالي", "حنشون": "فرع درايف ثرو العوالي", "بدوي": "فرع درايف ثرو العوالي",
    "علي": "فرع درايف ثرو الشوقيه", "اسامه": "فرع درايف ثرو الشوقيه",
}
WORK_START = "08:00"
ALLOWED_LATE_MINUTES = 15
TEST_MODE = False

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    import math as m
    phi1, phi2 = m.radians(lat1), m.radians(lat2)
    dphi = m.radians(lat2 - lat1)
    dlambda = m.radians(lon2 - lon1)
    a = m.sin(dphi/2)**2 + m.cos(phi1)*m.cos(phi2)*m.sin(dlambda/2)**2
    return R * 2 * m.atan2(m.sqrt(a), m.sqrt(1-a))

def init_db():
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, name TEXT, branch TEXT, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, name TEXT, branch TEXT, date TEXT, check_in TEXT, check_out TEXT, check_in_lat REAL, check_in_lon REAL, check_out_lat REAL, check_out_lon REAL, status TEXT)")
    conn.commit(); conn.close()

def get_user(tid):
    conn = sqlite3.connect("attendance.db")
    c = conn.cursor(); c.execute("SELECT name, branch FROM users WHERE telegram_id=?", (tid,))
    row = c.fetchone(); conn.close(); return row

async def start(update, context):
    uid = update.effective_user.id
    ex = get_user(uid)
    if ex:
        name, branch = ex
        kb = [[KeyboardButton("📍 تسجيل حضور")],[KeyboardButton("🚪 تسجيل انصراف")],[KeyboardButton("📊 سجلي اليوم"), KeyboardButton("🏢 فروعي")],[KeyboardButton("📋 تقرير اليوم")]]
        await update.message.reply_text(f"أهلاً {name} 👋\nفرعك: {branch}\n🟢 النظام شغال 24 ساعة\nاختر:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    else:
        kb = []
        names = list(EMPLOYEES.keys())
        for i in range(0, len(names), 2):
            row = [InlineKeyboardButton(names[j], callback_data=f"reg_{names[j]}") for j in range(i, min(i+2, len(names)))]
            kb.append(row)
        await update.message.reply_text("👋 أهلاً في بوت بصمة نُسيبه - شغال 24/7\nاختر اسمك:", reply_markup=InlineKeyboardMarkup(kb))

async def register_callback(update, context):
    q = update.callback_query; await q.answer()
    name = q.data.replace("reg_", ""); branch = EMPLOYEES.get(name, "فرع ساحة دان")
    conn = sqlite3.connect("attendance.db"); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?)", (q.from_user.id, name, branch, datetime.now().isoformat()))
    conn.commit(); conn.close()
    await q.edit_message_text(f"✅ تم تسجيلك: {name}\nفرعك: {branch}\n\nالآن /start")
    kb = [[KeyboardButton("📍 تسجيل حضور")],[KeyboardButton("🚪 تسجيل انصراف")],[KeyboardButton("📊 سجلي اليوم"), KeyboardButton("🏢 فروعي")]]
    await q.message.reply_text("اختر:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def handle_location(update, context):
    uid = update.effective_user.id; ud = get_user(uid)
    if not ud: await update.message.reply_text("سجل /start أولاً"); return
    name, assigned = ud; lat = update.message.location.latitude; lon = update.message.location.longitude
    closest, mind = None, float('inf')
    for bn, bd in BRANCHES.items():
        d = haversine(lat, lon, bd["lat"], bd["lon"])
        if d < mind: mind = d; closest = bn
    action = context.user_data.get("action", "in"); allowed = BRANCHES[closest]["radius"]
    if mind > allowed:
        await update.message.reply_text(f"❌ أنت بعيد {int(mind)}م عن {closest}\nلازم تكون داخل {allowed}م"); return
    today = datetime.now().strftime("%Y-%m-%d"); now_str = datetime.now().strftime("%H:%M:%S")
    now_t = datetime.now(); work = datetime.strptime(WORK_START, "%H:%M").replace(year=now_t.year, month=now_t.month, day=now_t.day)
    late = work + timedelta(minutes=ALLOWED_LATE_MINUTES)
    conn = sqlite3.connect("attendance.db"); c = conn.cursor()
    if action == "in":
        c.execute("SELECT id FROM attendance WHERE telegram_id=? AND date=? AND check_in IS NOT NULL", (uid, today))
        if c.fetchone(): await update.message.reply_text("⚠️ مسجل حضور اليوم already"); conn.close(); return
        status = "متأخر" if now_t > late else "حاضر"
        c.execute("INSERT INTO attendance (telegram_id, name, branch, date, check_in, check_in_lat, check_in_lon, status) VALUES (?,?,?,?,?,?,?,?)", (uid, name, closest, today, now_str, lat, lon, status))
        conn.commit(); await update.message.reply_text(f"✅ تم تسجيل حضور\n👤 {name}\n🏢 {closest}\n⏰ {now_str}\n📍 {int(mind)}م\n📌 {status}")
    else:
        c.execute("SELECT id, check_in, check_out FROM attendance WHERE telegram_id=? AND date=? ORDER BY id DESC LIMIT 1", (uid, today))
        row = c.fetchone()
        if not row: await update.message.reply_text("❌ ما سجلت حضور اليوم"); conn.close(); return
        if row[2]: await update.message.reply_text("⚠️ مسجل انصراف already"); conn.close(); return
        c.execute("UPDATE attendance SET check_out=?, check_out_lat=?, check_out_lon=? WHERE id=?", (now_str, lat, lon, row[0])); conn.commit()
        await update.message.reply_text(f"✅ تم تسجيل انصراف\n👤 {name}\n🏢 {closest}\n⏰ {now_str}")
    conn.close()

async def handle_text(update, context):
    t = update.message.text or ""
    if "حضور" in t:
        context.user_data["action"] = "in"
        await update.message.reply_text("📍 أرسل موقعك الحالي:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 إرسال موقعي الحالي", request_location=True)]], resize_keyboard=True))
    elif "انصراف" in t:
        context.user_data["action"] = "out"
        await update.message.reply_text("📍 أرسل موقعك الحالي:", reply_markup=ReplyKeyboardMarkup([[KeyboardButton("📍 إرسال موقعي الحالي", request_location=True)]], resize_keyboard=True))
    elif "سجلي" in t:
        conn = sqlite3.connect("attendance.db"); c = conn.cursor()
        c.execute("SELECT date, check_in, check_out, branch, status FROM attendance WHERE telegram_id=? ORDER BY date DESC LIMIT 7", (update.effective_user.id,))
        rows = c.fetchall(); conn.close()
        msg = "📊 آخر 7 أيام:\n\n" + "\n".join([f"{r[0]} | {r[3]}\nدخول {r[1]} خروج {r[2] or '-' } ({r[4]})\n---" for r in rows]) if rows else "لا يوجد سجل"
        await update.message.reply_text(msg)
    elif "تقرير" in t or "/report" in t:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect("attendance.db"); c = conn.cursor()
        c.execute("SELECT name, branch, check_in, check_out, status FROM attendance WHERE date=? ORDER BY check_in", (today,))
        rows = c.fetchall(); conn.close()
        if not rows: await update.message.reply_text(f"📋 لا يوجد حضور اليوم {today}"); return
        msg = f"📋 تقرير حضور {today}:\n\n"
        for r in rows: msg += f"👤 {r[0]} | {r[1]}\n⏰ دخول {r[2]} - خروج {r[3] or '---'} | {r[4]}\n---\n"
        await update.message.reply_text(msg)
    elif "فروعي" in t:
        await update.message.reply_text("🏢 فروع نُسيبه (80م):\n1- فرع ساحة دان\n2- فرع درايف ثرو العوالي\n3- فرع درايف ثرو الشوقيه")
    else:
        kb = [[KeyboardButton("📍 تسجيل حضور")],[KeyboardButton("🚪 تسجيل انصراف")],[KeyboardButton("📊 سجلي اليوم"), KeyboardButton("🏢 فروعي")]]
        await update.message.reply_text("اختر:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

def run_bot():
    init_db()
    asyncio.set_event_loop(asyncio.new_event_loop())
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", handle_text))
    app.add_handler(CallbackQueryHandler(register_callback, pattern="^reg_"))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("✅ بوت نُسيبه شغال 24/7 - TEST_MODE", TEST_MODE, flush=True)
    app.run_polling()

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
