"""Тикеты поддержки (Flask Blueprint).

- Пользователь создаёт тикет, пишет сообщения.
- Ответы админа отправляют email уведомления (SMTP из настроек).
- Интеграция с Telegram-ботом: дублирование уведомлений (см. settings).
"""
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Blueprint, request, jsonify, render_template, redirect, url_for

from store.app import db
from store.modules.models import Ticket, TicketMessage
from store.modules import settings_manager as sm

logger = logging.getLogger(__name__)

tickets_bp = Blueprint('support_tickets', __name__, url_prefix='/store/tickets')


def _user_from_panel():
    from store.panel_session import get_panel_user_id
    from store.panel_data import get_panel_user
    uid = get_panel_user_id(request.cookies.get('session', ''))
    if not uid:
        return None
    u = get_panel_user(uid)
    return {'user_id': uid, 'username': u.get('username', '') if u else ''}


def _send_email(to_email: str, subject: str, html_body: str, text_body: str = ''):
    """Отправка email через SMTP из настроек. Airт тихом при ошибке."""
    s = sm.load_all_settings()
    server = s.get('smtp_server')
    if not server:
        logger.info("SMTP не настроен, email не отправлен")
        return False
    port = int(s.get('smtp_port', 587))
    user = s.get('smtp_user')
    password = s.get('smtp_password')
    from_addr = s.get('smtp_from') or user

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_email
    if html_body:
        msg.attach(MIMEText(html_body, 'html'))
    if text_body:
        msg.attach(MIMEText(text_body, 'plain'))

    try:
        with smtplib.SMTP(server, port) as smtp:
            smtp.ehlo()
            if port == 587:
                smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.sendmail(from_addr, [to_email], msg.as_string())
        logger.info(f"Email отправлен на {to_email}")
        return True
    except Exception as e:
        logger.exception(f"Ошибка отправки email: {e}")
        return False


# ------------------------------------------------------------------
# Страницы / API
# ------------------------------------------------------------------

@tickets_bp.route('', methods=['GET'])
def list_tickets():
    user = _user_from_panel()
    if not user:
        return redirect(url_for('vpn_purchase.purchase_page'))
    tickets = Ticket.query.filter_by(user_id=user['user_id']).order_by(Ticket.created_at.desc()).all()
    return render_template('tickets.html', tickets=tickets)


@tickets_bp.route('', methods=['POST'])
def create_ticket():
    user = _user_from_panel()
    if not user:
        return jsonify({'error': 'Не авторизован'}), 401
    subject = request.form.get('subject', '').strip()
    body = request.form.get('body', '').strip()
    if not subject or not body:
        return jsonify({'error': 'Заполните тему и сообщение'}), 400

    ticket = Ticket(user_id=user['user_id'], username=user['username'], subject=subject, status='open')
    db.session.add(ticket)
    db.session.flush()
    db.session.add(TicketMessage(ticket_id=ticket.id, author_role='user', author_id=user['user_id'], body=body))
    db.session.commit()

    # Уведомление админу
    admin_email = sm.get_admin_email()
    if admin_email:
        _send_email(
            admin_email,
            f"Новый тикет: {subject}",
            f"<b>От:</b> {user['username']}<br><b>{body}</b>",
            body,
        )
    return jsonify({'status': 'created', 'ticket_id': ticket.id})


@tickets_bp.route('/<int:ticket_id>', methods=['GET'])
def view_ticket(ticket_id):
    user = _user_from_panel()
    if not user:
        return redirect(url_for('vpn_purchase.purchase_page'))
    ticket = Ticket.query.filter_by(id=ticket_id, user_id=user['user_id']).first()
    if not ticket:
        return jsonify({'error': 'Тикет не найден'}), 404
    return render_template('ticket_detail.html', ticket=ticket)


@tickets_bp.route('/<int:ticket_id>/reply', methods=['POST'])
def reply_ticket(ticket_id):
    user = _user_from_panel()
    if not user:
        return jsonify({'error': 'Не авторизован'}), 401
    body = request.form.get('body', '').strip()
    if not body:
        return jsonify({'error': 'Пустое сообщение'}), 400
    ticket = Ticket.query.filter_by(id=ticket_id, user_id=user['user_id']).first()
    if not ticket:
        return jsonify({'error': 'Тикет не найден'}), 404
    ticket.status = 'open'
    db.session.add(TicketMessage(ticket_id=ticket.id, author_role='user', author_id=user['user_id'], body=body))
    db.session.commit()
    return redirect(url_for('support_tickets.view_ticket', ticket_id=ticket.id))


def setup_tickets(app):
    app.register_blueprint(tickets_bp)
    logger.info("Support tickets: настроены")