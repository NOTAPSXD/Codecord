from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db, Project, Category, User, Ticket, socketio
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import json
from collections import defaultdict

admin = Blueprint('admin', __name__)

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Analytics and Logging
class Analytics:
    def __init__(self):
        self.online_users = set()
        self.user_actions = []
        self.chat_messages = []
        self.voice_sessions = []
        self.downloads = []
        
    def log_user_action(self, user_id, action, details):
        self.user_actions.append({
            'user_id': user_id,
            'action': action,
            'details': details,
            'timestamp': datetime.utcnow()
        })
        
    def get_user_stats(self, user_id):
        return {
            'messages': len([m for m in self.chat_messages if m['user_id'] == user_id]),
            'voice_time': sum(s['duration'] for s in self.voice_sessions if s['user_id'] == user_id),
            'downloads': len([d for d in self.downloads if d['user_id'] == user_id])
        }
        
    def get_system_stats(self):
        return {
            'total_users': User.query.count(),
            'online_users': len(self.online_users),
            'total_projects': Project.query.count(),
            'total_downloads': len(self.downloads),
            'active_voice_rooms': len(set(s['room'] for s in self.voice_sessions if s['end_time'] is None))
        }

analytics = Analytics()

# User Management
@admin.route('/admin/users')
@login_required
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@admin.route('/admin/user/<int:user_id>/ban', methods=['POST'])
@login_required
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_banned = True
    db.session.commit()
    analytics.log_user_action(current_user.id, 'ban_user', {'banned_user_id': user_id})
    socketio.emit('user_banned', {'user_id': user_id}, broadcast=True)
    flash(f'User {user.username} has been banned')
    return redirect(url_for('admin.manage_users'))

@admin.route('/admin/user/<int:user_id>/unban', methods=['POST'])
@login_required
@admin_required
def unban_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_banned = False
    db.session.commit()
    analytics.log_user_action(current_user.id, 'unban_user', {'unbanned_user_id': user_id})
    flash(f'User {user.username} has been unbanned')
    return redirect(url_for('admin.manage_users'))

@admin.route('/admin/user/<int:user_id>/mute', methods=['POST'])
@login_required
@admin_required
def mute_user(user_id):
    user = User.query.get_or_404(user_id)
    duration = int(request.form.get('duration', 3600))  # Default 1 hour
    user.muted_until = datetime.utcnow() + timedelta(seconds=duration)
    db.session.commit()
    analytics.log_user_action(current_user.id, 'mute_user', {
        'muted_user_id': user_id,
        'duration': duration
    })
    socketio.emit('user_muted', {
        'user_id': user_id,
        'until': user.muted_until.isoformat()
    }, broadcast=True)
    flash(f'User {user.username} has been muted for {duration//3600} hours')
    return redirect(url_for('admin.manage_users'))

@admin.route('/admin/user/<int:user_id>/unmute', methods=['POST'])
@login_required
@admin_required
def unmute_user(user_id):
    user = User.query.get_or_404(user_id)
    user.muted_until = None
    db.session.commit()
    analytics.log_user_action(current_user.id, 'unmute_user', {'unmuted_user_id': user_id})
    socketio.emit('user_unmuted', {'user_id': user_id}, broadcast=True)
    flash(f'User {user.username} has been unmuted')
    return redirect(url_for('admin.manage_users'))

@admin.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    analytics.log_user_action(current_user.id, 'delete_user', {'deleted_user_id': user_id})
    socketio.emit('user_deleted', {'user_id': user_id}, broadcast=True)
    flash(f'User {username} has been deleted')
    return redirect(url_for('admin.manage_users'))

# Analytics Dashboard
@admin.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    system_stats = analytics.get_system_stats()
    recent_actions = analytics.user_actions[-50:]  # Last 50 actions
    return render_template('admin/dashboard.html',
                         system_stats=system_stats,
                         recent_actions=recent_actions)

@admin.route('/admin/analytics')
@login_required
@admin_required
def analytics_dashboard():
    # Get time-based statistics
    now = datetime.utcnow()
    last_24h = now - timedelta(days=1)
    last_7d = now - timedelta(days=7)
    
    # User activity
    daily_users = defaultdict(int)
    for action in analytics.user_actions:
        if action['timestamp'] > last_7d:
            daily_users[action['timestamp'].date()] += 1
    
    # Project downloads
    daily_downloads = defaultdict(int)
    for download in analytics.downloads:
        if download['timestamp'] > last_7d:
            daily_downloads[download['timestamp'].date()] += 1
    
    # Voice room usage
    voice_stats = {
        'total_sessions': len(analytics.voice_sessions),
        'active_rooms': len(set(s['room'] for s in analytics.voice_sessions if s['end_time'] is None)),
        'total_duration': sum(s['duration'] for s in analytics.voice_sessions)
    }
    
    return render_template('admin/analytics.html',
                         daily_users=dict(daily_users),
                         daily_downloads=dict(daily_downloads),
                         voice_stats=voice_stats)

# Logs
@admin.route('/admin/logs')
@login_required
@admin_required
def view_logs():
    logs = analytics.user_actions
    return render_template('admin/logs.html', logs=logs)

# Socket.IO events for analytics
@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        analytics.online_users.add(current_user.id)
        analytics.log_user_action(current_user.id, 'connect', {})

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        analytics.online_users.discard(current_user.id)
        analytics.log_user_action(current_user.id, 'disconnect', {})

@socketio.on('message')
def handle_message(data):
    if current_user.is_authenticated:
        analytics.chat_messages.append({
            'user_id': current_user.id,
            'message': data['message'],
            'timestamp': datetime.utcnow()
        })

@socketio.on('join_voice')
def handle_join_voice(data):
    if current_user.is_authenticated:
        analytics.voice_sessions.append({
            'user_id': current_user.id,
            'room': data['room'],
            'start_time': datetime.utcnow(),
            'end_time': None,
            'duration': 0
        })

@socketio.on('leave_voice')
def handle_leave_voice(data):
    if current_user.is_authenticated:
        for session in analytics.voice_sessions:
            if session['user_id'] == current_user.id and session['end_time'] is None:
                session['end_time'] = datetime.utcnow()
                session['duration'] = (session['end_time'] - session['start_time']).total_seconds()
                break

@socketio.on('download_project')
def handle_download(data):
    if current_user.is_authenticated:
        analytics.downloads.append({
            'user_id': current_user.id,
            'project_id': data['project_id'],
            'timestamp': datetime.utcnow()
        })

# Project Management
@admin.route('/admin/projects')
@login_required
@admin_required
def manage_projects():
    projects = Project.query.all()
    categories = Category.query.all()
    return render_template('admin/projects.html', projects=projects, categories=categories)

@admin.route('/admin/project/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_project():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        category_id = request.form.get('category_id')
        download_link = request.form.get('download_link')
        
        thumbnail = request.files.get('thumbnail')
        if thumbnail:
            filename = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join('static/uploads/projects', filename))
            thumbnail_path = f'uploads/projects/{filename}'
        else:
            thumbnail_path = None
            
        project = Project(
            title=title,
            description=description,
            category_id=category_id,
            thumbnail=thumbnail_path,
            download_link=download_link
        )
        
        db.session.add(project)
        db.session.commit()
        
        flash('Project added successfully')
        return redirect(url_for('admin.manage_projects'))
        
    categories = Category.query.all()
    return render_template('admin/add_project.html', categories=categories)

@admin.route('/admin/project/edit/<int:project_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_project(project_id):
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        project.title = request.form.get('title')
        project.description = request.form.get('description')
        project.category_id = request.form.get('category_id')
        project.download_link = request.form.get('download_link')
        
        thumbnail = request.files.get('thumbnail')
        if thumbnail:
            filename = secure_filename(thumbnail.filename)
            thumbnail.save(os.path.join('static/uploads/projects', filename))
            project.thumbnail = f'uploads/projects/{filename}'
            
        db.session.commit()
        flash('Project updated successfully')
        return redirect(url_for('admin.manage_projects'))
        
    categories = Category.query.all()
    return render_template('admin/edit_project.html', project=project, categories=categories)

@admin.route('/admin/project/delete/<int:project_id>')
@login_required
@admin_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted successfully')
    return redirect(url_for('admin.manage_projects'))

# Category Management
@admin.route('/admin/categories')
@login_required
@admin_required
def manage_categories():
    categories = Category.query.all()
    return render_template('admin/categories.html', categories=categories)

@admin.route('/admin/category/add', methods=['POST'])
@login_required
@admin_required
def add_category():
    name = request.form.get('name')
    category = Category(name=name)
    db.session.add(category)
    db.session.commit()
    flash('Category added successfully')
    return redirect(url_for('admin.manage_categories'))

@admin.route('/admin/category/delete/<int:category_id>')
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted successfully')
    return redirect(url_for('admin.manage_categories'))

# Ticket Management
@admin.route('/admin/tickets')
@login_required
@admin_required
def manage_tickets():
    tickets = Ticket.query.all()
    return render_template('admin/tickets.html', tickets=tickets)

@admin.route('/admin/ticket/<int:ticket_id>/status', methods=['POST'])
@login_required
@admin_required
def change_ticket_status(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    new_status = request.form.get('status')
    if new_status in ['open', 'in_progress', 'closed']:
        ticket.status = new_status
        db.session.commit()
        flash(f'Ticket status changed to {new_status}')
    return redirect(url_for('admin.manage_tickets')) 