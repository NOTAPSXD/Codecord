<<<<<<< HEAD
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create necessary directories
os.makedirs('db', exist_ok=True)
os.makedirs('static/uploads/projects', exist_ok=True)
os.makedirs('static/uploads/profiles', exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///db/codexverse.db')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Admin configuration
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@codexverse.com')

db = SQLAlchemy(app)
socketio = SocketIO(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    profile_pic = db.Column(db.String(200))
    role = db.Column(db.String(20), default='user')  # user, staff, admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tickets = db.relationship('Ticket', backref='user', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    thumbnail = db.Column(db.String(200))
    download_link = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    projects = db.relationship('Project', backref='category', lazy=True)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='open')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('TicketMessage', backref='ticket', lazy=True)

class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))

        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )

        db.session.add(user)
        db.session.commit()

        flash('Registration successful!')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))

        flash('Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/voice')
@login_required
def voice():
    return render_template('voice.html')

@app.route('/projects')
def projects():
    categories = Category.query.all()
    return render_template('projects.html', categories=categories)

@app.route('/project/<int:project_id>')
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    return render_template('project_detail.html', project=project)

@app.route('/tickets')
@login_required
def tickets():
    user_tickets = Ticket.query.filter_by(user_id=current_user.id).all()
    return render_template('tickets.html', tickets=user_tickets)

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(current_user.username)

@socketio.on('message')
def handle_message(data):
    emit('message', {
        'user': current_user.username,
        'message': data['message'],
        'timestamp': datetime.utcnow().strftime('%H:%M:%S')
    }, broadcast=True)

@socketio.on('join_voice')
def handle_join_voice(data):
    room = data['room']
    join_room(room)
    emit('user_joined_voice', {
        'user': current_user.username,
        'room': room
    }, room=room)

@socketio.on('leave_voice')
def handle_leave_voice(data):
    room = data['room']
    leave_room(room)
    emit('user_left_voice', {
        'user': current_user.username,
        'room': room
    }, room=room)

# Create default admin user if none exists
def create_default_admin():
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            password_hash=generate_password_hash(ADMIN_PASSWORD),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print('Default admin user created!')
        print(f'Username: {ADMIN_USERNAME}')
        print(f'Password: {ADMIN_PASSWORD}')
        print(f'Email: {ADMIN_EMAIL}')

# Main entry
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    with app.app_context():
        db.create_all()         # Create tables if not already created
        create_default_admin()  # Create default admin if none

    socketio.run(app, host="0.0.0.0", port=port)
=======
from setuptools import setup, find_packages

setup(
    name="codexverse",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        'Flask==2.3.3',
        'Flask-SQLAlchemy==3.1.1',
        'Flask-Login==0.6.2',
        'Flask-SocketIO==5.3.6',
        'Flask-WTF==1.2.1',
        'Pillow==10.0.0',
        'python-dotenv==1.0.0',
        'Werkzeug==2.3.7',
        'eventlet==0.33.3',
        'gunicorn==21.2.0',
        'Flask-Migrate==4.0.5',
        'Flask-Admin==1.6.1',
        'Flask-Mail==0.9.1',
        'Flask-CORS==4.0.0',
        'python-jose==3.3.0',
        'bcrypt==4.0.1'
    ],
    python_requires='>=3.8',
) 
>>>>>>> 811b9e70f9e4fe1d85b01eca33aa982fe5b5000f
