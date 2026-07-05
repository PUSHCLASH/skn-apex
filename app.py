import os
import bcrypt
import hashlib
import base64
import json
import random
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')
CORS(app, supports_credentials=True)

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set")

# ============================================
# ADMIN CREDENTIALS
# ============================================

ADMIN_ID = "09082007"
ADMIN_PASSWORD = "48821"
ADMIN_FACE_HASH = None

def get_admin_face_hash():
    global ADMIN_FACE_HASH
    if ADMIN_FACE_HASH is None:
        try:
            with open('static/images/admin-face.png', 'rb') as f:
                image_data = f.read()
                ADMIN_FACE_HASH = hashlib.sha256(image_data).hexdigest()
        except:
            ADMIN_FACE_HASH = "admin-face-hash-placeholder"
    return ADMIN_FACE_HASH

# ============================================
# DATABASE
# ============================================

def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    conn.cursor_factory = psycopg2.extras.DictCursor
    return conn

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated

# ============================================
# STAR RATING ENGINE
# ============================================

def calculate_stars(user):
    car_type = user.get('car_type', 'hatchback')
    car_model = user.get('car_model', '').lower()
    
    luxury_cars = ['bmw', 'mercedes', 'audi', 'porsche', 'jaguar', 'land rover', 'volvo', 'lexus']
    suv_cars = ['creta', 'seltos', 'harrier', 'safari', 'fortuner', 'scorpio', 'xuv', 'compass']
    sedan_cars = ['city', 'verna', 'civic', 'elantra', 'superb', 'octavia']
    
    stars = 1
    
    if any(car in car_model for car in luxury_cars):
        stars = 5
    elif car_type == 'suv' or any(car in car_model for car in suv_cars):
        stars = 4
    elif car_type == 'sedan' or any(car in car_model for car in sedan_cars):
        stars = 3
    elif car_type == 'hatchback':
        stars = 2
    else:
        stars = 1
    
    if user.get('is_vip', False):
        stars += 1
    if user.get('subscription_type'):
        stars += 1
    
    return min(stars, 7)

# ============================================
# WHATSAPP NOTIFICATION (Placeholder)
# ============================================

def send_whatsapp(phone, message):
    print(f"WhatsApp to {phone}: {message}")
    return True

# ============================================
# TERMS & CONDITIONS DATA
# ============================================

TERMS_DATA = {
    'title': 'Terms & Conditions',
    'content': """
1. Acceptance of Terms
By using SKN APEX, you agree to these terms.

2. User Account
You are responsible for maintaining account security.

3. Subscription & Payments
All subscriptions are non-refundable after 7 days.

4. Privacy
Your data is protected and not shared with third parties.

5. Code of Conduct
Use the app responsibly. Misuse results in termination.

6. Termination
We reserve the right to terminate accounts.

7. Updates
Terms may be updated with prior notice.

8. Contact
For queries: +91 8950592855
"""
}

PRIVACY_DATA = {
    'title': 'Privacy Policy',
    'content': """
1. Data Collection
We collect name, email, phone, and car details.

2. Data Usage
Used for queue, payments, and communication.

3. Data Security
Encrypted and stored securely.

4. No Sharing
We do not share data with third parties.

5. User Rights
You can request data deletion.

6. Cookies
Used for session management.

7. Contact
For privacy: +91 8950592855
"""
}

# ============================================
# PAGE ROUTES
# ============================================

@app.route('/')
def index():
    return render_template('welcome.html')

@app.route('/register')
def register_page():
    return render_template('register.html', terms=TERMS_DATA, privacy=PRIVACY_DATA)

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/logout')
def logout_page():
    session.clear()
    return redirect('/')

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    return render_template('dashboard.html', user=user)

@app.route('/profile')
@login_required
def profile_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/queue')
@login_required
def queue_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    return render_template('queue.html', user=user)

@app.route('/payment')
@login_required
def payment_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    return render_template('payment.html', user=user)

@app.route('/subscriptions')
@login_required
def subscriptions_page():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    return render_template('subscriptions.html', user=user)

@app.route('/terms')
def terms_page():
    return render_template('terms.html', data=TERMS_DATA)

@app.route('/privacy')
def privacy_page():
    return render_template('privacy.html', data=PRIVACY_DATA)

@app.route('/worker-login')
def worker_login_page():
    return render_template('worker_login.html')

@app.route('/worker-dashboard')
def worker_dashboard():
    if 'worker_id' not in session:
        return redirect('/worker-login')
    return render_template('worker_dashboard.html')

@app.route('/admin-login')
def admin_login_page():
    return render_template('admin_login.html')

@app.route('/admin-dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM users')
    total_users = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM fillups')
    total_fillups = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM users WHERE is_vip = true')
    vip_users = cur.fetchone()[0]
    
    cur.execute("SELECT subscription_type, COUNT(*) FROM users WHERE subscription_type IS NOT NULL GROUP BY subscription_type")
    subscriptions = cur.fetchall()
    
    cur.execute('SELECT name, car_number, created_at FROM users ORDER BY created_at DESC LIMIT 10')
    recent_users = cur.fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
        total_users=total_users,
        total_fillups=total_fillups,
        vip_users=vip_users,
        subscriptions=subscriptions,
        recent_users=recent_users
    )

# ============================================
# API ROUTES
# ============================================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')
    car_number = data.get('car_number').upper()
    car_model = data.get('car_model')
    car_type = data.get('car_type')
    terms_accepted = data.get('terms_accepted', False)

    if not terms_accepted:
        return jsonify({'error': 'You must accept Terms & Conditions'}), 400

    if not name or not email or not phone or not password or not car_number:
        return jsonify({'error': 'All fields required'}), 400

    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Email already registered'}), 400
    
    cur.execute('SELECT * FROM users WHERE car_number = %s', (car_number,))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Car number already registered'}), 400

    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    cur.execute('''
        INSERT INTO users (name, email, phone, password_hash, car_number, car_model, car_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (name, email, phone, password_hash, car_number, car_model, car_type))
    user_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    session['user_id'] = user_id
    
    send_whatsapp(phone, f"Welcome to SKN APEX, {name}!")
    
    return jsonify({
        'status': 'success',
        'user': {'id': user_id, 'name': name, 'email': email}
    })

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    user = cur.fetchone()
    conn.close()

    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401

    if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return jsonify({'error': 'Invalid credentials'}), 401

    session['user_id'] = user['id']
    return jsonify({
        'status': 'success',
        'user': {'id': user['id'], 'name': user['name'], 'email': user['email']}
    })

@app.route('/api/profile', methods=['GET'])
@login_required
def get_profile():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    
    stars = calculate_stars(user)
    
    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'email': user['email'],
        'phone': user['phone'],
        'car_number': user['car_number'],
        'car_model': user['car_model'],
        'car_type': user['car_type'],
        'star_rating': stars,
        'credits': user.get('credits', 0),
        'subscription_type': user.get('subscription_type'),
        'subscription_end': user.get('subscription_end'),
        'is_vip': user.get('is_vip', False),
        'profile_photo': user.get('profile_photo')
    })

@app.route('/api/update-profile', methods=['POST'])
@login_required
def update_profile():
    data = request.get_json()
    name = data.get('name')
    phone = data.get('phone')
    car_model = data.get('car_model')
    car_type = data.get('car_type')
    profile_photo = data.get('profile_photo')
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET name = COALESCE(%s, name),
            phone = COALESCE(%s, phone),
            car_model = COALESCE(%s, car_model),
            car_type = COALESCE(%s, car_type),
            profile_photo = COALESCE(%s, profile_photo)
        WHERE id = %s
        RETURNING id
    ''', (name, phone, car_model, car_type, profile_photo, session['user_id']))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/api/queue/status', methods=['GET'])
def queue_status():
    return jsonify({
        'total': random.randint(5, 20),
        'waiting': [
            {'position': i, 'car_number': f'DL 01 AB {1000+i}', 'status': 'waiting'} 
            for i in range(1, random.randint(6, 15))
        ],
        'serving': [{'position': 1, 'car_number': 'DL 01 AB 1001', 'status': 'serving'}],
        'completed': []
    })

@app.route('/api/queue/join', methods=['POST'])
@login_required
def join_queue():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT credits FROM users WHERE id = %s', (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    
    credits = user['credits'] if user and user['credits'] else 0
    
    if credits <= 0:
        return jsonify({'error': 'No credits. Please subscribe.'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE users SET credits = credits - 1 WHERE id = %s RETURNING credits', (session['user_id'],))
    updated = cur.fetchone()
    conn.commit()
    conn.close()
    
    token = random.randint(100, 999)
    position = random.randint(2, 10)
    wait_time = position * 2
    
    return jsonify({
        'status': 'success',
        'token': token,
        'position': position,
        'estimated_wait': wait_time,
        'credits_remaining': updated['credits'] if updated else 0
    })

# ============================================
# SUBSCRIPTION (SIMPLE UPI - NO RAZORPAY)
# ============================================

PLANS = {
    'weekly': {'name': 'Weekly', 'price': 999, 'credits': 2, 'days': 7, 'savings': '33%'},
    'monthly': {'name': 'Monthly', 'price': 2999, 'credits': 8, 'days': 30, 'savings': '50%'},
    '3month': {'name': '3-Month', 'price': 7999, 'credits': 28, 'days': 90, 'savings': '62%'}
}

@app.route('/api/subscription/plans', methods=['GET'])
def get_plans():
    return jsonify(PLANS)

@app.route('/api/subscription/subscribe', methods=['POST'])
@login_required
def subscribe():
    data = request.get_json()
    plan_id = data.get('plan_id')
    
    if plan_id not in PLANS:
        return jsonify({'error': 'Invalid plan'}), 400
    
    plan = PLANS[plan_id]
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET credits = credits + %s, 
            subscription_type = %s,
            subscription_end = %s,
            is_vip = TRUE
        WHERE id = %s
        RETURNING credits, phone, name, car_number
    ''', (plan['credits'], plan_id, (datetime.now() + timedelta(days=plan['days'])).date(), session['user_id']))
    updated = cur.fetchone()
    conn.commit()
    conn.close()
    
    # Send WhatsApp notification
    phone = updated['phone'] if updated else ''
    message = f"🎉 SKN APEX Subscription Confirmed!\nPlan: {plan['name']}\nCredits: {plan['credits']}\nAmount: ₹{plan['price']}\nThank you!"
    send_whatsapp(phone, message)
    
    return jsonify({
        'status': 'success',
        'credits': updated['credits'] if updated else 0,
        'valid_until': (datetime.now() + timedelta(days=plan['days'])).isoformat()
    })

@app.route('/api/ai-assistant', methods=['GET'])
@login_required
def ai_assistant():
    messages = [
        "💡 Tip: Use your credits wisely! Each queue join uses 1 credit.",
        "🚀 Upgrade to VIP for priority service!",
        "📊 Track your fuel usage in your profile.",
        "🎯 Set a daily goal and track your progress!",
        "🔔 Enable notifications for real-time queue updates.",
        "💎 Subscribe to monthly plan and save 50%!"
    ]
    return jsonify({'message': random.choice(messages)})

# ============================================
# ADMIN & WORKER LOGIN
# ============================================

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    admin_id = data.get('admin_id')
    password = data.get('password')

    if admin_id != ADMIN_ID or password != ADMIN_PASSWORD:
        return jsonify({'error': 'Invalid admin credentials'}), 401

    face_data = data.get('face_data')
    if not face_data:
        return jsonify({'error': 'Face verification required'}), 401

    try:
        face_bytes = base64.b64decode(face_data.split(',')[1])
        face_hash = hashlib.sha256(face_bytes).hexdigest()
        stored_hash = get_admin_face_hash()
        
        session['is_admin'] = True
        session['admin_id'] = admin_id
        
        return jsonify({'status': 'success', 'message': 'Admin login successful'})
    except Exception as e:
        return jsonify({'error': 'Face verification failed'}), 401

@app.route('/api/worker/login', methods=['POST'])
def worker_login():
    data = request.get_json()
    worker_id = data.get('worker_id')
    password = data.get('password')
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM workers WHERE worker_id = %s AND password_hash = %s', 
                (worker_id, hashlib.md5(password.encode()).hexdigest()))
    worker = cur.fetchone()
    conn.close()
    
    if not worker:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    session['worker_id'] = worker['id']
    return jsonify({'status': 'success', 'worker': dict(worker)})

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
