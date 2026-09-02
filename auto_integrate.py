import os
import re

def integrate_modules():
    app_path = '/app/app.py'
    if not os.path.exists(app_path):
        print(f"❌ Файл {app_path} не найден. Пропускаю интеграцию.")
        return

    with open(app_path, 'r', encoding='utf-8') as f:
        content = f.read()

    changes_made = False

    # 1. Добавляем импорты
    imports_block = """
# --- AUTO-INTEGRATED MODULES START ---
try:
    from vpn_purchase import setup_vpn_purchase_module
    from vpn_auto_provision import setup_auto_provisioning
    from referral_system import setup_referral_system, on_user_register, on_user_deposit
    from telegram_bot_runner import run_telegram_bot_thread
    from settings_manager import load_all_settings
    MODULES_ENABLED = True
except ImportError as e:
    print(f"⚠️ Warning: Could not import some modules: {e}")
    MODULES_ENABLED = False
# --- AUTO-INTEGRATED MODULES END ---
"""

    if "# --- AUTO-INTEGRATED MODULES START ---" not in content:
        # Вставляем после основных импортов Flask
        content = content.replace("from flask import Flask", f"from flask import Flask\n{imports_block}")
        changes_made = True
        print("✅ Импорты модулей добавлены.")

    # 2. Добавляем инициализацию в блок создания app
    # Ищем место после app = Flask(__name__)
    init_block = """
    # Auto-initialization of modules
    if MODULES_ENABLED:
        try:
            load_all_settings(app) # Загружаем настройки из БД/JSON
            setup_vpn_purchase_module(app)
            setup_auto_provisioning(app, db.engine, VpnPurchase) # Предполагаем, что модели импортированы
            setup_referral_system(app)
            # Запускаем бота в отдельном потоке
            import threading
            bot_thread = threading.Thread(target=run_telegram_bot_thread, args=(app,), daemon=True)
            bot_thread.start()
            print("🚀 All modules (VPN, Referral, Bot, Auto-provision) started successfully!")
        except Exception as e:
            print(f"❌ Error starting modules: {e}")
"""

    # Простая эвристика: ищем app = Flask(__name__) и добавляем код после него с отступом
    if "if MODULES_ENABLED:" not in content:
        pattern = r"(app = Flask\(__name__\))"
        match = re.search(pattern, content)
        if match:
            insert_pos = match.end()
            # Находим конец строки
            newline_pos = content.find('\n', insert_pos)
            content = content[:newline_pos+1] + "    " + init_block.strip().replace('\n', '\n    ') + "\n" + content[newline_pos+1:]
            changes_made = True
            print("✅ Инициализация модулей добавлена в app.py.")

    if changes_made:
        with open(app_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("💾 Файл app.py обновлен и готов к запуску со всеми модулями.")
    else:
        print("ℹ️ Файл app.py уже содержит интеграцию модулей.")

if __name__ == "__main__":
    integrate_modules()
