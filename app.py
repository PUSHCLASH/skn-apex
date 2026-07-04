import os
import bcrypt
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
    return jsonify({
        'id': user['id'],
        'name': user['name'],
        'email': user['email'],
        'car_number': user['car_number'],
        'car_model': user['car_model'],
        'car_type': user['car_type'],
        'star_rating': 3,
        'credits': 0,
        'subscription_type': None,
        'is_vip': False
    })

@app.route('/api/queue/status', methods=['GET'])
def queue_status():
    return jsonify({
        'total': 0,
        'waiting': [],
        'serving': [],
        'completed': []
    })

@app.route('/api/queue/join', methods=['POST'])
@login_required
def join_queue():
    return jsonify({
        'status': 'success',
        'token': 1,
        'position': 1,
        'estimated_wait': 2
    })

@app.route('/api/subscription/plans', methods=['GET'])
def get_plans():
    return jsonify({
        'weekly': {'name': 'Weekly', 'price': 999, 'credits': 2, 'days': 7},
        'monthly': {'name': 'Monthly', 'price': 2999, 'credits': 8, 'days': 30},
        '3month': {'name': '3-Month', 'price': 7999, 'credits': 28, 'days': 90}
    })

@app.route('/api/subscription/subscribe', methods=['POST'])
@login_required
def subscribe():
    return jsonify({'status': 'success', 'credits': 8, 'valid_until': '2025-08-01'})

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
