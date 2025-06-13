from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import json
from dotenv import load_dotenv
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus

# Load environment variables
load_dotenv()

# Create necessary directories
os.makedirs('db', exist_ok=True)
os.makedirs('static/uploads/projects', exist_ok=True)
os.makedirs('static/uploads/profiles', exist_ok=True)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')

# MongoDB Atlas connection string
app.config['MONGO_URI'] = "mongodb+srv://notaps:codex@codex.jyhkgq5.mongodb.net/codexverse?retryWrites=true&w=majority"

app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Admin configuration
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@codexverse.com')

try:
    mongo = PyMongo(app)
    # Test the connection
    mongo.db.command('ping')
    print("Successfully connected to MongoDB Atlas!")
except ConnectionFailure as e:
    print("Could not connect to MongoDB Atlas. Please check your connection string and credentials.")
    print(f"Error: {e}")
    exit(1)

socketio = SocketIO(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']
        self.profile_pic = user_data.get('profile_pic')
        self.role = user_data.get('role', 'user')
        self.created_at = user_data.get('created_at', datetime.utcnow())

    @staticmethod
    def get(user_id):
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        return User(user_data) if user_data else None

    @staticmethod
    def get_by_username(username):
        user_data = mongo.db.users.find_one({'username': username})
        return User(user_data) if user_data else None

    @staticmethod
    def get_by_email(email):
        user_data = mongo.db.users.find_one({'email': email})
        return User(user_data) if user_data else None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

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

        if mongo.db.users.find_one({'username': username}):
            flash('Username already exists')
            return redirect(url_for('register'))

        if mongo.db.users.find_one({'email': email}):
            flash('Email already registered')
            return redirect(url_for('register'))

        user_data = {
            'username': username,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'user',
            'created_at': datetime.utcnow()
        }

        mongo.db.users.insert_one(user_data)
        flash('Registration successful!')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user_data = mongo.db.users.find_one({'username': username})
        if user_data and check_password_hash(user_data['password_hash'], password):
            user = User(user_data)
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
    categories = list(mongo.db.categories.find())
    return render_template('projects.html', categories=categories)

@app.route('/project/<project_id>')
def project_detail(project_id):
    project = mongo.db.projects.find_one({'_id': ObjectId(project_id)})
    if not project:
        return redirect(url_for('projects'))
    return render_template('project_detail.html', project=project)

@app.route('/tickets')
@login_required
def tickets():
    user_tickets = list(mongo.db.tickets.find({'user_id': current_user.id}))
    return render_template('tickets.html', tickets=user_tickets)

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(current_user.username)

@socketio.on('message')
def handle_message(data):
    message_data = {
        'user': current_user.username,
        'message': data['message'],
        'timestamp': datetime.utcnow()
    }
    mongo.db.messages.insert_one(message_data)
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
    admin = mongo.db.users.find_one({'role': 'admin'})
    if not admin:
        admin_data = {
            'username': ADMIN_USERNAME,
            'email': ADMIN_EMAIL,
            'password_hash': generate_password_hash(ADMIN_PASSWORD),
            'role': 'admin',
            'created_at': datetime.utcnow()
        }
        mongo.db.users.insert_one(admin_data)
        print('Default admin user created!')
        print(f'Username: {ADMIN_USERNAME}')
        print(f'Password: {ADMIN_PASSWORD}')
        print(f'Email: {ADMIN_EMAIL}')

# Main entry
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    create_default_admin()  # Create default admin if none
    socketio.run(app, host="0.0.0.0", port=port)
