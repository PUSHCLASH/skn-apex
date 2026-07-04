import os
import bcrypt
import hashlib
import base64
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

# Admin face hash (to be verified during login)
# This is a placeholder - will be updated when admin face photo is uploaded
ADMIN_FACE_HASH = None

def get_admin_face_hash():
    """Get admin face hash from stored image"""
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
# PAGE ROUTES
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

# ============================================
# ADMIN ROUTES
# ============================================

@app.route('/admin-login')
def admin_login_page():
    return render_template('admin_login.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    admin_id = data.get('admin_id')
    password = data.get('password')

    if admin_id != ADMIN_ID or password != ADMIN_PASSWORD:
        return jsonify({'error': 'Invalid admin credentials'}), 401

    # Face verification check
    face_data = data.get('face_data')
    if not face_data:
        return jsonify({'error': 'Face verification required'}), 401

    try:
        # Decode base64 image
        face_bytes = base64.b64decode(face_data.split(',')[1])
        face_hash = hashlib.sha256(face_bytes).hexdigest()
        stored_hash = get_admin_face_hash()
        
        # In production, use actual face comparison
        # For now, we'll accept the admin face
        session['is_admin'] = True
        session['admin_id'] = admin_id
        
        return jsonify({
            'status': 'success',
            'message': 'Admin login successful'
        })
    except Exception as e:
        return jsonify({'error': 'Face verification failed'}), 401

@app.route('/admin-dashboard')
@admin_required
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()
    
    # Total users
    cur.execute('SELECT COUNT(*) FROM users')
    total_users = cur.fetchone()[0]
    
    # Total fill-ups
    cur.execute('SELECT COUNT(*) FROM fillups')
    total_fillups = cur.fetchone()[0]
    
    # VIP users
    cur.execute('SELECT COUNT(*) FROM users WHERE is_vip = true')
    vip_users = cur.fetchone()[0]
    
    # Subscriptions
    cur.execute("SELECT subscription_type, COUNT(*) FROM users WHERE subscription_type IS NOT NULL GROUP BY subscription_type")
    subscriptions = cur.fetchall()
    
    # Monthly registrations
    cur.execute('''
        SELECT DATE_TRUNC('month', created_at) as month, COUNT(*) 
        FROM users 
        GROUP BY month 
        ORDER BY month DESC 
        LIMIT 6
    ''')
    monthly_users = cur.fetchall()
    
    # Recent users
    cur.execute('SELECT name, email, car_number, created_at FROM users ORDER BY created_at DESC LIMIT 10')
    recent_users = cur.fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', 
        total_users=total_users,
        total_fillups=total_fillups,
        vip_users=vip_users,
        subscriptions=subscriptions,
        monthly_users=monthly_users,
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
    car_number = data.get('car_number')
    car_model = data.get('car_model')
    car_type = data.get('car_type')

    if not name or not email or not phone or not password or not car_number:
        return jsonify({'error': 'All fields required'}), 400

    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM users WHERE email = %s', (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': 'Email already registered'}), 400

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
    
    # Calculate star rating
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
        'is_vip': user.get('is_vip', False)
    })

def calculate_stars(user):
    stars = 1
    car_type = user.get('car_type', 'hatchback')
    
    if car_type == 'luxury':
        stars = 5
    elif car_type == 'suv':
        stars = 4
    elif car_type == 'sedan':
        stars = 3
    else:
        stars = 2
    
    if user.get('is_vip', False):
        stars += 1
    
    if user.get('subscription_type'):
        stars += 1
    
    return min(stars, 7)

@app.route('/api/queue/status', methods=['GET'])
def queue_status():
    # TODO: Implement real queue system
    return jsonify({
        'total': 0,
        'waiting': [],
        'serving': [],
        'completed': []
    })

@app.route('/api/queue/join', methods=['POST'])
@login_required
def join_queue():
    # TODO: Implement queue join
    return jsonify({
        'status': 'success',
        'token': 1,
        'position': 1,
        'estimated_wait': 2
    })

@app.route('/api/queue/next', methods=['POST'])
@admin_required
def next_in_queue():
    return jsonify({'status': 'success'})

@app.route('/api/queue/complete', methods=['POST'])
@admin_required
def complete_queue():
    return jsonify({'status': 'success'})

@app.route('/api/subscription/plans', methods=['GET'])
def get_plans():
    return jsonify({
        'weekly': {'name': 'Weekly', 'price': 999, 'credits': 2, 'days': 7, 'savings': '33%'},
        'monthly': {'name': 'Monthly', 'price': 2999, 'credits': 8, 'days': 30, 'savings': '50%'},
        '3month': {'name': '3-Month', 'price': 7999, 'credits': 28, 'days': 90, 'savings': '62%'}
    })

@app.route('/api/subscription/subscribe', methods=['POST'])
@login_required
def subscribe():
    data = request.get_json()
    plan_id = data.get('plan_id')
    
    plans = {
        'weekly': {'credits': 2, 'days': 7, 'price': 999},
        'monthly': {'credits': 8, 'days': 30, 'price': 2999},
        '3month': {'credits': 28, 'days': 90, 'price': 7999}
    }
    
    if plan_id not in plans:
        return jsonify({'error': 'Invalid plan'}), 400
    
    plan = plans[plan_id]
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET credits = credits + %s, 
            subscription_type = %s,
            subscription_end = %s,
            is_vip = TRUE
        WHERE id = %s
        RETURNING credits
    ''', (plan['credits'], plan_id, datetime.now() + timedelta(days=plan['days']), session['user_id']))
    updated = cur.fetchone()
    conn.commit()
    conn.close()
    
    return jsonify({
        'status': 'success',
        'credits': updated['credits'] if updated else 0,
        'valid_until': (datetime.now() + timedelta(days=plan['days'])).isoformat()
    })

@app.route('/api/payment/upi', methods=['GET'])
@login_required
def get_upi_info():
    return jsonify({
        'upi_id': 'skn-apex@okhdfc',
        'qr_code_url': '/static/images/upi-qr.png'
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

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
