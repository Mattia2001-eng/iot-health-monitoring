from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
from functools import wraps
import numpy as np

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-here')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///health_monitoring.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Modelli Database
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sensor_data = db.relationship('SensorData', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_active(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)

class SensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sensor_type = db.Column(db.String(50), nullable=False)  # acc, bvp, eda, hr, ibi, temp
    value = db.Column(db.Float)
    raw_data = db.Column(db.Text)  # JSON per dati multi-dimensionali

class Anomaly(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    sensor_type = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    value = db.Column(db.Float)
    threshold = db.Column(db.Float)
    moving_avg = db.Column(db.Float)
    notified = db.Column(db.Boolean, default=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Accesso negato. Solo gli amministratori possono accedere a questa pagina.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes per l'autenticazione
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Username o password non validi')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# API per ricezione dati sensori
@app.route('/sensors/<client_id>/<sensor_type>', methods=['POST'])
def receive_sensor_data(client_id, sensor_type):
    try:
        data = request.json if request.is_json else request.form
        
        # Trova l'utente associato al client_id
        user = User.query.filter_by(username=client_id.split('_')[0]).first()
        if not user:
            return jsonify({'error': 'Client non autorizzato'}), 401
        
        # Salva i dati del sensore
        sensor_data = SensorData(
            user_id=user.id,
            client_id=client_id,
            sensor_type=sensor_type,
            value=float(data.get('value', 0)) if 'value' in data else None,
            raw_data=json.dumps(data)
        )
        db.session.add(sensor_data)
        
        # Controlla anomalie (media mobile)
        check_anomalies(user.id, sensor_type)
        
        db.session.commit()
        return jsonify({'status': 'ok'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sensors/<client_id>', methods=['GET'])
def get_sensor_list(client_id):
    user = User.query.filter_by(username=client_id.split('_')[0]).first()
    if not user:
        return jsonify({'error': 'Client non autorizzato'}), 401
    
    sensor_types = db.session.query(SensorData.sensor_type).filter_by(
        user_id=user.id
    ).distinct().all()
    
    return jsonify([s[0] for s in sensor_types]), 200

# Dashboard
@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    # Ottieni i dati dell'utente corrente o tutti se admin
    if current_user.is_admin:
        users = User.query.all()
    else:
        users = [current_user]
    
    # Prepara i dati per i grafici
    chart_data = {}
    stats = {}
    
    for user in users:
        user_data = {}
        user_stats = {}
        
        # Ultimi 7 giorni di dati per ogni tipo di sensore
        week_ago = datetime.utcnow() - timedelta(days=7)
        
        for sensor_type in ['acc', 'bvp', 'eda', 'hr', 'ibi', 'temp']:
            data = SensorData.query.filter(
                SensorData.user_id == user.id,
                SensorData.sensor_type == sensor_type,
                SensorData.timestamp > week_ago
            ).order_by(SensorData.timestamp).all()
            
            if data:
                user_data[sensor_type] = {
                    'timestamps': [d.timestamp.strftime('%Y-%m-%d %H:%M:%S') for d in data],
                    'values': [d.value for d in data if d.value is not None]
                }
                
                # Calcola statistiche
                values = [d.value for d in data if d.value is not None]
                if values:
                    user_stats[sensor_type] = {
                        'mean': np.mean(values),
                        'std': np.std(values),
                        'min': np.min(values),
                        'max': np.max(values),
                        'count': len(values)
                    }
        
        chart_data[user.username] = user_data
        stats[user.username] = user_stats
    
    # Ottieni anomalie recenti
    anomalies = Anomaly.query.order_by(Anomaly.timestamp.desc()).limit(20).all()
    
    return render_template('dashboard.html', 
                         chart_data=json.dumps(chart_data),
                         stats=stats,
                         anomalies=anomalies,
                         is_admin=current_user.is_admin)

# Amministrazione
@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.all()
    return render_template('admin.html', users=users)

@app.route('/admin/create_user', methods=['GET', 'POST'])
@admin_required
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        is_admin = request.form.get('is_admin') == 'on'
        
        # Verifica se l'utente esiste già
        if User.query.filter_by(username=username).first():
            flash('Username già esistente')
            return redirect(url_for('create_user'))
        
        # Crea nuovo utente
        user = User(
            username=username,
            email=email,
            is_admin=is_admin
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'Utente {username} creato con successo')
        return redirect(url_for('admin_panel'))
    
    return render_template('register.html')

@app.route('/admin/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('Non puoi eliminare il tuo stesso account')
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f'Utente {user.username} eliminato')
    
    return redirect(url_for('admin_panel'))

# Funzioni di utilità
def check_anomalies(user_id, sensor_type, window_size=10, threshold_multiplier=2):
    """Controlla anomalie usando media mobile"""
    recent_data = SensorData.query.filter_by(
        user_id=user_id,
        sensor_type=sensor_type
    ).order_by(SensorData.timestamp.desc()).limit(window_size + 1).all()
    
    if len(recent_data) < window_size:
        return
    
    values = [d.value for d in recent_data if d.value is not None]
    if len(values) < window_size:
        return
    
    # Calcola media mobile
    moving_avg = np.mean(values[1:window_size+1])
    current_value = values[0]
    std_dev = np.std(values[1:window_size+1])
    threshold = moving_avg + (threshold_multiplier * std_dev)
    
    # Rileva anomalia
    if current_value > threshold:
        anomaly = Anomaly(
            user_id=user_id,
            sensor_type=sensor_type,
            value=current_value,
            threshold=threshold,
            moving_avg=moving_avg
        )
        db.session.add(anomaly)
        
        # Qui si potrebbe inviare email/notifica
        send_anomaly_notification(user_id, sensor_type, current_value, threshold)

def send_anomaly_notification(user_id, sensor_type, value, threshold):
    """Invia notifica per anomalia rilevata"""
    user = User.query.get(user_id)
    if user:
        # Implementare invio email qui
        print(f"ANOMALIA RILEVATA per {user.username}: {sensor_type} = {value} (soglia: {threshold})")

# API per statistiche
@app.route('/api/stats/<username>')
@login_required
def get_user_stats(username):
    if not current_user.is_admin and current_user.username != username:
        return jsonify({'error': 'Non autorizzato'}), 403
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': 'Utente non trovato'}), 404
    
    week_ago = datetime.utcnow() - timedelta(days=7)
    stats = {}
    
    for sensor_type in ['acc', 'bvp', 'eda', 'hr', 'ibi', 'temp']:
        data = SensorData.query.filter(
            SensorData.user_id == user.id,
            SensorData.sensor_type == sensor_type,
            SensorData.timestamp > week_ago
        ).all()
        
        values = [d.value for d in data if d.value is not None]
        if values:
            stats[sensor_type] = {
                'mean': float(np.mean(values)),
                'std': float(np.std(values)),
                'min': float(np.min(values)),
                'max': float(np.max(values)),
                'count': len(values),
                'last_update': data[-1].timestamp.isoformat() if data else None
            }
    
    return jsonify(stats)

# Inizializzazione database
@app.before_first_request
def create_tables():
    db.create_all()
    
    # Crea admin di default se non esiste
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@example.com',
            is_admin=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created: username='admin', password='admin123'")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)