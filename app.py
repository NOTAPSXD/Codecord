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

# Add this function to create admin user if not exists
def create_admin_user():
    admin_exists = mongo.db.users.find_one({'role': 'admin'})
    if not admin_exists:
        admin_data = {
            'username': ADMIN_USERNAME,
            'email': ADMIN_EMAIL,
            'password_hash': generate_password_hash(ADMIN_PASSWORD),
            'role': 'admin',
            'created_at': datetime.utcnow()
        }
        mongo.db.users.insert_one(admin_data)
        print("Admin user created successfully!")

try:
    mongo = PyMongo(app)
    # Test the connection
    mongo.db.command('ping')
    print("Successfully connected to MongoDB Atlas!")
    # Create admin user if not exists
    create_admin_user()
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
        print(f"Initializing User with data: {user_data}")
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data['email']
        self.password_hash = user_data['password_hash']
        self.profile_pic = user_data.get('profile_pic')
        self.role = user_data.get('role', 'user')
        self.created_at = user_data.get('created_at', datetime.utcnow())
        print(f"User initialized: {self.username} with role {self.role}")

    @staticmethod
    def get(user_id):
        print(f"Getting user by ID: {user_id}")
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if user_data:
            print(f"Found user: {user_data['username']}")
            return User(user_data)
        print("User not found")
        return None

    @staticmethod
    def get_by_username(username):
        print(f"Getting user by username: {username}")
        user_data = mongo.db.users.find_one({'username': username})
        if user_data:
            print(f"Found user: {user_data['username']}")
            return User(user_data)
        print("User not found")
        return None

    @staticmethod
    def get_by_email(email):
        print(f"Getting user by email: {email}")
        user_data = mongo.db.users.find_one({'email': email})
        if user_data:
            print(f"Found user: {user_data['username']}")
            return User(user_data)
        print("User not found")
        return None

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

        print(f"Attempting to register user: {username} with email: {email}")

        if mongo.db.users.find_one({'username': username}):
            print(f"Username {username} already exists")
            flash('Username already exists')
            return redirect(url_for('register'))

        if mongo.db.users.find_one({'email': email}):
            print(f"Email {email} already registered")
            flash('Email already registered')
            return redirect(url_for('register'))

        user_data = {
            'username': username,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'user',
            'created_at': datetime.utcnow()
        }

        result = mongo.db.users.insert_one(user_data)
        print(f"User registered successfully with ID: {result.inserted_id}")
        flash('Registration successful!')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        print(f"Login attempt for: {email}")

        # Try to find user by email
        user_data = mongo.db.users.find_one({'email': email})
        print(f"User found by email: {user_data is not None}")
        
        # If not found by email, try username
        if not user_data:
            user_data = mongo.db.users.find_one({'username': email})
            print(f"User found by username: {user_data is not None}")

        if user_data:
            print("User found, checking password")
            if check_password_hash(user_data['password_hash'], password):
                print("Password correct, logging in user")
                user = User(user_data)
                login_user(user)
                return redirect(url_for('index'))
            else:
                print("Password incorrect")
        else:
            print("No user found with provided credentials")

        flash('Invalid email or password')

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
@login_required
def projects():
    # Get projects from database
    projects = list(mongo.db.projects.find())
    categories = mongo.db.projects.distinct('category')
    return render_template('projects.html', projects=projects, categories=categories)

@app.route('/project/<project_id>')
def project_detail(project_id):
    project = mongo.db.projects.find_one({'_id': ObjectId(project_id)})
    if not project:
        return redirect(url_for('projects'))
    return render_template('project_detail.html', project=project)

@app.route('/tickets')
@login_required
def tickets():
    # Get tickets from database
    tickets = list(mongo.db.tickets.find())
    return render_template('tickets.html', tickets=tickets)

@app.route('/tickets/new', methods=['GET', 'POST'])
@login_required
def new_ticket():
    if request.method == 'POST':
        ticket = {
            'title': request.form.get('title'),
            'description': request.form.get('description'),
            'priority': request.form.get('priority'),
            'status': 'open',
            'author': current_user.username,
            'created_at': datetime.utcnow()
        }
        mongo.db.tickets.insert_one(ticket)
        flash('Ticket created successfully!', 'success')
        return redirect(url_for('tickets'))
    return render_template('new_ticket.html')

@app.route('/tickets/<ticket_id>')
@login_required
def view_ticket(ticket_id):
    ticket = mongo.db.tickets.find_one({'_id': ObjectId(ticket_id)})
    if not ticket:
        flash('Ticket not found!', 'error')
        return redirect(url_for('tickets'))
    return render_template('view_ticket.html', ticket=ticket)

@app.route('/tickets/<ticket_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ticket(ticket_id):
    if current_user.role != 'admin':
        flash('You do not have permission to edit tickets!', 'error')
        return redirect(url_for('tickets'))
    
    ticket = mongo.db.tickets.find_one({'_id': ObjectId(ticket_id)})
    if not ticket:
        flash('Ticket not found!', 'error')
        return redirect(url_for('tickets'))

    if request.method == 'POST':
        mongo.db.tickets.update_one(
            {'_id': ObjectId(ticket_id)},
            {'$set': {
                'title': request.form.get('title'),
                'description': request.form.get('description'),
                'priority': request.form.get('priority'),
                'status': request.form.get('status')
            }}
        )
        flash('Ticket updated successfully!', 'success')
        return redirect(url_for('tickets'))
    
    return render_template('edit_ticket.html', ticket=ticket)

@app.route('/tickets/<ticket_id>', methods=['DELETE'])
@login_required
def delete_ticket(ticket_id):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    result = mongo.db.tickets.delete_one({'_id': ObjectId(ticket_id)})
    if result.deleted_count:
        return jsonify({'message': 'Ticket deleted successfully'}), 200
    return jsonify({'error': 'Ticket not found'}), 404

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('You do not have permission to access the admin dashboard.', 'error')
        return redirect(url_for('index'))
    
    # Get statistics for admin dashboard
    total_users = mongo.db.users.count_documents({})
    total_tickets = mongo.db.tickets.count_documents({})
    open_tickets = mongo.db.tickets.count_documents({'status': 'open'})
    total_projects = mongo.db.projects.count_documents({})
    
    # Get recent activity
    recent_tickets = list(mongo.db.tickets.find().sort('created_at', -1).limit(5))
    recent_users = list(mongo.db.users.find().sort('created_at', -1).limit(5))
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_tickets=total_tickets,
                         open_tickets=open_tickets,
                         total_projects=total_projects,
                         recent_tickets=recent_tickets,
                         recent_users=recent_users)

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

# Main entry
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
