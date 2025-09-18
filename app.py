# -*- coding: utf-8 -*-
import os, datetime, random, mimetypes, re, json, secrets
from urllib.parse import quote_plus
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, g, abort, Response, send_file
from flask_sqlalchemy import SQLAlchemy
from passlib.hash import argon2
from werkzeug.utils import secure_filename

from sqlalchemy import inspect  # SQLAlchemy 2.x: инспектор


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
STATIC_FOLDER = os.path.join(BASE_DIR, "static")
DECOY_DOWNLOAD = os.path.join(STATIC_FOLDER, "img", "no-download.svg")
DEFAULT_AVATARS = {
    "student": "/static/img/lion_student.svg",
    "specialist": "/static/img/lion_teacher.svg",
}
ALLOWED_IMG = {"png","jpg","jpeg","gif","webp"}
ALLOWED_VIDEO = {"mp4", "mov", "avi", "mkv", "webm"}

db = SQLAlchemy()


def ensure_schema():
    """Простые миграции для поддержания схемы без Alembic."""

    engine = db.engine
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "user" in existing_tables:
            column_names = {col["name"] for col in inspector.get_columns("user")}
            alters = []
            if "age" not in column_names:
                alters.append('ALTER TABLE "user" ADD COLUMN age INTEGER')
            if "education" not in column_names:
                alters.append('ALTER TABLE "user" ADD COLUMN education VARCHAR(255)')
            if "graduation_year" not in column_names:
                alters.append('ALTER TABLE "user" ADD COLUMN graduation_year VARCHAR(10)')
            if "course_image" not in column_names:
                alters.append('ALTER TABLE "user" ADD COLUMN course_image VARCHAR(255)')
            if "telegram" not in column_names:
                alters.append('ALTER TABLE "user" ADD COLUMN telegram VARCHAR(120)')
            for stmt in alters:
                conn.exec_driver_sql(stmt)

        metadata_tables = db.Model.metadata.tables
        for table_name in ("course_access_request", "notification", "user_device_session"):
            if table_name not in existing_tables and table_name in metadata_tables:
                metadata_tables[table_name].create(conn)
                existing_tables.add(table_name)

RU = {"login_title":"Вход","email":"Email","password":"Пароль","sign_in":"Войти","register":"Зарегистрироваться","feed":"Лента","search":"Поиск","chat":"Чат","notifications":"Уведомления","plan":"Мой план","profile_title":"Профиль","complete_profile":"Заполните профиль","close":"Закрыть","welcome_title":"Добро пожаловать!","tagline":"Найдите своего специалиста!","first_time":"Впервые у нас?","signup":"Зарегистрироваться","submit":"Далее","cancel":"Отмена","name_title":"Расскажите о себе","first_name":"Имя","last_name":"Фамилия","avatar_title":"Аватар","nickname_title":"Придумайте никнейм","suggestions":"Варианты никнейма","university":"ВУЗ"}
EN = {"login_title":"Sign in","email":"Email","password":"Password","sign_in":"Sign in","register":"Register","feed":"Feed","search":"Search","chat":"Chat","notifications":"Notifications","plan":"My plan","profile_title":"Profile","complete_profile":"Complete your profile","close":"Close","welcome_title":"Welcome!","tagline":"Find your specialist!","first_time":"New here?","signup":"Sign up","submit":"Next","cancel":"Cancel","name_title":"Tell us about you","first_name":"First name","last_name":"Last name","avatar_title":"Avatar","nickname_title":"Choose a nickname","suggestions":"Suggestions","university":"University"}
def tr(lang, key): return (RU if lang=="ru" else EN).get(key, key)

# ---------- Глобальные утилиты ----------
def avatar_url(user=None):
    """Единая точка получения URL аватара (глобальная, доступна во всех view)."""
    if not user:
        return DEFAULT_AVATARS["student"]
    if getattr(user, "avatar", None):
        return user.avatar
    return DEFAULT_AVATARS.get(getattr(user, "role", None) or "student", DEFAULT_AVATARS["student"])


def format_price(amount):
    if amount is None:
        return ""
    try:
        value = int(amount)
    except (TypeError, ValueError):
        return str(amount)
    return f"{value:,}".replace(",", " ") + " ₽"


def current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def absolute_upload_path(rel_url):
    if not rel_url:
        return None
    safe = rel_url.lstrip("/")
    return os.path.join(BASE_DIR, safe)


def send_decoy_image(download=False):
    if os.path.exists(DECOY_DOWNLOAD):
        opts = dict(
            mimetype=mimetypes.guess_type(DECOY_DOWNLOAD)[0] or "image/jpeg",
            as_attachment=download,
        )
        if download:
            opts["download_name"] = "access-denied.jpg"
        return send_file(DECOY_DOWNLOAD, **opts)
    abort(404)


def stream_video_file(path, mimetype):
    range_header = request.headers.get("Range", None)
    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        size = os.path.getsize(path)
        if match:
            start = int(match.group(1))
            end = match.group(2)
            end = int(end) if end else size - 1
            end = min(end, size - 1)
            length = end - start + 1
            with open(path, "rb") as fh:
                fh.seek(start)
                data = fh.read(length)
            rv = Response(data, 206, mimetype=mimetype, direct_passthrough=True)
            rv.headers.add("Content-Range", f"bytes {start}-{end}/{size}")
            rv.headers.add("Accept-Ranges", "bytes")
            rv.headers.add("Content-Length", str(length))
            return rv
    rv = send_file(path, mimetype=mimetype, conditional=True)
    rv.headers.add("Accept-Ranges", "bytes")
    return rv

def create_app():
    app = Flask(__name__, instance_relative_config=True, static_folder="static", template_folder="templates")
    app.config.from_mapping(
        SECRET_KEY="dev",
        SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "app.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=UPLOAD_FOLDER,
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=7),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
    )
    app.config.from_pyfile("config.py", silent=True)
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER,"avatars"), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER,"courses"), exist_ok=True)

    db.init_app(app)

    # Глобальные значения в g и контекст в шаблонах
    def _globals():
        g.lang = session.get("lang", "ru")
        g.theme = session.get("theme", "dark")
        g.device_alert = None
        g.active_device_session = None
        g.unread_notifications = 0
        user = current_user()
        if user:
            g.unread_notifications = Notification.query.filter_by(user_id=user.id, is_read=False).count()
            if user.role == "student":
                token = session.get("device_token")
                if token:
                    session_entry = UserDeviceSession.query.filter_by(user_id=user.id, token=token, is_active=True).first()
                    if session_entry:
                        session_entry.last_seen = datetime.datetime.utcnow()
                        g.active_device_session = session_entry
                        if session_entry.pending_alert:
                            alert_payload = parse_payload(session_entry.alert_payload)
                            if not alert_payload.get("ip"):
                                alert_payload["ip"] = session_entry.ip_address
                            if not alert_payload.get("user_agent"):
                                alert_payload["user_agent"] = session_entry.user_agent
                            if not alert_payload.get("attempt_time") and session_entry.alert_created_at:
                                alert_payload["attempt_time"] = session_entry.alert_created_at.isoformat()
                            if alert_payload.get("ip") and not alert_payload.get("map_url"):
                                alert_payload["map_url"] = f"https://yandex.ru/map-widget/v1/?z=5&text={quote_plus(alert_payload['ip'])}"
                            g.device_alert = alert_payload
                    else:
                        session.pop("device_token", None)
    def inject_i18n():
        return dict(
            t=lambda k: tr(g.lang, k),
            lang=g.lang,
            theme=g.theme,
            current_user=current_user,
            avatar_url=avatar_url,  # функцию тоже пробрасываем в шаблоны
            format_price=format_price,
            unread_notifications=g.unread_notifications,
        )
    app.before_request(_globals)
    app.context_processor(inject_i18n)

    with app.app_context():
        db.create_all()
        ensure_schema()

    register_routes(app)
    return app

# ---------- Модели ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    age = db.Column(db.Integer)
    first_name = db.Column(db.String(120))
    last_name = db.Column(db.String(120))
    nickname = db.Column(db.String(120), unique=True)
    avatar = db.Column(db.String(255))
    age = db.Column(db.Integer)
    education = db.Column(db.String(255))
    graduation_year = db.Column(db.String(10))
    course_image = db.Column(db.String(255))
    telegram = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    student = db.relationship("StudentProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    specialist = db.relationship("SpecialistProfile", backref="user", uselist=False, cascade="all, delete-orphan")
    posts = db.relationship("Post", backref="user", lazy=True, cascade="all, delete-orphan")
    courses = db.relationship("Course", backref="owner", cascade="all, delete-orphan", order_by="Course.created_at")
    notifications = db.relationship("Notification", backref="user", cascade="all, delete-orphan")
    purchase_requests = db.relationship(
        "CourseAccessRequest",
        foreign_keys="CourseAccessRequest.student_id",
        backref="student",
        cascade="all, delete-orphan",
    )
    device_sessions = db.relationship("UserDeviceSession", backref="user", cascade="all, delete-orphan")

class StudentProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    looking_for = db.Column(db.Text)

class SpecialistProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    education_degree = db.Column(db.String(120))
    workplace = db.Column(db.String(255))
    keywords = db.Column(db.Text)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255))
    summary = db.Column(db.Text)
    image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class ConversationMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("conversation.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255))
    topic = db.Column(db.String(255))
    description = db.Column(db.Text)
    cover_image = db.Column(db.String(255))
    preview_clip = db.Column(db.String(255))
    price = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    videos = db.relationship("CourseVideo", backref="course", cascade="all, delete-orphan", order_by="CourseVideo.order_index")
    access_requests = db.relationship("CourseAccessRequest", backref="course", cascade="all, delete-orphan")


class CourseVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    title = db.Column(db.String(255))
    file_path = db.Column(db.String(255), nullable=False)
    quality_label = db.Column(db.String(50))
    order_index = db.Column(db.Integer, default=0)


class CourseAccessRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("course_id", "student_id", name="uq_course_student"),)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255))
    message = db.Column(db.Text)
    category = db.Column(db.String(50), default="general")
    payload = db.Column(db.Text)
    related_request_id = db.Column(db.Integer, db.ForeignKey("course_access_request.id"))
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    request = db.relationship("CourseAccessRequest", backref="notifications", foreign_keys=[related_request_id])


class UserDeviceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    user_agent = db.Column(db.String(255))
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    pending_alert = db.Column(db.Boolean, default=False)
    alert_payload = db.Column(db.Text)
    alert_created_at = db.Column(db.DateTime)

# ---------- Хелперы ----------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def w(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_screen"))
        return f(*args, **kwargs)
    return w


def create_notification(user_id, title, message, category="general", payload=None, related_request=None):
    if payload is not None and not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False)
    notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        category=category,
        payload=payload,
        related_request_id=getattr(related_request, "id", related_request),
    )
    db.session.add(notif)
    return notif


def parse_payload(text):
    if not text:
        return {}
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return {}

def ensure_bots():
    if User.query.filter_by(email="alice@bots.dev").first(): return
    bots = [
        ("alice@bots.dev","specialist","Alice","Johnson","alice-tutor",DEFAULT_AVATARS["specialist"],"математика, ЕГЭ","Магистр","МГУ",
         [("Линал: с чего начать","Сводка тем.","")]),
        ("bob@bots.dev","specialist","Bob","Lee","bob-coder",DEFAULT_AVATARS["specialist"],"python, алгоритмы","Магистр","ИТМО",
         [("Python: 3 практики","Заметки для старта.","")]),
    ]
    for email, role, fn, ln, nick, avatar, kw, deg, work, posts in bots:
        u = User(email=email, role=role, password_hash=argon2.hash("Passw0rd!"), first_name=fn, last_name=ln, nickname=nick, avatar=avatar)
        if role == "specialist":
            u.specialist = SpecialistProfile(education_degree=deg, workplace=work, keywords=kw)
        db.session.add(u); db.session.commit()
        for title, summary, img in posts:
            db.session.add(Post(user_id=u.id, title=title, summary=summary, image=img))
        db.session.commit()

def translit(s):
    table = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'h','ц':'c','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
    return ''.join(table.get(ch, ch) for ch in (s or '').lower())

# ---------- Роуты ----------
def register_routes(app):
    @app.route("/set-theme/<theme>")
    def set_theme(theme):
        session["theme"] = theme if theme in ("light","dark") else "light"
        return ("",204)

    @app.route("/logout")
    def logout():
        user = current_user()
        token = session.get("device_token")
        session.clear()
        if user and user.role == "student" and token:
            entry = UserDeviceSession.query.filter_by(user_id=user.id, token=token).first()
            if entry:
                db.session.delete(entry)
                db.session.commit()
        return redirect(url_for("login_screen"))

    @app.route("/")
    def login_screen():
        return render_template("login_single.html")

    @app.route("/login", methods=["GET","POST"])
    def login_single():
        if request.method == "POST":
            email = request.form.get("email","").strip().lower()
            password = request.form.get("password","")
            remember = bool(request.form.get("remember"))
            user = User.query.filter_by(email=email).first()
            if not user or not argon2.verify(password, user.password_hash):
                flash("Неверная пара email/пароль.","error")
                return render_template("login_single.html")
            if user.role == "student":
                existing_session = UserDeviceSession.query.filter_by(user_id=user.id, is_active=True).first()
                if existing_session:
                    forwarded = request.headers.get("X-Forwarded-For", "")
                    ip_addr = (forwarded.split(",")[0].strip() if forwarded else None) or (request.remote_addr or "")
                    attempt_payload = {
                        "ip": ip_addr,
                        "user_agent": request.user_agent.string,
                        "device": request.user_agent.platform or request.user_agent.browser or "Неизвестно",
                        "attempt_time": datetime.datetime.utcnow().isoformat(),
                    }
                    if ip_addr:
                        attempt_payload["map_url"] = f"https://yandex.ru/map-widget/v1/?z=5&text={quote_plus(ip_addr)}"
                    existing_session.pending_alert = True
                    existing_session.alert_payload = json.dumps(attempt_payload, ensure_ascii=False)
                    existing_session.alert_created_at = datetime.datetime.utcnow()
                    db.session.commit()
                    flash("Вход доступен только с одного устройства. Мы отправили уведомление на активный сеанс.", "error")
                    return render_template("login_single.html")
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            if user.role == "student":
                token = secrets.token_hex(16)
                session["device_token"] = token
                forwarded = request.headers.get("X-Forwarded-For", "")
                ip_addr = (forwarded.split(",")[0].strip() if forwarded else None) or (request.remote_addr or "")
                entry = UserDeviceSession(
                    user_id=user.id,
                    token=token,
                    user_agent=request.user_agent.string,
                    ip_address=ip_addr,
                    created_at=datetime.datetime.utcnow(),
                    last_seen=datetime.datetime.utcnow(),
                    is_active=True,
                )
                db.session.add(entry)
            if remember: app.permanent_session_lifetime = datetime.timedelta(days=int(app.config.get("REMEMBER_DAYS",30)))
            else: app.permanent_session_lifetime = datetime.timedelta(days=int(app.config.get("SESSION_DAYS",7)))
            if user.role == "student":
                db.session.commit()
            return redirect(url_for("profile"))
        return render_template("login_single.html")

    @app.route("/register")
    def register():
        return render_template("register_choose.html")

    @app.route("/register/<role>", methods=["GET","POST"])
    def register_role(role):
        role = role.lower()
        if role not in ("student","specialist"): return redirect(url_for("register"))
        if request.args.get("reset"):
            session.pop("pending_user", None)
        pending = session.get("pending_user")
        if request.method == "POST":
            stage = request.form.get("stage")
            if stage == "verify":
                code = (request.form.get("code") or "").strip()
                if not pending or pending.get("role") != role:
                    flash("Сессия подтверждения истекла.","error")
                    return redirect(url_for("register_role", role=role))
                if code != pending.get("code"):
                    flash("Неверный код подтверждения.","error")
                    return render_template("register_verify.html", role=role, email=pending.get("email"))
                if User.query.filter_by(email=pending.get("email")).first():
                    flash("Почта уже зарегистрирована. Войдите.","error")
                    session.pop("pending_user", None)
                    return redirect(url_for("login_single"))
                u = User(email=pending["email"], role=role, password_hash=argon2.hash(pending["password"]))
                if role=="student":
                    u.student = StudentProfile()
                else:
                    u.specialist = SpecialistProfile()
                db.session.add(u); db.session.commit()
                session.clear(); session["user_id"]=u.id; session.permanent=True
                flash("Регистрация подтверждена.","ok")
                return redirect(url_for("profile", tab="about"))
            email = request.form.get("email","").strip().lower()
            password = request.form.get("password","")
            confirm = request.form.get("confirm","")
            if password != confirm:
                flash("Пароли не совпадают.","error"); return render_template("register_role.html", role=role)
            if not email or not password:
                flash("Укажите почту и пароль.","error"); return render_template("register_role.html", role=role)
            if User.query.filter_by(email=email).first():
                flash("Почта уже зарегистрирована. Войдите.", "error"); return redirect(url_for("login_single"))
            code = f"{random.randint(100000, 999999)}"
            session["pending_user"] = {"email": email, "password": password, "role": role, "code": code}
            print(f"[TriLink] Verification code for {email}: {code}")
            flash("Код подтверждения отправлен. Проверьте консоль приложения.", "ok")
            return render_template("register_verify.html", role=role, email=email)
        if pending and pending.get("role") == role:
            return render_template("register_verify.html", role=role, email=pending.get("email"))
        return render_template("register_role.html", role=role)

    @app.route("/onboarding/name", methods=["GET","POST"])
    @login_required
    def onb_name():
        u = current_user()
        if request.method=="POST":
            u.first_name = request.form.get("first_name","").strip()
            u.last_name = request.form.get("last_name","").strip()
            if u.role=="student":
                uni = request.form.get("university","").strip()
                if not u.student:
                    u.student = StudentProfile(looking_for=uni)
                else:
                    u.student.looking_for = uni
            db.session.commit()
            if "cancel" in request.form: return redirect(url_for("profile"))
            return redirect(url_for("onb_avatar"))
        return render_template("onb_name.html")

    @app.route("/onboarding/avatar", methods=["GET","POST"])
    @login_required
    def onb_avatar():
        u = current_user()
        if request.method=="POST":
            file = request.files.get("avatar")
            if file and file.filename:
                ext = file.filename.rsplit(".",1)[-1].lower()
                if ext in ALLOWED_IMG:
                    path = os.path.join(UPLOAD_FOLDER,"avatars", secure_filename(f"user{u.id}_avatar.{ext}"))
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    file.save(path); u.avatar = "/uploads/avatars/" + os.path.basename(path); db.session.commit()
            if "cancel" in request.form: return redirect(url_for("profile"))
            return redirect(url_for("onb_nick"))
        # здесь нужно строковое значение URL для предпросмотра
        return render_template("onb_avatar.html", avatar_url=avatar_url(u))

    @app.route("/onboarding/nickname", methods=["GET","POST"])
    @login_required
    def onb_nick():
        u = current_user()
        base_first = translit(u.first_name or "user")
        base_last = translit(u.last_name or "new")
        suggestions = [f"{base_first}-{base_last}", f"{base_first}.{base_last}1", f"{base_last}{base_first}"]
        if request.method=="POST":
            if "cancel" in request.form: return redirect(url_for("profile"))
            nick = request.form.get("nickname","").strip()
            deny = set(["admin","support","moderator","romie","trilink","superuser","help","owner"])
            if not nick or nick.lower() in deny or User.query.filter(User.nickname==nick, User.id!=u.id).first():
                flash("Введите уникальный ник.","error"); return render_template("onb_nick.html", suggestions=suggestions)
            u.nickname = nick; db.session.commit()
            return redirect(url_for("welcome"))
        return render_template("onb_nick.html", suggestions=suggestions)

    @app.route("/welcome")
    @login_required
    def welcome():
        u = current_user()
        return render_template("welcome.html", nickname=u.nickname or u.email.split("@")[0])

    @app.route("/feed")
    @login_required
    def feed():
        message = "Совсем скоро будет доступно!"
        posts = []
        # ensure_bots()  # оставлено закомментированным до включения ленты
        return render_template("feed.html", posts=posts, disabled_message=message)

    @app.route("/search")
    @login_required
    def search():
        q_raw = (request.args.get("q") or "").strip()
        q_lower = q_raw.lower()
        q_clean = q_lower.lstrip("@")
        explicit_nick = q_raw.startswith("@")
        ensure_bots()
        all_people = User.query.order_by(User.created_at.desc()).all()

        specialists_with_courses = []
        others = []
        for person in all_people:
            if person.role == "specialist" and person.courses:
                latest = max(person.courses, key=lambda c: c.created_at or datetime.datetime.min)
                specialists_with_courses.append((person, latest.created_at or datetime.datetime.min))
            else:
                others.append(person)
        specialists_with_courses.sort(key=lambda pair: pair[1], reverse=True)
        others.sort(key=lambda p: p.created_at or datetime.datetime.min, reverse=True)

        suggestion_people = [p for p, _ in specialists_with_courses] + others
        suggestions = []
        for person in suggestion_people:
            latest_course = None
            if person.courses:
                latest_course = max(person.courses, key=lambda c: c.created_at or datetime.datetime.min)
            suggestions.append({
                "id": person.id,
                "name": f"{(person.first_name or '').strip()} {(person.last_name or '').strip()}".strip() or person.email,
                "nickname": person.nickname,
                "role": person.role,
                "has_course": bool(person.courses),
                "course_title": latest_course.title if latest_course else None,
                "avatar": avatar_url(person),
                "url": url_for("public_profile", user_id=person.id, course_id=(latest_course.id if latest_course else None)),
            })

        results = []
        seen = set()

        def add_result(person, course):
            key = (person.id, course.id if course else None)
            if key in seen:
                return
            seen.add(key)
            results.append({"person": person, "course": course})

        def person_matches(person, needle):
            hay = " ".join(filter(None, [
                person.first_name or "",
                person.last_name or "",
                person.nickname or "",
                person.role or "",
                (person.specialist.keywords if person.specialist else ""),
                (person.student.looking_for if person.student else ""),
            ])).lower()
            return needle in hay

        def course_matches(course, needle):
            hay = " ".join(filter(None, [
                course.title or "",
                course.subject or "",
                course.topic or "",
                course.description or "",
            ])).lower()
            return needle in hay

        if q_clean:
            for person, _ in specialists_with_courses:
                matched_courses = [
                    course for course in sorted(person.courses, key=lambda c: c.created_at or datetime.datetime.min, reverse=True)
                    if course_matches(course, q_clean)
                ]
                if matched_courses:
                    for course in matched_courses:
                        add_result(person, course)
                elif person_matches(person, q_clean):
                    add_result(person, None)
        else:
            for person, _ in specialists_with_courses:
                courses_sorted = sorted(person.courses, key=lambda c: c.created_at or datetime.datetime.min, reverse=True)
                for course in courses_sorted:
                    add_result(person, course)

        if q_clean and not results:
            # Fallback: allow partial nickname search even if no other data matched
            for person in suggestion_people:
                nickname = (person.nickname or "").lower()
                if person.courses:
                    if nickname and q_clean in nickname:
                        course = max(person.courses, key=lambda c: c.created_at or datetime.datetime.min)
                        add_result(person, course)
                elif nickname:
                    if explicit_nick and q_clean in nickname:
                        add_result(person, None)
                    elif not explicit_nick and q_clean == nickname:
                        add_result(person, None)

        return render_template("search.html", results=results, q=q_raw, suggestions=suggestions)

    @app.route("/notifications")
    @login_required
    def notifications_center():
        user = current_user()
        items = []
        notifications = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).all()
        dirty = False
        for notif in notifications:
            payload = parse_payload(notif.payload)
            items.append({"notification": notif, "payload": payload})
            if notif.category not in ("purchase_request",) and not notif.is_read:
                notif.is_read = True
                dirty = True
        if dirty:
            db.session.commit()
        return render_template("notifications.html", items=items)

    @app.route("/courses/<int:course_id>/request-access", methods=["POST"])
    @login_required
    def course_request_access(course_id):
        user = current_user()
        course = Course.query.get_or_404(course_id)
        if user.id == course.user_id:
            return {"ok": False, "message": "Это ваш курс."}, 400
        if user.role != "student":
            return {"ok": False, "requires_student": True}, 403
        request_entry = CourseAccessRequest.query.filter_by(course_id=course.id, student_id=user.id).first()
        if request_entry and request_entry.status == "approved":
            return {"ok": True, "state": "approved"}
        if request_entry and request_entry.status == "pending":
            return {"ok": True, "state": "pending"}
        now = datetime.datetime.utcnow()
        if request_entry:
            request_entry.status = "pending"
            request_entry.updated_at = now
        else:
            request_entry = CourseAccessRequest(course_id=course.id, student_id=user.id, status="pending", created_at=now, updated_at=now)
            db.session.add(request_entry)
        payload = {
            "student_id": user.id,
            "student_name": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email,
            "student_nick": user.nickname,
            "course_id": course.id,
            "course_title": course.title,
            "course_url": url_for("public_profile", user_id=course.owner.id, course_id=course.id, _external=False),
            "student_url": url_for("public_profile", user_id=user.id, _external=False),
        }
        create_notification(
            course.user_id,
            "Новая заявка на курс",
            f"{payload['student_name']} хочет приобрести интенсив {course.title}.",
            category="purchase_request",
            payload=payload,
            related_request=request_entry,
        )
        db.session.commit()
        return {"ok": True, "state": "pending"}

    @app.route("/courses/requests/<int:request_id>/<action>", methods=["POST"])
    @login_required
    def handle_course_request(request_id, action):
        user = current_user()
        req = CourseAccessRequest.query.get_or_404(request_id)
        course = req.course
        if course.user_id != user.id:
            abort(403)
        now = datetime.datetime.utcnow()
        if action == "approve":
            req.status = "approved"
            req.updated_at = now
            create_notification(
                req.student_id,
                "Заявка одобрена",
                f"Специалист подтвердил доступ к интенсиву {course.title}.",
                category="purchase_approved",
                payload={
                    "course_url": url_for("public_profile", user_id=course.owner.id, course_id=course.id),
                    "course_title": course.title,
                },
                related_request=req,
            )
        elif action == "decline":
            req.status = "declined"
            req.updated_at = now
            create_notification(
                req.student_id,
                "Заявка отклонена",
                f"Специалист отклонил запрос на интенсив {course.title}.",
                category="purchase_declined",
                payload={
                    "search_url": url_for("search"),
                    "course_title": course.title,
                },
                related_request=req,
            )
        else:
            abort(400)
        for notif in Notification.query.filter_by(related_request_id=req.id, user_id=user.id).all():
            notif.is_read = True
        db.session.commit()
        flash("Решение сохранено.", "ok")
        return redirect(url_for("notifications_center"))

    @app.route("/device-alert/<action>", methods=["POST"])
    @login_required
    def device_alert_action(action):
        user = current_user()
        if user.role != "student":
            abort(403)
        token = session.get("device_token")
        if not token:
            return {"ok": False, "message": "Сеанс не найден."}, 400
        entry = UserDeviceSession.query.filter_by(user_id=user.id, token=token).first()
        if not entry:
            return {"ok": False, "message": "Сеанс не найден."}, 400
        if action == "dismiss":
            entry.pending_alert = False
            entry.alert_payload = None
            entry.alert_created_at = None
            db.session.commit()
            return {"ok": True}
        if action == "terminate":
            db.session.delete(entry)
            db.session.commit()
            session.clear()
            return {"ok": True, "redirect": url_for("login_screen")}
        abort(400)

    @app.route("/support")
    def support_redirect():
        return redirect("https://t.me/ezizkafromag")

    @app.route("/people/<int:user_id>")
    @login_required
    def public_profile(user_id):
        person = User.query.get_or_404(user_id)
        viewer = current_user()
        viewer_requests = {}
        if viewer and viewer.role == "student":
            viewer_requests = {
                req.course_id: req
                for req in CourseAccessRequest.query.filter_by(student_id=viewer.id).all()
            }

        def build_access(course):
            info = {
                "is_owner": viewer.id == course.user_id if viewer else False,
                "has_access": False,
                "pending": False,
                "requires_student_login": False,
                "status": "new",
                "request_id": None,
            }
            if info["is_owner"]:
                info["has_access"] = True
                info["status"] = "owner"
                return info
            if not viewer:
                info["status"] = "anonymous"
                return info
            if viewer.role != "student":
                info["requires_student_login"] = True
                info["status"] = "wrong_role"
                return info
            req = viewer_requests.get(course.id)
            if req:
                info["status"] = req.status
                info["request_id"] = req.id
                if req.status == "approved":
                    info["has_access"] = True
                elif req.status == "pending":
                    info["pending"] = True
            return info

        courses_payload = []
        for course in sorted(person.courses, key=lambda c: c.created_at or datetime.datetime.utcnow(), reverse=True):
            ordered_videos = sorted(course.videos, key=lambda v: (v.order_index or 0, v.id))
            grouped = {}
            for video in ordered_videos:
                base_title = (video.title or "").strip()
                if not base_title:
                    base_title = f"Урок {len(grouped) + 1}"
                if base_title not in grouped:
                    grouped[base_title] = []
                grouped[base_title].append(video)
            lessons = []
            for idx, (title, vids) in enumerate(grouped.items(), start=1):
                sources = []
                for v in vids:
                    sources.append({
                        "quality": v.quality_label or "Оригинал",
                        "src": url_for("course_video_stream", course_id=course.id, video_id=v.id),
                        "download": url_for("course_video_stream", course_id=course.id, video_id=v.id, download=1),
                    })
                lessons.append({
                    "order": idx,
                    "title": title,
                    "sources": sources,
                })
            courses_payload.append({
                "course": course,
                "lessons": lessons,
                "video_total": len(ordered_videos),
                "access": build_access(course),
            })
        selected_id = request.args.get("course_id", type=int)
        selected_course = None
        for payload in courses_payload:
            if selected_id and payload["course"].id == selected_id:
                selected_course = payload
                break
        if not selected_course and courses_payload:
            selected_course = courses_payload[0]
        other_courses = [payload for payload in courses_payload if not selected_course or payload["course"].id != selected_course["course"].id]
        return render_template(
            "user_public.html",
            person=person,
            avatar=avatar_url(person),
            courses=courses_payload,
            selected_course=selected_course,
            other_courses=other_courses,
        )

    @app.route("/courses/new", methods=["GET","POST"])
    @login_required
    def course_create():
        u = current_user()
        if u.role != "specialist":
            flash("Добавлять курсы могут только специалисты.", "error")
            return redirect(url_for("profile", tab="course"))
        form = {
            "title": "",
            "subject": "",
            "topic": "",
            "description": "",
            "price": "",
            "video_meta": [{"title": "", "quality": ""}],
            "is_edit": False,
            "existing_videos": [],
        }
        if request.method == "POST":
            form["title"] = (request.form.get("title") or "").strip()
            form["subject"] = (request.form.get("subject") or "").strip()
            form["topic"] = (request.form.get("topic") or "").strip()
            form["description"] = (request.form.get("description") or "").strip()
            form["price"] = (request.form.get("price") or "").strip()
            video_titles = [t.strip() for t in request.form.getlist("video_title[]")]
            video_qualities = [q.strip() for q in request.form.getlist("video_quality[]")]
            meta = []
            file_count = len(request.files.getlist("video_file[]"))
            max_len = max(len(video_titles), len(video_qualities), file_count, 1)
            for idx in range(max_len):
                title = video_titles[idx] if idx < len(video_titles) else ""
                quality = video_qualities[idx] if idx < len(video_qualities) else ""
                meta.append({"title": title, "quality": quality})
            form["video_meta"] = meta or [{"title": "", "quality": ""}]
            errors = []
            if not form["title"]:
                errors.append("Укажите заголовок курса.")
            price_value = None
            if form["price"]:
                try:
                    price_value = int(round(float(form["price"].replace(",", "."))))
                    if price_value < 0:
                        raise ValueError
                except ValueError:
                    errors.append("Цена должна быть числом.")
            else:
                errors.append("Укажите цену интенсива.")
            cover = request.files.get("cover_image")
            if not cover or not cover.filename:
                errors.append("Загрузите изображение интенсива.")
            video_files = request.files.getlist("video_file[]")
            prepared_videos = []
            for idx, meta_info in enumerate(form["video_meta"]):
                file = video_files[idx] if idx < len(video_files) else None
                if file and file.filename:
                    ext = file.filename.rsplit(".", 1)[-1].lower()
                    if ext not in ALLOWED_VIDEO:
                        errors.append(f"Формат видео {file.filename} не поддерживается.")
                        continue
                    title = meta_info.get("title") or f"Урок {idx+1}"
                    quality = meta_info.get("quality") or "Оригинал"
                    prepared_videos.append({
                        "file": file,
                        "title": title,
                        "quality": quality,
                        "ext": ext,
                    })
            if not prepared_videos:
                errors.append("Добавьте хотя бы одно видео.")
            if cover and cover.filename:
                cover_ext = cover.filename.rsplit(".", 1)[-1].lower()
                if cover_ext not in ALLOWED_IMG:
                    errors.append("Формат изображения не поддерживается.")
            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template("course_form.html", form=form)
            course = Course(
                user_id=u.id,
                title=form["title"],
                subject=form["subject"] or None,
                topic=form["topic"] or None,
                description=form["description"] or None,
                price=price_value,
            )
            db.session.add(course)
            db.session.flush()
            course_dir = os.path.join(UPLOAD_FOLDER, "courses", f"user{u.id}", f"course{course.id}")
            os.makedirs(course_dir, exist_ok=True)
            cover_ext = cover.filename.rsplit(".", 1)[-1].lower()
            cover_filename = secure_filename(f"cover.{cover_ext}")
            cover_path = os.path.join(course_dir, cover_filename)
            cover.save(cover_path)
            course.cover_image = "/".join(["", "uploads", "courses", f"user{u.id}", f"course{course.id}", cover_filename])
            videos_dir = os.path.join(course_dir, "videos")
            os.makedirs(videos_dir, exist_ok=True)
            for order, video in enumerate(prepared_videos):
                filename = secure_filename(f"video{order+1}_{datetime.datetime.utcnow().timestamp():.0f}.{video['ext']}")
                file_path = os.path.join(videos_dir, filename)
                video["file"].save(file_path)
                rel_path = "/".join(["", "uploads", "courses", f"user{u.id}", f"course{course.id}", "videos", filename])
                db.session.add(CourseVideo(
                    course_id=course.id,
                    title=video["title"],
                    file_path=rel_path,
                    quality_label=video["quality"],
                    order_index=order,
                ))
            db.session.commit()
            flash("Курс опубликован!", "ok")
            return redirect(url_for("profile", tab="course"))
        return render_template("course_form.html", form=form)

    @app.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
    @login_required
    def course_edit(course_id):
        u = current_user()
        course = Course.query.get_or_404(course_id)
        if course.user_id != u.id:
            flash("Можно редактировать только свои интенсивы.", "error")
            return redirect(url_for("profile", tab="course"))
        ordered_videos = sorted(course.videos, key=lambda v: (v.order_index or 0, v.id))
        form = {
            "title": course.title or "",
            "subject": course.subject or "",
            "topic": course.topic or "",
            "description": course.description or "",
            "price": str(course.price or ""),
            "video_meta": [],
            "is_edit": True,
            "cover_preview": course.cover_image,
            "existing_videos": [
                {
                    "id": video.id,
                    "title": video.title or "",
                    "quality": video.quality_label or "Оригинал",
                    "order": video.order_index if video.order_index is not None else idx,
                }
                for idx, video in enumerate(ordered_videos)
            ],
        }
        if request.method == "POST":
            form["title"] = (request.form.get("title") or "").strip()
            form["subject"] = (request.form.get("subject") or "").strip()
            form["topic"] = (request.form.get("topic") or "").strip()
            form["description"] = (request.form.get("description") or "").strip()
            form["price"] = (request.form.get("price") or "").strip()
            price_value = None
            errors = []
            if not form["title"]:
                errors.append("Укажите заголовок курса.")
            if form["price"]:
                try:
                    price_value = int(round(float(form["price"].replace(",", "."))))
                    if price_value < 0:
                        raise ValueError
                except ValueError:
                    errors.append("Цена должна быть числом.")
            else:
                errors.append("Укажите цену интенсива.")

            remove_ids = set()
            for val in request.form.getlist("remove_video_ids[]"):
                try:
                    remove_ids.add(int(val))
                except (TypeError, ValueError):
                    continue

            updated_existing = []
            for idx, video in enumerate(ordered_videos):
                title_val = (request.form.get(f"existing_title_{video.id}") or "").strip()
                quality_val = (request.form.get(f"existing_quality_{video.id}") or "").strip()
                order_raw = (request.form.get(f"existing_order_{video.id}") or "").strip()
                form_entry = {
                    "id": video.id,
                    "title": title_val,
                    "quality": quality_val,
                    "order": order_raw,
                    "marked": video.id in remove_ids,
                }
                form["existing_videos"][idx] = form_entry
                try:
                    order_val = int(order_raw)
                except (TypeError, ValueError):
                    order_val = idx
                updated_existing.append({
                    "video": video,
                    "title": title_val or video.title or f"Урок {idx+1}",
                    "quality": quality_val or video.quality_label or "Оригинал",
                    "order": order_val,
                    "remove": video.id in remove_ids,
                })

            video_titles = [t.strip() for t in request.form.getlist("video_title[]")]
            video_qualities = [q.strip() for q in request.form.getlist("video_quality[]")]
            video_files = request.files.getlist("video_file[]")
            meta = []
            max_len = max(len(video_titles), len(video_qualities), len(video_files))
            for idx in range(max_len):
                title = video_titles[idx] if idx < len(video_titles) else ""
                quality = video_qualities[idx] if idx < len(video_qualities) else ""
                if title or quality or idx < len(video_titles):
                    meta.append({"title": title, "quality": quality})
            form["video_meta"] = meta

            prepared_videos = []
            for idx, meta_info in enumerate(meta):
                file = video_files[idx] if idx < len(video_files) else None
                if file and file.filename:
                    ext = file.filename.rsplit(".", 1)[-1].lower()
                    if ext not in ALLOWED_VIDEO:
                        errors.append(f"Формат видео {file.filename} не поддерживается.")
                        continue
                    title = meta_info.get("title") or f"Новый урок {idx+1}"
                    quality = meta_info.get("quality") or "Оригинал"
                    prepared_videos.append({
                        "file": file,
                        "title": title,
                        "quality": quality,
                        "ext": ext,
                    })
                elif meta_info.get("title") or meta_info.get("quality"):
                    errors.append("Загрузите файл для нового видео.")

            keep_existing = [item for item in updated_existing if not item["remove"]]
            if not keep_existing and not prepared_videos:
                errors.append("Добавьте хотя бы одно видео.")

            cover = request.files.get("cover_image")
            if cover and cover.filename:
                cover_ext = cover.filename.rsplit(".", 1)[-1].lower()
                if cover_ext not in ALLOWED_IMG:
                    errors.append("Формат изображения не поддерживается.")

            if errors:
                for err in errors:
                    flash(err, "error")
                if not form["video_meta"]:
                    form["video_meta"] = [{"title": "", "quality": ""}]
                return render_template("course_form.html", form=form, course=course)

            # Ensure base directories exist
            course_dir = os.path.join(UPLOAD_FOLDER, "courses", f"user{u.id}", f"course{course.id}")
            os.makedirs(course_dir, exist_ok=True)

            # Update core fields
            course.title = form["title"]
            course.subject = form["subject"] or None
            course.topic = form["topic"] or None
            course.description = form["description"] or None
            course.price = price_value

            # Handle cover replacement
            if cover and cover.filename:
                cover_ext = cover.filename.rsplit(".", 1)[-1].lower()
                cover_filename = secure_filename(f"cover.{cover_ext}")
                cover_path = os.path.join(course_dir, cover_filename)
                cover.save(cover_path)
                if course.cover_image:
                    old_path = os.path.join(BASE_DIR, course.cover_image.lstrip("/"))
                    if os.path.exists(old_path) and old_path != cover_path:
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
                course.cover_image = "/".join(["", "uploads", "courses", f"user{u.id}", f"course{course.id}", cover_filename])
                form["cover_preview"] = course.cover_image

            # Remove videos marked for deletion
            for item in updated_existing:
                if item["remove"]:
                    video = item["video"]
                    video_path = os.path.join(BASE_DIR, video.file_path.lstrip("/")) if video.file_path else None
                    db.session.delete(video)
                    if video_path and os.path.exists(video_path):
                        try:
                            os.remove(video_path)
                        except OSError:
                            pass

            # Apply updates to remaining videos and normalize order
            keep_existing = [item for item in updated_existing if not item["remove"]]
            keep_existing.sort(key=lambda x: x["order"])
            for idx, item in enumerate(keep_existing):
                video = item["video"]
                video.title = item["title"]
                video.quality_label = item["quality"] or "Оригинал"
                video.order_index = idx

            videos_dir = os.path.join(course_dir, "videos")
            os.makedirs(videos_dir, exist_ok=True)
            offset = len(keep_existing)
            for order, video in enumerate(prepared_videos, start=offset):
                filename = secure_filename(f"video{order+1}_{datetime.datetime.utcnow().timestamp():.0f}.{video['ext']}")
                file_path = os.path.join(videos_dir, filename)
                video["file"].save(file_path)
                rel_path = "/".join(["", "uploads", "courses", f"user{u.id}", f"course{course.id}", "videos", filename])
                db.session.add(CourseVideo(
                    course_id=course.id,
                    title=video["title"],
                    file_path=rel_path,
                    quality_label=video["quality"],
                    order_index=order,
                ))

            db.session.commit()
            flash("Интенсив обновлён.", "ok")
            return redirect(url_for("profile", tab="course"))

        if not form["video_meta"]:
            form["video_meta"] = [{"title": "", "quality": ""}]
        return render_template("course_form.html", form=form, course=course)

    class ConvHelper:
        @staticmethod
        def get_or_create(a,b):
            existing = db.session.query(Conversation).join(ConversationMember).filter(ConversationMember.user_id.in_([a,b])).all()
            for c in existing:
                ids = set(m.user_id for m in ConversationMember.query.filter_by(conversation_id=c.id))
                if ids == set([a,b]): return c
            c = Conversation(); db.session.add(c); db.session.commit()
            db.session.add(ConversationMember(conversation_id=c.id, user_id=a))
            db.session.add(ConversationMember(conversation_id=c.id, user_id=b)); db.session.commit()
            return c

    @app.route("/chat")
    @login_required
    def chat_index():
        uid = session["user_id"]
        conv_ids = [m.conversation_id for m in ConversationMember.query.filter_by(user_id=uid).all()]
        convs = []
        for cid in conv_ids:
            other_id = [m.user_id for m in ConversationMember.query.filter_by(conversation_id=cid).all() if m.user_id!=uid][0]
            other = User.query.get(other_id)
            last = Message.query.filter_by(conversation_id=cid).order_by(Message.created_at.desc()).first()
            convs.append({"id":cid,"other":other,"last":last})
        return render_template("chat.html", conversations=convs)

    @app.route("/chat/with/<int:user_id>", methods=["GET","POST"])
    @login_required
    def chat_with(user_id):
        me = session["user_id"]
        if me == user_id:
            flash("Нельзя писать самому себе.","error"); return redirect(url_for("chat_index"))
        c = ConvHelper.get_or_create(me, user_id)
        if request.method == "POST":
            text_ = (request.form.get("text") or "").strip()
            if text_:
                db.session.add(Message(conversation_id=c.id, sender_id=me, text=text_)); db.session.commit()
        msgs = Message.query.filter_by(conversation_id=c.id).order_by(Message.created_at.asc()).all()
        other_id = [m.user_id for m in ConversationMember.query.filter_by(conversation_id=c.id).all() if m.user_id!=me][0]
        other = User.query.get(other_id)
        return render_template("chat_with.html", other=other, messages=msgs)

    @app.route("/profile", methods=["GET","POST"])
    @login_required
    def profile():
        u = current_user()
        tab = request.args.get("tab") or request.form.get("tab") or "summary"
        if tab not in ("summary","about","course"):
            tab = "summary"
        courses_data = []
        for course in sorted(u.courses, key=lambda c: c.created_at or datetime.datetime.utcnow(), reverse=True):
            courses_data.append({
                "course": course,
                "video_count": len(course.videos),
                "edit_url": url_for("course_edit", course_id=course.id),
                "public_url": url_for("public_profile", user_id=u.id, course_id=course.id),
            })
        purchased_courses = []
        if u.role == "student":
            approved_requests = CourseAccessRequest.query.filter_by(student_id=u.id, status="approved").order_by(CourseAccessRequest.updated_at.desc()).all()
            for req in approved_requests:
                course = req.course
                if not course:
                    continue
                purchased_courses.append({
                    "course": course,
                    "teacher": course.owner,
                    "video_count": len(course.videos),
                    "public_url": url_for("public_profile", user_id=course.owner.id, course_id=course.id),
                    "approved_at": req.updated_at,
                })
        if request.method == "POST":
            action = request.form.get("action")
            if action == "about":
                if "cancel" in request.form:
                    return redirect(url_for("profile"))
                u.first_name = request.form.get("first_name","").strip() or None
                u.last_name = request.form.get("last_name","").strip() or None
                nickname = request.form.get("nickname","").strip() or None
                if nickname:
                    existing = User.query.filter(User.nickname==nickname, User.id!=u.id).first()
                    if existing:
                        flash("Никнейм уже занят.","error")
                        return redirect(url_for("profile", tab="about"))
                u.nickname = nickname
                age_val = request.form.get("age","").strip()
                try:
                    u.age = int(age_val) if age_val else None
                except ValueError:
                    flash("Возраст должен быть числом.","error")
                    return redirect(url_for("profile", tab="about"))
                u.education = request.form.get("education","").strip() or None
                grad = request.form.get("graduation_year","").strip()
                if grad and (not grad.isdigit() or len(grad) not in (2,4)):
                    flash("Год выпуска должен состоять из цифр.","error")
                    return redirect(url_for("profile", tab="about"))
                u.graduation_year = grad or None
                telegram_val = request.form.get("telegram","").strip()
                if not telegram_val:
                    flash("Укажите ник в Telegram.", "error")
                    return redirect(url_for("profile", tab="about"))
                u.telegram = telegram_val
                file = request.files.get("avatar")
                if file and file.filename:
                    ext = file.filename.rsplit(".",1)[-1].lower()
                    if ext in ALLOWED_IMG:
                        path = os.path.join(UPLOAD_FOLDER,"avatars", secure_filename(f"user{u.id}_avatar.{ext}"))
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        file.save(path)
                        u.avatar = "/uploads/avatars/" + os.path.basename(path)
                    else:
                        flash("Неподдерживаемый формат файла.","error")
                        return redirect(url_for("profile", tab="about"))
                db.session.commit()
                flash("Профиль обновлён.","ok")
                return redirect(url_for("profile"))
        return render_template("profile.html", user=u, tab=tab, avatar=avatar_url(u), courses=courses_data, purchased_courses=purchased_courses)

    @app.route("/courses/<int:course_id>/videos/<int:video_id>")
    @login_required
    def course_video_stream(course_id, video_id):
        course = Course.query.get_or_404(course_id)
        video = CourseVideo.query.filter_by(id=video_id, course_id=course_id).first_or_404()
        user = current_user()
        if not user:
            abort(403)
        if user.id != course.user_id:
            if user.role != "student":
                return send_decoy_image(download=request.args.get("download") == "1")
            approved = CourseAccessRequest.query.filter_by(course_id=course.id, student_id=user.id, status="approved").first()
            if not approved:
                return send_decoy_image(download=request.args.get("download") == "1")
        file_path = absolute_upload_path(video.file_path)
        if not file_path or not os.path.exists(file_path):
            abort(404)
        if request.args.get("download") == "1":
            return send_decoy_image(download=True)
        fetch_mode = request.headers.get("Sec-Fetch-Mode", "")
        if fetch_mode == "navigate":
            return send_decoy_image(download=True)
        mimetype = mimetypes.guess_type(file_path)[0] or "video/mp4"
        return stream_video_file(file_path, mimetype)

    @app.route("/uploads/<path:filename>")
    def uploaded(filename):
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext in ALLOWED_VIDEO:
            return send_decoy_image(download=True)
        return send_from_directory(UPLOAD_FOLDER, filename)

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
