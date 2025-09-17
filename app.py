# -*- coding: utf-8 -*-
import os, datetime, random
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, g
from flask_sqlalchemy import SQLAlchemy
from passlib.hash import argon2
from werkzeug.utils import secure_filename

from sqlalchemy import inspect, text  # SQLAlchemy 2.x: инспектор и text


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DEFAULT_AVATARS = {
    "student": "/static/img/lion_student.svg",
    "specialist": "/static/img/lion_teacher.svg",
}
ALLOWED_IMG = {"png","jpg","jpeg","gif","webp"}
ALLOWED_VIDEO = {"mp4", "mov", "avi", "mkv", "webm"}

db = SQLAlchemy()


def ensure_schema():
    """Apply simple runtime migrations that are not covered by create_all()."""

    # ``db.engine`` is only available inside an application context, so the
    # function is expected to be called from there.
    engine = db.engine

    # ``engine.begin()`` opens a transaction and commits it automatically
    # which ensures that the DDL executed below is persisted.
    with engine.begin() as conn:
        inspector = inspect(conn)

        if "user" not in inspector.get_table_names():
            return

        column_names = {col["name"] for col in inspector.get_columns("user")}
        if "age" not in column_names:
            ddl = text('ALTER TABLE "user" ADD COLUMN age INTEGER')
            conn.execute(ddl)

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
    def inject_i18n():
        return dict(
            t=lambda k: tr(g.lang, k),
            lang=g.lang,
            theme=g.theme,
            current_user=current_user,
            avatar_url=avatar_url,  # функцию тоже пробрасываем в шаблоны
            format_price=format_price,
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


class CourseVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    title = db.Column(db.String(255))
    file_path = db.Column(db.String(255), nullable=False)
    quality_label = db.Column(db.String(50))
    order_index = db.Column(db.Integer, default=0)

# ---------- Хелперы ----------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def w(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_screen"))
        return f(*args, **kwargs)
    return w

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

def ensure_schema():
    engine = db.engine
    inspector = inspect(engine)
    user_cols = {col["name"] for col in inspector.get_columns("user")}
    alters = []
    # Экранируем имя таблицы "user" — кросс-СУБД безопаснее
    if "age" not in user_cols:
        alters.append('ALTER TABLE "user" ADD COLUMN age INTEGER')
    if "education" not in user_cols:
        alters.append('ALTER TABLE "user" ADD COLUMN education VARCHAR(255)')
    if "graduation_year" not in user_cols:
        alters.append('ALTER TABLE "user" ADD COLUMN graduation_year VARCHAR(10)')
    if "course_image" not in user_cols:
        alters.append('ALTER TABLE "user" ADD COLUMN course_image VARCHAR(255)')
    if "telegram" not in user_cols:
        alters.append('ALTER TABLE "user" ADD COLUMN telegram VARCHAR(120)')
    if not alters:
        return
    # SQLAlchemy 2.x: сырые SQL через exec_driver_sql() или text(...)
    with engine.begin() as conn:
        for stmt in alters:
            conn.exec_driver_sql(stmt)
            # альтернатива:
            # conn.execute(text(stmt))

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
        session.clear(); return redirect(url_for("login_screen"))

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
            session.clear(); session["user_id"] = user.id; session.permanent = True
            if remember: app.permanent_session_lifetime = datetime.timedelta(days=int(app.config.get("REMEMBER_DAYS",30)))
            else: app.permanent_session_lifetime = datetime.timedelta(days=int(app.config.get("SESSION_DAYS",7)))
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
        q = (request.args.get("q") or "").strip()
        q_clean = q.lstrip("@").lower()
        ensure_bots()
        people = User.query.order_by(User.created_at.desc()).all()
        if q_clean:
            def match(p):
                hay = " ".join(filter(None, [
                    p.first_name or "",
                    p.last_name or "",
                    p.nickname or "",
                    p.role or "",
                    (p.specialist.keywords if p.specialist else ""),
                    (p.student.looking_for if p.student else ""),
                ])).lower()
                return q_clean in hay
            people = list(filter(match, people))
        return render_template("search.html", people=people, q=q)

    @app.route("/support")
    def support_redirect():
        return redirect("https://t.me/ezizkafromag")

    @app.route("/people/<int:user_id>")
    @login_required
    def public_profile(user_id):
        person = User.query.get_or_404(user_id)
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
                        "src": v.file_path,
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
            })
        return render_template("user_public.html", person=person, avatar=avatar_url(person), courses=courses_payload)

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
            "video_meta": [{"title": "", "quality": "Оригинал"}],
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
            for idx in range(max(len(video_titles), 1)):
                title = video_titles[idx] if idx < len(video_titles) else ""
                quality = video_qualities[idx] if idx < len(video_qualities) else "Оригинал"
                meta.append({"title": title, "quality": quality or "Оригинал"})
            form["video_meta"] = meta or [{"title": "", "quality": "Оригинал"}]
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
            preview_clip = request.files.get("preview_clip")
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
            if preview_clip and preview_clip.filename:
                preview_ext = preview_clip.filename.rsplit(".", 1)[-1].lower()
                if preview_ext not in ALLOWED_VIDEO:
                    errors.append("Формат файла превью не поддерживается.")
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
            if preview_clip and preview_clip.filename:
                preview_ext = preview_clip.filename.rsplit(".", 1)[-1].lower()
                preview_filename = secure_filename(f"preview.{preview_ext}")
                preview_path = os.path.join(course_dir, preview_filename)
                preview_clip.save(preview_path)
                course.preview_clip = "/".join(["", "uploads", "courses", f"user{u.id}", f"course{course.id}", preview_filename])
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
        return render_template("profile.html", user=u, tab=tab, avatar=avatar_url(u), courses=courses_data)

    @app.route("/uploads/<path:filename>")
    def uploaded(filename):
        return send_from_directory(UPLOAD_FOLDER, filename)

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
