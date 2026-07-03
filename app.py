import os
import time
import json
import hashlib
import jwt
import bcrypt
import qrcode
import base64
from io import BytesIO
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, request, jsonify, render_template, send_file, g
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from threading import Lock
import requests
import razorpay

# ============================================
# APP INITIALIZATION
# ============================================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-this')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ============================================
# RAZORPAY INITIALIZATION
# ============================================

RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET')
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID else None

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
# JWT AUTHENTICATION
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
            current_user = get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def get_user_by_id(user_id):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    return cur.fetchone()

def get_user_by_email(email):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    return cur.fetchone()

def get_user_by_car(car_number):
    cur = get_db().cursor()
    cur.execute('SELECT * FROM users WHERE car_number = %s', (car_number,))
    return cur.fetchone()

# ============================================
# STAR RATING ENGINE
# ============================================

def calculate_star_rating(user_data):
    """Calculate star rating based on user profile"""
    stars = 0
    reasons = []
    
    # Base stars based on car type
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
    
    # Bonus for subscription
    if user_data.get('subscription_active', False):
        stars += 1
        reasons.append("Active subscriber")
    
    # Bonus for VIP
    if user_data.get('is_vip', False):
        stars += 1
        reasons.append("VIP member")
    
    # Bonus for loyalty
    total_fillups = user_data.get('total_fillups', 0)
    if total_fillups >= 50:
        stars += 1
        reasons.append("50+ fill-ups")
    elif total_fillups >= 20:
        stars += 0.5
        reasons.append("20+ fill-ups")
    
    # Cap at 7 stars
    stars = min(int(stars), 7)
    return stars, reasons

# ============================================
# SUBSCRIPTION & CREDIT SYSTEM
# ============================================

def get_user_credits(user_id):
    """Get user's available credits"""
    cur = get_db().cursor()
    cur.execute('''
        SELECT credits, subscription_type, subscription_end 
        FROM users WHERE id = %s
    ''', (user_id,))
    row = cur.fetchone()
    if row:
        return {
            'credits': row['credits'] if row['credits'] else 0,
            'subscription_type': row['subscription_type'],
            'subscription_end': row['subscription_end']
        }
    return {'credits': 0, 'subscription_type': None, 'subscription_end': None}

def use_credit(user_id):
    """Use one credit and update user"""
    cur = get_db().cursor()
    cur.execute('UPDATE users SET credits = credits - 1 WHERE id = %s AND credits > 0 RETURNING credits', (user_id,))
    updated = cur.fetchone()
    get_db().commit()
    return updated

def rollover_credits(user_id):
    """Rollover unused credits to next period"""
    cur = get_db().cursor()
    cur.execute('SELECT credits, subscription_type FROM users WHERE id = %s', (user_id,))
    row = cur.fetchone()
    if row:
        credits = row['credits'] if row['credits'] else 0
        if credits > 0:
            cur.execute('UPDATE users SET credits = credits + %s WHERE id = %s', (credits, user_id))
            get_db().commit()
            return True
    return False

# ============================================
# QR CODE GENERATION
# ============================================

def generate_qr(data):
    """Generate QR code for payment"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

# ============================================
# AUTH ROUTES
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

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    car_number = data.get('car_number', '').strip().upper()
    car_model = data.get('car_model', '').strip()
    car_type = data.get('car_type', 'hatchback')
    
    # Validation
    if not name or not email or not phone or not password or not car_number:
        return jsonify({'error': 'All fields are required'}), 400
    
    if not email or '@' not in email:
        return jsonify({'error': 'Invalid email'}), 400
    
    # Check existing
    if get_user_by_email(email):
        return jsonify({'error': 'Email already registered'}), 400
    
    if get_user_by_car(car_number):
        return jsonify({'error': 'Car number already registered'}), 400
    
    # Hash password
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    # Insert user
    cur = get_db().cursor()
    cur.execute('''
        INSERT INTO users (name, email, phone, password_hash, car_number, car_model, car_type, join_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (name, email, phone, password_hash, car_number, car_model, car_type, datetime.now(timezone.utc).date()))
    
    user_id = cur.fetchone()[0]
    get_db().commit()
    
    # Generate token
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

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    
    user = get_user_by_email(email)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Verify password
    if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Calculate stars
    user_data = dict(user)
    stars, reasons = calculate_star_rating(user_data)
    
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

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    user = dict(current_user)
    stars, reasons = calculate_star_rating(user)
    credits = get_user_credits(user['id'])
    
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
        'credits': credits['credits'],
        'subscription_type': credits['subscription_type'],
        'subscription_end': credits['subscription_end'],
        'total_fillups': user.get('total_fillups', 0),
        'is_vip': user.get('is_vip', False)
    })

# ============================================
# QUEUE MANAGEMENT (LIVE)
# ============================================

# In-memory queue (will be replaced with Redis in production)
active_queue = []
queue_lock = Lock()
queue_position = {}

@app.route('/api/queue/join', methods=['POST'])
@token_required
def join_queue(current_user):
    global active_queue, queue_position
    
    # Check if already in queue
    with queue_lock:
        if current_user['id'] in queue_position:
            return jsonify({'error': 'Already in queue'}), 400
        
        # Check credits
        credits = get_user_credits(current_user['id'])
        if credits['credits'] <= 0 and not credits['subscription_type']:
            return jsonify({'error': 'No credits available. Please subscribe or pay.'}), 400
        
        # Assign token
        token = len(active_queue) + 1
        active_queue.append({
            'user_id': current_user['id'],
            'car_number': current_user['car_number'],
            'name': current_user['name'],
            'token': token,
            'joined_at': datetime.now(timezone.utc).isoformat(),
            'status': 'waiting'
        })
        queue_position[current_user['id']] = token
    
    # Use one credit if not subscribed
    if not credits['subscription_type']:
        use_credit(current_user['id'])
    
    # Broadcast update
    socketio.emit('queue_update', get_queue_data())
    
    return jsonify({
        'status': 'success',
        'token': token,
        'position': len(active_queue),
        'estimated_wait': len(active_queue) * 3  # 3 minutes per car
    })

@app.route('/api/queue/status', methods=['GET'])
def get_queue_status():
    return jsonify(get_queue_data())

def get_queue_data():
    with queue_lock:
        return {
            'total': len(active_queue),
            'waiting': [q for q in active_queue if q['status'] == 'waiting'],
            'serving': [q for q in active_queue if q['status'] == 'serving'],
            'completed': [q for q in active_queue if q['status'] == 'completed']
        }

@socketio.on('queue_poll')
def handle_queue_poll():
    emit('queue_update', get_queue_data())

@app.route('/api/queue/next', methods=['POST'])
@token_required
def next_in_queue(current_user):
    global active_queue
    
    with queue_lock:
        if current_user.get('is_admin') or current_user.get('is_staff'):
            for q in active_queue:
                if q['status'] == 'waiting':
                    q['status'] = 'serving'
                    socketio.emit('queue_update', get_queue_data())
                    return jsonify({'status': 'success', 'serving': q})
    return jsonify({'error': 'No cars waiting or unauthorized'}), 400

# ============================================
# PAYMENT ROUTES
# ============================================

@app.route('/api/create-order', methods=['POST'])
@token_required
def create_payment_order(current_user):
    data = request.get_json()
    amount = data.get('amount', 0)
    
    if amount <= 0:
        return jsonify({'error': 'Invalid amount'}), 400
    
    if not razorpay_client:
        return jsonify({'error': 'Payment gateway not configured'}), 500
    
    try:
        order = razorpay_client.order.create({
            'amount': amount * 100,  # Convert to paise
            'currency': 'INR',
            'payment_capture': 1,
            'receipt': f'order_{datetime.now().timestamp()}'
        })
        return jsonify({
            'order_id': order['id'],
            'amount': amount,
            'currency': 'INR'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/payment-webhook', methods=['POST'])
def payment_webhook():
    data = request.get_json()
    # Verify signature (implement proper verification)
    
    payment_id = data.get('payload', {}).get('payment', {}).get('entity', {}).get('id')
    order_id = data.get('payload', {}).get('order', {}).get('entity', {}).get('id')
    
    if payment_id and order_id:
        # Update payment status in database
        # Send receipt via WhatsApp
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'failed'}), 400

# ============================================
# SUBSCRIPTION ROUTES
# ============================================

SUBSCRIPTION_PLANS = {
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
    return jsonify(SUBSCRIPTION_PLANS)

@app.route('/api/subscription/subscribe', methods=['POST'])
@token_required
def subscribe(current_user):
    data = request.get_json()
    plan_id = data.get('plan_id')
    payment_id = data.get('payment_id')
    
    if plan_id not in SUBSCRIPTION_PLANS:
        return jsonify({'error': 'Invalid plan'}), 400
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    # Activate subscription
    cur = get_db().cursor()
    cur.execute('''
        UPDATE users 
        SET subscription_type = %s, 
            subscription_end = %s, 
            credits = credits + %s,
            is_vip = TRUE
        WHERE id = %s
    ''', (plan_id, datetime.now(timezone.utc) + timedelta(days=plan['days']), plan['credits'], current_user['id']))
    get_db().commit()
    
    return jsonify({
        'status': 'success',
        'plan': plan_id,
        'credits': plan['credits'],
        'valid_until': (datetime.now(timezone.utc) + timedelta(days=plan['days'])).isoformat()
    })

# ============================================
# ADMIN ROUTES
# ============================================

@app.route('/api/admin/workers', methods=['POST'])
@token_required
def add_worker(current_user):
    if not current_user.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    cur = get_db().cursor()
    cur.execute('''
        INSERT INTO workers (name, phone, role, specialization, experience_years, rank_level)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    ''', (data['name'], data['phone'], data['role'], data['specialization'], data['experience_years'], data['rank_level']))
    worker_id = cur.fetchone()[0]
    get_db().commit()
    
    return jsonify({'status': 'success', 'worker_id': worker_id})

@app.route('/api/admin/schedule', methods=['POST'])
@token_required
def create_schedule(current_user):
    if not current_user.get('is_admin'):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    cur = get_db().cursor()
    cur.execute('''
        INSERT INTO worker_schedules (worker_id, shift_date, shift_start, shift_end, shift_type)
        VALUES (%s, %s, %s, %s, %s)
    ''', (data['worker_id'], data['shift_date'], data['shift_start'], data['shift_end'], data['shift_type']))
    get_db().commit()
    
    return jsonify({'status': 'success'})

# ============================================
# TEMPLATE ROUTES
# ============================================

@app.route('/dashboard')
@token_required
def dashboard(current_user):
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
    return render_template('subscriptions.html', user=current_user, plans=SUBSCRIPTION_PLANS)

@app.route('/workers')
@token_required
def workers_page(current_user):
    return render_template('workers.html', user=current_user)

@app.route('/schedule')
@token_required
def schedule_page(current_user):
    return render_template('schedule.html', user=current_user)

@app.route('/admin')
@token_required
def admin_page(current_user):
    return render_template('admin.html', user=current_user)

# ============================================
# START APP
# ============================================

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
