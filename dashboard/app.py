#!/usr/bin/env python3
"""
Music Planner Dashboard - Web UI for AI Music Generation
Now with user accounts!
"""

import os
import json
import subprocess
import glob
import re
import sqlite3
import secrets
import threading
import shutil
from datetime import datetime
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for, flash, session, g
from werkzeug.security import generate_password_hash, check_password_hash

# Use pbkdf2 instead of scrypt (broader compatibility)
def hash_password(password):
    return generate_password_hash(password, method='pbkdf2:sha256')
import yaml

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Paths
BASE_DIR = Path(__file__).parent.parent
ARTISTS_DIR = BASE_DIR / "artists"
CATALOG_DIR = BASE_DIR / "catalog"
CATALOG_FILE = CATALOG_DIR / "songs.json"
GENRES_DIR = BASE_DIR.parent / "ACESTEP_genres"
MUSIC_DIR = Path.home() / "Music" / "acestep"
GENERATE_SCRIPT = BASE_DIR / "generate.sh"
DATABASE = BASE_DIR / "dashboard" / "music_planner.db"
ARTIST_PHOTOS_DIR = BASE_DIR / "artist_photos"
COMFYUI_PORTRAITS_DIR = BASE_DIR.parent / "comfyui-portraits"

# Ensure artist photos directory exists
ARTIST_PHOTOS_DIR.mkdir(exist_ok=True)

# ============== DATABASE ==============

def get_db():
    """Get database connection."""
    if 'db' not in g:
        g.db = sqlite3.connect(str(DATABASE))
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize database tables."""
    db = get_db()
    db.executescript('''
        -- Core user table
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        -- Public profiles
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id INTEGER PRIMARY KEY,
            display_name TEXT,
            bio TEXT,
            avatar_url TEXT,
            is_public INTEGER DEFAULT 0,
            website TEXT,
            location TEXT,
            total_plays INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        -- Follow system
        CREATE TABLE IF NOT EXISTS follows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            follower_id INTEGER NOT NULL,
            following_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (follower_id) REFERENCES users(id),
            FOREIGN KEY (following_id) REFERENCES users(id),
            UNIQUE(follower_id, following_id)
        );
        
        -- Songs with extended fields
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            artist TEXT NOT NULL,
            concept TEXT,
            lyrics TEXT,
            file_path TEXT,
            tags TEXT,
            mode TEXT,
            rating INTEGER DEFAULT 0,
            is_public INTEGER DEFAULT 0,
            play_count INTEGER DEFAULT 0,
            like_count INTEGER DEFAULT 0,
            duration_seconds INTEGER DEFAULT 0,
            generation_cost REAL DEFAULT 0,
            generation_time_seconds INTEGER DEFAULT 0,
            steps_used INTEGER DEFAULT 0,
            takes_generated INTEGER DEFAULT 1,
            parent_song_id INTEGER,
            style_transfer_from INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (parent_song_id) REFERENCES songs(id),
            FOREIGN KEY (style_transfer_from) REFERENCES songs(id)
        );
        
        -- Song likes/favorites
        CREATE TABLE IF NOT EXISTS song_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (song_id) REFERENCES songs(id),
            UNIQUE(user_id, song_id)
        );
        
        -- Song comments
        CREATE TABLE IF NOT EXISTS song_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (song_id) REFERENCES songs(id)
        );
        
        -- Custom tags for songs
        CREATE TABLE IF NOT EXISTS song_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            song_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY (song_id) REFERENCES songs(id),
            UNIQUE(song_id, tag)
        );
        
        -- Listening/play history
        CREATE TABLE IF NOT EXISTS song_plays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            duration_listened INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (song_id) REFERENCES songs(id)
        );
        
        -- Playlists
        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            is_public INTEGER DEFAULT 0,
            cover_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        CREATE TABLE IF NOT EXISTS playlist_songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id),
            FOREIGN KEY (song_id) REFERENCES songs(id),
            UNIQUE(playlist_id, song_id)
        );
        
        -- Folders/Collections
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            parent_id INTEGER,
            color TEXT DEFAULT '#8b5cf6',
            icon TEXT DEFAULT '📁',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (parent_id) REFERENCES folders(id)
        );
        
        CREATE TABLE IF NOT EXISTS folder_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (folder_id) REFERENCES folders(id),
            UNIQUE(folder_id, item_type, item_id)
        );
        
        -- User badges/achievements
        CREATE TABLE IF NOT EXISTS badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            icon TEXT,
            category TEXT,
            requirement_type TEXT,
            requirement_value INTEGER DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS user_badges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            badge_id INTEGER NOT NULL,
            earned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (badge_id) REFERENCES badges(id),
            UNIQUE(user_id, badge_id)
        );
        
        -- Generation cost tracking
        CREATE TABLE IF NOT EXISTS generation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            song_id INTEGER,
            mode TEXT,
            steps INTEGER,
            duration INTEGER,
            takes INTEGER DEFAULT 1,
            cost REAL DEFAULT 0,
            compute_time_seconds INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (song_id) REFERENCES songs(id)
        );
        
        -- User artists
        CREATE TABLE IF NOT EXISTS user_artists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            style TEXT,
            voice TEXT,
            tags TEXT,
            description TEXT,
            photo_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, filename)
        );
        
        -- User genres
        CREATE TABLE IF NOT EXISTS user_genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            tags TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, filename)
        );
        
        -- User templates
        CREATE TABLE IF NOT EXISTS user_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            mode TEXT DEFAULT 'standard',
            artist TEXT,
            artist2 TEXT,
            vibe TEXT,
            duration INTEGER DEFAULT 120,
            steps INTEGER DEFAULT 60,
            quality TEXT DEFAULT 'normal',
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        -- Albums
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            artist TEXT NOT NULL,
            theme TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        CREATE TABLE IF NOT EXISTS album_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id INTEGER NOT NULL,
            song_id INTEGER NOT NULL,
            track_number INTEGER NOT NULL,
            FOREIGN KEY (album_id) REFERENCES albums(id),
            FOREIGN KEY (song_id) REFERENCES songs(id)
        );
        
        -- Artist photo generation jobs
        CREATE TABLE IF NOT EXISTS artist_photo_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            artist_filename TEXT,
            status TEXT DEFAULT 'pending',
            gender TEXT,
            age TEXT,
            ethnicity TEXT,
            hair_color TEXT,
            hair_style TEXT,
            eye_color TEXT,
            clothing TEXT,
            style TEXT,
            background TEXT,
            additional TEXT,
            photo_paths TEXT,
            selected_photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            error TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        CREATE INDEX IF NOT EXISTS idx_photo_jobs_user ON artist_photo_jobs(user_id);
        CREATE INDEX IF NOT EXISTS idx_photo_jobs_status ON artist_photo_jobs(status);
        
        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_songs_user ON songs(user_id);
        CREATE INDEX IF NOT EXISTS idx_songs_public ON songs(is_public);
        CREATE INDEX IF NOT EXISTS idx_artists_user ON user_artists(user_id);
        CREATE INDEX IF NOT EXISTS idx_genres_user ON user_genres(user_id);
        CREATE INDEX IF NOT EXISTS idx_templates_user ON user_templates(user_id);
        CREATE INDEX IF NOT EXISTS idx_albums_user ON albums(user_id);
        CREATE INDEX IF NOT EXISTS idx_follows_follower ON follows(follower_id);
        CREATE INDEX IF NOT EXISTS idx_follows_following ON follows(following_id);
        CREATE INDEX IF NOT EXISTS idx_likes_song ON song_likes(song_id);
        CREATE INDEX IF NOT EXISTS idx_likes_user ON song_likes(user_id);
        CREATE INDEX IF NOT EXISTS idx_comments_song ON song_comments(song_id);
        CREATE INDEX IF NOT EXISTS idx_plays_user ON song_plays(user_id);
        CREATE INDEX IF NOT EXISTS idx_plays_song ON song_plays(song_id);
        CREATE INDEX IF NOT EXISTS idx_song_tags ON song_tags(song_id);
        CREATE INDEX IF NOT EXISTS idx_playlists_user ON playlists(user_id);
        CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id);
        CREATE INDEX IF NOT EXISTS idx_gen_logs_user ON generation_logs(user_id);
    ''')
    db.commit()
    
    # Migrations for existing databases
    try:
        db.execute('ALTER TABLE user_artists ADD COLUMN photo_url TEXT')
        db.commit()
    except:
        pass  # Column already exists
    
    # Seed badges
    seed_badges(db)

def seed_badges(db):
    """Seed achievement badges."""
    badges = [
        # Generation milestones
        ('first_song', 'First Song', 'Generated your first song', '🎵', 'generation', 'songs_generated', 1),
        ('prolific_10', 'Getting Started', 'Generated 10 songs', '🎶', 'generation', 'songs_generated', 10),
        ('prolific_50', 'Prolific Producer', 'Generated 50 songs', '🎹', 'generation', 'songs_generated', 50),
        ('prolific_100', 'Hit Machine', 'Generated 100 songs', '💿', 'generation', 'songs_generated', 100),
        ('prolific_500', 'Music Factory', 'Generated 500 songs', '🏭', 'generation', 'songs_generated', 500),
        
        # Artist milestones
        ('first_artist', 'Artist Creator', 'Created your first custom artist', '🎤', 'artists', 'artists_created', 1),
        ('artist_5', 'Talent Scout', 'Created 5 custom artists', '🌟', 'artists', 'artists_created', 5),
        ('artist_10', 'Label Owner', 'Created 10 custom artists', '🏢', 'artists', 'artists_created', 10),
        
        # Social milestones
        ('first_follower', 'Rising Star', 'Got your first follower', '⭐', 'social', 'followers', 1),
        ('followers_10', 'Trending', 'Reached 10 followers', '📈', 'social', 'followers', 10),
        ('followers_100', 'Influencer', 'Reached 100 followers', '🔥', 'social', 'followers', 100),
        ('first_like', 'Liked', 'Received your first like', '❤️', 'social', 'likes_received', 1),
        ('likes_50', 'Fan Favorite', 'Received 50 likes', '💕', 'social', 'likes_received', 50),
        
        # Quality milestones
        ('five_star', 'Perfectionist', 'Gave a song 5 stars', '⭐', 'quality', 'five_star_ratings', 1),
        ('critic', 'Music Critic', 'Rated 50 songs', '📊', 'quality', 'songs_rated', 50),
        
        # Playlist milestones
        ('first_playlist', 'Curator', 'Created your first playlist', '📋', 'organization', 'playlists_created', 1),
        ('playlist_5', 'DJ', 'Created 5 playlists', '🎧', 'organization', 'playlists_created', 5),
        
        # Special
        ('early_adopter', 'Early Adopter', 'Joined during beta', '🚀', 'special', 'manual', 0),
        ('night_owl', 'Night Owl', 'Generated a song after midnight', '🦉', 'special', 'manual', 0),
        ('weekend_warrior', 'Weekend Warrior', 'Generated 10 songs in one weekend', '⚔️', 'special', 'manual', 0),
    ]
    
    for badge in badges:
        try:
            db.execute('''
                INSERT OR IGNORE INTO badges (name, display_name, description, icon, category, requirement_type, requirement_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', badge)
        except:
            pass
    db.commit()

def check_and_award_badges(user_id):
    """Check if user qualifies for any new badges."""
    db = get_db()
    
    # Get user stats
    stats = get_user_stats(user_id)
    
    # Get badges user doesn't have yet
    earned = db.execute('SELECT badge_id FROM user_badges WHERE user_id = ?', (user_id,)).fetchall()
    earned_ids = [e['badge_id'] for e in earned]
    
    # Check each badge
    badges = db.execute('SELECT * FROM badges WHERE requirement_type != "manual"').fetchall()
    new_badges = []
    
    for badge in badges:
        if badge['id'] in earned_ids:
            continue
            
        req_type = badge['requirement_type']
        req_val = badge['requirement_value']
        
        qualified = False
        if req_type == 'songs_generated' and stats.get('total_songs', 0) >= req_val:
            qualified = True
        elif req_type == 'artists_created' and stats.get('total_artists', 0) >= req_val:
            qualified = True
        elif req_type == 'followers' and stats.get('followers', 0) >= req_val:
            qualified = True
        elif req_type == 'likes_received' and stats.get('likes_received', 0) >= req_val:
            qualified = True
        elif req_type == 'playlists_created' and stats.get('playlists', 0) >= req_val:
            qualified = True
        elif req_type == 'songs_rated' and stats.get('songs_rated', 0) >= req_val:
            qualified = True
        elif req_type == 'five_star_ratings' and stats.get('five_star_given', 0) >= req_val:
            qualified = True
            
        if qualified:
            db.execute('INSERT INTO user_badges (user_id, badge_id) VALUES (?, ?)', (user_id, badge['id']))
            new_badges.append(badge)
    
    db.commit()
    return new_badges

def get_user_stats(user_id):
    """Get comprehensive stats for a user."""
    db = get_db()
    
    stats = {}
    
    # Songs
    stats['total_songs'] = db.execute('SELECT COUNT(*) FROM songs WHERE user_id = ?', (user_id,)).fetchone()[0]
    stats['public_songs'] = db.execute('SELECT COUNT(*) FROM songs WHERE user_id = ? AND is_public = 1', (user_id,)).fetchone()[0]
    
    # Artists
    stats['total_artists'] = db.execute('SELECT COUNT(*) FROM user_artists WHERE user_id = ?', (user_id,)).fetchone()[0]
    
    # Social
    stats['followers'] = db.execute('SELECT COUNT(*) FROM follows WHERE following_id = ?', (user_id,)).fetchone()[0]
    stats['following'] = db.execute('SELECT COUNT(*) FROM follows WHERE follower_id = ?', (user_id,)).fetchone()[0]
    
    # Likes
    stats['likes_received'] = db.execute('''
        SELECT COUNT(*) FROM song_likes l 
        JOIN songs s ON l.song_id = s.id 
        WHERE s.user_id = ?
    ''', (user_id,)).fetchone()[0]
    stats['likes_given'] = db.execute('SELECT COUNT(*) FROM song_likes WHERE user_id = ?', (user_id,)).fetchone()[0]
    
    # Playlists
    stats['playlists'] = db.execute('SELECT COUNT(*) FROM playlists WHERE user_id = ?', (user_id,)).fetchone()[0]
    
    # Plays
    stats['total_plays'] = db.execute('''
        SELECT COALESCE(SUM(play_count), 0) FROM songs WHERE user_id = ?
    ''', (user_id,)).fetchone()[0]
    
    # Ratings
    stats['songs_rated'] = db.execute('SELECT COUNT(*) FROM songs WHERE user_id = ? AND rating > 0', (user_id,)).fetchone()[0]
    stats['five_star_given'] = db.execute('SELECT COUNT(*) FROM songs WHERE user_id = ? AND rating = 5', (user_id,)).fetchone()[0]
    
    # Generation costs
    cost_row = db.execute('SELECT COALESCE(SUM(cost), 0), COALESCE(SUM(compute_time_seconds), 0) FROM generation_logs WHERE user_id = ?', (user_id,)).fetchone()
    stats['total_cost'] = cost_row[0]
    stats['total_compute_time'] = cost_row[1]
    
    # Badges
    stats['badges'] = db.execute('SELECT COUNT(*) FROM user_badges WHERE user_id = ?', (user_id,)).fetchone()[0]
    
    return stats

# ============== AUTH HELPERS ==============

def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Login required'}), 401
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get current logged-in user."""
    if 'user_id' not in session:
        return None
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    return user

@app.context_processor
def inject_user():
    """Make current user available in all templates."""
    return {'current_user': get_current_user()}

# ============== MIGRATION HELPER ==============

def migrate_existing_data(user_id):
    """Migrate existing JSON data to user's account."""
    db = get_db()
    
    # Migrate songs from JSON catalog
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE, 'r') as f:
            data = json.load(f)
        
        for song in data.get('songs', []):
            # Check if song already exists
            existing = db.execute('SELECT id FROM songs WHERE id = ?', (song['id'],)).fetchone()
            if not existing:
                db.execute('''
                    INSERT INTO songs (id, user_id, artist, concept, lyrics, file_path, tags, mode, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    song['id'],
                    user_id,
                    song.get('artist', ''),
                    song.get('concept', ''),
                    song.get('lyrics', ''),
                    song.get('file', ''),
                    song.get('tags', ''),
                    song.get('mode', ''),
                    f"{song.get('date', '')} {song.get('time', '')}"
                ))
        db.commit()
    
    # Migrate artists
    for f in ARTISTS_DIR.glob("*.md"):
        artist = parse_artist_file(f)
        existing = db.execute(
            'SELECT id FROM user_artists WHERE user_id = ? AND filename = ?',
            (user_id, artist['filename'])
        ).fetchone()
        if not existing:
            db.execute('''
                INSERT INTO user_artists (user_id, name, filename, style, voice, tags, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                artist.get('name', artist['filename']),
                artist['filename'],
                artist.get('style', ''),
                artist.get('voice', ''),
                artist.get('tags', ''),
                artist.get('body', '')
            ))
    db.commit()

# ============== ARTIST PARSING ==============

def parse_artist_file(filepath):
    """Parse artist markdown file with YAML frontmatter."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1])
                body = parts[2].strip()
                frontmatter['body'] = body
                frontmatter['filename'] = filepath.stem
                return frontmatter
            except:
                pass
    
    return {'filename': filepath.stem, 'name': filepath.stem, 'body': content}

def get_system_artists():
    """Get built-in system artists."""
    artists = []
    for f in ARTISTS_DIR.glob("*.md"):
        artist = parse_artist_file(f)
        artist['is_system'] = True
        artists.append(artist)
    return sorted(artists, key=lambda x: x.get('name', '').lower())

def get_user_artists(user_id):
    """Get user's custom artists."""
    db = get_db()
    rows = db.execute(
        'SELECT * FROM user_artists WHERE user_id = ? ORDER BY name',
        (user_id,)
    ).fetchall()
    return [dict(row) for row in rows]

def get_genres():
    """Get all genre guides."""
    genres = []
    for f in GENRES_DIR.glob("*.md"):
        with open(f, 'r') as file:
            content = file.read()
        
        title_match = re.search(r'^# (.+)', content, re.MULTILINE)
        title = title_match.group(1) if title_match else f.stem
        
        tags_match = re.search(r'```\n([^`]+)\n```', content)
        tags = tags_match.group(1).strip() if tags_match else ""
        
        genres.append({
            'filename': f.stem,
            'title': title,
            'tags': tags,
            'content': content
        })
    return sorted(genres, key=lambda x: x['title'].lower())

def get_user_songs(user_id):
    """Get user's songs."""
    db = get_db()
    rows = db.execute(
        'SELECT * FROM songs WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    songs = []
    for row in rows:
        song = dict(row)
        song['file'] = song.pop('file_path', '')
        song['file_exists'] = Path(song.get('file', '')).exists()
        songs.append(song)
    return songs

# ============== AUTH ROUTES ==============

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        
        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not email or '@' not in email:
            errors.append('Valid email required.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        
        if not errors:
            db = get_db()
            try:
                db.execute(
                    'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, hash_password(password))
                )
                db.commit()
                
                # Get the new user and log them in
                user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
                session['user_id'] = user['id']
                session['username'] = user['username']
                
                # Offer to migrate existing data
                flash(f'Welcome, {username}! Your account has been created.', 'success')
                return redirect(url_for('index'))
            except sqlite3.IntegrityError as e:
                if 'username' in str(e):
                    errors.append('Username already taken.')
                elif 'email' in str(e):
                    errors.append('Email already registered.')
                else:
                    errors.append('Registration failed.')
        
        for error in errors:
            flash(error, 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username = ? OR email = ?',
            (username, username.lower())
        ).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/migrate', methods=['POST'])
@login_required
def migrate():
    """Migrate existing JSON data to current user."""
    migrate_existing_data(session['user_id'])
    flash('Existing data has been imported to your account!', 'success')
    return redirect(url_for('index'))

# ============== PAGE ROUTES ==============

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/songs')
@login_required
def songs_page():
    return render_template('songs.html')

@app.route('/artists')
@login_required
def artists_page():
    return render_template('artists.html')

@app.route('/genres')
@login_required
def genres_page():
    return render_template('genres.html')

@app.route('/generate')
@login_required
def generate_page():
    return render_template('generate.html')

@app.route('/create')
@login_required
def create_page():
    return render_template('create.html')

@app.route('/templates')
@login_required
def templates_page():
    return render_template('templates.html')

@app.route('/playlists')
@login_required
def playlists_page():
    return render_template('playlists.html')

@app.route('/folders')
@login_required
def folders_page():
    return render_template('folders.html')

@app.route('/stats')
@login_required
def stats_page():
    return render_template('stats.html')

@app.route('/profile')
@login_required
def profile_page():
    return render_template('profile.html')

@app.route('/profile/edit')
@login_required
def profile_edit_page():
    return render_template('profile_edit.html')

@app.route('/u/<username>')
def public_profile_page(username):
    """Public profile page."""
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        return "User not found", 404
    
    profile = db.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],)).fetchone()
    if not profile or not profile['is_public']:
        return "Profile is private", 403
    
    return render_template('public_profile.html', profile_user=user, profile=profile)

@app.route('/discover')
@login_required
def discover_page():
    """Discover public songs and profiles."""
    return render_template('discover.html')

@app.route('/search')
@login_required  
def search_page():
    return render_template('search.html')

@app.route('/liked-songs')
@login_required
def liked_songs_page():
    return render_template('liked_songs.html')

# ============== API ROUTES ==============

@app.route('/api/stats')
@login_required
def api_stats():
    db = get_db()
    song_count = db.execute(
        'SELECT COUNT(*) FROM songs WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()[0]
    artist_count = db.execute(
        'SELECT COUNT(*) FROM user_artists WHERE user_id = ?',
        (session['user_id'],)
    ).fetchone()[0]
    
    # Check for legacy data (JSON catalog)
    has_legacy = False
    if CATALOG_FILE.exists():
        with open(CATALOG_FILE, 'r') as f:
            data = json.load(f)
        has_legacy = len(data.get('songs', [])) > 0
    
    return jsonify({
        'artists': len(get_system_artists()) + artist_count,
        'songs': song_count,
        'genres': len(get_genres()),
        'hasLegacyData': has_legacy
    })

@app.route('/api/artists')
@login_required
def api_artists():
    system_artists = get_system_artists()
    user_artists = get_user_artists(session['user_id'])
    
    # Mark user artists
    for a in user_artists:
        a['is_system'] = False
    
    return jsonify(system_artists + user_artists)

@app.route('/api/artists/<name>')
@login_required
def api_artist(name):
    # Check system artists first
    filepath = ARTISTS_DIR / f"{name}.md"
    if filepath.exists():
        artist = parse_artist_file(filepath)
        artist['is_system'] = True
        return jsonify(artist)
    
    # Check user artists
    db = get_db()
    artist = db.execute(
        'SELECT * FROM user_artists WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    ).fetchone()
    
    if artist:
        return jsonify(dict(artist))
    
    return jsonify({'error': 'Not found'}), 404

@app.route('/api/genres')
@login_required
def api_genres():
    """Get all genres (system + user)."""
    system_genres = get_genres()
    for g in system_genres:
        g['is_system'] = True
    
    # Get user genres
    db = get_db()
    rows = db.execute(
        'SELECT * FROM user_genres WHERE user_id = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    user_genres = []
    for row in rows:
        user_genres.append({
            'id': row['id'],
            'filename': row['filename'],
            'title': row['name'],
            'tags': row['tags'] or '',
            'content': row['description'] or '',
            'is_system': False
        })
    
    return jsonify(system_genres + user_genres)

@app.route('/api/genres/<name>', methods=['GET'])
@login_required
def api_get_genre(name):
    """Get a single genre."""
    # Check system genres first
    for g in get_genres():
        if g['filename'] == name:
            g['is_system'] = True
            return jsonify(g)
    
    # Check user genres
    db = get_db()
    row = db.execute(
        'SELECT * FROM user_genres WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    ).fetchone()
    
    if row:
        return jsonify({
            'id': row['id'],
            'filename': row['filename'],
            'title': row['name'],
            'tags': row['tags'] or '',
            'content': row['description'] or '',
            'is_system': False
        })
    
    return jsonify({'error': 'Genre not found'}), 404

@app.route('/api/genres', methods=['POST'])
@login_required
def api_create_genre():
    """Create a new user genre."""
    data = request.json
    name = data.get('name', '').strip()
    tags = data.get('tags', '').strip()
    description = data.get('description', '').strip()
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    filename = name.lower().replace(' ', '_').replace('-', '_')
    
    db = get_db()
    try:
        db.execute('''
            INSERT INTO user_genres (user_id, name, filename, tags, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (session['user_id'], name, filename, tags, description))
        db.commit()
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/genres/<name>', methods=['PUT'])
@login_required
def api_update_genre(name):
    """Update a user genre."""
    db = get_db()
    
    genre = db.execute(
        'SELECT * FROM user_genres WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    ).fetchone()
    
    if not genre:
        return jsonify({'error': 'Genre not found or not owned by you'}), 404
    
    data = request.json
    db.execute('''
        UPDATE user_genres SET name = ?, tags = ?, description = ?
        WHERE user_id = ? AND filename = ?
    ''', (
        data.get('name', genre['name']),
        data.get('tags', genre['tags']),
        data.get('description', genre['description']),
        session['user_id'],
        name
    ))
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/genres/<name>', methods=['DELETE'])
@login_required
def api_delete_genre(name):
    """Delete a user genre."""
    db = get_db()
    
    genre = db.execute(
        'SELECT * FROM user_genres WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    ).fetchone()
    
    if not genre:
        return jsonify({'error': 'Genre not found or not owned by you'}), 404
    
    db.execute(
        'DELETE FROM user_genres WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    )
    db.commit()
    
    return jsonify({'success': True})

# ============== TEMPLATES API ==============

@app.route('/api/templates')
@login_required
def api_get_templates():
    """Get user's templates."""
    db = get_db()
    rows = db.execute(
        'SELECT * FROM user_templates WHERE user_id = ? ORDER BY name',
        (session['user_id'],)
    ).fetchall()
    return jsonify([dict(row) for row in rows])

@app.route('/api/templates/<int:template_id>')
@login_required
def api_get_template(template_id):
    """Get a single template."""
    db = get_db()
    row = db.execute(
        'SELECT * FROM user_templates WHERE id = ? AND user_id = ?',
        (template_id, session['user_id'])
    ).fetchone()
    
    if not row:
        return jsonify({'error': 'Template not found'}), 404
    
    return jsonify(dict(row))

@app.route('/api/templates', methods=['POST'])
@login_required
def api_create_template():
    """Create a new template."""
    data = request.json
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': 'Name is required'}), 400
    
    db = get_db()
    cursor = db.execute('''
        INSERT INTO user_templates (user_id, name, mode, artist, artist2, vibe, duration, steps, quality, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        session['user_id'],
        name,
        data.get('mode', 'standard'),
        data.get('artist', ''),
        data.get('artist2', ''),
        data.get('vibe', ''),
        data.get('duration', 120),
        data.get('steps', 60),
        data.get('quality', 'normal'),
        data.get('tags', '')
    ))
    db.commit()
    
    return jsonify({'success': True, 'id': cursor.lastrowid})

@app.route('/api/templates/<int:template_id>', methods=['PUT'])
@login_required
def api_update_template(template_id):
    """Update a template."""
    db = get_db()
    
    template = db.execute(
        'SELECT * FROM user_templates WHERE id = ? AND user_id = ?',
        (template_id, session['user_id'])
    ).fetchone()
    
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    data = request.json
    db.execute('''
        UPDATE user_templates 
        SET name = ?, mode = ?, artist = ?, artist2 = ?, vibe = ?, duration = ?, steps = ?, quality = ?, tags = ?
        WHERE id = ? AND user_id = ?
    ''', (
        data.get('name', template['name']),
        data.get('mode', template['mode']),
        data.get('artist', template['artist']),
        data.get('artist2', template['artist2']),
        data.get('vibe', template['vibe']),
        data.get('duration', template['duration']),
        data.get('steps', template['steps']),
        data.get('quality', template['quality']),
        data.get('tags', template['tags']),
        template_id,
        session['user_id']
    ))
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/templates/<int:template_id>', methods=['DELETE'])
@login_required
def api_delete_template(template_id):
    """Delete a template."""
    db = get_db()
    
    template = db.execute(
        'SELECT * FROM user_templates WHERE id = ? AND user_id = ?',
        (template_id, session['user_id'])
    ).fetchone()
    
    if not template:
        return jsonify({'error': 'Template not found'}), 404
    
    db.execute(
        'DELETE FROM user_templates WHERE id = ? AND user_id = ?',
        (template_id, session['user_id'])
    )
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/songs')
@login_required
def api_songs():
    return jsonify(get_user_songs(session['user_id']))

@app.route('/api/artists/<name>', methods=['DELETE'])
@login_required
def api_delete_artist(name):
    """Delete a user-created artist."""
    db = get_db()
    
    # Check if it's a user artist (not system)
    artist = db.execute(
        'SELECT * FROM user_artists WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    ).fetchone()
    
    if not artist:
        return jsonify({'error': 'Artist not found or not owned by you'}), 404
    
    db.execute(
        'DELETE FROM user_artists WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    )
    db.commit()
    
    return jsonify({'success': True, 'message': f'Deleted artist: {name}'})

@app.route('/api/artists/<name>', methods=['PUT'])
@login_required
def api_update_artist(name):
    """Update a user-created artist."""
    db = get_db()
    
    # Check if it's a user artist (not system)
    artist = db.execute(
        'SELECT * FROM user_artists WHERE user_id = ? AND filename = ?',
        (session['user_id'], name)
    ).fetchone()
    
    if not artist:
        return jsonify({'error': 'Artist not found or not owned by you'}), 404
    
    data = request.json
    
    # Update fields
    db.execute('''
        UPDATE user_artists 
        SET name = ?, style = ?, voice = ?, tags = ?, description = ?
        WHERE user_id = ? AND filename = ?
    ''', (
        data.get('name', artist['name']),
        data.get('style', artist['style']),
        data.get('voice', artist['voice']),
        data.get('tags', artist['tags']),
        data.get('description', artist['description']),
        session['user_id'],
        name
    ))
    db.commit()
    
    return jsonify({'success': True, 'message': f'Updated artist: {name}'})

@app.route('/api/songs/<int:song_id>', methods=['DELETE'])
@login_required
def api_delete_song(song_id):
    """Delete a user's song."""
    db = get_db()
    
    # Check ownership
    song = db.execute(
        'SELECT * FROM songs WHERE id = ? AND user_id = ?',
        (song_id, session['user_id'])
    ).fetchone()
    
    if not song:
        return jsonify({'error': 'Song not found or not owned by you'}), 404
    
    db.execute(
        'DELETE FROM songs WHERE id = ? AND user_id = ?',
        (song_id, session['user_id'])
    )
    db.commit()
    
    return jsonify({'success': True, 'message': 'Song deleted'})

@app.route('/api/songs/<int:song_id>/rate', methods=['POST'])
@login_required
def api_rate_song(song_id):
    """Rate a song."""
    data = request.json
    rating = data.get('rating', 0)
    
    if not 0 <= rating <= 5:
        return jsonify({'error': 'Rating must be 0-5'}), 400
    
    db = get_db()
    db.execute(
        'UPDATE songs SET rating = ? WHERE id = ? AND user_id = ?',
        (rating, song_id, session['user_id'])
    )
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/audio/<path:filename>')
@login_required
def api_audio(filename):
    """Serve audio files."""
    return send_from_directory(MUSIC_DIR, filename)

@app.route('/api/generate', methods=['POST'])
@login_required
def api_generate():
    """Generate a song."""
    data = request.json
    mode = data.get('mode', 'standard')
    artist = data.get('artist')
    artist2 = data.get('artist2')
    concept = data.get('concept')
    lyrics = data.get('lyrics')
    vibe = data.get('vibe')
    duration = data.get('duration', 120)
    steps = data.get('steps', 60)
    
    cmd = [str(GENERATE_SCRIPT)]
    
    if mode == 'standard':
        cmd.extend([artist, concept])
    elif mode == 'collab':
        cmd.extend(['--collab', artist, artist2, concept])
    elif mode == 'battle':
        cmd.extend(['--battle', artist, artist2, concept])
    elif mode == 'album':
        cmd.extend(['--album', artist, concept])
    elif mode == 'vibe':
        cmd.extend(['--vibe', vibe, concept])
    elif mode == 'lyrics':
        cmd.extend(['--lyrics', lyrics])
    
    cmd.extend(['--duration', str(duration), '--steps', str(steps)])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(BASE_DIR)
        )
        
        # Extract song info and save to user's catalog
        song_id_match = re.search(r'SONG_ID=(\d+)', result.stdout)
        audio_match = re.search(r'AUDIO_FILE=(.+)', result.stdout)
        
        if song_id_match and audio_match:
            song_id = int(song_id_match.group(1))
            audio_file = audio_match.group(1)
            
            # Extract lyrics from output if available
            lyrics_match = re.search(r'LYRICS_START(.+?)LYRICS_END', result.stdout, re.DOTALL)
            song_lyrics = lyrics_match.group(1).strip() if lyrics_match else ''
            
            # Save to database
            db = get_db()
            db.execute('''
                INSERT OR REPLACE INTO songs (id, user_id, artist, concept, lyrics, file_path, tags, mode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (song_id, session['user_id'], artist or '', concept or '', song_lyrics, audio_file, '', mode))
            db.commit()
        
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr,
            'audio_file': audio_match.group(1) if audio_match else None
        })
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Generation timed out'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/create/artist', methods=['POST'])
@login_required
def api_create_artist():
    """Create a new artist for the user."""
    data = request.json
    description = data.get('description')
    
    cmd = [str(GENERATE_SCRIPT), '--artist', description]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR)
        )
        
        # Parse the created artist and save to user's collection
        artist_match = re.search(r'ARTIST_FILE=(.+)', result.stdout)
        if artist_match and result.returncode == 0:
            artist_file = Path(artist_match.group(1))
            if artist_file.exists():
                artist = parse_artist_file(artist_file)
                db = get_db()
                # Map YAML fields correctly
                style = artist.get('personality', '') or artist.get('style', '')
                if artist.get('mood'):
                    style = f"{style} - {artist.get('mood')}" if style else artist.get('mood')
                
                voice = artist.get('vocal_style', '') or artist.get('voice', '')
                if artist.get('vocal_gender'):
                    voice = f"{artist.get('vocal_gender')}, {voice}" if voice else artist.get('vocal_gender')
                
                tags = artist.get('signature_tags', '') or artist.get('tags', '')
                
                db.execute('''
                    INSERT INTO user_artists (user_id, name, filename, style, voice, tags, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session['user_id'],
                    artist.get('name', artist['filename']),
                    artist['filename'],
                    style,
                    voice,
                    tags,
                    artist.get('body', '')
                ))
                db.commit()
        
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============== PROFILE API ==============

@app.route('/api/profile')
@login_required
def api_get_profile():
    """Get current user's profile."""
    db = get_db()
    user = db.execute('SELECT id, username, email, created_at FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    profile = db.execute('SELECT * FROM user_profiles WHERE user_id = ?', (session['user_id'],)).fetchone()
    
    if not profile:
        db.execute('INSERT INTO user_profiles (user_id) VALUES (?)', (session['user_id'],))
        db.commit()
        profile = db.execute('SELECT * FROM user_profiles WHERE user_id = ?', (session['user_id'],)).fetchone()
    
    stats = get_user_stats(session['user_id'])
    badges = db.execute('''
        SELECT b.* FROM badges b
        JOIN user_badges ub ON b.id = ub.badge_id
        WHERE ub.user_id = ?
        ORDER BY ub.earned_at DESC
    ''', (session['user_id'],)).fetchall()
    
    return jsonify({
        'user': dict(user),
        'profile': dict(profile),
        'stats': stats,
        'badges': [dict(b) for b in badges]
    })

@app.route('/api/profile', methods=['PUT'])
@login_required
def api_update_profile():
    """Update current user's profile."""
    db = get_db()
    data = request.json
    
    profile = db.execute('SELECT * FROM user_profiles WHERE user_id = ?', (session['user_id'],)).fetchone()
    if not profile:
        db.execute('INSERT INTO user_profiles (user_id) VALUES (?)', (session['user_id'],))
    
    db.execute('''
        UPDATE user_profiles SET
            display_name = ?, bio = ?, is_public = ?, website = ?, location = ?
        WHERE user_id = ?
    ''', (
        data.get('display_name', ''),
        data.get('bio', ''),
        1 if data.get('is_public') else 0,
        data.get('website', ''),
        data.get('location', ''),
        session['user_id']
    ))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/profile/<username>')
def api_get_public_profile(username):
    """Get a user's public profile."""
    db = get_db()
    user = db.execute('SELECT id, username, created_at FROM users WHERE username = ?', (username,)).fetchone()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    profile = db.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user['id'],)).fetchone()
    if not profile or not profile['is_public']:
        return jsonify({'error': 'Profile is private'}), 403
    
    stats = get_user_stats(user['id'])
    songs = db.execute('SELECT * FROM songs WHERE user_id = ? AND is_public = 1 ORDER BY created_at DESC LIMIT 20', (user['id'],)).fetchall()
    
    is_following = False
    if 'user_id' in session:
        follow = db.execute('SELECT 1 FROM follows WHERE follower_id = ? AND following_id = ?', (session['user_id'], user['id'])).fetchone()
        is_following = follow is not None
    
    return jsonify({
        'user': dict(user),
        'profile': dict(profile),
        'stats': stats,
        'songs': [dict(s) for s in songs],
        'is_following': is_following
    })

# ============== FOLLOW API ==============

@app.route('/api/follow/<int:user_id>', methods=['POST'])
@login_required
def api_follow(user_id):
    if user_id == session['user_id']:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    db = get_db()
    try:
        db.execute('INSERT INTO follows (follower_id, following_id) VALUES (?, ?)', (session['user_id'], user_id))
        db.commit()
        check_and_award_badges(user_id)
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Already following'}), 400

@app.route('/api/follow/<int:user_id>', methods=['DELETE'])
@login_required
def api_unfollow(user_id):
    db = get_db()
    db.execute('DELETE FROM follows WHERE follower_id = ? AND following_id = ?', (session['user_id'], user_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/followers')
@login_required
def api_get_followers():
    db = get_db()
    followers = db.execute('''
        SELECT u.id, u.username, p.display_name, p.avatar_url
        FROM follows f JOIN users u ON f.follower_id = u.id
        LEFT JOIN user_profiles p ON u.id = p.user_id
        WHERE f.following_id = ?
    ''', (session['user_id'],)).fetchall()
    return jsonify([dict(f) for f in followers])

@app.route('/api/following')
@login_required
def api_get_following():
    db = get_db()
    following = db.execute('''
        SELECT u.id, u.username, p.display_name, p.avatar_url
        FROM follows f JOIN users u ON f.following_id = u.id
        LEFT JOIN user_profiles p ON u.id = p.user_id
        WHERE f.follower_id = ?
    ''', (session['user_id'],)).fetchall()
    return jsonify([dict(f) for f in following])

# ============== LIKES API ==============

@app.route('/api/songs/<int:song_id>/like', methods=['POST'])
@login_required
def api_like_song(song_id):
    db = get_db()
    try:
        db.execute('INSERT INTO song_likes (user_id, song_id) VALUES (?, ?)', (session['user_id'], song_id))
        db.execute('UPDATE songs SET like_count = like_count + 1 WHERE id = ?', (song_id,))
        db.commit()
        song = db.execute('SELECT user_id FROM songs WHERE id = ?', (song_id,)).fetchone()
        if song:
            check_and_award_badges(song['user_id'])
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Already liked'}), 400

@app.route('/api/songs/<int:song_id>/like', methods=['DELETE'])
@login_required
def api_unlike_song(song_id):
    db = get_db()
    result = db.execute('DELETE FROM song_likes WHERE user_id = ? AND song_id = ?', (session['user_id'], song_id))
    if result.rowcount > 0:
        db.execute('UPDATE songs SET like_count = like_count - 1 WHERE id = ? AND like_count > 0', (song_id,))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/songs/<int:song_id>/liked')
@login_required
def api_check_liked(song_id):
    db = get_db()
    liked = db.execute('SELECT 1 FROM song_likes WHERE user_id = ? AND song_id = ?', (session['user_id'], song_id)).fetchone()
    return jsonify({'liked': liked is not None})

@app.route('/api/liked-songs')
@login_required
def api_get_liked_songs():
    db = get_db()
    songs = db.execute('''
        SELECT s.*, u.username as owner_username FROM song_likes l
        JOIN songs s ON l.song_id = s.id JOIN users u ON s.user_id = u.id
        WHERE l.user_id = ? ORDER BY l.created_at DESC
    ''', (session['user_id'],)).fetchall()
    return jsonify([dict(s) for s in songs])

# ============== COMMENTS API ==============

@app.route('/api/songs/<int:song_id>/comments')
def api_get_comments(song_id):
    db = get_db()
    comments = db.execute('''
        SELECT c.*, u.username, p.display_name FROM song_comments c
        JOIN users u ON c.user_id = u.id LEFT JOIN user_profiles p ON u.id = p.user_id
        WHERE c.song_id = ? ORDER BY c.created_at DESC
    ''', (song_id,)).fetchall()
    return jsonify([dict(c) for c in comments])

@app.route('/api/songs/<int:song_id>/comments', methods=['POST'])
@login_required
def api_add_comment(song_id):
    data = request.json
    content = data.get('content', '').strip()
    if not content:
        return jsonify({'error': 'Comment cannot be empty'}), 400
    db = get_db()
    db.execute('INSERT INTO song_comments (user_id, song_id, content) VALUES (?, ?, ?)', (session['user_id'], song_id, content))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def api_delete_comment(comment_id):
    db = get_db()
    comment = db.execute('SELECT * FROM song_comments WHERE id = ?', (comment_id,)).fetchone()
    if not comment:
        return jsonify({'error': 'Not found'}), 404
    if comment['user_id'] != session['user_id']:
        return jsonify({'error': 'Not your comment'}), 403
    db.execute('DELETE FROM song_comments WHERE id = ?', (comment_id,))
    db.commit()
    return jsonify({'success': True})

# ============== TAGS API ==============

@app.route('/api/songs/<int:song_id>/tags')
@login_required
def api_get_song_tags(song_id):
    db = get_db()
    tags = db.execute('SELECT tag FROM song_tags WHERE song_id = ?', (song_id,)).fetchall()
    return jsonify([t['tag'] for t in tags])

@app.route('/api/songs/<int:song_id>/tags', methods=['POST'])
@login_required
def api_add_song_tag(song_id):
    db = get_db()
    song = db.execute('SELECT user_id FROM songs WHERE id = ?', (song_id,)).fetchone()
    if not song or song['user_id'] != session['user_id']:
        return jsonify({'error': 'Not your song'}), 403
    data = request.json
    tag = data.get('tag', '').strip().lower()
    if not tag:
        return jsonify({'error': 'Tag cannot be empty'}), 400
    try:
        db.execute('INSERT INTO song_tags (song_id, tag) VALUES (?, ?)', (song_id, tag))
        db.commit()
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Tag already exists'}), 400

@app.route('/api/songs/<int:song_id>/tags/<tag>', methods=['DELETE'])
@login_required
def api_remove_song_tag(song_id, tag):
    db = get_db()
    song = db.execute('SELECT user_id FROM songs WHERE id = ?', (song_id,)).fetchone()
    if not song or song['user_id'] != session['user_id']:
        return jsonify({'error': 'Not your song'}), 403
    db.execute('DELETE FROM song_tags WHERE song_id = ? AND tag = ?', (song_id, tag))
    db.commit()
    return jsonify({'success': True})

# ============== PLAYLISTS API ==============

@app.route('/api/playlists')
@login_required
def api_get_playlists():
    db = get_db()
    playlists = db.execute('''
        SELECT p.*, COUNT(ps.id) as song_count FROM playlists p
        LEFT JOIN playlist_songs ps ON p.id = ps.playlist_id
        WHERE p.user_id = ? GROUP BY p.id ORDER BY p.created_at DESC
    ''', (session['user_id'],)).fetchall()
    return jsonify([dict(p) for p in playlists])

@app.route('/api/playlists', methods=['POST'])
@login_required
def api_create_playlist():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    db = get_db()
    cursor = db.execute('INSERT INTO playlists (user_id, name, description, is_public) VALUES (?, ?, ?, ?)',
        (session['user_id'], name, data.get('description', ''), 1 if data.get('is_public') else 0))
    db.commit()
    check_and_award_badges(session['user_id'])
    return jsonify({'success': True, 'id': cursor.lastrowid})

@app.route('/api/playlists/<int:playlist_id>')
@login_required
def api_get_playlist(playlist_id):
    db = get_db()
    playlist = db.execute('SELECT * FROM playlists WHERE id = ?', (playlist_id,)).fetchone()
    if not playlist:
        return jsonify({'error': 'Not found'}), 404
    if playlist['user_id'] != session['user_id'] and not playlist['is_public']:
        return jsonify({'error': 'Private'}), 403
    songs = db.execute('''
        SELECT s.*, ps.position FROM playlist_songs ps
        JOIN songs s ON ps.song_id = s.id WHERE ps.playlist_id = ? ORDER BY ps.position
    ''', (playlist_id,)).fetchall()
    return jsonify({'playlist': dict(playlist), 'songs': [dict(s) for s in songs]})

@app.route('/api/playlists/<int:playlist_id>', methods=['PUT'])
@login_required
def api_update_playlist(playlist_id):
    db = get_db()
    playlist = db.execute('SELECT * FROM playlists WHERE id = ? AND user_id = ?', (playlist_id, session['user_id'])).fetchone()
    if not playlist:
        return jsonify({'error': 'Not found'}), 404
    data = request.json
    db.execute('UPDATE playlists SET name = ?, description = ?, is_public = ? WHERE id = ?',
        (data.get('name', playlist['name']), data.get('description', playlist['description']), 1 if data.get('is_public') else 0, playlist_id))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/playlists/<int:playlist_id>', methods=['DELETE'])
@login_required
def api_delete_playlist(playlist_id):
    db = get_db()
    db.execute('DELETE FROM playlist_songs WHERE playlist_id = ?', (playlist_id,))
    db.execute('DELETE FROM playlists WHERE id = ? AND user_id = ?', (playlist_id, session['user_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/playlists/<int:playlist_id>/songs', methods=['POST'])
@login_required
def api_add_to_playlist(playlist_id):
    db = get_db()
    playlist = db.execute('SELECT * FROM playlists WHERE id = ? AND user_id = ?', (playlist_id, session['user_id'])).fetchone()
    if not playlist:
        return jsonify({'error': 'Not found'}), 404
    data = request.json
    max_pos = db.execute('SELECT MAX(position) FROM playlist_songs WHERE playlist_id = ?', (playlist_id,)).fetchone()[0] or 0
    try:
        db.execute('INSERT INTO playlist_songs (playlist_id, song_id, position) VALUES (?, ?, ?)', (playlist_id, data.get('song_id'), max_pos + 1))
        db.commit()
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Already in playlist'}), 400

@app.route('/api/playlists/<int:playlist_id>/songs/<int:song_id>', methods=['DELETE'])
@login_required
def api_remove_from_playlist(playlist_id, song_id):
    db = get_db()
    db.execute('DELETE FROM playlist_songs WHERE playlist_id = ? AND song_id = ?', (playlist_id, song_id))
    db.commit()
    return jsonify({'success': True})

# ============== FOLDERS API ==============

@app.route('/api/folders')
@login_required
def api_get_folders():
    db = get_db()
    folders = db.execute('''
        SELECT f.*, COUNT(fi.id) as item_count FROM folders f
        LEFT JOIN folder_items fi ON f.id = fi.folder_id
        WHERE f.user_id = ? GROUP BY f.id ORDER BY f.name
    ''', (session['user_id'],)).fetchall()
    return jsonify([dict(f) for f in folders])

@app.route('/api/folders', methods=['POST'])
@login_required
def api_create_folder():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name required'}), 400
    db = get_db()
    cursor = db.execute('INSERT INTO folders (user_id, name, parent_id, color, icon) VALUES (?, ?, ?, ?, ?)',
        (session['user_id'], name, data.get('parent_id'), data.get('color', '#8b5cf6'), data.get('icon', '📁')))
    db.commit()
    return jsonify({'success': True, 'id': cursor.lastrowid})

@app.route('/api/folders/<int:folder_id>')
@login_required
def api_get_folder(folder_id):
    db = get_db()
    folder = db.execute('SELECT * FROM folders WHERE id = ? AND user_id = ?', (folder_id, session['user_id'])).fetchone()
    if not folder:
        return jsonify({'error': 'Not found'}), 404
    items = db.execute('SELECT * FROM folder_items WHERE folder_id = ?', (folder_id,)).fetchall()
    songs, artists = [], []
    for item in items:
        if item['item_type'] == 'song':
            s = db.execute('SELECT * FROM songs WHERE id = ?', (item['item_id'],)).fetchone()
            if s: songs.append(dict(s))
        elif item['item_type'] == 'artist':
            a = db.execute('SELECT * FROM user_artists WHERE id = ?', (item['item_id'],)).fetchone()
            if a: artists.append(dict(a))
    return jsonify({'folder': dict(folder), 'songs': songs, 'artists': artists})

@app.route('/api/folders/<int:folder_id>', methods=['PUT'])
@login_required
def api_update_folder(folder_id):
    db = get_db()
    data = request.json
    db.execute('UPDATE folders SET name = ?, color = ?, icon = ? WHERE id = ? AND user_id = ?',
        (data.get('name'), data.get('color'), data.get('icon'), folder_id, session['user_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@login_required
def api_delete_folder(folder_id):
    db = get_db()
    db.execute('DELETE FROM folder_items WHERE folder_id = ?', (folder_id,))
    db.execute('DELETE FROM folders WHERE id = ? AND user_id = ?', (folder_id, session['user_id']))
    db.commit()
    return jsonify({'success': True})

@app.route('/api/folders/<int:folder_id>/items', methods=['POST'])
@login_required
def api_add_to_folder(folder_id):
    db = get_db()
    data = request.json
    try:
        db.execute('INSERT INTO folder_items (folder_id, item_type, item_id) VALUES (?, ?, ?)',
            (folder_id, data.get('item_type'), data.get('item_id')))
        db.commit()
        return jsonify({'success': True})
    except:
        return jsonify({'error': 'Already in folder'}), 400

@app.route('/api/folders/<int:folder_id>/items/<item_type>/<int:item_id>', methods=['DELETE'])
@login_required
def api_remove_from_folder(folder_id, item_type, item_id):
    db = get_db()
    db.execute('DELETE FROM folder_items WHERE folder_id = ? AND item_type = ? AND item_id = ?', (folder_id, item_type, item_id))
    db.commit()
    return jsonify({'success': True})

# ============== DETAILED STATS API ==============

@app.route('/api/stats/detailed')
@login_required
def api_detailed_stats():
    stats = get_user_stats(session['user_id'])
    db = get_db()
    gen_history = db.execute('''
        SELECT DATE(created_at) as date, COUNT(*) as count, SUM(cost) as cost
        FROM generation_logs WHERE user_id = ? AND created_at > datetime('now', '-30 days')
        GROUP BY DATE(created_at) ORDER BY date
    ''', (session['user_id'],)).fetchall()
    top_artists = db.execute('''
        SELECT artist, COUNT(*) as count, AVG(rating) as avg_rating FROM songs
        WHERE user_id = ? GROUP BY artist ORDER BY count DESC LIMIT 10
    ''', (session['user_id'],)).fetchall()
    rating_dist = db.execute('SELECT rating, COUNT(*) as count FROM songs WHERE user_id = ? AND rating > 0 GROUP BY rating', (session['user_id'],)).fetchall()
    most_played = db.execute('SELECT * FROM songs WHERE user_id = ? AND play_count > 0 ORDER BY play_count DESC LIMIT 10', (session['user_id'],)).fetchall()
    recent_plays = db.execute('''
        SELECT s.*, sp.played_at FROM song_plays sp JOIN songs s ON sp.song_id = s.id
        WHERE sp.user_id = ? ORDER BY sp.played_at DESC LIMIT 20
    ''', (session['user_id'],)).fetchall()
    cost_by_mode = db.execute('SELECT mode, SUM(cost) as total_cost, COUNT(*) as count FROM generation_logs WHERE user_id = ? GROUP BY mode', (session['user_id'],)).fetchall()
    best_tags = db.execute('''
        SELECT st.tag, COUNT(*) as count, AVG(s.rating) as avg_rating FROM song_tags st
        JOIN songs s ON st.song_id = s.id WHERE s.user_id = ? AND s.rating > 0
        GROUP BY st.tag HAVING count >= 2 ORDER BY avg_rating DESC LIMIT 10
    ''', (session['user_id'],)).fetchall()
    return jsonify({
        'overview': stats, 'generation_history': [dict(g) for g in gen_history],
        'top_artists': [dict(a) for a in top_artists], 'rating_distribution': [dict(r) for r in rating_dist],
        'most_played': [dict(s) for s in most_played], 'recent_plays': [dict(p) for p in recent_plays],
        'cost_by_mode': [dict(c) for c in cost_by_mode], 'best_tags': [dict(t) for t in best_tags]
    })

@app.route('/api/stats/record-play', methods=['POST'])
@login_required
def api_record_play():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO song_plays (user_id, song_id, duration_listened) VALUES (?, ?, ?)',
        (session['user_id'], data.get('song_id'), data.get('duration', 0)))
    db.execute('UPDATE songs SET play_count = play_count + 1 WHERE id = ?', (data.get('song_id'),))
    db.commit()
    return jsonify({'success': True})

# ============== SEARCH API ==============

@app.route('/api/search')
@login_required
def api_search():
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'all')
    if not query:
        return jsonify({'songs': [], 'artists': [], 'users': []})
    db = get_db()
    results = {}
    if search_type in ['all', 'songs']:
        songs = db.execute('''
            SELECT s.*, u.username as owner FROM songs s JOIN users u ON s.user_id = u.id
            WHERE s.user_id = ? AND (s.artist LIKE ? OR s.concept LIKE ? OR s.lyrics LIKE ? OR s.tags LIKE ?)
            ORDER BY s.created_at DESC LIMIT 50
        ''', (session['user_id'], f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
        results['songs'] = [dict(s) for s in songs]
    if search_type in ['all', 'artists']:
        artists = db.execute('SELECT * FROM user_artists WHERE user_id = ? AND (name LIKE ? OR style LIKE ? OR tags LIKE ?) LIMIT 20',
            (session['user_id'], f'%{query}%', f'%{query}%', f'%{query}%')).fetchall()
        results['artists'] = [dict(a) for a in artists]
    if search_type in ['all', 'users']:
        users = db.execute('''
            SELECT u.id, u.username, p.display_name, p.bio FROM users u
            LEFT JOIN user_profiles p ON u.id = p.user_id
            WHERE p.is_public = 1 AND (u.username LIKE ? OR p.display_name LIKE ?) LIMIT 20
        ''', (f'%{query}%', f'%{query}%')).fetchall()
        results['users'] = [dict(u) for u in users]
    return jsonify(results)

@app.route('/api/search/tags')
@login_required
def api_search_by_tags():
    tags = [t.strip().lower() for t in request.args.get('tags', '').split(',') if t.strip()]
    if not tags:
        return jsonify([])
    db = get_db()
    placeholders = ','.join(['?' for _ in tags])
    songs = db.execute(f'''
        SELECT DISTINCT s.* FROM songs s JOIN song_tags st ON s.id = st.song_id
        WHERE s.user_id = ? AND st.tag IN ({placeholders}) ORDER BY s.created_at DESC
    ''', [session['user_id']] + tags).fetchall()
    return jsonify([dict(s) for s in songs])

# ============== DISCOVER API ==============

@app.route('/api/discover/songs')
@login_required
def api_discover_songs():
    db = get_db()
    songs = db.execute('''
        SELECT s.*, u.username as owner, p.display_name as owner_name FROM songs s
        JOIN users u ON s.user_id = u.id LEFT JOIN user_profiles p ON u.id = p.user_id
        WHERE s.is_public = 1 ORDER BY s.like_count DESC, s.created_at DESC LIMIT 50
    ''').fetchall()
    return jsonify([dict(s) for s in songs])

@app.route('/api/discover/users')
@login_required
def api_discover_users():
    db = get_db()
    users = db.execute('''
        SELECT u.id, u.username, p.display_name, p.bio, p.avatar_url,
            (SELECT COUNT(*) FROM follows WHERE following_id = u.id) as followers,
            (SELECT COUNT(*) FROM songs WHERE user_id = u.id AND is_public = 1) as public_songs
        FROM users u JOIN user_profiles p ON u.id = p.user_id
        WHERE p.is_public = 1 ORDER BY followers DESC LIMIT 50
    ''').fetchall()
    return jsonify([dict(u) for u in users])

# ============== BADGES API ==============

@app.route('/api/badges')
@login_required
def api_get_all_badges():
    db = get_db()
    badges = db.execute('SELECT * FROM badges ORDER BY category, requirement_value').fetchall()
    earned = [e['badge_id'] for e in db.execute('SELECT badge_id FROM user_badges WHERE user_id = ?', (session['user_id'],)).fetchall()]
    result = []
    for badge in badges:
        b = dict(badge)
        b['earned'] = badge['id'] in earned
        result.append(b)
    return jsonify(result)

@app.route('/api/badges/check', methods=['POST'])
@login_required
def api_check_badges():
    new_badges = check_and_award_badges(session['user_id'])
    return jsonify({'new_badges': [dict(b) for b in new_badges]})

# ============== SONG VISIBILITY ==============

@app.route('/api/songs/<int:song_id>/visibility', methods=['PUT'])
@login_required
def api_set_song_visibility(song_id):
    db = get_db()
    song = db.execute('SELECT * FROM songs WHERE id = ? AND user_id = ?', (song_id, session['user_id'])).fetchone()
    if not song:
        return jsonify({'error': 'Not found'}), 404
    data = request.json
    db.execute('UPDATE songs SET is_public = ? WHERE id = ?', (1 if data.get('is_public') else 0, song_id))
    db.commit()
    return jsonify({'success': True})

# ============== STYLE TRANSFER & EXTEND ==============

@app.route('/api/songs/<int:song_id>/style-transfer', methods=['POST'])
@login_required
def api_style_transfer(song_id):
    db = get_db()
    song = db.execute('SELECT * FROM songs WHERE id = ?', (song_id,)).fetchone()
    if not song:
        return jsonify({'error': 'Song not found'}), 404
    if song['user_id'] != session['user_id'] and not song['is_public']:
        return jsonify({'error': 'Cannot access'}), 403
    data = request.json
    if not data.get('artist'):
        return jsonify({'error': 'New artist required'}), 400
    return jsonify({'success': True, 'message': 'Style transfer queued', 'original_song': song_id, 'new_artist': data.get('artist')})

@app.route('/api/songs/<int:song_id>/extend', methods=['POST'])
@login_required
def api_extend_song(song_id):
    db = get_db()
    song = db.execute('SELECT * FROM songs WHERE id = ? AND user_id = ?', (song_id, session['user_id'])).fetchone()
    if not song:
        return jsonify({'error': 'Not found or not yours'}), 404
    data = request.json
    return jsonify({'success': True, 'message': 'Extension queued', 'song_id': song_id, 'extension_type': data.get('type', 'verse')})

# ============== ARTIST PHOTO GENERATION ==============

def run_photo_generation(job_id, options):
    """Background task to generate artist photos via ComfyUI."""
    import sys
    sys.path.insert(0, str(COMFYUI_PORTRAITS_DIR))
    
    try:
        # Import the generate module
        from generate import generate, OUTPUT_DIR
        
        generated_paths = []
        
        # Generate 4 photos
        for i in range(4):
            try:
                path = generate(
                    gender=options.get('gender'),
                    age=options.get('age'),
                    ethnicity=options.get('ethnicity'),
                    clothing=options.get('clothing'),
                    framing='headshot',
                    style=options.get('style', 'photorealistic'),
                    background=options.get('background'),
                    additional=options.get('additional'),
                    quality='high',
                    resolution='full_hd',
                    aspect='portrait'
                )
                
                # Copy upscaled photo to artist_photos directory
                dest_filename = f"job_{job_id}_option_{i+1}.png"
                dest_path = ARTIST_PHOTOS_DIR / dest_filename
                shutil.copy(path, dest_path)
                generated_paths.append(dest_filename)
                
            except Exception as e:
                print(f"Error generating photo {i+1}: {e}")
                continue
        
        # Update job status in database
        import sqlite3
        db = sqlite3.connect(str(DATABASE))
        if generated_paths:
            db.execute('''
                UPDATE artist_photo_jobs 
                SET status = 'completed', photo_paths = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(generated_paths), job_id))
        else:
            db.execute('''
                UPDATE artist_photo_jobs 
                SET status = 'failed', error = 'All generations failed', completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (job_id,))
        db.commit()
        db.close()
        
    except Exception as e:
        import sqlite3
        db = sqlite3.connect(str(DATABASE))
        db.execute('''
            UPDATE artist_photo_jobs 
            SET status = 'failed', error = ?, completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (str(e), job_id))
        db.commit()
        db.close()


@app.route('/api/artist-photos/generate', methods=['POST'])
@login_required
def api_generate_artist_photos():
    """Start artist photo generation job."""
    data = request.json
    db = get_db()
    
    # Create job record
    cursor = db.execute('''
        INSERT INTO artist_photo_jobs (
            user_id, artist_filename, status, gender, age, ethnicity,
            hair_color, hair_style, eye_color, clothing, style, background, additional
        ) VALUES (?, ?, 'generating', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        session['user_id'],
        data.get('artist_filename'),
        data.get('gender'),
        data.get('age'),
        data.get('ethnicity'),
        data.get('hair_color'),
        data.get('hair_style'),
        data.get('eye_color'),
        data.get('clothing'),
        data.get('style', 'photorealistic'),
        data.get('background'),
        data.get('additional')
    ))
    db.commit()
    job_id = cursor.lastrowid
    
    # Build additional prompt from appearance details
    additional_parts = []
    if data.get('hair_color'):
        additional_parts.append(f"{data['hair_color']} hair")
    if data.get('hair_style'):
        additional_parts.append(f"{data['hair_style']} hair style")
    if data.get('eye_color'):
        additional_parts.append(f"{data['eye_color']} eyes")
    
    options = {
        'gender': data.get('gender'),
        'age': data.get('age'),
        'ethnicity': data.get('ethnicity'),
        'clothing': data.get('clothing'),
        'style': data.get('style', 'photorealistic'),
        'background': data.get('background'),
        'additional': ', '.join(additional_parts) if additional_parts else data.get('additional')
    }
    
    # Start background generation
    thread = threading.Thread(target=run_photo_generation, args=(job_id, options))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'job_id': job_id,
        'message': 'Photo generation started. This may take a few minutes.'
    })


@app.route('/api/artist-photos/jobs')
@login_required
def api_get_photo_jobs():
    """Get all photo jobs for current user."""
    db = get_db()
    jobs = db.execute('''
        SELECT * FROM artist_photo_jobs 
        WHERE user_id = ? 
        ORDER BY created_at DESC
    ''', (session['user_id'],)).fetchall()
    
    result = []
    for job in jobs:
        j = dict(job)
        if j['photo_paths']:
            j['photo_paths'] = json.loads(j['photo_paths'])
        result.append(j)
    
    return jsonify(result)


@app.route('/api/artist-photos/jobs/<int:job_id>')
@login_required
def api_get_photo_job(job_id):
    """Get specific photo job status."""
    db = get_db()
    job = db.execute('''
        SELECT * FROM artist_photo_jobs 
        WHERE id = ? AND user_id = ?
    ''', (job_id, session['user_id'])).fetchone()
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    j = dict(job)
    if j['photo_paths']:
        j['photo_paths'] = json.loads(j['photo_paths'])
    
    return jsonify(j)


@app.route('/api/artist-photos/jobs/<int:job_id>/select', methods=['POST'])
@login_required
def api_select_artist_photo(job_id):
    """Select a photo from a completed job."""
    db = get_db()
    job = db.execute('''
        SELECT * FROM artist_photo_jobs 
        WHERE id = ? AND user_id = ? AND status = 'completed'
    ''', (job_id, session['user_id'])).fetchone()
    
    if not job:
        return jsonify({'error': 'Job not found or not completed'}), 404
    
    data = request.json
    selected_photo = data.get('photo')
    
    if not selected_photo:
        return jsonify({'error': 'No photo selected'}), 400
    
    photo_paths = json.loads(job['photo_paths']) if job['photo_paths'] else []
    if selected_photo not in photo_paths:
        return jsonify({'error': 'Invalid photo selection'}), 400
    
    # Update job with selection
    db.execute('''
        UPDATE artist_photo_jobs SET selected_photo = ? WHERE id = ?
    ''', (selected_photo, job_id))
    
    photo_url = f'/artist-photos/{selected_photo}'
    
    # If linked to an artist, update the artist
    if job['artist_filename']:
        # First check if it's a user artist (in database)
        user_artist = db.execute('''
            SELECT * FROM user_artists WHERE user_id = ? AND filename = ?
        ''', (session['user_id'], job['artist_filename'])).fetchone()
        
        if user_artist:
            # Update user artist in database
            db.execute('''
                UPDATE user_artists SET photo_url = ? WHERE id = ?
            ''', (photo_url, user_artist['id']))
        else:
            # Check if it's a system artist (file-based)
            artist_file = ARTISTS_DIR / f"{job['artist_filename']}.md"
            if not artist_file.exists():
                artist_file = ARTISTS_DIR / job['artist_filename']
            
            if artist_file.exists():
                content = artist_file.read_text()
                # Add photo_url to frontmatter
                if '---' in content:
                    parts = content.split('---', 2)
                    if len(parts) >= 3:
                        frontmatter = parts[1]
                        body = parts[2]
                        # Add or update photo_url
                        if 'photo_url:' in frontmatter:
                            frontmatter = re.sub(r'photo_url:.*\n', f'photo_url: {photo_url}\n', frontmatter)
                        else:
                            frontmatter = frontmatter.rstrip() + f'\nphoto_url: {photo_url}\n'
                        content = f'---{frontmatter}---{body}'
                        artist_file.write_text(content)
    
    db.commit()
    
    return jsonify({
        'success': True,
        'selected_photo': selected_photo,
        'photo_url': f'/artist-photos/{selected_photo}'
    })


@app.route('/artist-photos/<path:filename>')
def serve_artist_photo(filename):
    """Serve artist photos."""
    return send_from_directory(str(ARTIST_PHOTOS_DIR), filename)


@app.route('/api/artist-photos/jobs/<int:job_id>', methods=['DELETE'])
@login_required
def api_delete_photo_job(job_id):
    """Delete a photo job and its files."""
    db = get_db()
    job = db.execute('''
        SELECT * FROM artist_photo_jobs 
        WHERE id = ? AND user_id = ?
    ''', (job_id, session['user_id'])).fetchone()
    
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    # Delete photo files
    if job['photo_paths']:
        for photo in json.loads(job['photo_paths']):
            photo_path = ARTIST_PHOTOS_DIR / photo
            if photo_path.exists():
                photo_path.unlink()
    
    # Delete job record
    db.execute('DELETE FROM artist_photo_jobs WHERE id = ?', (job_id,))
    db.commit()
    
    return jsonify({'success': True})


# ============== STARTUP ==============

if __name__ == '__main__':
    # Ensure directories exist
    CATALOG_DIR.mkdir(exist_ok=True)
    
    # Initialize database
    with app.app_context():
        init_db()
    
    print("🎵 Music Planner Dashboard")
    print("   http://localhost:5555")
    app.run(host='0.0.0.0', port=5555, debug=True)
