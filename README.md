# ADHD Focus Bot v2

Telegram-бот с правильной структурой дневника.

## Структура дневника

**Утро:**
- 2 мин разминка (с таймером по упражнениям)
- Today's focus — A-план на день
- Free writing
- Gratitude
- Inner child

**Вечер:**
- Achievements of the day
- Praise yourself
- Highlights of the day
- Plans for tomorrow: A / B B / C C C

---

## Деплой на Railway

### 1. Создай бота
- Напиши @BotFather → /newbot → скопируй токен

### 2. Загрузи на GitHub
- Создай репозиторий
- Загрузи bot.py и requirements.txt

### 3. Railway
- railway.app → New Project → GitHub repo
- Variables → добавь:
  ```
  BOT_TOKEN=твой_токен
  ANTHROPIC_KEY=sk-ant-...   (опционально, для коуча)
  USER_NAME=Артём             (опционально, твоё имя)
  ```

### 4. Включи уведомления
В bot.py найди в конце:
```python
# YOUR_USER_ID = 123456789
# scheduler.add_job(morning_notif, 'cron', hour=8, ...)
# scheduler.add_job(evening_notif, 'cron', hour=21, ...)
```
- Узнай свой ID через @userinfobot
- Убери # и замени YOUR_USER_ID
- Учти UTC: Тбилиси = UTC+4, значит 8:00 утра = hour=4

### 5. Проверь
Найди бота в Telegram → /start
