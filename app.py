"""Smart Temperature Monitoring & Alert System — Flask application."""
from datetime import datetime, timedelta, timezone
from functools import wraps
import os
import secrets
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, flash, has_request_context, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config

db = SQLAlchemy()
csrf = CSRFProtect()


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    role = db.relationship("Role")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class StorageLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    facility = db.Column(db.String(120), nullable=False, default="North Wing")
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)


class Sensor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_location.id"), nullable=False)
    is_online = db.Column(db.Boolean, default=True, nullable=False)
    battery_pct = db.Column(db.Integer, default=92, nullable=False)
    last_seen = db.Column(db.DateTime, default=now_utc, nullable=False)
    location = db.relationship("StorageLocation")


class SensorStatusEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey("sensor.id"), nullable=False, index=True)
    is_online = db.Column(db.Boolean, nullable=False)
    occurred_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    actor_label = db.Column(db.String(120), nullable=False, default="Monitoring service")
    sensor = db.relationship("Sensor")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey("storage_location.id"), nullable=False)
    sensor_id = db.Column(db.Integer, db.ForeignKey("sensor.id"), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    location = db.relationship("StorageLocation")
    sensor = db.relationship("Sensor")
    batches = db.relationship("Batch", back_populates="product", order_by="Batch.id", cascade="all, delete-orphan")
    thresholds = db.relationship("ThresholdVersion", back_populates="product", order_by="ThresholdVersion.version.desc()")

    @property
    def batch_number(self):
        return self.batches[0].batch_number if self.batches else "Unassigned"

    @property
    def current_threshold(self):
        return self.thresholds[0] if self.thresholds else None


class Batch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    batch_number = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    product = db.relationship("Product", back_populates="batches")


class ThresholdVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    minimum_c = db.Column(db.Float, nullable=False)
    maximum_c = db.Column(db.Float, nullable=False)
    label = db.Column(db.String(160), nullable=False, default="Demonstration threshold — verify locally")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    product = db.relationship("Product", back_populates="thresholds")
    __table_args__ = (db.UniqueConstraint("product_id", "version", name="uq_product_threshold_version"),)


class TemperatureReading(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey("sensor.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    threshold_version_id = db.Column(db.Integer, db.ForeignKey("threshold_version.id"), nullable=False)
    temperature_c = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    simulated = db.Column(db.Boolean, default=True, nullable=False)
    sensor = db.relationship("Sensor")
    product = db.relationship("Product")
    threshold = db.relationship("ThresholdVersion")


class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_code = db.Column(db.String(32), unique=True, nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False, index=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey("sensor.id"), nullable=False)
    threshold_version_id = db.Column(db.Integer, db.ForeignKey("threshold_version.id"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    current_excursion_started_at = db.Column(db.DateTime, nullable=True)
    recovered_at = db.Column(db.DateTime, nullable=True)
    accumulated_seconds = db.Column(db.Integer, nullable=False, default=0)
    max_temperature_c = db.Column(db.Float, nullable=False)
    min_temperature_c = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="warning")
    status = db.Column(db.String(20), nullable=False, default="open")
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    escalated_at = db.Column(db.DateTime, nullable=True)
    assessed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assessed_at = db.Column(db.DateTime, nullable=True)
    assessment = db.Column(db.Text, nullable=True)
    product = db.relationship("Product")
    sensor = db.relationship("Sensor")
    threshold = db.relationship("ThresholdVersion")
    acknowledged_user = db.relationship("User", foreign_keys=[acknowledged_by])
    assessed_user = db.relationship("User", foreign_keys=[assessed_by])

    @property
    def duration_seconds(self):
        current = max(0, int((now_utc() - self.current_excursion_started_at).total_seconds())) if self.current_excursion_started_at else 0
        return self.accumulated_seconds + current


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), nullable=True, index=True)
    sensor_id = db.Column(db.Integer, db.ForeignKey("sensor.id"), nullable=True)
    alert_type = db.Column(db.String(40), nullable=False)
    severity = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    incident = db.relationship("Incident")
    sensor = db.relationship("Sensor")


class IncidentEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_label = db.Column(db.String(120), nullable=False, default="System")
    occurred_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)


class ReviewNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey("incident.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=now_utc, nullable=False)
    user = db.relationship("User")


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    actor_label = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    entity_type = db.Column(db.String(60), nullable=False)
    entity_id = db.Column(db.String(60), nullable=True)
    details = db.Column(db.Text, nullable=True)
    occurred_at = db.Column(db.DateTime, default=now_utc, nullable=False, index=True)


def audit(action, entity_type, entity_id=None, details=""):
    user = current_user()
    db.session.add(AuditLog(user_id=user.id if user else None,
                            actor_label=user.name if user else "System",
                            action=action, entity_type=entity_type,
                            entity_id=str(entity_id) if entity_id is not None else None,
                            details=details))


def current_user():
    if not has_request_context():
        return None
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify(error="Sign in required"), 401
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user or user.role.name not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="You do not have permission for this action"), 403
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def event(incident, event_type, description, actor=None):
    actor = actor or current_user()
    db.session.add(IncidentEvent(incident_id=incident.id, event_type=event_type,
        description=description, actor_id=actor.id if actor else None,
        actor_label=actor.name if actor else "Monitoring service"))


def create_alert(alert_type, severity, message, incident=None, sensor=None):
    db.session.add(Alert(incident_id=incident.id if incident else None,
        sensor_id=sensor.id if sensor else None, alert_type=alert_type,
        severity=severity, message=message))
    if incident:
        event(incident, "alert_generated", f"{severity.title()} alert generated for authorized healthcare staff.")
        event(incident, "alert_delivered", "In-app notification saved to the staff alert center.")


def run_escalations():
    """Apply the configured escalation window to unacknowledged incidents."""
    threshold_minutes = current_app_config().get("ESCALATION_MINUTES", 5)
    cutoff = now_utc() - timedelta(minutes=threshold_minutes)
    pending = Incident.query.filter(Incident.status != "reviewed", Incident.acknowledged_at.is_(None),
                                    Incident.escalated_at.is_(None), Incident.started_at <= cutoff).all()
    for incident in pending:
        incident.escalated_at = now_utc()
        incident.severity = "critical"
        event(incident, "incident_escalated", f"Automatically escalated after {threshold_minutes} minutes without acknowledgement.", actor=None)
        create_alert("unacknowledged_escalation", "critical", f"{incident.incident_code} was automatically escalated after {threshold_minutes} minutes.", incident)
        audit("incident_auto_escalated", "incident", incident.id, f"No acknowledgement within {threshold_minutes} minutes")


def get_products_for_sensor(sensor):
    return Product.query.filter_by(sensor_id=sensor.id, active=True).order_by(Product.id).first()


def process_reading(sensor, temperature, simulated=True):
    """Persist a reading and update an auditable incident state machine."""
    product = get_products_for_sensor(sensor)
    if not product or not product.current_threshold:
        raise ValueError("This sensor is not assigned to an active product with thresholds")
    threshold = product.current_threshold
    at = now_utc()
    reading = TemperatureReading(sensor_id=sensor.id, product_id=product.id,
        threshold_version_id=threshold.id, temperature_c=temperature,
        recorded_at=at, simulated=simulated)
    db.session.add(reading)
    sensor.last_seen = at
    sensor.is_online = True
    active = Incident.query.filter_by(sensor_id=sensor.id).filter(Incident.status != "reviewed").order_by(Incident.id.desc()).first()
    outside = temperature < threshold.minimum_c or temperature > threshold.maximum_c
    if outside:
        delta = max(threshold.minimum_c - temperature, temperature - threshold.maximum_c, 0)
        severity = "critical" if delta >= 2.0 else "warning"
        if not active:
            active = Incident(incident_code=f"INC-{at:%y%m%d}-{secrets.token_hex(3).upper()}",
                product_id=product.id, sensor_id=sensor.id, threshold_version_id=threshold.id,
                started_at=at, current_excursion_started_at=at,
                max_temperature_c=temperature, min_temperature_c=temperature,
                severity=severity, status="open")
            db.session.add(active)
            db.session.flush()
            direction = "high" if temperature > threshold.maximum_c else "low"
            event(active, "excursion_detected", f"{direction.title()} temperature excursion detected at {temperature:.1f} °C. Thresholds in force: {threshold.minimum_c:g} to {threshold.maximum_c:g} °C.", actor=None)
            create_alert(f"{direction}_temperature", severity,
                f"{product.name}: {temperature:.1f} °C is outside its demo range.", active, sensor)
        else:
            if active.current_excursion_started_at is None:
                active.current_excursion_started_at = at
                active.recovered_at = None
                active.status = "open"
                event(active, "excursion_reoccurred", f"Temperature moved out of range again at {temperature:.1f} °C.", actor=None)
                create_alert("repeated_excursion", severity, f"Repeated excursion: {product.name} at {temperature:.1f} °C.", active, sensor)
            active.max_temperature_c = max(active.max_temperature_c, temperature)
            active.min_temperature_c = min(active.min_temperature_c, temperature)
            if severity == "critical" and active.severity != "critical":
                active.severity = "critical"
                event(active, "severity_updated", "Incident severity raised to critical based on the excursion magnitude.", actor=None)
                create_alert("critical_excursion", "critical", f"Critical excursion for {product.name}.", active, sensor)
        mins = max(0, int((at - active.current_excursion_started_at).total_seconds() // 60))
        if mins >= current_app_config().get("PROLONGED_MINUTES", 5) and not any(e.event_type == "prolonged_excursion" for e in IncidentEvent.query.filter_by(incident_id=active.id).all()):
            active.severity = "critical"
            event(active, "prolonged_excursion", f"Current excursion has lasted at least {mins} minute(s). Review is required.", actor=None)
            create_alert("prolonged_excursion", "critical", f"Prolonged excursion: {product.name} has been out of range for {mins} minute(s).", active, sensor)
        active.max_temperature_c = max(active.max_temperature_c, temperature)
        active.min_temperature_c = min(active.min_temperature_c, temperature)
    elif active and active.current_excursion_started_at:
        active.accumulated_seconds += max(0, int((at - active.current_excursion_started_at).total_seconds()))
        active.current_excursion_started_at = None
        active.recovered_at = at
        active.status = "recovered"
        event(active, "temperature_recovered", f"Temperature returned to range at {temperature:.1f} °C. Incident remains open for human review; no safety determination was made.", actor=None)
        create_alert("temperature_recovered", "info", f"{product.name} returned to its configured range. Human review remains pending.", active, sensor)
    return reading, active


def current_app_config():
    from flask import current_app
    return current_app.config


def seed_demo():
    if Role.query.first():
        return
    roles = {name: Role(name=name) for name in ("Admin", "Healthcare Staff", "Auditor")}
    db.session.add_all(roles.values())
    db.session.flush()
    users = [
        User(name="Maya Chen", email="admin@demo.local", password_hash=generate_password_hash("Admin123!"), role=roles["Admin"]),
        User(name="Jordan Lee", email="staff@demo.local", password_hash=generate_password_hash("Staff123!"), role=roles["Healthcare Staff"]),
        User(name="Avery Morgan", email="auditor@demo.local", password_hash=generate_password_hash("Audit123!"), role=roles["Auditor"]),
    ]
    db.session.add_all(users)
    locations = [StorageLocation(name="Vaccine refrigerator · 01", facility="Main clinic"),
                 StorageLocation(name="Biologics cold room", facility="Research wing"),
                 StorageLocation(name="Pharmacy refrigerator · 02", facility="Main clinic")]
    db.session.add_all(locations)
    db.session.flush()
    sensors = [Sensor(sensor_code="SNS-0421", location=locations[0], battery_pct=94),
               Sensor(sensor_code="SNS-0422", location=locations[1], battery_pct=81),
               Sensor(sensor_code="SNS-0423", location=locations[2], battery_pct=68)]
    db.session.add_all(sensors)
    db.session.flush()
    db.session.add_all([SensorStatusEvent(sensor=s, is_online=True, occurred_at=now_utc() - timedelta(days=30), actor_label="Demo seed") for s in sensors])
    products = [
        Product(product_code="VAC-MRNA-01", name="mRNA vaccine · demo batch", category="Vaccine", location=locations[0], sensor=sensors[0]),
        Product(product_code="BIO-INS-12", name="Insulin · demo batch", category="Biologic", location=locations[1], sensor=sensors[1]),
        Product(product_code="VAC-FLU-06", name="Influenza vaccine · demo batch", category="Vaccine", location=locations[2], sensor=sensors[2]),
    ]
    db.session.add_all(products)
    db.session.flush()
    db.session.add_all([Batch(product=product, batch_number=batch_number) for product, batch_number in zip(products, ["B-2408-17", "IN-2409-04", "FL-2410-22"])])
    bounds = [(2, 8), (2, 8), (2, 8)]
    for product, (low, high) in zip(products, bounds):
        threshold = ThresholdVersion(product=product, version=1, minimum_c=low, maximum_c=high,
             label="DEMO VALUE — confirm product-specific storage requirements", created_by=users[0].id)
        db.session.add(threshold)
    db.session.flush()
    for sensor, product in zip(sensors, products):
        threshold = product.current_threshold
        db.session.add(TemperatureReading(sensor=sensor, product=product, threshold=threshold,
            temperature_c=5.1 + sensor.id * 0.45, recorded_at=now_utc() - timedelta(minutes=3), simulated=True))
        db.session.add(TemperatureReading(sensor=sensor, product=product, threshold=threshold,
            temperature_c=4.8 + sensor.id * 0.5, recorded_at=now_utc() - timedelta(minutes=1), simulated=True))
    demo_start = now_utc() - timedelta(minutes=3)
    demo_incident = Incident(incident_code="INC-DEMO-001", product=products[0], sensor=sensors[0],
        threshold=products[0].current_threshold, started_at=demo_start,
        current_excursion_started_at=None, recovered_at=now_utc() - timedelta(minutes=1),
        accumulated_seconds=88, max_temperature_c=9.2, min_temperature_c=5.0,
        severity="warning", status="recovered")
    db.session.add(demo_incident)
    db.session.flush()
    db.session.add_all([
        IncidentEvent(incident_id=demo_incident.id, event_type="excursion_detected",
            description="High temperature excursion detected at 9.2 °C. Demo threshold in force: 2 to 8 °C.",
            actor_label="Monitoring service", occurred_at=demo_start),
        IncidentEvent(incident_id=demo_incident.id, event_type="alert_generated",
            description="Warning alert generated for authorized healthcare staff.", actor_label="Monitoring service", occurred_at=demo_start),
        IncidentEvent(incident_id=demo_incident.id, event_type="alert_delivered",
            description="In-app notification saved to the staff alert center.", actor_label="Monitoring service", occurred_at=demo_start),
        IncidentEvent(incident_id=demo_incident.id, event_type="temperature_recovered",
            description="Temperature returned to range. Incident remains pending human review; no safety determination was made.",
            actor_label="Monitoring service", occurred_at=now_utc() - timedelta(minutes=1)),
    ])
    db.session.add(Alert(incident_id=demo_incident.id, sensor_id=sensors[0].id,
        alert_type="high_temperature", severity="warning",
        message="mRNA vaccine · demo batch: temperature exceeded its configured demo range.", created_at=demo_start))
    audit("demo_seeded", "system", details="Created demonstration users, storage locations, sensors, products and readings.")
    db.session.commit()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    csrf.init_app(app)

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user(), "csrf_token_value": generate_csrf, "now": now_utc}

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("error.html", code=403, message="This account does not have access to that action."), 403

    @app.route("/")
    def index():
        return redirect(url_for("dashboard")) if current_user() else redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user():
            return redirect(url_for("dashboard"))
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = User.query.filter_by(email=email, active=True).first()
            if user and user.check_password(password):
                session.clear()
                session["user_id"] = user.id
                session.permanent = True
                audit("login", "user", user.id, "Successful sign-in")
                db.session.commit()
                target = request.args.get("next", "")
                if not target.startswith("/") or target.startswith("//") or "\\" in target or urlsplit(target).netloc:
                    target = url_for("dashboard")
                return redirect(target)
            flash("Email or password was not recognized.", "error")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        audit("logout", "user", current_user().id, "Signed out")
        db.session.commit()
        session.clear()
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("dashboard.html", active="dashboard")

    @app.route("/monitoring")
    @login_required
    def monitoring():
        return render_template("monitoring.html", active="monitoring")

    @app.route("/simulation")
    @roles_required("Admin", "Healthcare Staff")
    def simulation():
        return render_template("simulation.html", active="simulation")

    @app.route("/products", methods=["GET", "POST"])
    @login_required
    def products_page():
        if request.method == "POST":
            if current_user().role.name != "Admin":
                abort(403)
            try:
                name = request.form.get("name", "").strip()
                code = request.form.get("product_code", "").strip().upper()
                batch = request.form.get("batch_number", "").strip()
                category = request.form.get("category", "").strip()
                lo, hi = float(request.form.get("minimum_c", "")), float(request.form.get("maximum_c", ""))
                location = db.session.get(StorageLocation, int(request.form.get("location_id", "0")))
                sensor = db.session.get(Sensor, int(request.form.get("sensor_id", "0"))) if request.form.get("sensor_id") else None
                if not name or not code or not batch or not category or not location or not math.isfinite(lo) or not math.isfinite(hi) or lo >= hi or (sensor and sensor.location_id != location.id):
                    raise ValueError("Check the required fields, temperature range, and sensor location.")
                if Product.query.filter_by(product_code=code).first():
                    raise ValueError("Product ID must be unique.")
                if Batch.query.filter_by(batch_number=batch).first():
                    raise ValueError("Batch number must be unique in this demonstration workspace.")
                product = Product(name=name, product_code=code, category=category, location=location, sensor=sensor)
                db.session.add(product)
                db.session.flush()
                db.session.add(Batch(product=product, batch_number=batch))
                db.session.add(ThresholdVersion(product=product, version=1, minimum_c=lo, maximum_c=hi,
                    label="Administrator-configured demo value — verify product requirements", created_by=current_user().id))
                audit("product_created", "product", product.id, f"Added {code} with threshold version 1.")
                db.session.commit()
                flash("Product added with a versioned demo threshold.", "success")
            except (ValueError, TypeError) as exc:
                db.session.rollback()
                flash(str(exc) or "Please check the form values.", "error")
            return redirect(url_for("products_page"))
        return render_template("products.html", active="products", products=Product.query.order_by(Product.id).all(),
            locations=StorageLocation.query.order_by(StorageLocation.name).all(), sensors=Sensor.query.order_by(Sensor.sensor_code).all())

    @app.post("/products/<int:product_id>/threshold")
    @roles_required("Admin")
    def update_product_threshold(product_id):
        product = db.session.get(Product, product_id) or abort(404)
        try:
            low = float(request.form.get("minimum_c", ""))
            high = float(request.form.get("maximum_c", ""))
            label = request.form.get("label", "").strip() or "Administrator-configured demo value — verify product requirements"
            if not math.isfinite(low) or not math.isfinite(high) or low >= high or len(label) > 160:
                raise ValueError("Enter a valid range and a label up to 160 characters.")
            next_version = (product.current_threshold.version if product.current_threshold else 0) + 1
            version = ThresholdVersion(product=product, version=next_version, minimum_c=low,
                maximum_c=high, label=label, created_by=current_user().id)
            db.session.add(version)
            audit("threshold_version_created", "product", product.id,
                  f"Threshold version {next_version}: {low:g} to {high:g} °C")
            db.session.commit()
            flash(f"Threshold version {next_version} saved. Existing records keep their prior version.", "success")
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc) or "Please check the threshold values.", "error")
        return redirect(url_for("products_page"))

    @app.route("/sensors", methods=["GET", "POST"])
    @login_required
    def sensors_page():
        if request.method == "POST":
            if current_user().role.name != "Admin":
                abort(403)
            code = request.form.get("sensor_code", "").strip().upper()
            location = db.session.get(StorageLocation, request.form.get("location_id", type=int))
            if not code or not location or Sensor.query.filter_by(sensor_code=code).first():
                flash("Provide a unique sensor ID and a valid location.", "error")
            else:
                sensor = Sensor(sensor_code=code, location=location, battery_pct=100)
                db.session.add(sensor)
                db.session.flush()
                db.session.add(SensorStatusEvent(sensor=sensor, is_online=True, occurred_at=now_utc(),
                    actor_label=current_user().name))
                audit("sensor_registered", "sensor", code, f"Registered at {location.name}")
                db.session.commit()
                flash("Sensor registered.", "success")
            return redirect(url_for("sensors_page"))
        sensor_rows = Sensor.query.order_by(Sensor.id).all()
        latest_readings = {sensor.id: TemperatureReading.query.filter_by(sensor_id=sensor.id).order_by(TemperatureReading.recorded_at.desc()).first() for sensor in sensor_rows}
        return render_template("sensors.html", active="sensors", sensors=sensor_rows, latest_readings=latest_readings, locations=StorageLocation.query.all(), products=Product.query.all())

    @app.route("/locations", methods=["GET", "POST"])
    @login_required
    def add_location():
        if request.method == "POST":
            if current_user().role.name != "Admin":
                abort(403)
            name = request.form.get("name", "").strip()
            facility = request.form.get("facility", "").strip()
            if not name or not facility or len(name) > 120 or len(facility) > 120 or StorageLocation.query.filter_by(name=name).first():
                flash("Enter a unique location name and facility.", "error")
            else:
                location = StorageLocation(name=name, facility=facility)
                db.session.add(location)
                db.session.flush()
                audit("storage_location_created", "storage_location", location.id, f"{name} · {facility}")
                db.session.commit()
                flash("Storage location added.", "success")
            return redirect(url_for("add_location"))
        locations = StorageLocation.query.order_by(StorageLocation.name).all()
        counts = {location.id: {"products": Product.query.filter_by(location_id=location.id, active=True).count(),
                    "sensors": Sensor.query.filter_by(location_id=location.id).count()} for location in locations}
        return render_template("locations.html", active="locations", locations=locations, counts=counts)

    @app.route("/alerts")
    @login_required
    def alerts_page():
        return render_template("alerts.html", active="alerts")

    @app.route("/incidents")
    @login_required
    def incidents_page():
        return render_template("incidents.html", active="incidents")

    @app.route("/incidents/<int:incident_id>")
    @login_required
    def incident_details(incident_id):
        incident = db.session.get(Incident, incident_id) or abort(404)
        events = IncidentEvent.query.filter_by(incident_id=incident.id).order_by(IncidentEvent.occurred_at.asc(), IncidentEvent.id.asc()).all()
        notes = ReviewNote.query.filter_by(incident_id=incident.id).order_by(ReviewNote.created_at.desc()).all()
        return render_template("incident_details.html", active="incidents", incident=incident, events=events, notes=notes)

    @app.route("/reports")
    @login_required
    def reports_page():
        return render_template("reports.html", active="reports")

    @app.route("/team", methods=["GET", "POST"])
    @roles_required("Admin")
    def team_page():
        if request.method == "POST":
            name, email = request.form.get("name", "").strip(), request.form.get("email", "").strip().lower()
            password, role_name = request.form.get("password", ""), request.form.get("role", "")
            role = Role.query.filter_by(name=role_name).first()
            if not name or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 10 or not role or User.query.filter_by(email=email).first():
                flash("Use a unique email, valid role, and password of at least 10 characters.", "error")
            else:
                user = User(name=name, email=email, password_hash=generate_password_hash(password), role=role)
                db.session.add(user)
                db.session.flush()
                audit("user_created", "user", user.id, f"Created account with role {role_name}")
                db.session.commit()
                flash("User account created.", "success")
            return redirect(url_for("team_page"))
        return render_template("team.html", active="team", users=User.query.order_by(User.id).all(), roles=Role.query.all())

    @app.post("/team/<int:user_id>/toggle")
    @roles_required("Admin")
    def toggle_user(user_id):
        user = db.session.get(User, user_id) or abort(404)
        if user.id == current_user().id:
            flash("You cannot deactivate your own account.", "error")
        else:
            user.active = not user.active
            audit("user_activated" if user.active else "user_deactivated", "user", user.id, user.email)
            db.session.commit()
            flash("User status updated.", "success")
        return redirect(url_for("team_page"))

    @app.get("/api/dashboard")
    @login_required
    def api_dashboard():
        if current_user().role.name != "Auditor":
            run_escalations()
            db.session.commit()
        products = Product.query.filter_by(active=True).all()
        sensors = Sensor.query.all()
        incidents = Incident.query.filter(Incident.status != "reviewed").all()
        alerts = Alert.query.order_by(Alert.created_at.desc()).limit(8).all()
        readings = TemperatureReading.query.order_by(TemperatureReading.recorded_at.desc()).limit(48).all()
        timeline_events = IncidentEvent.query.order_by(IncidentEvent.occurred_at.desc(), IncidentEvent.id.desc()).limit(6).all()
        latest_by_sensor = {}
        for r in readings:
            latest_by_sensor.setdefault(r.sensor_id, r)
        return jsonify(summary={"products": len(products), "active_sensors": sum(s.is_online for s in sensors),
            "locations_normal": len({p.location_id for p in products if p.sensor_id in latest_by_sensor and
                p.current_threshold.minimum_c <= latest_by_sensor[p.sensor_id].temperature_c <= p.current_threshold.maximum_c}),
            "warning_alerts": Alert.query.filter_by(severity="warning", acknowledged_at=None).count(),
            "critical_excursions": Incident.query.filter(Incident.status != "reviewed", Incident.severity == "critical").count(),
            "pending_reviews": Incident.query.filter(Incident.status != "reviewed").count()},
            products=[product_json(p, latest_by_sensor.get(p.sensor_id)) for p in products],
            alerts=[alert_json(a) for a in alerts],
            timeline=[{"event_type": e.event_type, "description": e.description,
                "actor": e.actor_label, "at": e.occurred_at.isoformat() + "Z",
                "incident_code": db.session.get(Incident, e.incident_id).incident_code if db.session.get(Incident, e.incident_id) else "",
                "url": url_for("incident_details", incident_id=e.incident_id)} for e in timeline_events],
            readings=[{"at": r.recorded_at.isoformat() + "Z", "temperature": r.temperature_c, "sensor": r.sensor.sensor_code} for r in sorted(readings, key=lambda x: x.recorded_at)])

    @app.get("/api/sensors")
    @login_required
    def api_sensors():
        return jsonify(sensors=[sensor_json(s) for s in Sensor.query.order_by(Sensor.id).all()])

    @app.get("/api/readings")
    @login_required
    def api_readings():
        q = TemperatureReading.query
        sensor_id = request.args.get("sensor_id", type=int)
        if sensor_id:
            q = q.filter_by(sensor_id=sensor_id)
        since = request.args.get("since") or request.args.get("from")
        if since:
            try:
                q = q.filter(TemperatureReading.recorded_at >= datetime.fromisoformat(since.replace("Z", "+00:00")).replace(tzinfo=None))
            except ValueError:
                return jsonify(error="Invalid date filter"), 400
        if request.args.get("to"):
            try:
                end = datetime.fromisoformat(request.args["to"]) + timedelta(days=1)
                q = q.filter(TemperatureReading.recorded_at < end)
            except ValueError:
                return jsonify(error="Invalid date filter"), 400
        rows = q.order_by(TemperatureReading.recorded_at.desc()).limit(250).all()
        return jsonify(readings=[{"at": r.recorded_at.isoformat() + "Z", "temperature": r.temperature_c,
            "sensor_id": r.sensor_id, "product": r.product.name, "simulated": r.simulated} for r in reversed(rows)])

    @app.post("/api/readings")
    @roles_required("Admin", "Healthcare Staff")
    def api_ingest_reading():
        data = request.get_json(silent=True) or {}
        try:
            sensor = db.session.get(Sensor, int(data.get("sensor_id", 0)))
            temperature = float(data.get("temperature_c"))
            if not sensor or not math.isfinite(temperature) or not -80 <= temperature <= 100:
                raise ValueError("Choose a sensor and enter a plausible temperature.")
            if not sensor.is_online:
                return jsonify(error="Sensor is offline. Reconnect it before sending readings."), 409
            reading, incident = process_reading(sensor, temperature, simulated=bool(data.get("simulated", True)))
            audit("temperature_reading_recorded", "reading", reading.id,
                  f"{sensor.sensor_code}: {temperature:.2f} C; simulated={reading.simulated}")
            db.session.commit()
            return jsonify(reading={"id": reading.id, "temperature_c": reading.temperature_c, "recorded_at": reading.recorded_at.isoformat() + "Z"},
                incident={"id": incident.id, "code": incident.incident_code, "severity": incident.severity, "status": incident.status} if incident else None), 201
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            return jsonify(error=str(exc) or "Invalid reading"), 400

    @app.post("/api/sensors/<int:sensor_id>/connection")
    @roles_required("Admin", "Healthcare Staff")
    def api_sensor_connection(sensor_id):
        sensor = db.session.get(Sensor, sensor_id) or abort(404)
        data = request.get_json(silent=True) or {}
        online = bool(data.get("online"))
        if online == sensor.is_online:
            return jsonify(sensor=sensor_json(sensor))
        sensor.is_online = online
        sensor.last_seen = now_utc()
        db.session.add(SensorStatusEvent(sensor=sensor, is_online=online, occurred_at=sensor.last_seen,
                                         actor_label=current_user().name))
        status = "reconnected" if online else "disconnected"
        create_alert("sensor_" + status, "info" if online else "warning",
            f"Sensor {sensor.sensor_code} {status}.", sensor=sensor)
        audit("sensor_" + status, "sensor", sensor.id, sensor.sensor_code)
        db.session.commit()
        return jsonify(sensor=sensor_json(sensor))

    @app.get("/api/alerts")
    @login_required
    def api_alerts():
        if current_user().role.name != "Auditor":
            run_escalations()
            db.session.commit()
        q = Alert.query.order_by(Alert.created_at.desc())
        if request.args.get("unread") == "1":
            q = q.filter(Alert.acknowledged_at.is_(None))
        return jsonify(alerts=[alert_json(a) for a in q.limit(100).all()])

    @app.post("/api/alerts/<int:alert_id>/acknowledge")
    @roles_required("Admin", "Healthcare Staff")
    def api_ack_alert(alert_id):
        alert = db.session.get(Alert, alert_id) or abort(404)
        if not alert.acknowledged_at:
            alert.acknowledged_by = current_user().id
            alert.acknowledged_at = now_utc()
            if alert.incident and not alert.incident.acknowledged_at:
                alert.incident.acknowledged_by = current_user().id
                alert.incident.acknowledged_at = alert.acknowledged_at
                event(alert.incident, "alert_acknowledged", f"Alert acknowledged by {current_user().name}.")
            audit("alert_acknowledged", "alert", alert.id, alert.message)
            db.session.commit()
        return jsonify(alert=alert_json(alert))

    @app.post("/api/incidents/<int:incident_id>/notes")
    @roles_required("Admin", "Healthcare Staff")
    def api_incident_note(incident_id):
        incident = db.session.get(Incident, incident_id) or abort(404)
        note = (request.get_json(silent=True) or {}).get("note", "").strip()
        if not note or len(note) > 4000:
            return jsonify(error="Add a note up to 4,000 characters."), 400
        record = ReviewNote(incident_id=incident.id, user_id=current_user().id, note=note)
        db.session.add(record)
        event(incident, "investigation_note", "Investigation note added.")
        audit("incident_note_added", "incident", incident.id, note[:250])
        db.session.commit()
        return jsonify(note={"id": record.id, "author": current_user().name,
            "created_at": record.created_at.isoformat() + "Z", "note": record.note}), 201

    @app.post("/api/incidents/<int:incident_id>/acknowledge")
    @roles_required("Admin", "Healthcare Staff")
    def api_ack_incident(incident_id):
        incident = db.session.get(Incident, incident_id) or abort(404)
        if not incident.acknowledged_at:
            incident.acknowledged_by = current_user().id
            incident.acknowledged_at = now_utc()
            event(incident, "alert_acknowledged", f"Incident acknowledged by {current_user().name}.")
            for alert in Alert.query.filter_by(incident_id=incident.id, acknowledged_at=None).all():
                alert.acknowledged_by = current_user().id
                alert.acknowledged_at = incident.acknowledged_at
            audit("incident_acknowledged", "incident", incident.id, "Staff acknowledgement")
            db.session.commit()
        return jsonify(incident=incident_json(incident))

    @app.post("/api/incidents/<int:incident_id>/escalate")
    @roles_required("Admin", "Healthcare Staff")
    def api_escalate(incident_id):
        incident = db.session.get(Incident, incident_id) or abort(404)
        if not incident.escalated_at:
            incident.escalated_at = now_utc()
            incident.severity = "critical"
            event(incident, "incident_escalated", f"Incident manually escalated by {current_user().name}.")
            create_alert("incident_escalated", "critical", f"{incident.incident_code} was escalated for review.", incident)
            audit("incident_escalated", "incident", incident.id, "Manual escalation")
            db.session.commit()
        return jsonify(incident=incident_json(incident))

    @app.post("/api/incidents/<int:incident_id>/assessment")
    @roles_required("Admin", "Healthcare Staff")
    def api_assessment(incident_id):
        incident = db.session.get(Incident, incident_id) or abort(404)
        data = request.get_json(silent=True) or {}
        assessment = data.get("assessment", "").strip()
        if len(assessment) < 4 or len(assessment) > 4000:
            return jsonify(error="Enter a reviewer assessment up to 4,000 characters."), 400
        incident.status = "reviewed"
        incident.assessed_by = current_user().id
        incident.assessed_at = now_utc()
        incident.assessment = assessment
        event(incident, "reviewer_assessment", "Reviewer assessment recorded. The assessment is a human decision; the system does not declare product safety.")
        audit("incident_assessed", "incident", incident.id, assessment[:250])
        db.session.commit()
        return jsonify(incident=incident_json(incident))

    @app.get("/api/incidents")
    @login_required
    def api_incidents():
        if current_user().role.name != "Auditor":
            run_escalations()
            db.session.commit()
        q = Incident.query
        if request.args.get("status") == "pending":
            q = q.filter(Incident.status != "reviewed")
        if request.args.get("from"):
            try:
                q = q.filter(Incident.started_at >= datetime.fromisoformat(request.args["from"]))
            except ValueError:
                return jsonify(error="Invalid start date"), 400
        if request.args.get("to"):
            try:
                q = q.filter(Incident.started_at < datetime.fromisoformat(request.args["to"]) + timedelta(days=1))
            except ValueError:
                return jsonify(error="Invalid end date"), 400
        return jsonify(incidents=[incident_json(i) for i in q.order_by(Incident.started_at.desc()).limit(250).all()])

    @app.get("/api/reports.csv")
    @login_required
    def reports_csv():
        from flask import Response
        import csv
        import io
        start, end = request.args.get("from"), request.args.get("to")
        q = TemperatureReading.query
        try:
            if start: q = q.filter(TemperatureReading.recorded_at >= datetime.fromisoformat(start))
            if end: q = q.filter(TemperatureReading.recorded_at < datetime.fromisoformat(end) + timedelta(days=1))
        except ValueError:
            return jsonify(error="Invalid date range"), 400
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["recorded_at_utc", "sensor_id", "product", "batch", "location", "temperature_c", "minimum_c", "maximum_c", "simulated"])
        for r in q.order_by(TemperatureReading.recorded_at.asc()).limit(10000).all():
            writer.writerow([r.recorded_at.isoformat() + "Z", r.sensor.sensor_code, r.product.name,
                r.product.batch_number, r.product.location.name, r.temperature_c,
                r.threshold.minimum_c, r.threshold.maximum_c, r.simulated])
        audit("report_exported", "temperature_readings", details=f"CSV export; from={start or 'all'}; to={end or 'all'}")
        db.session.commit()
        return Response(output.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=temperature-report.csv"})

    @app.get("/api/reports/summary")
    @login_required
    def reports_summary():
        from_text, to_text = request.args.get("from"), request.args.get("to")
        try:
            from_dt = datetime.fromisoformat(from_text) if from_text else now_utc() - timedelta(days=30)
            to_dt = datetime.fromisoformat(to_text) + timedelta(days=1) if to_text else now_utc()
        except ValueError:
            return jsonify(error="Invalid date range"), 400
        if to_dt <= from_dt:
            return jsonify(error="End date must be after start date"), 400
        products = Product.query.all()
        result = []
        for product in products:
            incidents = Incident.query.filter_by(product_id=product.id).filter(
                Incident.started_at >= from_dt, Incident.started_at < to_dt).all()
            uptime_total = Sensor.query.filter_by(id=product.sensor_id).first()
            result.append({"product": product.name, "batch": product.batch_number,
                "location": product.location.name, "incidents": len(incidents),
                "duration_minutes": round(sum(i.duration_seconds for i in incidents) / 60, 1),
                "sensor": uptime_total.sensor_code if uptime_total else "Unassigned",
                "online": uptime_total.is_online if uptime_total else False,
                "ack_minutes": round(sum((i.acknowledged_at - i.started_at).total_seconds() / 60 for i in incidents if i.acknowledged_at) / max(1, sum(1 for i in incidents if i.acknowledged_at)), 1) if any(i.acknowledged_at for i in incidents) else None})
        locations = []
        for location in StorageLocation.query.order_by(StorageLocation.name).all():
            rows = Incident.query.join(Product, Incident.product_id == Product.id).filter(
                Product.location_id == location.id, Incident.started_at >= from_dt,
                Incident.started_at < to_dt).all()
            locations.append({"location": location.name, "facility": location.facility,
                "incidents": len(rows), "duration_minutes": round(sum(i.duration_seconds for i in rows) / 60, 1)})
        period_start, period_end = from_dt, to_dt
        duration = max(1.0, (period_end - period_start).total_seconds())
        weighted = 0.0
        sensor_count = Sensor.query.count()
        for sensor in Sensor.query.all():
            events = SensorStatusEvent.query.filter(SensorStatusEvent.sensor_id == sensor.id,
                SensorStatusEvent.occurred_at <= period_end).order_by(SensorStatusEvent.occurred_at.asc()).all()
            baseline = [e for e in events if e.occurred_at <= period_start]
            online = baseline[-1].is_online if baseline else sensor.is_online
            cursor = period_start
            for status_event in (e for e in events if period_start < e.occurred_at <= period_end):
                if online:
                    weighted += max(0.0, (status_event.occurred_at - cursor).total_seconds())
                online = status_event.is_online
                cursor = status_event.occurred_at
            if online:
                weighted += max(0.0, (period_end - cursor).total_seconds())
        uptime_pct = round(100 * weighted / (duration * max(1, sensor_count)), 1)
        reading_query = TemperatureReading.query
        incident_query = Incident.query
        alert_query = Alert.query
        reading_query = reading_query.filter(TemperatureReading.recorded_at >= from_dt, TemperatureReading.recorded_at < to_dt)
        incident_query = incident_query.filter(Incident.started_at >= from_dt, Incident.started_at < to_dt)
        alert_query = alert_query.filter(Alert.created_at >= from_dt, Alert.created_at < to_dt)
        return jsonify(products=result, locations=locations, incidents=incident_query.count(), alerts=alert_query.count(),
                       readings=reading_query.count(), uptime_pct=uptime_pct)

    @app.get("/api/audit")
    @roles_required("Admin", "Auditor")
    def api_audit():
        rows = AuditLog.query.order_by(AuditLog.occurred_at.desc()).limit(250).all()
        return jsonify(logs=[{"actor": r.actor_label, "action": r.action, "entity": r.entity_type,
            "entity_id": r.entity_id, "details": r.details, "at": r.occurred_at.isoformat() + "Z"} for r in rows])

    @app.get("/api/products")
    @login_required
    def api_products():
        products = Product.query.order_by(Product.id).all()
        latest = {p.sensor_id: TemperatureReading.query.filter_by(sensor_id=p.sensor_id).order_by(TemperatureReading.recorded_at.desc()).first() for p in products if p.sensor_id}
        return jsonify(products=[product_json(p, latest.get(p.sensor_id)) for p in products])

    with app.app_context():
        db.create_all()
        seed_demo()
    return app


def product_json(product, reading=None):
    threshold = product.current_threshold
    return {"id": product.id, "code": product.product_code, "name": product.name,
        "batch": product.batch_number, "category": product.category,
        "location": product.location.name, "facility": product.location.facility,
        "sensor_id": product.sensor_id, "sensor": product.sensor.sensor_code if product.sensor else "Unassigned",
        "online": bool(product.sensor and product.sensor.is_online),
        "temperature_c": reading.temperature_c if reading else None,
        "updated_at": reading.recorded_at.isoformat() + "Z" if reading else None,
        "minimum_c": threshold.minimum_c if threshold else None,
        "maximum_c": threshold.maximum_c if threshold else None,
        "threshold_label": threshold.label if threshold else "No configured range"}


def sensor_json(sensor):
    product = get_products_for_sensor(sensor)
    latest = TemperatureReading.query.filter_by(sensor_id=sensor.id).order_by(TemperatureReading.recorded_at.desc()).first()
    return {"id": sensor.id, "code": sensor.sensor_code, "location": sensor.location.name,
        "facility": sensor.location.facility, "online": sensor.is_online, "battery_pct": sensor.battery_pct,
        "last_seen": sensor.last_seen.isoformat() + "Z" if sensor.last_seen else None,
        "product": product.name if product else "Unassigned",
        "temperature_c": latest.temperature_c if latest else None}


def incident_json(incident):
    return {"id": incident.id, "code": incident.incident_code, "product": incident.product.name,
        "batch": incident.product.batch_number, "location": incident.product.location.name,
        "sensor": incident.sensor.sensor_code, "severity": incident.severity,
        "status": incident.status, "started_at": incident.started_at.isoformat() + "Z",
        "recovered_at": incident.recovered_at.isoformat() + "Z" if incident.recovered_at else None,
        "duration_seconds": incident.duration_seconds,
        "acknowledged_at": incident.acknowledged_at.isoformat() + "Z" if incident.acknowledged_at else None,
        "escalated_at": incident.escalated_at.isoformat() + "Z" if incident.escalated_at else None,
        "minimum_c": incident.threshold.minimum_c, "maximum_c": incident.threshold.maximum_c,
        "max_temperature_c": incident.max_temperature_c, "min_temperature_c": incident.min_temperature_c,
        "url": url_for("incident_details", incident_id=incident.id)}


def alert_json(alert):
    return {"id": alert.id, "incident_id": alert.incident_id,
        "incident_code": alert.incident.incident_code if alert.incident else None,
        "type": alert.alert_type, "severity": alert.severity, "message": alert.message,
        "created_at": alert.created_at.isoformat() + "Z",
        "acknowledged_at": alert.acknowledged_at.isoformat() + "Z" if alert.acknowledged_at else None,
        "sensor": alert.sensor.sensor_code if alert.sensor else None,
        "incident_url": url_for("incident_details", incident_id=alert.incident_id) if alert.incident_id else None}


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1", port=int(os.environ.get("PORT", "5000")))
