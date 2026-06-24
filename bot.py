"""
ADHD Focus Bot v4
- Персонализация: имя + пол
- Русский язык по умолчанию
- Утро: разминка, фокус, задачи A/B/C, free writing, благодарность, внутренний ребёнок
- Вечер: достижения, похвала, highlights, планы A/B/C, AI-анализ дня
- Навыки СДВГ из тренинга (ежедневный совет)
- AI: коуч + утренняя мотивация + вечерний анализ
- Уведомления: 9:00 и 21:00 по Тбилиси (UTC+4)
"""

import os, json, sqlite3, asyncio, random
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ── CONFIG ─────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY", "")
# Укажи свой Telegram ID для уведомлений (узнай через @userinfobot)
NOTIFY_USER_ID = int(os.getenv("NOTIFY_USER_ID", "0"))
# Тбилиси UTC+4: 9:00=5 UTC, 13:00=9 UTC, 21:00=17 UTC
MORNING_HOUR_UTC = int(os.getenv("MORNING_HOUR_UTC", "5"))   # 9:00 Тбилиси
MIDDAY_HOUR_UTC  = int(os.getenv("MIDDAY_HOUR_UTC",  "9"))   # 13:00 Тбилиси
EVENING_HOUR_UTC = int(os.getenv("EVENING_HOUR_UTC", "17"))  # 21:00 Тбилиси

# ── CONVERSATION STATES ────────────────────────────────────────────────────
(ONBOARD_NAME, ONBOARD_GENDER,
 M_EXERCISE, M_FOCUS, M_B1, M_B2, M_C1, M_C2, M_C3,
 M_WRITING, M_GRATITUDE, M_CHILD,
 E_ACH, E_PRAISE, E_HIGHLIGHTS,
 E_A, E_B1, E_B2, E_C1, E_C2, E_C3) = range(21)

# ── ADHD SKILLS FROM TRAINING ──────────────────────────────────────────────
SKILLS = [
    {
        "name": "📋 Список дел и календарь",
        "desc": "Записывай ВСЁ в список дел — даже очевидное.",
        "tip": "Нет такого дела, которое ты не мог(ла) бы забыть. Список дел разгружает оперативную память мозга. Календарь — для встреч с конкретным временем. Список дел — для всего остального."
    },
    {
        "name": "🔤 Приоритеты A, B, C",
        "desc": "1 задача A (must), 2 задачи B (should), 3 задачи C (nice to have).",
        "tip": "Сначала A, потом B, потом C. Мозг с СДВГ любит брать лёгкое первым — это ловушка. Сделай A даже если хочется пропустить. Если сделал(а) только A — день прожит не зря."
    },
    {
        "name": "🛑 Навык СТОП",
        "desc": "С-Стой. Т-Только шаг назад. О-Осмотрись. П-Попытайся действовать осознанно.",
        "tip": "Используй когда: отвлёкся(ась), застрял(а), чувствуешь импульс сделать что-то необдуманное, или просто залип(ла) в телефоне. Цель — не изменить поведение, а ЗАМЕТИТЬ что происходит."
    },
    {
        "name": "👣 Первый неподавляющий шаг",
        "desc": "Не разбивай задачу на много шагов — найди только ПЕРВЫЙ.",
        "tip": "Первый шаг должен: завершаться за один день и не вызывать желания отложить. Если хочется отложить — шаг слишком большой, уменьши его. Начало — самое сложное. После старта обычно легче."
    },
    {
        "name": "⚡ Активация",
        "desc": "Не жди мотивации — запускай себя действием.",
        "tip": "Мотивация не придёт сама. Физическая активность (встать, потянуться, 5 приседаний) или сильные ощущения (холодная вода, громкая музыка) помогают запустить мозг. Сначала действие — потом мотивация."
    },
    {
        "name": "😴 Планирование отдыха",
        "desc": "Отдых нужно планировать намеренно — сам он не случится.",
        "tip": "Перерывы 5-10 минут каждые 25-30 минут. Отдыхай ДО того как перегорел(а) — потом уже поздно. Гиперфокус — это не суперсила, он истощает. Составь список отдыха заранее, чтобы не было паралича выбора."
    },
    {
        "name": "⚓ Бросить якорь",
        "desc": "Техника для эмоционального шторма.",
        "tip": "1. Замети шторм внутри (мысли, чувства, ощущения). 2. Вдави ноги в пол, выпрями спину, сожми пальцы. 3. Найди 5 предметов вокруг, услышь 3-4 звука. Якорь не уберёт шторм — но удержит тебя в нём."
    },
    {
        "name": "⏱ Работа по таймеру",
        "desc": "Чередуй работу и отдых по таймеру.",
        "tip": "Выясни сколько минут ты можешь работать над скучной задачей без остановки. Поставь таймер на это время. Работай только до сигнала. Потом отдых. Это профилактирует гиперфокус и истощение."
    },
    {
        "name": "📝 Бумажка гениальных мыслей",
        "desc": "Записывай отвлекающие мысли, но не выполняй их сразу.",
        "tip": "Когда работаешь и приходит отвлекающая мысль — запиши её, скажи себе 'займусь позже' и вернись к задаче. В конце дня реши: это правда важно, или просто казалось привлекательным?"
    },
    {
        "name": "💧 Холодная вода",
        "desc": "Быстрое снижение перевозбуждения через температуру.",
        "tip": "Умойся холодной водой или плесни на лицо — это активирует рефлекс ныряльщика и замедляет сердечный ритм. Помогает при сильных эмоциях, перевозбуждении и когда нужно быстро успокоиться."
    },
    {
        "name": "🌬 Дыхание",
        "desc": "Выдох длиннее вдоха успокаивает нервную систему.",
        "tip": "Вдох 4 счёта — выдох 8 счётов. Или квадрат: вдох 4, задержка 4, выдох 4, задержка 4. Замедленное дыхание активирует парасимпатическую систему. Используй перед сном, при тревоге, для переключения."
    },
    {
        "name": "🏠 Изменение среды",
        "desc": "Убери отвлекающие факторы — не полагайся на силу воли.",
        "tip": "Телефон вне поля зрения. Лишние вкладки закрыты. Стол свободен. Наушники надеты. Каждый отвлекающий фактор требует своей стратегии. Среда влияет на фокус сильнее, чем сила воли."
    },
    {
        "name": "🤲 Готовность и полуулыбка",
        "desc": "Техника работы с сопротивлением к задаче.",
        "tip": "Почувствуй опору под ногами. Расслабь лицо от лба вниз. Мягко приподними уголки губ — это улыбка себе, не на камеру. Ладони вверх. Приступи к задаче. Когда заметишь сопротивление — повтори."
    },
]

MOTIVATIONS_M = [
    "Сегодня хороший день чтобы сделать то, что важно.",
    "Один шаг — и ты уже в движении.",
    "Только одно главное. Остальное подождёт.",
    "Твой мозг нестандартный. Это сила.",
    "Чуть больше чем вчера — этого достаточно.",
    "Ты проснулся. Уже хорошо. Дальше легче.",
    "Сделай одно дело. Потом ещё одно.",
]

MOTIVATIONS_F = [
    "Сегодня хороший день чтобы сделать то, что важно.",
    "Один шаг — и ты уже в движении.",
    "Только одно главное. Остальное подождёт.",
    "Твой мозг нестандартный. Это сила.",
    "Чуть больше чем вчера — этого достаточно.",
    "Ты проснулась. Уже хорошо. Дальше легче.",
    "Сделай одно дело. Потом ещё одно.",
]

WARMUP = [
    ("Шея — повороты 🔄", "Медленно влево-вправо, 5 раз"),
    ("Плечи — круги 🔄", "Вперёд 5 раз, назад 5 раз"),
    ("Запястья 🤲", "Покрути кулаки в обе стороны"),
    ("Поясница ↔️", "Наклоны влево-вправо"),
    ("Колени 🦵", "Поднимай колени стоя, по 5 раз"),
    ("Голеностоп 🦶", "Вращение каждой ногой по 10 сек"),
]

# ── DATABASE ───────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT DEFAULT '',
        gender TEXT DEFAULT 'M',
        focus TEXT DEFAULT '',
        streak TEXT DEFAULT '[]',
        last_skill_date TEXT DEFAULT '',
        buddy_name TEXT DEFAULT ''
    )""")
    # Добавить колонку buddy_name если её нет (для старых БД)
    try:
        c.execute("ALTER TABLE users ADD COLUMN buddy_name TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS diary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, date TEXT, block TEXT, data TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, text TEXT,
        priority TEXT DEFAULT 'C',
        done INTEGER DEFAULT 0,
        created TEXT
    )""")
    conn.commit(); conn.close()

def get_all_users():
    """Вернуть всех зарегистрированных пользователей (у кого есть имя)."""
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE name != ''")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_user(uid):
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users(user_id) VALUES(?)", (uid,))
        conn.commit()
        c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
        row = c.fetchone()
    conn.close()
    cols = ["user_id","name","gender","focus","streak","last_skill_date","buddy_name"]
    return dict(zip(cols, row))

def update_user(uid, **kwargs):
    conn = sqlite3.connect("adhd.db")
    c = conn.cursor()
    for k, v in kwargs.items():
        c.execute(f"UPDATE users SET {k}=? WHERE user_id=?", (v, uid))
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
    user = get_user(uid)
    streak = json.loads(user["streak"])
    today = date.today().isoformat()
    if today not in streak:
        streak.append(today)
        update_user(uid, streak=json.dumps(streak))

def calc_streak(uid):
    user = get_user(uid)
    streak = sorted(set(json.loads(user["streak"])), reverse=True)
    if not streak: return 0
    count = 0
    cur = date.today()
    for i, d in enumerate(streak):
        if (cur - date.fromisoformat(d)).days == i: count += 1
        else: break
    return count

# ── HELPERS ────────────────────────────────────────────────────────────────
def g(gender, male, female):
    """Вернуть нужную форму слова в зависимости от пола."""
    return female if gender == 'F' else male

def skip_kb(cb):
    return InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить →", callback_data=cb)]])

MINIAPP_URL = "https://adhd-miniapp.vercel.app"

def main_menu():
    from telegram import WebAppInfo
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Список Навыков", web_app=WebAppInfo(url=MINIAPP_URL))],
        [InlineKeyboardButton("☀️ Утро", callback_data="go_morning"),
         InlineKeyboardButton("🌙 Вечер", callback_data="go_evening")],
        [InlineKeyboardButton("🤖 Коуч", callback_data="go_coach"),
         InlineKeyboardButton("🧠 Навык дня", callback_data="go_skill")],
        [InlineKeyboardButton("👥 Бадди", callback_data="go_buddy"),
         InlineKeyboardButton("🔥 Подряд", callback_data="go_streak")],
    ])

def today_str():
    return datetime.now().strftime("%d %B %Y")

def get_daily_skill(uid):
    """Возвращает навык дня — меняется каждый день."""
    today = date.today().isoformat()
    idx = hash(today + str(uid)) % len(SKILLS)
    return SKILLS[idx]

# ── ONBOARDING ─────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    init_db()
    user = get_user(uid)

    # Если уже зарегистрирован — показать меню
    if user["name"]:
        hour = datetime.now().hour
        if hour < 12: block = "утро — начнём день"
        elif hour < 18: block = "день — работаем"
        else: block = "вечер — подводим итоги"
        await update.message.reply_text(
            f"С возвращением, {user['name']}! Сейчас {block} 👇",
            reply_markup=main_menu()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Привет! Я твой ADHD-помощник.\n\n"
        "Помогу начать день, не потеряться в задачах и закрыть вечер.\n\n"
        "Как тебя зовут?"
    )
    return ONBOARD_NAME

async def got_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) > 30:
        await update.message.reply_text("Имя слишком длинное, напиши покороче:")
        return ONBOARD_NAME
    ctx.user_data["onboard_name"] = name
    await update.message.reply_text(
        f"Отлично, {name}! Один вопрос для персонализации 👇",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Мужской", callback_data="gender_M"),
            InlineKeyboardButton("Женский", callback_data="gender_F"),
        ]])
    )
    return ONBOARD_GENDER

async def got_gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    name = ctx.user_data.get("onboard_name", "")
    gender = "M" if q.data == "gender_M" else "F"
    update_user(uid, name=name, gender=gender)

    greeting = g(gender, f"Готово, {name}! Поехали 🚀", f"Готово, {name}! Поехали 🚀")
    await q.message.reply_text(
        f"{greeting}\n\n"
        f"Я буду присылать напоминания:\n"
        f"☀️ Утром в 9:00 — настройка на день\n"
        f"🌙 Вечером в 21:00 — подведение итогов\n\n"
        f"Выбирай что хочешь сделать 👇",
        reply_markup=main_menu()
    )
    return ConversationHandler.END

# ── MORNING FLOW ───────────────────────────────────────────────────────────
async def morning_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    name = user["name"]
    gender = user["gender"]
    motiv = random.choice(MOTIVATIONS_F if gender == 'F' else MOTIVATIONS_M)

    # Показать вчерашние планы если есть
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    ev = get_diary(uid, "evening", yesterday)
    plans_text = ""
    if ev.get("plan_a"):
        plans_text = f"\n\n⭐ Помни — сегодня тебе важно:\n🅰️ {ev['plan_a']}"
        if ev.get("plan_b1"): plans_text += f"\n🅱️ {ev['plan_b1']}"
        if ev.get("plan_b2"): plans_text += f"\n🅱️ {ev['plan_b2']}"

    skill = get_daily_skill(uid)

    await q.message.reply_text(
        f"☀️ *Good Morning, {name}!*\n"
        f"_{today_str()}_\n\n"
        f"_{motiv}_{plans_text}\n\n"
        f"💡 *Навык дня:* {skill['name']}\n"
        f"_{skill['desc']}_",
        parse_mode="Markdown"
    )
    await asyncio.sleep(0.5)
    await q.message.reply_text(
        "🏃 *2 минуты утренней разминки*\n\n"
        "Тело нужно разбудить — это важно для мозга с СДВГ.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ Начать разминку", callback_data="warmup_go")],
            [InlineKeyboardButton("Пропустить →", callback_data="skip_warmup")],
        ])
    )
    return M_EXERCISE

async def warmup_go(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    msg = await q.message.reply_text("Начинаем! 🏃")
    for i, (name, hint) in enumerate(WARMUP):
        dots = "🟡"*(i+1) + "⚪"*(len(WARMUP)-i-1)
        await msg.edit_text(f"{dots}\n\n*{name}*\n_{hint}_\n\n⏱ 20 секунд...", parse_mode="Markdown")
        await asyncio.sleep(20)
    await msg.edit_text("✅ *Тело проснулось!* Теперь — фокус.", parse_mode="Markdown")
    await ask_morning_focus(q.message)
    return M_FOCUS

async def skip_warmup(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await ask_morning_focus(q.message)
    return M_FOCUS

async def ask_morning_focus(message):
    await message.reply_text(
        "🎯 *Today's focus — задача A*\n\n"
        "Одно самое важное дело на сегодня.\n"
        "_Если сделаешь только его — день прожит не зря._",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_m_focus")
    )

async def got_m_focus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_focus"] = update.message.text
    await ask_m_b1(update.message)
    return M_B1

async def skip_m_focus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["m_focus"] = ""
    await ask_m_b1(q.message)
    return M_B1

async def ask_m_b1(message):
    await message.reply_text(
        "🅱️ *Задача B1* — важно, желательно сегодня:",
        parse_mode="Markdown",
        reply_markup=skip_kb("skip_m_b1")
    )

async def got_m_b1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_b1"] = update.message.text
    await ask_m_b2(update.message); return M_B2

async def skip_m_b1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["m_b1"] = ""
    await ask_m_b2(q.message); return M_B2

async def ask_m_b2(message):
    await message.reply_text("🅱️ *Задача B2:*", parse_mode="Markdown", reply_markup=skip_kb("skip_m_b2"))

async def got_m_b2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_b2"] = update.message.text
    await ask_m_c1(update.message); return M_C1

async def skip_m_b2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["m_b2"] = ""; await ask_m_c1(q.message); return M_C1

async def ask_m_c1(message):
    await message.reply_text(
        "🅲 *Задачи C* — если останется время:\n\nC1:",
        parse_mode="Markdown", reply_markup=skip_kb("skip_m_c_all")
    )

async def got_m_c1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_c1"] = update.message.text
    await update.message.reply_text("🅲 *C2:*", parse_mode="Markdown", reply_markup=skip_kb("skip_m_c_all"))
    return M_C2

async def got_m_c2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_c2"] = update.message.text
    await update.message.reply_text("🅲 *C3:*", parse_mode="Markdown", reply_markup=skip_kb("skip_m_c_all"))
    return M_C3

async def got_m_c3(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_c3"] = update.message.text
    await ask_writing(update.message); return M_WRITING

async def skip_m_c_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data.setdefault("m_c1", "")
    ctx.user_data.setdefault("m_c2", "")
    ctx.user_data.setdefault("m_c3", "")
    await ask_writing(q.message); return M_WRITING

async def ask_writing(message):
    await message.reply_text(
        "📝 *Free writing*\n\nВсё что есть в голове — без фильтра. Мысли, сны, тревоги, идеи.",
        parse_mode="Markdown", reply_markup=skip_kb("skip_m_writing")
    )

async def got_writing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_writing"] = update.message.text
    await ask_gratitude(update.message); return M_GRATITUDE

async def skip_m_writing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["m_writing"] = ""; await ask_gratitude(q.message); return M_GRATITUDE

async def ask_gratitude(message):
    await message.reply_text(
        "🙏 *Gratitude*\n\nЗа что благодарен(а) сегодня? Большое или маленькое — всё считается.",
        parse_mode="Markdown", reply_markup=skip_kb("skip_m_gratitude")
    )

async def got_gratitude(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_gratitude"] = update.message.text
    await ask_child(update.message); return M_CHILD

async def skip_m_gratitude(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["m_gratitude"] = ""; await ask_child(q.message); return M_CHILD

async def ask_child(message):
    await message.reply_text(
        "💛 *Inner child*\n\nСкажи себе что-то доброе. Как бы ты поговорил(а) с лучшим другом?",
        parse_mode="Markdown", reply_markup=skip_kb("skip_m_child")
    )

async def got_child(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["m_child"] = update.message.text
    await finish_morning(update.message, update.effective_user.id, ctx)
    return ConversationHandler.END

async def skip_m_child(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["m_child"] = ""
    await finish_morning(q.message, q.from_user.id, ctx)
    return ConversationHandler.END

async def finish_morning(message, uid, ctx):
    user = get_user(uid)
    focus = ctx.user_data.get("m_focus", "")
    if focus: update_user(uid, focus=focus)

    save_diary(uid, "morning", {
        "focus":    focus,
        "b1":       ctx.user_data.get("m_b1", ""),
        "b2":       ctx.user_data.get("m_b2", ""),
        "c1":       ctx.user_data.get("m_c1", ""),
        "c2":       ctx.user_data.get("m_c2", ""),
        "c3":       ctx.user_data.get("m_c3", ""),
        "writing":  ctx.user_data.get("m_writing", ""),
        "gratitude":ctx.user_data.get("m_gratitude", ""),
        "child":    ctx.user_data.get("m_child", ""),
    })

    tasks_text = ""
    if focus:       tasks_text += f"\n🅰️ {focus}"
    if ctx.user_data.get("m_b1"): tasks_text += f"\n🅱️ {ctx.user_data['m_b1']}"
    if ctx.user_data.get("m_b2"): tasks_text += f"\n🅱️ {ctx.user_data['m_b2']}"

    # AI мотивация если есть ключ
    ai_msg = ""
    if ANTHROPIC_KEY and focus:
        ai_msg = await ai_morning_boost(user["name"], user["gender"], focus)
        if ai_msg: ai_msg = f"\n\n🤖 _{ai_msg}_"

    await message.reply_text(
        f"✅ *Утро {g(user['gender'], 'записано', 'записана')}!*\n"
        f"{tasks_text if tasks_text else '_(задачи не заданы)_'}"
        f"{ai_msg}\n\n"
        f"{g(user['gender'], 'Вперёд', 'Вперёд')}, {user['name']}! 💪",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── EVENING FLOW ───────────────────────────────────────────────────────────
async def evening_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    streak = calc_streak(uid)

    morning = get_diary(uid, "morning")
    focus_recap = f"\n🎯 Фокус был: _{morning['focus']}_" if morning.get("focus") else ""

    await q.message.reply_text(
        f"🌙 *It was a nice day, {user['name']}!*\n"
        f"_{today_str()}_{focus_recap}\n\n"
        f"🔥 Стрик: *{streak} {'день' if streak==1 else 'дня' if streak<5 else 'дней'}*\n\n"
        f"Давай закроем этот день.",
        parse_mode="Markdown"
    )
    await asyncio.sleep(0.5)
    await q.message.reply_text(
        "⭐ *Achievements of the day*\n\nЧего достиг(ла) сегодня? Большое или маленькое — всё считается.",
        parse_mode="Markdown", reply_markup=skip_kb("skip_e_ach")
    )
    return E_ACH

async def got_e_ach(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_ach"] = update.message.text
    await ask_praise(update.message); return E_PRAISE

async def skip_e_ach(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["e_ach"] = ""; await ask_praise(q.message); return E_PRAISE

async def ask_praise(message):
    await message.reply_text(
        "🎉 *Praise yourself*\n\n"
        "Скажи себе 'молодец'. Что сегодня сделал(а) хорошо?\n"
        "_Даже маленькая победа заслуживает признания._",
        parse_mode="Markdown", reply_markup=skip_kb("skip_e_praise")
    )

async def got_e_praise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_praise"] = update.message.text
    await ask_highlights(update.message); return E_HIGHLIGHTS

async def skip_e_praise(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["e_praise"] = ""; await ask_highlights(q.message); return E_HIGHLIGHTS

async def ask_highlights(message):
    await message.reply_text(
        "✨ *Highlights of the day*\n\nЧто сегодня заставило улыбнуться? Или какой инсайт пришёл?",
        parse_mode="Markdown", reply_markup=skip_kb("skip_e_highlights")
    )

async def got_e_highlights(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_highlights"] = update.message.text
    await ask_plan_a(update.message); return E_A

async def skip_e_highlights(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["e_highlights"] = ""; await ask_plan_a(q.message); return E_A

async def ask_plan_a(message):
    await message.reply_text(
        "📋 *Plans for tomorrow — задача A*\n\n"
        "Самое важное на завтра. Must do.\n"
        "_Утром увидишь первым._",
        parse_mode="Markdown", reply_markup=skip_kb("skip_e_a")
    )

async def got_e_a(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_a"] = update.message.text
    await update.message.reply_text("🅱️ *Задача B1 на завтра:*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_b1"))
    return E_B1

async def skip_e_a(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["e_a"] = ""
    await q.message.reply_text("🅱️ *Задача B1 на завтра:*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_b1"))
    return E_B1

async def got_e_b1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_b1"] = update.message.text
    await update.message.reply_text("🅱️ *Задача B2:*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_b2"))
    return E_B2

async def skip_e_b1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["e_b1"] = ""
    await q.message.reply_text("🅱️ *Задача B2:*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_b2"))
    return E_B2

async def got_e_b2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_b2"] = update.message.text
    await ask_e_c1(update.message); return E_C1

async def skip_e_b2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["e_b2"] = ""; await ask_e_c1(q.message); return E_C1

async def ask_e_c1(message):
    await message.reply_text("🅲 *Задача C1 (nice to have):*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_c_all"))

async def got_e_c1(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_c1"] = update.message.text
    await update.message.reply_text("🅲 *C2:*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_c_all"))
    return E_C2

async def got_e_c2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_c2"] = update.message.text
    await update.message.reply_text("🅲 *C3:*", parse_mode="Markdown", reply_markup=skip_kb("skip_e_c_all"))
    return E_C3

async def got_e_c3(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["e_c3"] = update.message.text
    await finish_evening(update.message, update.effective_user.id, ctx)
    return ConversationHandler.END

async def skip_e_c_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data.setdefault("e_c1", "")
    ctx.user_data.setdefault("e_c2", "")
    ctx.user_data.setdefault("e_c3", "")
    await finish_evening(q.message, q.from_user.id, ctx)
    return ConversationHandler.END

async def finish_evening(message, uid, ctx):
    user = get_user(uid)
    data = {k: ctx.user_data.get(k, "") for k in
            ["e_ach","e_praise","e_highlights","e_a","e_b1","e_b2","e_c1","e_c2","e_c3"]}
    save_diary(uid, "evening", data)
    add_streak(uid)
    streak = calc_streak(uid)

    plans = ""
    if data["e_a"]:  plans += f"\n🅰️ {data['e_a']}"
    if data["e_b1"]: plans += f"\n🅱️ {data['e_b1']}"
    if data["e_b2"]: plans += f"\n🅱️ {data['e_b2']}"
    if data["e_c1"]: plans += f"\n🅲 {data['e_c1']}"

    # AI анализ дня
    ai_analysis = ""
    if ANTHROPIC_KEY:
        morning = get_diary(uid, "morning")
        ai_analysis = await ai_day_analysis(user["name"], user["gender"], morning, data)
        if ai_analysis: ai_analysis = f"\n\n🤖 *Анализ дня:*\n_{ai_analysis}_"

    await message.reply_text(
        f"✅ *День закрыт!*\n\n"
        f"🔥 Стрик: *{streak} {'день' if streak==1 else 'дня' if streak<5 else 'дней'}*\n"
        f"{'📋 *Планы на завтра:*' + plans if plans else ''}"
        f"{ai_analysis}\n\n"
        f"_Well done. See you tomorrow, {user['name']}_ 👋",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── AI FUNCTIONS ───────────────────────────────────────────────────────────
async def ai_morning_boost(name, gender, focus):
    """Короткая AI-мотивация утром на основе фокуса."""
    if not ANTHROPIC_KEY: return ""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_KEY)
        gender_hint = "женского рода" if gender == 'F' else "мужского рода"
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            system=f"Ты поддерживающий коуч. Пользователь: {name}, {gender_hint}, СДВГ. Пиши по-русски, 1-2 предложения, конкретно и тепло.",
            messages=[{"role":"user","content":f"Моя главная задача сегодня: {focus}. Дай короткий мотивирующий посыл."}]
        )
        return resp.content[0].text.strip()
    except: return ""

async def ai_day_analysis(name, gender, morning_data, evening_data):
    """AI-анализ прожитого дня вечером."""
    if not ANTHROPIC_KEY: return ""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_KEY)
        gender_hint = "женского рода" if gender == 'F' else "мужского рода"
        context = f"Утренний фокус: {morning_data.get('focus','не задан')}\n"
        if evening_data.get("e_ach"): context += f"Достижения: {evening_data['e_ach']}\n"
        if evening_data.get("e_highlights"): context += f"Highlights: {evening_data['e_highlights']}\n"
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=f"Ты коуч для {name} ({gender_hint}), у которой/которого СДВГ. Анализируй день кратко и тепло. 2-3 предложения. Отмечай прогресс и дай один конкретный совет на завтра. Пиши по-русски.",
            messages=[{"role":"user","content":f"Вот мой день:\n{context}\nДай короткий анализ."}]
        )
        return resp.content[0].text.strip()
    except: return ""

async def send_coach(message, text, uid):
    """Отправить запрос AI-коучу."""
    if not ANTHROPIC_KEY:
        await message.reply_text("⚠️ AI-коуч не настроен. Добавь ANTHROPIC_KEY в переменные Railway.", reply_markup=main_menu())
        return
    user = get_user(uid)
    gender_hint = "женского рода" if user["gender"] == 'F' else "мужского рода"
    thinking = await message.reply_text("🤖 думаю...")
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=ANTHROPIC_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=f"Ты прямой коуч для {user['name']} ({gender_hint}), СДВГ. Кратко, по делу, одно действие. Максимум 2-3 предложения. Используй методы из тренинга: ABC-приоритеты, первый неподавляющий шаг, активация, СТОП. Пиши по-русски.",
            messages=[{"role":"user","content":text}]
        )
        await thinking.edit_text(
            f"🤖 {resp.content[0].text}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="go_menu")]])
        )
    except Exception as e:
        await thinking.edit_text(f"Ошибка: {e}")

# ── COACH MENU ─────────────────────────────────────────────────────────────
COACH_PROMPTS = {
    "c_start":    "Не могу начать задачу — застрял(а) и откладываю",
    "c_dist":     "Только что отвлёкся(ась), помоги вернуться к задаче прямо сейчас",
    "c_next":     "Не знаю что делать дальше — подскажи следующий конкретный шаг",
    "c_procr":    "Прокрастинирую и понимаю это — что делать прямо сейчас?",
    "c_overload": "Слишком много всего, не знаю с чего начать — помоги расставить приоритеты",
    "c_tip":      "Дай один быстрый совет из тренинга навыков СДВГ",
}

async def coach_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.message.reply_text(
        "🤖 *Коуч*\n\nЧто происходит? Пиши сам(а) или выбери быструю кнопку:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Не могу начать", callback_data="c_start")],
            [InlineKeyboardButton("😵 Отвлёкся(ась)", callback_data="c_dist")],
            [InlineKeyboardButton("❓ Что дальше?", callback_data="c_next")],
            [InlineKeyboardButton("😩 Прокрастинирую", callback_data="c_procr")],
            [InlineKeyboardButton("🌀 Всё навалилось", callback_data="c_overload")],
            [InlineKeyboardButton("💡 Совет дня", callback_data="c_tip")],
            [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")],
        ])
    )
    ctx.user_data["coach_mode"] = True

async def coach_quick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    prompt = COACH_PROMPTS.get(q.data, "")
    await send_coach(q.message, prompt, q.from_user.id)

# ── SKILL OF THE DAY ───────────────────────────────────────────────────────
async def show_skill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    skill = get_daily_skill(uid)
    await q.message.reply_text(
        f"🧠 *Навык дня*\n\n"
        f"*{skill['name']}*\n\n"
        f"{skill['tip']}\n\n"
        f"_Источник: тренинг навыков для взрослых с СДВГ (Safren / СДВГ в квадрате)_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="go_menu")]])
    )

# ── STREAK ─────────────────────────────────────────────────────────────────
async def show_streak(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    s = calc_streak(uid)
    await q.message.reply_text(
        f"🔥 *Стрик: {s} {'день' if s==1 else 'дня' if s<5 else 'дней'} подряд*\n\n"
        f"{'Продолжай! Каждый день считается.' if s>0 else 'Заполни утро или вечер — и стрик пойдёт.'}\n\n"
        f"_Стрик растёт когда ты закрываешь вечерний блок._",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ── GENERAL CALLBACKS ──────────────────────────────────────────────────────
async def go_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["coach_mode"] = False
    await q.message.reply_text("Главное меню 👇", reply_markup=main_menu())

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if ctx.user_data.get("awaiting_buddy"):
        ctx.user_data["awaiting_buddy"] = False
        bname = update.message.text.strip()
        update_user(uid, buddy_name=bname)
        await update.message.reply_text(
            f"👥 *Бадди добавлен: {bname}*\n\nВ 13:00 бот предложит обратиться к нему при трудностях.",
            parse_mode="Markdown", reply_markup=main_menu()
        )
    elif ctx.user_data.get("coach_mode"):
        await send_coach(update.message, update.message.text, uid)
    else:
        await update.message.reply_text("Выбери что хочешь сделать 👇", reply_markup=main_menu())


# ── BUDDY ──────────────────────────────────────────────────────────────────
async def buddy_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    buddy = user.get("buddy_name","")
    buddy_tip = (
        "🔵 *Body doubling* — просто работайте рядом (видеозвонок, кафе). "
        "Мозг с СДВГ активируется от присутствия другого человека — даже без слов.\n\n"
        "🟣 *Accountability buddy* — утром говоришь другу свой A-план, вечером отчитываешься. "
        "Внешняя ответственность работает там, где внутренняя не справляется."
    )
    text = f"👥 *Бадди при СДВГ*\n\n{buddy_tip}\n\n"
    if buddy:
        text += f"*Твой бадди:* {buddy}"
        buttons = [
            [InlineKeyboardButton("✏️ Изменить", callback_data="buddy_set")],
            [InlineKeyboardButton("💬 Написать бадди сейчас", callback_data="buddy_ping")],
            [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")],
        ]
    else:
        text += "_Бадди не задан._"
        buttons = [
            [InlineKeyboardButton("➕ Добавить бадди", callback_data="buddy_set")],
            [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")],
        ]
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

async def buddy_set(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["awaiting_buddy"] = True
    await q.message.reply_text("Напиши имя своего бадди:")

async def buddy_ping(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    buddy = user.get("buddy_name","бадди")
    morning = get_diary(uid, "morning")
    focus = morning.get("focus","моя главная задача")
    await q.message.reply_text(
        f"👥 *Шаблон для {buddy}:*\n\n"
        f"_«{buddy}, привет! Работаю над: {focus}. Поработаем вместе 25 минут? Можно просто видеозвонок с тишиной.»_\n\n"
        f"Скопируй и отправь! Body doubling работает даже онлайн.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="go_menu")]])
    )

# ── MIDDAY NOTIFICATION ─────────────────────────────────────────────────────
async def midday_notification(app):
    """13:00 — дневной чекин с реальными ситуациями из тренинга."""
    user_ids = get_all_users()
    for uid in user_ids:
        try:
            user = get_user(uid)
            morning = get_diary(uid, "morning")

            if not morning:
                await app.bot.send_message(uid,
                    f"☕ *{user['name']}, как дела?*\n\nУтренний дневник не заполнен — и это нормально. Как сейчас?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Всё хорошо", callback_data="mid_ok")],
                        [InlineKeyboardButton("🤖 Нужна помощь", callback_data="mid_coach")],
                    ])
                )
                continue

            tasks = build_tasks_summary(morning)
            await app.bot.send_message(uid,
                f"☕ *Дневной чекин, {user['name']}!*\n\n"
                f"Твои задачи:\n{tasks}\n\nКак идут дела?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Всё по плану", callback_data="mid_ok")],
                    [InlineKeyboardButton("❓ Непонятно с чего начать", callback_data="mid_nostart")],
                    [InlineKeyboardButton("😰 Задача подавляет/пугает", callback_data="mid_scary")],
                    [InlineKeyboardButton("⏳ Жду подходящего момента", callback_data="mid_waiting")],
                    [InlineKeyboardButton("🎯 Боюсь сделать плохо", callback_data="mid_perfect")],
                    [InlineKeyboardButton("🧱 Внутреннее сопротивление", callback_data="mid_resist")],
                    [InlineKeyboardButton("⚡ Мало времени", callback_data="mid_time")],
                    [InlineKeyboardButton("📱 Залип(ла) в телефоне", callback_data="mid_phone")],
                    [InlineKeyboardButton("🤖 Коуч", callback_data="mid_coach")],
                ])
            )
        except Exception as e:
            print(f"Ошибка дневного уведомления для {uid}: {e}")

async def midday_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ответы на дневной чекин — ситуации и инструменты из реального тренинга."""
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    name = user["name"]
    morning = get_diary(uid, "morning")
    focus = morning.get("focus", "твоя A-задача")
    action = q.data

    back_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Коуч поможет", callback_data="mid_coach")],
        [InlineKeyboardButton("👥 Нужен бадди", callback_data="mid_buddy")],
        [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")],
    ])

    if action == "mid_ok":
        await q.message.reply_text(
            f"💪 *Отлично, {name}!*\n\nПродолжай. Помни про перерывы — 5-10 минут каждые 25-30 минут.\n_Гиперфокус истощает — не пропускай отдых._\n\nДо вечера! 🌙",
            parse_mode="Markdown", reply_markup=main_menu()
        )

    elif action == "mid_nostart":
        await q.message.reply_text(
            f"❓ *Непонятно с чего начать*\n\nЗадача: _{focus}_\n\n"
            f"Что делали на тренинге в этой ситуации:\n\n"
            f"👣 *Выделить первый шаг* — одно конкретное действие. Что нужно сделать в первую очередь?\n\n"
            f"🤔 *За и против* — зачем это вообще важно? Короткое напоминание себе.\n\n"
            f"⚡ *Активация тела* — встань, потянись, попрыгай, умойся. Тело запускает мозг.\n\n"
            f"👥 *Помощь бадди* — иногда нужно просто сказать кому-то «я начинаю».\n\n"
            f"🤖 *Обратиться к ИИ* — опиши задачу и попроси разбить на шаги.\n\n"
            f"_Начни с активации тела — это самый быстрый способ запуститься._",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif action == "mid_scary":
        await q.message.reply_text(
            f"😰 *Задача подавляет — это исполнительная дисфункция, не лень*\n\nЗадача: _{focus}_\n\n"
            f"👣 *Найди шаг, который не фрустрирует* — уменьшай пока не исчезнет желание отложить\n\n"
            f"🛑 *СТОП* — остановись, дыши, осмотрись прежде чем действовать\n\n"
            f"🤲 *Ладони готовности* — расслабь лицо, ладони вверх, приступи\n\n"
            f"🖐 *5 чувств* — 5 предметов, 4 ощущения, 3 звука — вернись в тело\n\n"
            f"💧 *Успокой себя* — холодная вода, дыхание, аптечка самоуспокоения\n\n"
            f"👥 *Поговори с бадди* — body doubling работает даже без слов\n\n"
            f"⏱ *Таймер на 2 минуты* — только начать. После старта обычно легче.",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif action == "mid_waiting":
        await q.message.reply_text(
            f"⏳ *«Начну когда буду готов(а)»*\n\nЭтот момент обычно не наступает — это ловушка.\n\n"
            f"🤲 *Ладони + 5 чувств* — возвращает в настоящий момент\n\n"
            f"⏱ *Таймер* — поставь на 10 минут. Не на весь день. Просто попробуй.\n\n"
            f"⚡ *Активация* — тело сначала, голова потом. Попрыгай, умойся.\n\n"
            f"💧 *Тазик/кастрюля ледяной воды* — радикально, но работает мгновенно\n\n"
            f"🎵 *Активная музыка* — 3-5 минут энергичной музыки перед стартом\n\n"
            f"🔤 *За и против* — напомни себе ЗАЧЕМ это важно\n\n"
            f"_Подходящее состояние появляется ПОСЛЕ начала, а не до._",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif action == "mid_perfect":
        await q.message.reply_text(
            f"🎯 *Перфекционизм — страх сделать недостаточно хорошо*\n\nЗадача: _{focus}_\n\n"
            f"💩 *Поставь цель «сделать плохо»* — буквально. Разреши себе черновик.\n\n"
            f"✌️ *Сделать просто как-нибудь* — готово > идеально. Всегда.\n\n"
            f"🤲 *Принятие реальности* — ладони готовности, позволь себе быть несовершенным(ой)\n\n"
            f"📋 *Долгосрочные приоритеты* — это вообще важно в масштабе месяца?\n\n"
            f"👏 *Похвали себя* — за то что начал(а), не за результат\n\n"
            f"🧠 *Представь что получилось плохо — и прими это* — мысленная репетиция\n\n"
            f"👫 *Поговори с другом* — страх часто преувеличен, взгляд со стороны помогает\n\n"
            f"_Всем не угодишь. Сделанное лучше идеального._",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif action == "mid_resist":
        await q.message.reply_text(
            f"🧱 *Внутреннее сопротивление*\n\nЗнаешь что надо, но не можешь начать. Пробуй по списку:\n\n"
            f"🛌 *Пойти поспать 20 минут* — иногда это честный ответ\n\n"
            f"🏋️ *Зарядка/движение* — физическая активность запускает дофамин\n\n"
            f"💧 *Тазик ледяной воды* — радикально, но работает\n\n"
            f"🤲 *Ладони готовности* — расслабь лицо, ладони вверх, приступи\n\n"
            f"🏆 *Награда за выполнение* — что получишь после? Пообещай себе.\n\n"
            f"⏱ *Таймер + маячок внимания* — 25 мин работы + стикер на видном месте\n\n"
            f"🛑 *СТОП* — остановись и замети что именно сопротивляется\n\n"
            f"👏 *Похвали себя* — за любую попытку, не только за результат",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif action == "mid_time":
        tasks = build_tasks_summary(morning)
        await q.message.reply_text(
            f"⚡ *Мало времени — расставляем приоритеты*\n\n"
            f"Твои задачи:\n{tasks}\n\n"
            f"*Только A-задача:* _{focus}_\n\n"
            f"🐘 *Разделить слона* — какой самый маленький шаг прямо сейчас?\n\n"
            f"🌸 *Начать с приятной части* — войди через то, что не пугает\n\n"
            f"⏱ *Работа по таймеру* — короткие спринты, не марафон\n\n"
            f"🌍 *Изменить условия* — можно совместить? Слушать тренинг во время рутины\n\n"
            f"⚓ *Якорь* — верни внимание в тело, потом к задаче\n\n"
            f"_Незавершённые задачи не переносятся — завтра выбираешь заново._",
            parse_mode="Markdown", reply_markup=back_kb
        )

    elif action == "mid_phone":
        await q.message.reply_text(
            f"📱 *Поймал(а) себя — это уже победа!*\n\n"
            f"Навык *СТОП*:\n"
            f"🛑 *С* — Стоп. Положи телефон.\n"
            f"👣 *Т* — Шаг назад. Глубокий вдох.\n"
            f"👀 *О* — Осмотрись. 5 предметов вокруг.\n"
            f"✅ *П* — Попытайся. Возвращайся к задаче.\n\n"
            f"Твоя A-задача: *{focus}*\n\n"
            f"_Поставь таймер на 10 минут и просто открой нужный файл._",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Иду работать", callback_data="mid_ok")],
                [InlineKeyboardButton("🤖 Нужна помощь", callback_data="mid_coach")],
            ])
        )

    elif action == "mid_coach":
        ctx.user_data["coach_mode"] = True
        await q.message.reply_text(
            f"🤖 *Коуч на связи, {name}.* Что происходит?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Не могу начать", callback_data="c_start")],
                [InlineKeyboardButton("😩 Прокрастинирую", callback_data="c_procr")],
                [InlineKeyboardButton("🌀 Всё навалилось", callback_data="c_overload")],
                [InlineKeyboardButton("◀️ Меню", callback_data="go_menu")],
            ])
        )

    elif action == "mid_buddy":
        buddy = user.get("buddy_name","")
        if buddy:
            await q.message.reply_text(
                f"👥 *Бадди-режим!*\n\n"
                f"Напиши {buddy} прямо сейчас:\n\n"
                f"_«{buddy}, привет! Работаю над: {focus}. Поработаем вместе 25 минут? Даже просто видеозвонок с тишиной.»_\n\n"
                f"Body doubling работает даже без слов и с выключенной камерой.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Меню", callback_data="go_menu")]])
            )
        else:
            await q.message.reply_text("👥 Бадди не задан. Нажми «Бадди» в меню.", reply_markup=main_menu())

# ── SCHEDULED NOTIFICATIONS ────────────────────────────────────────────────
async def morning_notification(app):
    user_ids = get_all_users()
    for uid in user_ids:
        try:
            user = get_user(uid)
            name = user.get("name", "")
            gender = user.get("gender", "M")

            yesterday = (date.today() - timedelta(days=1)).isoformat()
            ev = get_diary(uid, "evening", yesterday)
            plan_text = ""
            if ev.get("e_a"):
                plan_text = f"\n\n⭐ *Сегодня тебе важно:*\n🅰️ {ev['e_a']}"
                if ev.get("e_b1"): plan_text += f"\n🅱️ {ev['e_b1']}"
                if ev.get("e_b2"): plan_text += f"\n🅱️ {ev['e_b2']}"

            skill = get_daily_skill(uid)
            motiv = random.choice(MOTIVATIONS_F if gender == 'F' else MOTIVATIONS_M)

            await app.bot.send_message(
                uid,
                f"☀️ *Доброе утро, {name}!*\n\n"
                f"_{motiv}_{plan_text}\n\n"
                f"💡 *Навык дня:* {skill['name']}\n"
                f"_{skill['desc']}_\n\n"
                f"Готов(а) начать? 👇",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        except Exception as e:
            print(f"Ошибка утреннего уведомления для {uid}: {e}")

async def evening_notification(app):
    user_ids = get_all_users()
    for uid in user_ids:
        try:
            user = get_user(uid)
            name = user.get("name", "")
            await app.bot.send_message(
                uid,
                f"🌙 *Привет, {name}!*\n\n"
                f"День заканчивается. Время закрыть его и поставить планы на завтра.\n\n"
                f"5 минут — и голова свободна 👇",
                parse_mode="Markdown",
                reply_markup=main_menu()
            )
        except Exception as e:
            print(f"Ошибка вечернего уведомления для {uid}: {e}")

async def handle_web_app_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Принимает данные от Mini App и сохраняет в БД."""
    uid = update.effective_user.id
    raw = update.effective_message.web_app_data.data
    try:
        data = json.loads(raw)
    except Exception:
        return

    if data.get("type") == "morning":
        focus = data.get("focus", "")
        if focus:
            update_user(uid, focus=focus)
        save_diary(uid, "morning", {
            "focus":    focus,
            "b1":       data.get("b1", ""),
            "b2":       data.get("b2", ""),
            "c1":       data.get("c1", ""),
            "writing":  data.get("writing", ""),
            "gratitude":data.get("gratitude", ""),
        })
        user = get_user(uid)
        tasks = ""
        if focus: tasks += f"\n🅰️ {focus}"
        if data.get("b1"): tasks += f"\n🅱️ {data['b1']}"
        if data.get("b2"): tasks += f"\n🅱️ {data['b2']}"
        await update.message.reply_text(
            f"✅ *Утро записано!*{tasks}\n\nВперёд, {user['name']}! 💪",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )


# ── MAIN ───────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Онбординг
    onboard_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ONBOARD_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_name)],
            ONBOARD_GENDER: [CallbackQueryHandler(got_gender, pattern="^gender_")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    # Утренний flow
    morning_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(morning_start, pattern="^go_morning$")],
        states={
            M_EXERCISE: [
                CallbackQueryHandler(warmup_go,     pattern="^warmup_go$"),
                CallbackQueryHandler(skip_warmup,   pattern="^skip_warmup$"),
            ],
            M_FOCUS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_m_focus),    CallbackQueryHandler(skip_m_focus,    pattern="^skip_m_focus$")],
            M_B1:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_m_b1),       CallbackQueryHandler(skip_m_b1,       pattern="^skip_m_b1$")],
            M_B2:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_m_b2),       CallbackQueryHandler(skip_m_b2,       pattern="^skip_m_b2$")],
            M_C1:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_m_c1),       CallbackQueryHandler(skip_m_c_all,    pattern="^skip_m_c_all$")],
            M_C2:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_m_c2),       CallbackQueryHandler(skip_m_c_all,    pattern="^skip_m_c_all$")],
            M_C3:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_m_c3),       CallbackQueryHandler(skip_m_c_all,    pattern="^skip_m_c_all$")],
            M_WRITING:  [MessageHandler(filters.TEXT & ~filters.COMMAND, got_writing),    CallbackQueryHandler(skip_m_writing,  pattern="^skip_m_writing$")],
            M_GRATITUDE:[MessageHandler(filters.TEXT & ~filters.COMMAND, got_gratitude),  CallbackQueryHandler(skip_m_gratitude,pattern="^skip_m_gratitude$")],
            M_CHILD:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_child),      CallbackQueryHandler(skip_m_child,    pattern="^skip_m_child$")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    # Вечерний flow
    evening_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(evening_start, pattern="^go_evening$")],
        states={
            E_ACH:       [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_ach),      CallbackQueryHandler(skip_e_ach,      pattern="^skip_e_ach$")],
            E_PRAISE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_praise),   CallbackQueryHandler(skip_e_praise,   pattern="^skip_e_praise$")],
            E_HIGHLIGHTS:[MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_highlights),CallbackQueryHandler(skip_e_highlights,pattern="^skip_e_highlights$")],
            E_A:         [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_a),        CallbackQueryHandler(skip_e_a,        pattern="^skip_e_a$")],
            E_B1:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_b1),       CallbackQueryHandler(skip_e_b1,       pattern="^skip_e_b1$")],
            E_B2:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_b2),       CallbackQueryHandler(skip_e_b2,       pattern="^skip_e_b2$")],
            E_C1:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_c1),       CallbackQueryHandler(skip_e_c_all,    pattern="^skip_e_c_all$")],
            E_C2:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_c2),       CallbackQueryHandler(skip_e_c_all,    pattern="^skip_e_c_all$")],
            E_C3:        [MessageHandler(filters.TEXT & ~filters.COMMAND, got_e_c3),       CallbackQueryHandler(skip_e_c_all,    pattern="^skip_e_c_all$")],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(onboard_conv)
    app.add_handler(morning_conv)
    app.add_handler(evening_conv)
    app.add_handler(CallbackQueryHandler(coach_menu,  pattern="^go_coach$"))
    app.add_handler(CallbackQueryHandler(coach_quick, pattern="^c_(start|dist|next|procr|overload|tip)$"))
    app.add_handler(CallbackQueryHandler(show_skill,  pattern="^go_skill$"))
    app.add_handler(CallbackQueryHandler(show_streak, pattern="^go_streak$"))
    app.add_handler(CallbackQueryHandler(go_menu,     pattern="^go_menu$"))
    app.add_handler(CallbackQueryHandler(buddy_menu,      pattern="^go_buddy$"))
    app.add_handler(CallbackQueryHandler(buddy_set,       pattern="^buddy_set$"))
    app.add_handler(CallbackQueryHandler(buddy_ping,      pattern="^buddy_ping$"))
    app.add_handler(CallbackQueryHandler(midday_callback, pattern="^mid_"))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Уведомления (UTC время)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(morning_notification, 'cron',
                      hour=MORNING_HOUR_UTC, minute=0, args=[app])
    scheduler.add_job(midday_notification, 'cron',
                      hour=MIDDAY_HOUR_UTC, minute=0, args=[app])
    scheduler.add_job(evening_notification, 'cron',
                      hour=EVENING_HOUR_UTC, minute=0, args=[app])
    scheduler.start()
    print(f"✅ ADHD бот v3 запущен!")
    print(f"   Уведомления: {MORNING_HOUR_UTC}:00 и {EVENING_HOUR_UTC}:00 UTC")
    print(f"   Notify user ID: {NOTIFY_USER_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()
