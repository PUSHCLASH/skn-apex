import os
import time
import json
import jwt
import bcrypt
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from threading import Lock

# ============================================
# APP INITIALIZATION
# ============================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this')
CORS(app)

# ============================================
# DATABASE CONNECTION
# ============================================

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, sslmode='require')
        g.db.cursor_factory = psycopg2.extras.DictCursor
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db:
        db.close()

# ============================================
# JWT AUTHENTICATION HELPERS
# ============================================

def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token required'}), 401
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            cur = get_db().cursor()
            cur.execute('SELECT * FROM users WHERE id = %s', (data['user_id'],))
            current_user = cur.fetchone()
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def get_user_by_email(email):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    return cur.fetchone()

def get_user_by_car(car_number):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE car_number = %s', (car_number,))
    return cur.fetchone()

def get_user_by_id(user_id):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    return cur.fetchone()

# ============================================
# STAR RATING ENGINE
# ============================================

def calculate_star_rating(user_data):
    stars = 1
    reasons = []
    car_type = user_data.get('car_type', 'hatchback')
    if car_type == 'luxury':
        stars = 3
        reasons.append("Luxury car owner")
    elif car_type == 'suv':
        stars = 2
        reasons.append("SUV owner")
    elif car_type == 'sedan':
        stars = 2
        reasons.append("Sedan owner")
    else:
        stars = 1
        reasons.append("Hatchback owner")
    if user_data.get('subscription_type'):
        stars += 1
        reasons.append("Active subscriber")
    if user_data.get('total_fillups', 0) >= 50:
        stars += 1
        reasons.append("50+ fill-ups")
    elif user_data.get('total_fillups', 0) >= 20:
        stars += 0.5
        reasons.append("20+ fill-ups")
    stars = min(int(stars), 7)
    return stars, reasons

# ============================================
# PAGE ROUTES (SERVING HTML)
# ============================================

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/register')
def register_page():
    return render_template('register.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/dashboard')
@token_required
def dashboard_page(current_user):
    return render_template('dashboard.html', user=current_user)

@app.route('/profile')
@token_required
def profile_page(current_user):
    return render_template('profile.html', user=current_user)

@app.route('/queue')
@token_required
def queue_page(current_user):
    return render_template('queue.html', user=current_user)

@app.route('/payment')
@token_required
def payment_page(current_user):
    return render_template('payment.html', user=current_user)

@app.route('/subscriptions')
@token_required
def subscriptions_page(current_user):
    return render_template('subscriptions.html', user=current_user)

# ============================================
# API: REGISTER (POST)
# ============================================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    car_number = data.get('car_number', '').strip().upper()
    car_model = data.get('car_model', '').strip()
    car_type = data.get('car_type', 'hatchback')

    if not name or not email or not phone or not password or not car_number:
        return jsonify({'error': 'All fields are required'}), 400
    if '@' not in email:
        return jsonify({'error': 'Invalid email'}), 400

    if get_user_by_email(email):
        return jsonify({'error': 'Email already registered'}), 400
    if get_user_by_car(car_number):
        return jsonify({'error': 'Car number already registered'}), 400

    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    cur = get_db().cursor()
    cur.execute('''
        INSERT INTO users (name, email, phone, password_hash, car_number, car_model, car_type, join_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, email, phone, password_hash, car_number, car_model, car_type, datetime.now(timezone.utc).date()))
    user_id = cur.fetchone()[0]
    get_db().commit()

    token = generate_token(user_id)
    return jsonify({
        'status': 'success',
        'token': token,
        'user': {
            'id': user_id,
            'name': name,
            'email': email,
            'phone': phone,
            'car_number': car_number,
            'car_model': car_model,
            'car_type': car_type
        }
    })

# ============================================
# API: LOGIN (POST)
# ============================================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    email = data.get('email', '').strip()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    user = get_user_by_email(email)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401

    if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'Invalid credentials'}), 401

    stars, reasons = calculate_star_rating(dict(user))
    token = generate_token(user['id'])

    return jsonify({
        'status': 'success',
        'token': token,
        'user': {
            'id': user['id'],
            'name': user['name'],
            'email': user['email'],
            'phone': user['phone'],
            'car_number': user['car_number'],
            'car_model': user['car_model'],
            'car_type': user['car_type'],
            'star_rating': stars,
            'star_reason': reasons[0] if reasons else '',
            'credits': user.get('credits', 0),
            'subscription_type': user.get('subscription_type'),
            'is_vip': user.get('is_vip', False)
        }
    })

# ============================================
# API: PROFILE (GET)
# ============================================

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    user = dict(current_user)
    stars, reasons = calculate_star_rating(user)
    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'email': user['email'],
        'phone': user['phone'],
        'car_number': user['car_number'],
        'car_model': user['car_model'],
        'car_type': user['car_type'],
        'join_date': user['join_date'],
        'star_rating': stars,
        'star_reason': reasons,
        'credits': user.get('credits', 0),
        'subscription_type': user.get('subscription_type'),
        'subscription_end': user.get('subscription_end'),
        'total_fillups': user.get('total_fillups', 0),
        'is_vip': user.get('is_vip', False)
    })

# ============================================
# QUEUE SYSTEM (In-Memory - for quick start)
# ============================================

active_queue = []
queue_lock = Lock()
queue_counter = 0

@app.route('/api/queue/join', methods=['POST'])
@token_required
def join_queue(current_user):
    global active_queue, queue_counter
    with queue_lock:
        # Check if already in queue
        for item in active_queue:
            if item['user_id'] == current_user['id'] and item['status'] == 'waiting':
                return jsonify({'error': 'Already in queue'}), 400
        queue_counter += 1
        token = queue_counter
        active_queue.append({
            'user_id': current_user['id'],
            'car_number': current_user['car_number'],
            'name': current_user['name'],
            'token': token,
            'joined_at': datetime.now(timezone.utc).isoformat(),
            'status': 'waiting'
        })
    position = len([q for q in active_queue if q['status'] == 'waiting'])
    estimated_wait = position * 2
    return jsonify({
        'status': 'success',
        'token': token,
        'position': position,
        'estimated_wait': estimated_wait
    })

@app.route('/api/queue/status', methods=['GET'])
def get_queue_status():
    with queue_lock:
        waiting = [q for q in active_queue if q['status'] == 'waiting']
        serving = [q for q in active_queue if q['status'] == 'serving']
        completed = [q for q in active_queue if q['status'] == 'completed']
    return jsonify({
        'total': len(waiting) + len(serving),
        'waiting': waiting,
        'serving': serving,
        'completed': completed
    })

@app.route('/api/queue/next', methods=['POST'])
@token_required
def next_in_queue(current_user):
    if not current_user.get('is_admin') and not current_user.get('is_staff'):
        return jsonify({'error': 'Unauthorized'}), 403
    with queue_lock:
        for q in active_queue:
            if q['status'] == 'waiting':
                q['status'] = 'serving'
                return jsonify({'status': 'success', 'serving': q})
    return jsonify({'error': 'No cars waiting'}), 400

@app.route('/api/queue/complete', methods=['POST'])
@token_required
def complete_queue(current_user):
    if not current_user.get('is_admin') and not current_user.get('is_staff'):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    if not data or 'token' not in data:
        return jsonify({'error': 'Token required'}), 400
    token = data.get('token')
    with queue_lock:
        for q in active_queue:
            if q['token'] == token and q['status'] == 'serving':
                q['status'] = 'completed'
                cur = get_db().cursor()
                cur.execute('UPDATE users SET total_fillups = total_fillups + 1 WHERE id = %s', (q['user_id'],))
                get_db().commit()
                return jsonify({'status': 'success'})
    return jsonify({'error': 'Car not found or not serving'}), 404

# ============================================
# SUBSCRIPTION PLANS (Pricing & Features)
# ============================================

PLANS = {
    'weekly': {
        'name': 'Weekly',
        'price': 999,
        'credits': 2,
        'days': 7,
        'features': ['2 fill-ups', 'Skip queue', 'Priority service', 'Soft drink']
    },
    'monthly': {
        'name': 'Monthly',
        'price': 2999,
        'credits': 8,
        'days': 30,
        'features': ['8 fill-ups', 'Skip queue', 'Priority service', 'VIP badge', 'Soft drink']
    },
    '3month': {
        'name': '3-Month',
        'price': 7999,
        'credits': 28,
        'days': 90,
        'features': ['28 fill-ups', 'Skip queue', 'Priority service', 'VIP badge', 'Soft drink', 'Free check-up']
    }
}

@app.route('/api/subscription/plans', methods=['GET'])
def get_plans():
    return jsonify(PLANS)

@app.route('/api/subscription/subscribe', methods=['POST'])
@token_required
def subscribe(current_user):
    data = request.get_json()
    if not data or 'plan_id' not in data:
        return jsonify({'error': 'Plan ID required'}), 400
    plan_id = data.get('plan_id')
    if plan_id not in PLANS:
        return jsonify({'error': 'Invalid plan'}), 400
    plan = PLANS[plan_id]

    cur = get_db().cursor()
    cur.execute('''
        UPDATE users 
        SET subscription_type = %s, 
            subscription_end = %s, 
            credits = credits + %s,
            is_vip = TRUE
        WHERE id = %s
        RETURNING credits
    ''', (plan_id, datetime.now(timezone.utc) + timedelta(days=plan['days']), plan['credits'], current_user['id']))
    updated = cur.fetchone()
    get_db().commit()

    return jsonify({
        'status': 'success',
        'plan': plan_id,
        'credits': updated['credits'] if updated else 0,
        'valid_until': (datetime.now(timezone.utc) + timedelta(days=plan['days'])).isoformat()
    })

# ============================================
# UPI PAYMENT INFO (GET)
# ============================================

@app.route('/api/payment/upi', methods=['GET'])
@token_required
def get_upi_info(current_user):
    return jsonify({
        'upi_id': 'your-upi-id@bank',
        'qr_code_url': '/static/images/upi-qr.png',
        'amount': request.args.get('amount', 0)
    })

# ============================================
# HEALTH CHECK
# ============================================

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

# ============================================
# START THE APP
# ============================================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
