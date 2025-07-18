import os
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from .config import Config

# 확장 초기화
login_manager = LoginManager()
db = SQLAlchemy()


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

    # 블루프린트 등록
    from .auth.routes import auth_bp
    from .category.routes import category_bp
    from .email.routes import email_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(category_bp, url_prefix="/category")
    app.register_blueprint(email_bp, url_prefix="/email")

    # 메인 페이지를 카테고리 대시보드로 설정
    @app.route("/")
    def index():
        from flask_login import current_user

        if current_user.is_authenticated:
            from flask import redirect, url_for

            return redirect(url_for("category.list_categories"))
        else:
            from flask import redirect, url_for

            return redirect(url_for("auth.login"))

    # 데이터베이스 초기화
    with app.app_context():
        db.create_all()

    return app


def init_db(app):
    """데이터베이스 초기화"""
    with app.app_context():
        db.create_all()
        print("CleanBox 데이터베이스가 초기화되었습니다.")
