"""
VPN Purchase Module - Independent module for VPN subscription purchases
This module is designed to work independently from the main application updates.

Platega.io Integration:
- Uses X-MerchantId and X-Secret headers for authentication
- Supports payment link creation
- Handles callbacks for payment status

To integrate this module with your main FastAPI app:
1. Add this line to app.py after importing modules:
   from vpn_purchase import setup_vpn_purchase_module
   setup_vpn_purchase_module(app)

2. Add a link to /vpn/purchase in your user cabinet template (my_connections.html)

3. Set environment variables:
   - PLATEGA_MERCHANT_ID: Your merchant ID from Platega.io
   - PLATEGA_SECRET_KEY: Your secret API key from Platega.io
"""

import os
import json
import logging
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx

logger = logging.getLogger(__name__)

# Router for VPN purchase endpoints
vpn_purchase_router = APIRouter(prefix="/vpn", tags=["VPN Purchase"])

# Module directory
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# PLATEGA.IO CONFIGURATION
# Replace placeholders with real credentials from Platega.io dashboard
# ============================================================
PLATEGA_MERCHANT_ID = os.environ.get('PLATEGA_MERCHANT_ID', 'YOUR_MERCHANT_ID_HERE')  # ЗАГЛУШКА - замените на реальный MerchantId
PLATEGA_SECRET_KEY = os.environ.get('PLATEGA_SECRET_KEY', 'YOUR_SECRET_KEY_HERE')      # ЗАГЛУШКА - замените на реальный Secret Key
PLATEGA_BASE_URL = 'https://app.platega.io/'
PLATEGA_API_VERSION = 'v1'

# Pricing configuration (can be moved to database or config file)
VPN_PRICING = {
    "15_days": {"days": 15, "price": 200, "label": "15 дней"},
    "1_month": {"days": 30, "price": 400, "label": "1 месяц"},
    "3_months": {"days": 90, "price": 1100, "label": "3 месяца"},
    "6_months": {"days": 180, "price": 2100, "label": "6 месяцев"},
    "12_months": {"days": 365, "price": 4000, "label": "12 месяцев"},
}

# Payment methods configuration
PAYMENT_METHODS = [
    {"id": "platega", "name": "Platega.io", "enabled": True, "icon": "💳"}
]

# Valid promo codes (can be moved to database)
PROMO_CODES = {
    "WELCOME10": {"discount_percent": 10, "uses_limit": 100, "uses_count": 0},
    "NEWUSER20": {"discount_percent": 20, "uses_limit": 50, "uses_count": 0},
}

# Trial subscription configuration
TRIAL_SUBSCRIPTION = {
    "days": 3,
    "description": "Тестовая подписка на все сервера",
    "one_per_user": True,  # Only one trial per user
}


# ============================================================
# PLATEGA.IO API FUNCTIONS
# ============================================================

def get_platega_headers():
    """
    Get headers for Platega.io API requests.
    Uses X-MerchantId and X-Secret for authentication.
    """
    return {
        'Content-Type': 'application/json',
        'X-MerchantId': PLATEGA_MERCHANT_ID,
        'X-Secret': PLATEGA_SECRET_KEY,
    }


async def platega_create_payment_link(order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Create a payment link using Platega.io API.
    
    According to Platega.io documentation:
    - Endpoint: POST /api/payment-link/create (or similar based on API version)
    - Headers: X-MerchantId, X-Secret
    - Returns: payment URL for redirect
    
    Args:
        order_data: Dictionary containing order information
        
    Returns:
        Dictionary with payment_url or error message
    """
    # Check if credentials are still placeholders
    if PLATEGA_MERCHANT_ID == 'YOUR_MERCHANT_ID_HERE' or PLATEGA_SECRET_KEY == 'YOUR_SECRET_KEY_HERE':
        logger.warning("Platega.io credentials are not configured. Using simulation mode.")
        # Return simulated payment URL for development
        return {
            'success': True,
            'payment_url': f'https://app.platega.io/pay?order={order_data.get("order_id")}&amount={order_data.get("amount")}',
            'order_id': order_data.get('order_id'),
            'simulated': True
        }
    
    try:
        async with httpx.AsyncClient() as client:
            # Prepare payment request payload according to Platega.io API
            payload = {
                'amount': order_data['amount'],
                'currency': 'RUB',
                'orderId': order_data['order_id'],
                'description': order_data.get('description', 'VPN Subscription'),
                'successUrl': order_data.get('success_url', ''),
                'failUrl': order_data.get('fail_url', ''),
                # Additional optional fields per Platega.io docs
                'customer': {
                    'email': order_data.get('customer_email', ''),
                    'name': order_data.get('customer_name', ''),
                } if order_data.get('customer_email') else None,
            }
            
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            if 'customer' in payload and not payload['customer']:
                del payload['customer']
            
            # Make API request to Platega.io
            # Note: Actual endpoint may vary - check Platega.io documentation
            response = await client.post(
                f'{PLATEGA_BASE_URL}api/{PLATEGA_API_VERSION}/payment-link/create',
                headers=get_platega_headers(),
                json=payload,
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'payment_url': result.get('paymentUrl'),
                    'order_id': result.get('orderId'),
                    'transaction_id': result.get('transactionId'),
                }
            else:
                logger.error(f"Platega.io API error: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f'Platega.io API error: {response.status_code}'
                }
                
    except httpx.TimeoutException:
        logger.error("Platega.io API timeout")
        return {'success': False, 'error': 'Payment gateway timeout'}
    except Exception as e:
        logger.error(f"Error creating Platega.io payment link: {e}")
        return {'success': False, 'error': str(e)}


async def platega_check_payment_status(transaction_id: str) -> Optional[Dict[str, Any]]:
    """
    Check payment status using Platega.io API.
    
    Args:
        transaction_id: Transaction ID from Platega.io
        
    Returns:
        Dictionary with payment status
    """
    if PLATEGA_MERCHANT_ID == 'YOUR_MERCHANT_ID_HERE':
        # Simulation mode
        return {
            'success': True,
            'status': 'completed',  # completed, pending, failed
            'transaction_id': transaction_id,
            'simulated': True
        }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f'{PLATEGA_BASE_URL}api/{PLATEGA_API_VERSION}/transaction/{transaction_id}/status',
                headers=get_platega_headers(),
                timeout=30.0
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    'success': True,
                    'status': result.get('status'),
                    'amount': result.get('amount'),
                    'currency': result.get('currency'),
                }
            else:
                return {'success': False, 'error': f'Status check failed: {response.status_code}'}
                
    except Exception as e:
        logger.error(f"Error checking payment status: {e}")
        return {'success': False, 'error': str(e)}


@vpn_purchase_router.post("/platega/callback")
async def platega_payment_callback(request: Request):
    """
    Handle Platega.io payment callback/webhook.
    This endpoint receives notifications about payment status changes.
    
    According to Platega.io docs, they send POST requests with:
    - transaction_id
    - order_id
    - status
    - amount
    - signature (for verification)
    """
    try:
        data = await request.json()
        
        # Verify webhook signature if provided
        # signature = request.headers.get('X-Platega-Signature')
        # if signature and PLATEGA_SECRET_KEY != 'YOUR_SECRET_KEY_HERE':
        #     expected_signature = hmac.new(
        #         PLATEGA_SECRET_KEY.encode(),
        #         json.dumps(data, sort_keys=True).encode(),
        #         hashlib.sha256
        #     ).hexdigest()
        #     if signature != expected_signature:
        #         logger.warning("Invalid webhook signature")
        #         return JSONResponse({'error': 'Invalid signature'}, status_code=401)
        
        transaction_id = data.get('transaction_id') or data.get('id')
        order_id = data.get('order_id') or data.get('orderId')
        status = data.get('status')
        amount = data.get('amount')
        
        logger.info(f"Platega.io callback received: order={order_id}, status={status}, amount={amount}")
        
        # Update order status in database
        purchases = load_vpn_purchases()
        order_updated = False
        
        for i, purchase in enumerate(purchases):
            if purchase.get('order_id') == order_id or purchase.get('platega_transaction_id') == transaction_id:
                # Update order status based on payment status
                if status in ['completed', 'paid', 'success']:
                    purchases[i]['status'] = 'paid'
                    purchases[i]['paid_at'] = datetime.now().isoformat()
                    purchases[i]['platega_transaction_id'] = transaction_id
                    order_updated = True
                    
                    # Extend user's connection expiration
                    if purchase.get('connection_id'):
                        extend_connection_expiration(
                            purchase['connection_id'],
                            purchase['days']
                        )
                        
                elif status in ['failed', 'cancelled', 'expired']:
                    purchases[i]['status'] = 'cancelled'
                    order_updated = True
                    
                break
        
        if order_updated:
            save_vpn_purchases(purchases)
            logger.info(f"Order {order_id} updated to status: {status}")
        else:
            logger.warning(f"Order {order_id} not found for update")
        
        return JSONResponse({'status': 'ok'})
        
    except Exception as e:
        logger.error(f"Error processing Platega.io callback: {e}")
        return JSONResponse({'error': str(e)}, status_code=500)


def get_data_file_path():
    """Get path to data.json file."""
    return os.path.join(os.path.dirname(MODULE_DIR), 'data.json')


def load_vpn_purchases() -> list:
    """Load VPN purchases from data file."""
    data_file = get_data_file_path()
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('vpn_purchases', [])
        except Exception as e:
            logger.error(f"Error loading VPN purchases: {e}")
    return []


def save_vpn_purchases(purchases: list) -> bool:
    """Save VPN purchases to data file."""
    data_file = get_data_file_path()
    try:
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
        
        data['vpn_purchases'] = purchases
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving VPN purchases: {e}")
        return False


def load_trial_subscriptions() -> list:
    """Load trial subscriptions from data file."""
    data_file = get_data_file_path()
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('trial_subscriptions', [])
        except Exception as e:
            logger.error(f"Error loading trial subscriptions: {e}")
    return []


def save_trial_subscriptions(trials: list) -> bool:
    """Save trial subscriptions to data file."""
    data_file = get_data_file_path()
    try:
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}
        
        data['trial_subscriptions'] = trials
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving trial subscriptions: {e}")
        return False


def user_has_used_trial(user_id: int) -> bool:
    """Check if user has already used a trial subscription."""
    trials = load_trial_subscriptions()
    for trial in trials:
        if trial['user_id'] == user_id:
            return True
    return False


def validate_promocode(code: str) -> Optional[Dict[str, Any]]:
    """Validate promo code and return discount info."""
    if not code:
        return None
    
    code_upper = code.strip().upper()
    promo = PROMO_CODES.get(code_upper)
    
    if promo and promo['uses_count'] < promo['uses_limit']:
        return {
            'code': code_upper,
            'discount_percent': promo['discount_percent']
        }
    return None


def calculate_price(plan_id: str, promocode: Optional[str] = None) -> Dict[str, Any]:
    """Calculate final price with optional discount."""
    plan = VPN_PRICING.get(plan_id)
    if not plan:
        return {'error': 'Invalid plan'}
    
    base_price = plan['price']
    discount = 0
    discount_percent = 0
    
    if promocode:
        promo_info = validate_promocode(promocode)
        if promo_info:
            discount_percent = promo_info['discount_percent']
            discount = int(base_price * discount_percent / 100)
    
    final_price = base_price - discount
    
    return {
        'plan_id': plan_id,
        'base_price': base_price,
        'discount': discount,
        'discount_percent': discount_percent,
        'final_price': final_price,
        'days': plan['days'],
        'label': plan['label']
    }


@vpn_purchase_router.get("/purchase", response_class=HTMLResponse)
async def vpn_purchase_page(request: Request):
    """Render VPN purchase form page."""
    # Get user from session (integrated with main app's auth)
    # Try both 'user' and 'user_id' session keys for compatibility
    user = request.session.get('user')
    if not user:
        user_id = request.session.get('user_id')
        if not user_id:
            return RedirectResponse(url='/login', status_code=302)
        # Load user from data.json if only user_id is available
        data_file = get_data_file_path()
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for u in data.get('users', []):
                if u['id'] == user_id:
                    user = u
                    break
        if not user:
            return RedirectResponse(url='/login', status_code=302)
    
    # Load templates from main app
    templates_dir = os.path.join(os.path.dirname(MODULE_DIR), 'templates')
    templates = Jinja2Templates(directory=templates_dir)
    
    # Get language from cookies
    lang = request.cookies.get('lang', 'ru')
    
    # Load translations
    trans_file = os.path.join(os.path.dirname(MODULE_DIR), 'translations', f'{lang}.json')
    translations = {}
    if os.path.exists(trans_file):
        with open(trans_file, 'r', encoding='utf-8') as f:
            translations = json.load(f)
    
    def _(key):
        return translations.get(key, key)
    
    # Load site settings from data.json
    site_settings = {'title': 'Amnezia Panel', 'logo': '❤️', 'subtitle': 'Web Panel'}
    data_file = get_data_file_path()
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        site_settings = data.get('settings', {}).get('appearance', site_settings)
    
    context = {
        'request': request,
        'current_user': user,
        'lang': lang,
        'pricing': VPN_PRICING,
        'payment_methods': PAYMENT_METHODS,
        'site_settings': site_settings,
        'translations_json': json.dumps(translations),
        '_': _,
    }
    
    return templates.TemplateResponse('vpn_purchase.html', context)


@vpn_purchase_router.post("/calculate")
async def calculate_price_endpoint(
    request: Request,
    plan_id: str = Form(...),
    promocode: Optional[str] = Form(None)
):
    """Calculate price for selected plan with optional promocode."""
    result = calculate_price(plan_id, promocode)
    
    if 'error' in result:
        return JSONResponse({'error': result['error']}, status_code=400)
    
    return JSONResponse(result)


@vpn_purchase_router.post("/create_order")
async def create_order(
    request: Request,
    plan_id: str = Form(...),
    promocode: Optional[str] = Form(None),
    payment_method: str = Form(...)
):
    """Create a new VPN purchase order."""
    # Get user from session (compatible with both 'user' and 'user_id')
    user = request.session.get('user')
    if not user:
        user_id = request.session.get('user_id')
        if not user_id:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        # Load user from data.json
        data_file = get_data_file_path()
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for u in data.get('users', []):
                if u['id'] == user_id:
                    user = u
                    break
        if not user:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
    
    # Validate plan
    plan = VPN_PRICING.get(plan_id)
    if not plan:
        return JSONResponse({'error': 'Invalid plan'}, status_code=400)
    
    # Validate payment method
    payment = next((p for p in PAYMENT_METHODS if p['id'] == payment_method), None)
    if not payment or not payment['enabled']:
        return JSONResponse({'error': 'Invalid payment method'}, status_code=400)
    
    # Calculate final price
    price_info = calculate_price(plan_id, promocode)
    if 'error' in price_info:
        return JSONResponse({'error': price_info['error']}, status_code=400)
    
    # Create order
    order_id = f"VPN_{user['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    order = {
        'order_id': order_id,
        'user_id': user['id'],
        'username': user['username'],
        'plan_id': plan_id,
        'plan_label': plan['label'],
        'days': plan['days'],
        'base_price': price_info['base_price'],
        'discount': price_info['discount'],
        'discount_percent': price_info['discount_percent'],
        'promocode': promocode.upper() if promocode else None,
        'final_price': price_info['final_price'],
        'payment_method': payment_method,
        'payment_method_name': payment['name'],
        'status': 'pending',  # pending, paid, active, expired, cancelled
        'created_at': datetime.now().isoformat(),
        'expires_at': (datetime.now() + timedelta(days=plan['days'])).isoformat(),
        'payment_url': None,  # Will be filled by payment gateway
        # Fields for auto-provisioning module
        'provisioned': False,  # Flag: have access keys been issued?
        'provisioned_at': None,  # When access was issued
        'servers_count': 0,  # Total servers available
        'successful_connections': 0,  # How many connections were created
        'connection_id': None,  # Reference to user's connection
    }
    
    # Save order
    purchases = load_vpn_purchases()
    purchases.append(order)
    save_vpn_purchases(purchases)
    
    # Create payment link via Platega.io
    base_url = str(request.base_url).rstrip('/')
    payment_data = {
        'order_id': order_id,
        'amount': price_info['final_price'],
        'currency': 'RUB',
        'description': f"VPN Subscription: {plan['label']}",
        'success_url': f'{base_url}/vpn/payment/success?order_id={order_id}',
        'fail_url': f'{base_url}/vpn/payment/fail?order_id={order_id}',
        'customer_email': user.get('email', ''),
        'customer_name': user.get('username', ''),
    }
    
    # Call Platega.io API to create payment link
    platega_result = await platega_create_payment_link(payment_data)
    
    if platega_result.get('success'):
        # Update order with payment URL and transaction ID
        order['payment_url'] = platega_result.get('payment_url')
        order['platega_transaction_id'] = platega_result.get('transaction_id')
        
        # Update in storage
        for i, p in enumerate(purchases):
            if p['order_id'] == order_id:
                purchases[i] = order
                break
        save_vpn_purchases(purchases)
        
        # Return payment URL for redirect
        return JSONResponse({
            'success': True,
            'order_id': order_id,
            'payment_url': platega_result.get('payment_url'),
            'simulated': platega_result.get('simulated', False),
            'message': 'Заказ создан. Перенаправляем на оплату...'
        })
    else:
        # Payment link creation failed
        logger.error(f"Failed to create Platega.io payment link: {platega_result.get('error')}")
        return JSONResponse({
            'success': False,
            'error': 'Не удалось создать платежную ссылку. Попробуйте позже.',
            'details': platega_result.get('error')
        }, status_code=500)


@vpn_purchase_router.get("/my-orders")
async def my_orders(request: Request):
    """Get current user's VPN orders."""
    # Get user from session (compatible with both 'user' and 'user_id')
    user = request.session.get('user')
    if not user:
        user_id = request.session.get('user_id')
        if not user_id:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        # Load user from data.json
        data_file = get_data_file_path()
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for u in data.get('users', []):
                if u['id'] == user_id:
                    user = u
                    break
        if not user:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
    
    purchases = load_vpn_purchases()
    user_orders = [p for p in purchases if p['user_id'] == user['id']]
    
    # Sort by created_at descending
    user_orders.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Check trial eligibility
    has_used_trial = user_has_used_trial(user['id'])
    
    return JSONResponse({
        'orders': user_orders,
        'trial_used': has_used_trial,
        'trial_available': not has_used_trial
    })


@vpn_purchase_router.post("/activate_trial")
async def activate_trial_subscription(request: Request):
    """
    Activate a free 3-day trial subscription for the user.
    Can only be used once per user.
    Automatically triggers provisioning on all servers.
    """
    # Get user from session
    user = request.session.get('user')
    if not user:
        user_id = request.session.get('user_id')
        if not user_id:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
        # Load user from data.json
        data_file = get_data_file_path()
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for u in data.get('users', []):
                if u['id'] == user_id:
                    user = u
                    break
        if not user:
            return JSONResponse({'error': 'Unauthorized'}, status_code=401)
    
    # Check if user already used trial
    if user_has_used_trial(user['id']):
        return JSONResponse({
            'success': False,
            'error': 'Вы уже использовали тестовую подписку'
        }, status_code=400)
    
    # Create trial order
    order_id = f"TRIAL_{user['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    trial_days = TRIAL_SUBSCRIPTION['days']
    
    trial_order = {
        'order_id': order_id,
        'user_id': user['id'],
        'username': user['username'],
        'plan_id': 'trial',
        'plan_label': TRIAL_SUBSCRIPTION['description'],
        'days': trial_days,
        'base_price': 0,
        'discount': 0,
        'discount_percent': 0,
        'promocode': None,
        'final_price': 0,
        'payment_method': 'trial',
        'payment_method_name': 'Тестовый период',
        'status': 'paid',  # Auto-paid
        'is_trial': True,
        'created_at': datetime.now().isoformat(),
        'paid_at': datetime.now().isoformat(),
        'expires_at': (datetime.now() + timedelta(days=trial_days)).isoformat(),
        'payment_url': None,
        # Fields for auto-provisioning module
        'provisioned': False,
        'provisioned_at': None,
        'servers_count': 0,
        'successful_connections': 0,
        'connection_id': None,
    }
    
    # Save trial order
    purchases = load_vpn_purchases()
    purchases.append(trial_order)
    save_vpn_purchases(purchases)
    
    # Record that user has used trial
    trials = load_trial_subscriptions()
    trials.append({
        'user_id': user['id'],
        'username': user['username'],
        'order_id': order_id,
        'activated_at': datetime.now().isoformat(),
        'expires_at': trial_order['expires_at'],
        'days': trial_days,
    })
    save_trial_subscriptions(trials)
    
    logger.info(f"Trial subscription activated for user {user['id']} ({user['username']}), order: {order_id}")
    
    # Return success - auto-provisioning module will handle server access creation
    return JSONResponse({
        'success': True,
        'order_id': order_id,
        'days': trial_days,
        'message': f'Тестовая подписка на {trial_days} дня активирована! Доступы создаются...'
    })


@vpn_purchase_router.get("/payment/success")
async def payment_success(request: Request, order_id: str):
    """
    Handle successful payment redirect from Platega.io.
    Updates order status and extends subscription.
    """
    try:
        purchases = load_vpn_purchases()
        order_updated = False
        
        for i, purchase in enumerate(purchases):
            if purchase['order_id'] == order_id:
                # Verify payment status with Platega.io if transaction_id exists
                if purchase.get('platega_transaction_id'):
                    status_result = await platega_check_payment_status(
                        purchase['platega_transaction_id']
                    )
                    if not status_result.get('success') or status_result.get('status') not in ['completed', 'paid']:
                        logger.warning(f"Payment verification failed for order {order_id}")
                
                # Update order status
                purchases[i]['status'] = 'paid'
                purchases[i]['paid_at'] = datetime.now().isoformat()
                order_updated = True
                
                # Extend user's connection expiration
                if purchase.get('connection_id'):
                    extend_connection_expiration(
                        purchase['connection_id'],
                        purchase['days']
                    )
                break
        
        if order_updated:
            save_vpn_purchases(purchases)
        
        # Redirect to user cabinet with success message
        return RedirectResponse(url='/my-connections?payment=success', status_code=302)
        
    except Exception as e:
        logger.error(f"Error processing successful payment: {e}")
        return RedirectResponse(url='/my-connections?payment=error', status_code=302)


@vpn_purchase_router.get("/payment/fail")
async def payment_fail(request: Request, order_id: str):
    """
    Handle failed/cancelled payment redirect from Platega.io.
    """
    try:
        purchases = load_vpn_purchases()
        
        for i, purchase in enumerate(purchases):
            if purchase['order_id'] == order_id:
                purchases[i]['status'] = 'cancelled'
                break
        
        save_vpn_purchases(purchases)
        
        # Redirect to user cabinet with error message
        return RedirectResponse(url='/my-connections?payment=failed', status_code=302)
        
    except Exception as e:
        logger.error(f"Error processing failed payment: {e}")
        return RedirectResponse(url='/my-connections?payment=error', status_code=302)


def setup_vpn_purchase_module(app):
    """
    Setup VPN purchase module - call this from main app.py
    This function integrates the VPN purchase module with the main application.
    """
    app.include_router(vpn_purchase_router)
    logger.info("VPN Purchase Module loaded successfully")


# Helper function to get user's active subscriptions
def get_user_active_subscriptions(user_id: int) -> list:
    """Get all active VPN subscriptions for a user."""
    purchases = load_vpn_purchases()
    now = datetime.now()
    
    active = []
    for p in purchases:
        if p['user_id'] == user_id and p['status'] in ['paid', 'active']:
            expires = datetime.fromisoformat(p['expires_at'])
            if expires > now:
                active.append(p)
    
    return active


# Helper function to extend user's connection expiration
def extend_connection_expiration(connection_id: str, days: int) -> bool:
    """
    Extend the expiration date of a user's connection.
    This should be called after successful payment.
    """
    data_file = os.path.join(os.path.dirname(MODULE_DIR), 'data.json')
    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        connections = data.get('user_connections', [])
        for conn in connections:
            if conn['id'] == connection_id:
                current_expires = conn.get('expiration_date')
                if current_expires:
                    current_date = datetime.fromisoformat(current_expires[:10])
                else:
                    current_date = datetime.now()
                
                new_expires = current_date + timedelta(days=days)
                conn['expiration_date'] = new_expires.isoformat()[:10]
                break
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True
    except Exception as e:
        logger.error(f"Error extending connection expiration: {e}")
        return False
