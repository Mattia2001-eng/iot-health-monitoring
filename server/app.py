import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# ================== CONFIGURAZIONE ==================
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Database SQLite
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///health_monitoring.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ================== MODELLI DB ==================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sensor_data = db.relationship("SensorData", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class SensorData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    sensor_type = db.Column(db.String(50))
    value = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================== LOGIN ==================
@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            else:
                return redirect(url_for("user_dashboard"))
        else:
            flash("Credenziali non valide", "warning")
            return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ================== DASHBOARD ==================
@app.route("/dashboard")
@login_required
def user_dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    stats_week = calculate_stats(days=7, user=current_user)
    chart_data = prepare_chart_data(user=current_user)
    anomalies = get_recent_anomalies(user=current_user)

    return render_template(
        "user_dashboard.html",
        stats_week=stats_week,
        chart_data=json.dumps(chart_data),
        anomalies=anomalies,
        current_user=current_user
    )


@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("Accesso negato", "danger")
        return redirect(url_for("user_dashboard"))

    stats_week = calculate_stats(days=7)
    chart_data = prepare_chart_data()
    anomalies = get_recent_anomalies()
    users = User.query.all()

    return render_template(
        "admin_dashboard.html",
        stats_week=stats_week,
        chart_data=json.dumps(chart_data),
        anomalies=anomalies,
        users=users,
        current_user=current_user
    )

# ================== CREAZIONE UTENTI ==================
@app.route("/admin/create_user", methods=["GET", "POST"])
@login_required
def create_user():
    if not current_user.is_admin:
        flash("Accesso negato", "danger")
        return redirect(url_for("user_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        is_admin = "is_admin" in request.form

        if not username or not email or not password:
            flash("Tutti i campi sono obbligatori!", "danger")
            return redirect(url_for("create_user"))

        if User.query.filter_by(username=username).first():
            flash(f"Username '{username}' già esistente!", "danger")
            return redirect(url_for("create_user"))

        if User.query.filter_by(email=email).first():
            flash(f"Email '{email}' già registrata!", "danger")
            return redirect(url_for("create_user"))

        try:
            new_user = User(username=username, email=email, is_admin=is_admin)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash(f"Utente '{username}' creato con successo!", "success")
            return redirect(url_for("admin_dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"Errore durante la creazione: {str(e)}", "danger")
            return redirect(url_for("create_user"))

    return render_template("register.html", current_user=current_user)

# ================== API SENSORI ==================
@app.route("/api/data", methods=["POST"])
def receive_data():
    data = request.get_json()
    if not data:
        return {"error": "No data provided"}, 400

    username = data.get("username")
    sensor_type = data.get("sensor_type")
    value = data.get("value")

    if not username or not sensor_type or value is None:
        return {"error": "Invalid data"}, 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return {"error": f"User '{username}' not found"}, 404

    sensor_entry = SensorData(user_id=user.id, sensor_type=sensor_type, value=float(value))
    db.session.add(sensor_entry)
    db.session.commit()

    return {"status": "success"}, 200

# ================== FUNZIONI DI SUPPORTO ==================
def calculate_stats(days=7, user=None):
    stats = {}
    since = datetime.utcnow() - timedelta(days=days)

    if user:
        users = [user]
    else:
        users = User.query.all()

    for u in users:
        stats[u.username] = {}
        sensor_types = db.session.query(SensorData.sensor_type).filter(
            SensorData.user_id == u.id, SensorData.timestamp >= since
        ).distinct()
        for stype_tuple in sensor_types:
            stype = stype_tuple[0]
            values = [d.value for d in SensorData.query.filter_by(user_id=u.id, sensor_type=stype).all()]
            if values:
                stats[u.username][stype] = {
                    "mean": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values)
                }
    return stats


def prepare_chart_data(user=None):
    chart_data = {}
    if user:
        users = [user]
    else:
        users = User.query.all()

    for u in users:
        chart_data[u.username] = {}
        sensor_types = db.session.query(SensorData.sensor_type).filter_by(user_id=u.id).distinct()
        for stype_tuple in sensor_types:
            stype = stype_tuple[0]
            entries = SensorData.query.filter_by(user_id=u.id, sensor_type=stype).order_by(SensorData.timestamp).all()
            chart_data[u.username][stype] = {
                "timestamps": [e.timestamp.strftime("%H:%M:%S") for e in entries],
                "values": [e.value for e in entries]
            }
    return chart_data


def get_recent_anomalies(limit=10, user=None):
    if user:
        anomalies = SensorData.query.filter(
            SensorData.user_id == user.id,
            SensorData.value > 100
        ).order_by(SensorData.timestamp.desc()).limit(limit).all()
    else:
        anomalies = SensorData.query.filter(
            SensorData.value > 100
        ).order_by(SensorData.timestamp.desc()).limit(limit).all()
    return anomalies

# ================== RUN SERVER ==================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin_user = User(username="admin", email="admin@example.com", is_admin=True)
            admin_user.set_password("admin123")
            db.session.add(admin_user)
            db.session.commit()
            print("✅ Admin creato: username='admin', password='admin123'")

    app.run(host="0.0.0.0", port=5000, debug=True)
