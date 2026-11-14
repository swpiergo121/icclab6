#!/usr/bin/env python3

import os
import uuid
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

from templates_store import TEMPLATES

load_dotenv()

# ---------- App / DB config ----------
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ["SECRET_KEY"],
    SQLALCHEMY_DATABASE_URI=os.environ["DATABASE_URL"],
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # 5 MB upload limit
)
app.jinja_loader = DictLoader(TEMPLATES)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------- S3 config ----------
S3_BUCKET = os.environ["S3_BUCKET"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# On EC2 credentials come from the instance role automatically.
s3 = boto3.client("s3", region_name=AWS_REGION)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


# ---------- Model ----------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    image_key = db.Column(db.String(255))  # S3 object key, not a URL
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------- Helpers ----------
def admin_required(f):
    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def presigned_url(key):
    """Temporary URL (1 hour) to display a private S3 image."""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=3600,
    )


def delete_image(key):
    try:
        s3.delete_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as exc:
        app.logger.error("Could not delete S3 object %s: %s", key, exc)


app.jinja_env.globals["image_url"] = presigned_url


def save_user_form(user, is_new):
    """
    Validates the submitted form and applies it to `user`.
    Returns (error_message_or_None, old_image_key_to_delete_or_None).
    Validation happens before any mutation, so failed saves change nothing.
    """
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not username or not email:
        return "Username and email are required.", None
    if (is_new and not password) or (password and len(password) < 8):
        return "Password must be at least 8 characters.", None

    duplicate = User.query.filter(
        (User.username == username) | (User.email == email),
        User.id != (user.id or 0),
    ).first()
    if duplicate:
        return "Username or email already in use.", None

    image = request.files.get("image")
    has_image = image is not None and image.filename != ""
    ext = ""
    if has_image:
        ext = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return "Image must be png, jpg, jpeg, gif or webp.", None

    # Admins cannot remove their own admin flag (also covers the profile page).
    if user.id is not None and user.id == current_user.id:
        is_admin = user.is_admin
    else:
        is_admin = "is_admin" in request.form

    old_key = None
    new_key = None
    if has_image:
        new_key = f"users/{uuid.uuid4().hex}.{ext}"
        s3.upload_fileobj(image, S3_BUCKET, new_key,
                          ExtraArgs={"ContentType": image.mimetype})
        old_key = user.image_key

    user.username = username
    user.email = email
    user.is_admin = is_admin
    if password:
        user.set_password(password)
    if new_key:
        user.image_key = new_key

    return None, old_key


# ---------- Auth ----------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("list_users"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if user and user.is_admin and user.check_password(request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("list_users"))
        flash("Invalid credentials or not an admin.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------- Admin profile ----------
@app.route("/profile", methods=["GET", "POST"])
@admin_required
def profile():
    user = db.get_or_404(User, current_user.id)
    if request.method == "POST":
        error, old_key = save_user_form(user, is_new=False)
        if error:
            flash(error, "error")
        else:
            db.session.commit()
            if old_key:
                delete_image(old_key)
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("user_form.html", user=user, title="My profile", profile=True)


# ---------- CRUD: users ----------
@app.route("/admin/users")                                   # READ (list / search)
@admin_required
def list_users():
    q = request.args.get("q", "").strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.username.ilike(like)) | (User.email.ilike(like)))
    users = query.order_by(User.id).all()
    return render_template("users.html", users=users, q=q)


@app.route("/admin/users/<int:user_id>")                     # READ (detail)
@admin_required
def user_detail(user_id):
    user = db.get_or_404(User, user_id)
    return render_template("user_detail.html", user=user)


@app.route("/admin/users/new", methods=["GET", "POST"])      # CREATE
@admin_required
def new_user():
    user = User()
    if request.method == "POST":
        error, _ = save_user_form(user, is_new=True)
        if error:
            flash(error, "error")
        else:
            db.session.add(user)
            db.session.commit()
            flash("User created.", "success")
            return redirect(url_for("list_users"))
    return render_template("user_form.html", user=user, title="New user", profile=False)


@app.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])  # UPDATE
@admin_required
def edit_user(user_id):
    user = db.get_or_404(User, user_id)
    if request.method == "POST":
        error, old_key = save_user_form(user, is_new=False)
        if error:
            flash(error, "error")
        else:
            db.session.commit()
            if old_key:
                delete_image(old_key)
            flash("User updated.", "success")
            return redirect(url_for("user_detail", user_id=user.id))
    return render_template("user_form.html", user=user,
                           title=f"Edit {user.username}", profile=False)


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])      # DELETE
@admin_required
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("list_users"))
    image_key = user.image_key
    db.session.delete(user)
    db.session.commit()
    if image_key:
        delete_image(image_key)
    flash("User deleted.", "success")
    return redirect(url_for("list_users"))


# ---------- Startup ----------
with app.app_context():
    db.create_all()
    if os.environ.get("ADMIN_PASSWORD") and not User.query.filter_by(is_admin=True).first():
        admin = User(
            username=os.environ.get("ADMIN_USERNAME", "admin"),
            email=os.environ.get("ADMIN_EMAIL", "admin@example.com"),
            is_admin=True,
        )
        admin.set_password(os.environ["ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()

if __name__ == "__main__":
    app.run(debug=True)
