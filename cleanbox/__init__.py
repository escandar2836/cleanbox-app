import os
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from .config import Config

# 확장 초기화
login_manager = LoginManager()
# models.py에서 db 인스턴스를 import
from .models import db


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 사용자 로더"""
    from .models import User

    return User.query.get(user_id)


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 확장 초기화
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "CleanBox를 사용하려면 로그인해주세요."
    login_manager.login_message_category = "info"

    # 세션 설정 강화
    app.config["SESSION_COOKIE_SECURE"] = False  # 개발 환경용
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600  # 1시간

    # 모델 import (db.metadata에 테이블 등록을 위해)
    from . import models

    # 블루프린트 등록
    from .auth.routes import auth_bp
    from .category.routes import category_bp
    from .email.routes import email_bp
    from .main.routes import main_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(category_bp, url_prefix="/category")
    app.register_blueprint(email_bp, url_prefix="/email")
    app.register_blueprint(main_bp, url_prefix="/main")

    # 메인 페이지 설정
    @app.route("/")
    def index():
        from flask_login import current_user
        from flask import render_template, redirect, url_for, session

        # 랜딩페이지에서는 불필요한 세션 정리
        if not current_user.is_authenticated:
            # 로그인 관련 세션 정리
            session.pop("state", None)
            session.pop("adding_account", None)
            return render_template("landing.html")
        else:
            return redirect(url_for("main.dashboard"))

    # 데이터베이스 초기화 (테스트 환경이 아닌 경우에만)
    if not app.config.get("TESTING", False):
        with app.app_context():
            db.create_all()

    return app


def init_db(app):
    """데이터베이스 초기화"""
    with app.app_context():
        db.create_all()
        print("CleanBox 데이터베이스가 초기화되었습니다.")
