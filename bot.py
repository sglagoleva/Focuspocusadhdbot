import os, json, sqlite3, asyncio
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ── CONFIG ────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY", "")
USER_NAME     = os.getenv("USER_NAME", "Артём")

# Conversation states — morning
(M_EXERCISE, M_FOCUS, M_WRITING, M_GRATITUDE, M_CHILD) = range(5)

# Conversation states — evening
(E_ACH, E_PRAISE, E_HIGHLIGHTS, E_A, E_B1, E_B2, E_C1, E_C2, E_C3) = range(9, 18)

MOTIVATIONS = [
    "Сегодня твой день.",
    "Один шаг — и ты уже в движении.",
    "Только одно главное. Остальное подождёт.",
    "Твой мозг нестандартный. Это сила.",
    "Чуть больше чем вчера — этого достаточно.",
    "Ты проснулся. Уже хорошо.",
    "Сделай одно дело. Потом ещё одно.",
]

WARMUP_EXERCISES = [
    ("Шея — повороты 🔄", "Медленно влево-вправо, 5 раз"),
    ("Плечи — круги 🔄", "Вперёд 5 раз, назад 5 раз"),
    ("Запястья 🤲", "Покрути кулаки в обе стороны"),
    ("Поясница ↔️", "Наклоны влево-вправо"),
    ("Колени 🦵", "Поднимай колени стоя, по 5 раз"),
    ("Голеностоп 🦶", "Вращение каждой ногой"),
]

# ── DATABASE ──────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS diary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, date TEXT, block TEXT, data TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS streak (
        user_id INTEGER, date TEXT,
        PRIMARY KEY (user_id, date)
    )""")
    conn.commit(); conn.close()

def save_diary(uid, block, data):
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    d = date.today().isoformat()
    c.execute("DELETE FROM diary WHERE user_id=? AND date=? AND block=?", (uid, d, block))
    c.execute("INSERT INTO diary(user_id,date,block,data) VALUES(?,?,?,?)",
              (uid, d, block, json.dumps(data, ensure_ascii=False)))
    conn.commit(); conn.close()

def get_diary(uid, block, for_date=None):
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    d = for_date or date.today().isoformat()
    c.execute("SELECT data FROM diary WHERE user_id=? AND date=? AND block=?", (uid, d, block))
    row = c.fetchone()
    conn.close()
    return json.loads(row[0]) if row else {}

def add_streak(uid):
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO streak VALUES(?,?)", (uid, date.today().isoformat()))
    conn.commit(); conn.close()

def calc_streak(uid):
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    c.execute("SELECT date FROM streak WHERE user_id=? ORDER BY date DESC", (uid,))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    if not rows: return 0
    count = 0
    cur = date.today()
    for i, d in enumerate(rows):
        if (cur - date.fromisoformat(d)).days == i: count += 1
        else: break
    return count

# ── KEYBOARDS ─────────────────────────────────────────────────────────────
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("☀️ Утро", callback_data="go_morning"),
         InlineKeyboardButton("🌙 Вечер", callback_data="go_evening")],
        [InlineKeyboardButton("🤖 Коуч", callback_data="go_coach"),
         InlineKeyboardButton("📊 Мой стрик", callback_data="go_streak")],
    ])

def skip_kb(cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить →", callback_data=cb)]])

# ── /start ────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_db()
    hour = datetime.now().hour
    block = "утро" if hour < 12 else "вечер" if hour >= 18 else "день"
    motivation = MOTIVATIONS[datetime.now().weekday() % len(MOTIVATIONS)]

    await update.message.reply_text(
        f"👋 Привет, {USER_NAME}!\n\n"
        f"_{motivation}_\n\n"
        f"Сейчас {block}. Выбери блок 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── MORNING FLOW ──────────────────────────────────────────────────────────
async def morning_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    motivation = MOTIVATIONS[datetime.now().weekday() % len(MOTIVATIONS)]
    today = datetime.now().strftime("%d %B %Y")

    await q.message.reply_text(
        f"☀️ *GOOD MORNING, {USER_NAME}!*\n"
        f"_{today}_\n\n"
        f"_{motivation}_",
        parse_mode="Markdown"
    )
    await asyncio.sleep(0.5)

    # Exercise
    await q.message.reply_text(
        "🏃 *2 минуты утренней разминки*\n\n"
        "Пройдёмся по суставам — встань и двигайся!\n\n"
        "Нажми *Начать* — я буду вести тебя по упражнениям.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Начать разминку", callback_data="warmup_start")],
            [InlineKeyboardButton("Пропустить →", callback_data="skip_warmup")],
        ])
    )
    return M_EXERCISE

async def warmup_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    msg = await q.message.reply_text("Начинаем! 🏃")
    for i, (name, hint) in enumerate(WARMUP_EXERCISES):
        dots = "🟡" * (i+1) + "⚪" * (len(WARMUP_EXERCISES)-i-1)
        await msg.edit_text(
            f"{dots}\n\n*{name}*\n_{hint}_\n\n⏱ 20 секунд...",
            parse_mode="Markdown"
        )
        await asyncio.sleep(20)
    await msg.edit_text("✅ *Отлично! Тело проснулось.*\n\nТеперь — фокус дня.", parse_mode="Markdown")
    await ask_focus(q.message)
    return M_FOCUS

async def skip_warmup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await ask_focus(q.message)
    return M_FOCUS

async def ask_focus(message):
    await message.reply_text(
        "🎯 *Today's focus*\n\n"
        "Что самое важное сегодня?\n"
        "_Это твой A-план — если сделаешь только его, день прожит не зря._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_focus")
    )

async def got_focus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_focus"] = update.message.text
    await ask_writing(update.message)
    return M_WRITING

async def skip_focus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["m_focus"] = ""
    await ask_writing(q.message)
    return M_WRITING

async def ask_writing(message):
    await message.reply_text(
        "📝 *Free writing*\n\n"
        "Всё что есть в голове — вылей сюда.\n"
        "_Мысли, сны, тревоги, идеи. Без фильтра._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_writing")
    )

async def got_writing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_writing"] = update.message.text
    await ask_gratitude(update.message)
    return M_GRATITUDE

async def skip_writing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["m_writing"] = ""
    await ask_gratitude(q.message)
    return M_GRATITUDE

async def ask_gratitude(message):
    await message.reply_text(
        "🙏 *Gratitude*\n\n"
        "За что благодарен сегодня?\n"
        "_Большое или маленькое — всё считается._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_gratitude")
    )

async def got_gratitude(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_gratitude"] = update.message.text
    await ask_child(update.message)
    return M_CHILD

async def skip_gratitude(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["m_gratitude"] = ""
    await ask_child(q.message)
    return M_CHILD

async def ask_child(message):
    await message.reply_text(
        "💛 *Inner child*\n\n"
        "Скажи себе что-то доброе.\n"
        "_Как бы ты поговорил с лучшим другом?_",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_child")
    )

async def got_child(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_child"] = update.message.text
    await finish_morning(update.message, update.effective_user.id, ctx)
    return ConversationHandler.END

async def skip_child(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["m_child"] = ""
    await finish_morning(q.message, q.from_user.id, ctx)
    return ConversationHandler.END

async def finish_morning(message, uid, ctx):
    save_diary(uid, "morning", {
        "focus":    ctx.user_data.get("m_focus", ""),
        "writing":  ctx.user_data.get("m_writing", ""),
        "gratitude":ctx.user_data.get("m_gratitude", ""),
        "child":    ctx.user_data.get("m_child", ""),
    })
    focus = ctx.user_data.get("m_focus", "")
    await message.reply_text(
        f"✅ *Утро сохранено!*\n\n"
        f"{'🎯 Твой фокус: *' + focus + '*' if focus else '_(фокус не задан)_'}\n\n"
        f"Вперёд, {USER_NAME}. Ты готов.",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── EVENING FLOW ──────────────────────────────────────────────────────────
async def evening_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    streak = calc_streak(uid := q.from_user.id)

    # Show morning focus if set
    morning = get_diary(uid, "morning")
    focus_recap = ""
    if morning.get("focus"):
        focus_recap = f"\n🎯 Твой фокус был: _{morning['focus']}_\n"

    await q.message.reply_text(
        f"🌙 *IT WAS A NICE DAY, {USER_NAME}!*\n"
        f"_{datetime.now().strftime('%d %B %Y')}_\n"
        f"{focus_recap}\n"
        f"Давай закроем этот день.",
        parse_mode="Markdown"
    )
    await asyncio.sleep(0.5)
    await q.message.reply_text(
        "⭐ *Achievements of the day*\n\n"
        "Чего достиг сегодня? Большое или маленькое — всё считается.\n\n"
        "_Напиши одно или несколько через Enter_",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_ach")
    )
    return E_ACH

async def got_ach(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_ach"] = update.message.text
    await ask_praise(update.message)
    return E_PRAISE

async def skip_ach(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["e_ach"] = ""
    await ask_praise(q.message)
    return E_PRAISE

async def ask_praise(message):
    await message.reply_text(
        "🎉 *Praise yourself*\n\n"
        "Скажи себе «молодец». Что ты сделал сегодня хорошо?\n"
        "_Даже маленькая победа заслуживает признания._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_praise")
    )

async def got_praise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_praise"] = update.message.text
    await ask_highlights(update.message)
    return E_HIGHLIGHTS

async def skip_praise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["e_praise"] = ""
    await ask_highlights(q.message)
    return E_HIGHLIGHTS

async def ask_highlights(message):
    await message.reply_text(
        "✨ *Highlights of the day*\n\n"
        "Что сегодня заставило тебя улыбнуться?\n"
        "_Или какой инсайт пришёл?_",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_highlights")
    )

async def got_highlights(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_highlights"] = update.message.text
    await ask_plan_a(update.message)
    return E_A

async def skip_highlights(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["e_highlights"] = ""
    await ask_plan_a(q.message)
    return E_A

async def ask_plan_a(message):
    await message.reply_text(
        "📋 *Plans for tomorrow*\n\n"
        "Начнём с главного.\n\n"
        "🅰️ *A-план* — самое важное, must do.\n"
        "_Одно дело. Если сделаешь только его — завтра прожит не зря._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_a")
    )

async def got_a(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_a"] = update.message.text
    await ask_plan_b1(update.message)
    return E_B1

async def skip_a(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["e_a"] = ""
    await ask_plan_b1(q.message)
    return E_B1

async def ask_plan_b1(message):
    await message.reply_text(
        "🅱️ *B-план №1* — важно, should do.\n"
        "_Второй приоритет._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_b1")
    )

async def got_b1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_b1"] = update.message.text
    await ask_plan_b2(update.message)
    return E_B2

async def skip_b1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["e_b1"] = ""
    await ask_plan_b2(q.message)
    return E_B2

async def ask_plan_b2(message):
    await message.reply_text(
        "🅱️ *B-план №2* — важно, should do.\n"
        "_Третий приоритет._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_b2")
    )

async def got_b2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_b2"] = update.message.text
    await ask_plan_c1(update.message)
    return E_C1

async def skip_b2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["e_b2"] = ""
    await ask_plan_c1(q.message)
    return E_C1

async def ask_plan_c1(message):
    await message.reply_text(
        "🅲 *C-планы* — nice to have, если останется время.\n\n"
        "*C-план №1:*",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_c_all")
    )

async def got_c1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_c1"] = update.message.text
    await update.message.reply_text("*C-план №2:*", parse_mode="Markdown", reply_markup=skip_kb("skip_c_all"))
    return E_C2

async def got_c2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_c2"] = update.message.text
    await update.message.reply_text("*C-план №3:*", parse_mode="Markdown", reply_markup=skip_kb("skip_c_all"))
    return E_C3

async def got_c3(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_c3"] = update.message.text
    await finish_evening(update.message, update.effective_user.id, ctx)
    return ConversationHandler.END

async def skip_c_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.setdefault("e_c1", "")
    ctx.user_data.setdefault("e_c2", "")
    ctx.user_data.setdefault("e_c3", "")
    await finish_evening(q.message, q.from_user.id, ctx)
    return ConversationHandler.END

async def finish_evening(message, uid, ctx):
    data = {
        "achievements": ctx.user_data.get("e_ach", ""),
        "praise":       ctx.user_data.get("e_praise", ""),
        "highlights":   ctx.user_data.get("e_highlights", ""),
        "plan_a":       ctx.user_data.get("e_a", ""),
        "plan_b1":      ctx.user_data.get("e_b1", ""),
        "plan_b2":      ctx.user_data.get("e_b2", ""),
        "plan_c1":      ctx.user_data.get("e_c1", ""),
        "plan_c2":      ctx.user_data.get("e_c2", ""),
        "plan_c3":      ctx.user_data.get("e_c3", ""),
    }
    save_diary(uid, "evening", data)
    add_streak(uid)
    streak = calc_streak(uid)

    # Build plans summary
    plans = ""
    if data["plan_a"]:  plans += f"\n🅰️ *A:* {data['plan_a']}"
    if data["plan_b1"]: plans += f"\n🅱️ *B:* {data['plan_b1']}"
    if data["plan_b2"]: plans += f"\n🅱️ *B:* {data['plan_b2']}"
    if data["plan_c1"]: plans += f"\n🅲 *C:* {data['plan_c1']}"
    if data["plan_c2"]: plans += f"\n🅲 *C:* {data['plan_c2']}"
    if data["plan_c3"]: plans += f"\n🅲 *C:* {data['plan_c3']}"

    await message.reply_text(
        f"✅ *День закрыт!*\n\n"
        f"🔥 Стрик: *{streak} {'день' if streak==1 else 'дня' if streak<5 else 'дней'}* подряд\n\n"
        f"{'📋 *Планы на завтра:*' + plans if plans else ''}\n\n"
        f"_Well done. See you tomorrow, {USER_NAME}_ 👋",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── COACH ─────────────────────────────────────────────────────────────────
async def coach_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text(
        "🤖 *Коуч*\n\nЧто происходит? Пиши — отвечу коротко и по делу.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Не могу начать", callback_data="c_start")],
            [InlineKeyboardButton("😵 Отвлёкся", callback_data="c_dist")],
            [InlineKeyboardButton("❓ Что делать?", callback_data="c_next")],
            [InlineKeyboardButton("💡 Быстрый совет", callback_data="c_tip")],
            [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")],
        ])
    )
    ctx.user_data["coach_mode"] = True

COACH_PROMPTS = {
    "c_start": "Не могу начать задачу — застрял и откладываю",
    "c_dist":  "Только что отвлёкся, помоги вернуться к задаче",
    "c_next":  "Не знаю что делать дальше — подскажи следующий шаг",
    "c_tip":   "Дай один быстрый совет по продуктивности для СДВГ",
}

async def coach_quick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    prompt = COACH_PROMPTS.get(q.data, "")
    await send_coach(q.message, prompt)

async def send_coach(message, text):
    if not ANTHROPIC_KEY:
        await message.reply_text(
            "⚠️ Коуч не настроен.\nДобавь ANTHROPIC_KEY в переменные Railway.",
            reply_markup=main_menu()
        )
        return
    thinking = await message.reply_text("🤖 думаю...")
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=f"Ты прямой коуч для {USER_NAME} у которого СДВГ. Кратко, по делу, одно действие. Максимум 2-3 предложения. Отвечай на русском.",
            messages=[{"role": "user", "content": text}]
        )
        await thinking.edit_text(
            f"🤖 {resp.content[0].text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")]
            ])
        )
    except Exception as e:
        await thinking.edit_text(f"Ошибка: {e}")

async def streak_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    s = calc_streak(uid)
    await q.message.reply_text(
        f"🔥 *Твой стрик: {s} {'день' if s==1 else 'дня' if s<5 else 'дней'}*\n\n"
        f"{'Продолжай! Каждый день считается.' if s>0 else 'Заполни утро или вечер — и стрик пойдёт.'}",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def go_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Главное меню 👇", reply_markup=main_menu())

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("coach_mode"):
        await send_coach(update.message, update.message.text)
    else:
        await update.message.reply_text("Выбери блок 👇", reply_markup=main_menu())

# ── NOTIFICATIONS ──────────────────────────────────────────────────────────
async def morning_notif(app, uid):
    motivation = MOTIVATIONS[datetime.now().weekday() % len(MOTIVATIONS)]
    # Show yesterday's A plan if exists
    from datetime import timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    ev = get_diary(uid, "evening", yesterday)
    plan_text = f"\n\n🎯 Твой A-план на сегодня: *{ev['plan_a']}*" if ev.get("plan_a") else ""

    await app.bot.send_message(
        uid,
        f"☀️ *Доброе утро, {USER_NAME}!*\n\n"
        f"_{motivation}_{plan_text}\n\n"
        f"Начнём день? 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def evening_notif(app, uid):
    await app.bot.send_message(
        uid,
        f"🌙 *Привет, {USER_NAME}!*\n\n"
        f"День заканчивается. Время закрыть его и поставить планы на завтра.\n\n"
        f"5 минут — и голова свободна 👇",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Morning conversation
    morning_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(morning_start, pattern="^go_morning$")],
        states={
            M_EXERCISE: [
                CallbackQueryHandler(warmup_start,  pattern="^warmup_start$"),
                CallbackQueryHandler(skip_warmup,   pattern="^skip_warmup$"),
            ],
            M_FOCUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_focus),
                CallbackQueryHandler(skip_focus, pattern="^skip_focus$"),
            ],
            M_WRITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_writing),
                CallbackQueryHandler(skip_writing, pattern="^skip_writing$"),
            ],
            M_GRATITUDE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_gratitude),
                CallbackQueryHandler(skip_gratitude, pattern="^skip_gratitude$"),
            ],
            M_CHILD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_child),
                CallbackQueryHandler(skip_child, pattern="^skip_child$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    # Evening conversation
    evening_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(evening_start, pattern="^go_evening$")],
        states={
            E_ACH:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_ach),        CallbackQueryHandler(skip_ach,       pattern="^skip_ach$")],
            E_PRAISE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_praise),     CallbackQueryHandler(skip_praise,    pattern="^skip_praise$")],
            E_HIGHLIGHTS:[MessageHandler(filters.TEXT & ~filters.COMMAND, got_highlights), CallbackQueryHandler(skip_highlights,pattern="^skip_highlights$")],
            E_A:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_a),          CallbackQueryHandler(skip_a,         pattern="^skip_a$")],
            E_B1:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_b1),         CallbackQueryHandler(skip_b1,        pattern="^skip_b1$")],
            E_B2:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_b2),         CallbackQueryHandler(skip_b2,        pattern="^skip_b2$")],
            E_C1:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_c1),         CallbackQueryHandler(skip_c_all,     pattern="^skip_c_all$")],
            E_C2:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_c2),         CallbackQueryHandler(skip_c_all,     pattern="^skip_c_all$")],
            E_C3:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_c3),         CallbackQueryHandler(skip_c_all,     pattern="^skip_c_all$")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(morning_conv)
    app.add_handler(evening_conv)
    app.add_handler(CallbackQueryHandler(coach_menu,   pattern="^go_coach$"))
    app.add_handler(CallbackQueryHandler(coach_quick,  pattern="^c_(start|dist|next|tip)$"))
    app.add_handler(CallbackQueryHandler(streak_info,  pattern="^go_streak$"))
    app.add_handler(CallbackQueryHandler(go_menu,      pattern="^go_menu$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Scheduler — раскомментируй и замени YOUR_USER_ID на свой Telegram ID
    scheduler = AsyncIOScheduler()
    # YOUR_USER_ID = 123456789
    # scheduler.add_job(morning_notif, 'cron', hour=8,  minute=0, args=[app, YOUR_USER_ID])
    # scheduler.add_job(evening_notif, 'cron', hour=21, minute=0, args=[app, YOUR_USER_ID])
    scheduler.start()

    print(f"✅ ADHD бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
