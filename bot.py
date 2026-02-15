import asyncio
import os
import logging
import time
from collections import defaultdict
from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
import yt_dlp
from asyncio import to_thread
from aiohttp import web

# === НАСТРОЙКИ ===
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@flawlessvideohub")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1001234567890"))

# ОБЯЗАТЕЛЬНО ЗАМЕНИ НА СВОЙ РЕАЛЬНЫЙ ДОМЕН RENDER!
WEBHOOK_URL = "https://donaig-3.onrender.com"  # ←←← ИЗМЕНИ ЭТО!!!
WEBHOOK_PATH = "/webhook"

os.makedirs("downloads", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()]
)

bot = Bot(token=TOKEN)
dp = Dispatcher()

ALLOWED_DOMAINS = [
    "tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "instagram.com", "www.instagram.com",
    "youtube.com", "youtu.be", "m.youtube.com"
]

# === Middleware для защиты от флуда ===
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self):
        self.user_limits = defaultdict(list)
        self.download_times = defaultdict(float)

    async def __call__(self, handler, event: types.Message, data):
        user_id = event.from_user.id
        now = time.time()
        self.user_limits[user_id] = [t for t in self.user_limits[user_id] if now - t < 60]
        if len(self.user_limits[user_id]) >= 5:
            await event.answer("Слишком много запросов! Подожди минуту ⏳")
            logging.warning(f"Флуд от пользователя {user_id}")
            return
        self.user_limits[user_id].append(now)

        if hasattr(event, "text") and "http" in event.text.lower():
            last_download = self.download_times[user_id]
            if now - last_download < 30:
                await event.answer("Подожди 30 секунд перед следующим скачиванием ⏳")
                return
            self.download_times[user_id] = now

        return await handler(event, data)

dp.message.middleware(ThrottlingMiddleware())

# === Health check для Render и UptimeRobot ===
async def health(request):
    return web.Response(text="Bot is alive! OK")

# === Проверка подписки ===
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False

def subscribe_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}")
    builder.button(text="Проверить подписку", callback_data="check_sub")
    return builder.as_markup()

@dp.message(CommandStart())
async def start(message: types.Message):
    if await check_subscription(message.from_user.id):
        await message.answer("Привет! Отправь ссылку на видео из TikTok, Instagram Reels или YouTube Shorts.")
    else:
        await message.answer("Для использования бота подпишись на канал 👇", reply_markup=subscribe_keyboard())

@dp.callback_query(F.data == "check_sub")
async def check_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await callback.message.edit_text("Спасибо за подписку! Теперь отправь ссылку на видео.")
        await callback.answer()
    else:
        await callback.answer("Ты ещё не подписался! Подпишись и попробуй снова.", show_alert=True)

@dp.message(F.text.contains("http"))
async def handle_link(message: types.Message):
    if not await check_subscription(message.from_user.id):
        await message.answer("Подпишись на канал для использования бота!", reply_markup=subscribe_keyboard())
        return

    url = message.text.strip()
    logging.info(f"Пользователь {message.from_user.id} отправил ссылку: {url}")

    if not any(domain in url for domain in ALLOWED_DOMAINS):
        await message.answer("Поддерживаются только ссылки из TikTok, Instagram Reels и YouTube Shorts 😔")
        return

    await message.answer("Скачиваю видео... Подожди ⏳")

    try:
        filename = await download_video(url)
        file_size = os.path.getsize(filename)
        if file_size < 50 * 1024 * 1024:
            await message.answer_video(FSInputFile(filename), caption="Готово! Без водяных знаков 👍")
        else:
            await message.answer_document(FSInputFile(filename), caption="Видео большое, отправляю как файл 👍")
        os.remove(filename)
    except Exception as e:
        logging.error(f"Ошибка скачивания для пользователя {message.from_user.id}: {e}")
        await message.answer("Не удалось скачать видео 😔 Проверь ссылку или попробуй другое.")

async def download_video(url: str):
    ydl_opts = {
        'format': 'best[height<=720][ext=mp4]/best[ext=mp4]/best',  # Предпочтение готовым mp4 (без merge)
        'outtmpl': 'downloads/%(id)s.%(ext)s',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await to_thread(ydl.extract_info, url, download=True)  # ИСПРАВЛЕНО: убрана опечатка |
        filename = ydl.prepare_filename(info)
        return filename

# === Webhook сервер ===
async def on_startup(app):
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(url=webhook linearly_url)
    logging.info(f"Webhook установлен: {webhook_url}")

async def on_shutdown(app):
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook удалён")

async def web_server():
    app = web.Application()
    app.router.add_get('/', health)

    webhook_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000)))
    await site.start()

async def main():
    logging.info("Запуск бота в режиме webhook...")
    await web_server()

if __name__ == "__main__":
    asyncio.run(main())

