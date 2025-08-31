import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///health_monitoring.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ===== MODELLI DB =====
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

# ===== LOGIN =====
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("admin_dashboard" if user.is_admin else "user_dashboard"))
        flash("Credenziali non valide", "warning")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ===== DASHBOARD =====
@app.route("/dashboard")
@login_required
def user_dashboard():
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))

    chart_data = prepare_chart_data(user=current_user)
    anomalies = get_recent_anomalies(user=current_user)
    return render_template("user_dashboard.html", chart_data=json.dumps(chart_data), anomalies=anomalies, current_user=current_user)

@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash("Accesso negato", "danger")
        return redirect(url_for("user_dashboard"))

    chart_data = prepare_chart_data()
    anomalies = get_recent_anomalies()
    users = User.query.all()
    return render_template("admin_dashboard.html", chart_data=json.dumps(chart_data), anomalies=anomalies, users=users, current_user=current_user)

# ===== CREAZIONE UTENTI =====
@app.route("/admin/create_user", methods=["GET","POST"])
@login_required
def create_user():
    if not current_user.is_admin:
        return redirect(url_for("user_dashboard"))

    if request.method=="POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        is_admin = "is_admin" in request.form
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash("Username o email già esistenti", "danger")
            return redirect(url_for("create_user"))
        new_user = User(username=username,email=email,is_admin=is_admin)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash(f"Utente {username} creato!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("register.html", current_user=current_user)

@app.route("/admin/delete_user/<int:user_id>")
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return redirect(url_for("user_dashboard"))
    user = User.query.get(user_id)
    if user:
        SensorData.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash(f"Utente {user.username} eliminato", "success")
    return redirect(url_for("admin_dashboard"))

# ===== API SENSORI =====
@app.route("/api/data", methods=["POST"])
def receive_data():
    data = request.get_json()
    username = data.get("username")
    sensor_type = data.get("sensor_type")
    value = data.get("value")
    if not username or not sensor_type or value is None:
        return {"error":"Invalid data"},400
    user = User.query.filter_by(username=username).first()
    if not user:
        return {"error":"User not found"},404
    db.session.add(SensorData(user_id=user.id,sensor_type=sensor_type,value=float(value)))
    db.session.commit()
    return {"status":"success"},200

# ===== FUNZIONI DI SUPPORTO =====
def moving_average(values, window_size=5):
    if len(values)<window_size: return [sum(values)/len(values)]*len(values)
    ma=[]
    for i in range(len(values)):
        window=values[max(0,i-window_size+1):i+1]
        ma.append(sum(window)/len(window))
    return ma

def prepare_chart_data(user=None, window_size=5, threshold=100):
    chart_data={}
    users=[user] if user else User.query.all()
    for u in users:
        chart_data[u.username]={}
        sensor_types=db.session.query(SensorData.sensor_type).filter_by(user_id=u.id).distinct()
        for stype,_ in sensor_types:
            entries=SensorData.query.filter_by(user_id=u.id,sensor_type=stype).order_by(SensorData.timestamp).all()
            values=[e.value for e in entries]
            timestamps=[e.timestamp.strftime("%H:%M:%S") for e in entries]
            chart_data[u.username][stype]={
                "timestamps":timestamps,
                "values":values,
                "moving_average":moving_average(values,window_size),
                "anomalies":[v if v>threshold else None for v in values]
            }
    return chart_data

def get_recent_anomalies(limit=10, user=None, threshold=100):
    query=SensorData.query
    if user: query=query.filter(SensorData.user_id==user.id)
    anomalies=query.filter(SensorData.value>threshold).order_by(SensorData.timestamp.desc()).limit(limit).all()
    return anomalies

# ===== RUN SERVER =====
if __name__=="__main__":
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            admin_user=User(username="admin",email="admin@example.com",is_admin=True)
            admin_user.set_password("admin123")
            db.session.add(admin_user)
            db.session.commit()
    app.run(host="0.0.0.0", port=5000, debug=True)
