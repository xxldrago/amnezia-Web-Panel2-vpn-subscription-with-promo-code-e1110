import asyncio
import threading
import logging

def run_telegram_bot_thread(flask_app):
    """Запускает бота в отдельном потоке, чтобы не блокировать Flask"""
    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from vpn_telegram_bot import main as bot_main
            # Передаем контекст приложения если нужно, или бот берет из БД напрямую
            loop.run_until_complete(bot_main())
        except Exception as e:
            logging.error(f"Telegram bot crashed: {e}")
        finally:
            loop.close()

    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    print("🤖 Telegram Bot thread started.")