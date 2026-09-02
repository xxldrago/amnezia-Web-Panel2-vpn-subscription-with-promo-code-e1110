"""Telegram-бот продаж и поддержки (aiogram 3) для store-системы.

Работает как отдельный процесс (контейнер). Пользователь идентифицируется по
telegramId из общего data.json панели. Для доступа к БД store переиспользует
create_app() (сервер не запускается), платёжные ссылки создаются через
существующий модуль vpn_purchase.create_payment_link.
"""
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from store.app import create_app, db
from store.modules.models import VpnPurchase, Ticket, TicketMessage, TrialSubscription
from store.modules import settings_manager as sm
from store.panel_data import get_panel_users

logger = logging.getLogger(__name__)

# Приложение store для контекста БД в бэкграундном процессе (HTTP-сервер не запускаем).
_app = create_app()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _user_by_telegram_id(tg_id: str):
    tg_id = str(tg_id)
    for u in get_panel_users():
        if str(u.get('telegramId', '')) == tg_id:
            return u
    return None


def _menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить VPN", callback_data="buy")],
        [InlineKeyboardButton(text="🎁 Тестовая подписка", callback_data="trial")],
        [InlineKeyboardButton(text="📋 Мои заказы", callback_data="orders")],
        [InlineKeyboardButton(text="🎁 Рефералка", callback_data="referral")],
        [InlineKeyboardButton(text="🎫 Поддержка", callback_data="support")],
    ])


def _pricing_kb():
    with _app.app_context():
        pricing = sm.get_pricing()
    buttons = [
        [InlineKeyboardButton(text=f"{p['label']} — {p['price']}₽", callback_data=f"plan:{pid}")]
        for pid, p in pricing.items()
    ]
    buttons.append([InlineKeyboardButton(text="⬅ Назад", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------

async def start(message: Message):
    await message.answer(
        "👋 Привет! Я бот VPN-сервиса. Что вас интересует?",
        reply_markup=_menu(),
    )


async def cb_menu(query: CallbackQuery):
    await query.message.edit_text("👋 Главное меню:", reply_markup=_menu())
    await query.answer()


async def cb_buy(query: CallbackQuery):
    await query.message.edit_text("Выберите тариф:", reply_markup=_pricing_kb())
    await query.answer()


async def cb_plan(query: CallbackQuery):
    plan_id = query.data.split(":", 1)[1]
    user = _user_by_telegram_id(query.from_user.id)
    if not user:
        await query.message.edit_text(
            "❌ Пользователь не привязан к панели. Зарегистрируйтесь на сайте.",
            reply_markup=_menu())
        await query.answer()
        return

    with _app.app_context():
        pricing = sm.get_pricing()
        plan = pricing.get(plan_id)
        if not plan:
            await query.answer("Неверный тариф", show_alert=True)
            return
        now = datetime.utcnow()
        order = VpnPurchase(
            order_id=f"VPN_{user.get('username', 'u')}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:4]}",
            user_id=user['id'],
            username=user.get('username', ''),
            plan_id=plan_id,
            plan_label=plan['label'],
            days=plan['days'],
            base_price=plan['price'],
            final_price=plan['price'],
            payment_method='platega',
            payment_method_name='Platega.io',
            status='pending',
            created_at=now,
            expires_at=now + timedelta(days=plan['days']),
        )
        db.session.add(order)
        db.session.flush()
        # Создаём платёжную ссылку (переиспользуем модуль web-части)
        from store.modules import vpn_purchase
        pay = vpn_purchase.create_payment_link({
            'order_id': order.order_id,
            'amount': plan['price'],
            'plan_label': plan['label'],
            'username': user.get('username', ''),
            'email': '',
        })
        if pay.get('payment_url'):
            order.payment_url = pay['payment_url']
        db.session.commit()
        order_id = order.order_id
        pay_url = pay.get('payment_url', '')

    await query.message.edit_text(
        f"✅ Вы выбрали: {plan['label']} — {plan['price']}₽\n"
        f"Заказ: `{order_id}`\n\n"
        f"Оплата: {pay_url}\n\n"
        "После оплаты VPN-доступы выдаются автоматически.",
        reply_markup=_menu(),
    )
    await query.answer()


async def cb_trial(query: CallbackQuery):
    user = _user_by_telegram_id(query.from_user.id)
    if not user:
        await query.message.edit_text("❌ Пользователь не привязан к панели.", reply_markup=_menu())
        await query.answer()
        return
    from store.modules import vpn_provision
    with _app.app_context():
        res = vpn_provision.activate_trial_and_provision(user['id'], user.get('username', ''))
    msg = ("✅ Тестовая подписка на 3 дня активирована!" if res.get('success')
           else f"⚠️ {res.get('error', 'Ошибка активации')}")
    await query.message.edit_text(msg, reply_markup=_menu())
    await query.answer()


async def cb_orders(query: CallbackQuery):
    user = _user_by_telegram_id(query.from_user.id)
    if not user:
        await query.message.edit_text("❌ Пользователь не привязан к панели.", reply_markup=_menu())
        await query.answer()
        return
    with _app.app_context():
        orders = (VpnPurchase.query.filter_by(user_id=user['id'])
                  .order_by(VpnPurchase.created_at.desc()).limit(10).all())
        trial_used = db.session.query(TrialSubscription).filter_by(user_id=user['id']).first() is not None
    if not orders:
        text = "У вас пока нет заказов."
    else:
        text = "\n".join(f"{o.plan_label} — {o.status} ({o.final_price}₽)" for o in orders)
    await query.message.edit_text(f"📋 Ваши заказы:\n{text}", reply_markup=_menu())
    await query.answer()


async def cb_referral(query: CallbackQuery):
    user = _user_by_telegram_id(query.from_user.id)
    if not user:
        await query.message.edit_text("❌ Пользователь не привязан к панели.", reply_markup=_menu())
        await query.answer()
        return
    from store.modules.referral_system import ensure_referral_user
    with _app.app_context():
        ru = ensure_referral_user(user['id'], user.get('username', ''))
    with _app.app_context():
        site = sm.get_site_url()
    link = f"{site}/store/referral?invite={ru.referral_code}"
    await query.message.edit_text(
        f"🎁 Ваша реферальная ссылка:\n`{link}`\nКод: `{ru.referral_code}`",
        reply_markup=_menu(),
    )
    await query.answer()


async def cb_support(query: CallbackQuery):
    await query.message.edit_text(
        "🎫 Для создания тикета напишите сообщение в формате:\n"
        "`тикет Тема | текст`\n\n"
        "Пример: `тикет Проблема с подключением | Не работает конфиг`",
        reply_markup=_menu(),
    )
    await query.answer()


async def handle_ticket_msg(message: Message):
    text = (message.text or "").strip()
    if text.lower().startswith("тикет") and "|" in text:
        user = _user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer("❌ Пользователь не привязан к панели.")
            return
        # Формат: 'тикет Тема | текст' → subject = 'Тема', body = 'текст'
        head = text[len("тикет"):].lstrip(" |")
        subject, _, body = head.partition("|")
        subject = subject.strip()
        body = body.strip()
        if not subject or not body:
            await message.answer("Неверный формат. Используйте: `тикет Тема | текст`")
            return
        with _app.app_context():
            t = Ticket(user_id=user['id'], username=user.get('username', ''), subject=subject, status='open')
            db.session.add(t)
            db.session.flush()
            db.session.add(TicketMessage(ticket_id=t.id, author_role='user', author_id=user['id'], body=body))
            db.session.commit()
            t_id = t.id
        await message.answer(f"✅ Тикет #{t_id} создан. Мы ответим в ближайшее время.")
        return
    await message.answer("Используйте кнопки ниже 👇", reply_markup=_menu())


# ------------------------------------------------------------------
# Запуск
# ------------------------------------------------------------------

async def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не задан. Бот не запущен.")
        return
    bot = Bot(token=token)
    dp = Dispatcher()

    dp.message.register(start, CommandStart())
    dp.message.register(handle_ticket_msg)
    dp.callback_query.register(cb_menu, F.data == "menu")
    dp.callback_query.register(cb_buy, F.data == "buy")
    dp.callback_query.register(cb_plan, F.data.startswith("plan:"))
    dp.callback_query.register(cb_trial, F.data == "trial")
    dp.callback_query.register(cb_orders, F.data == "orders")
    dp.callback_query.register(cb_referral, F.data == "referral")
    dp.callback_query.register(cb_support, F.data == "support")

    logger.info("Telegram-бот store запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())