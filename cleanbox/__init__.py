import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, redirect, url_for
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
    from sqlalchemy.exc import OperationalError, DisconnectionError

    try:
        return User.query.get(user_id)
    except (OperationalError, DisconnectionError) as e:
        # 데이터베이스 연결 오류 시 로그 기록
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"데이터베이스 연결 오류 (사용자 로딩): {e}")
        return None
    except Exception as e:
        # 기타 예외 처리
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"사용자 로딩 오류: {e}")
        return None


def create_app(config_class=Config):
    """CleanBox Flask 애플리케이션 팩토리"""

    app = Flask(__name__)
    app.config.from_object(config_class)

    # 로깅 설정
    if not app.debug and not app.testing:
        if not os.path.exists("logs"):
            os.mkdir("logs")
        file_handler = RotatingFileHandler(
            "logs/cleanbox.log", maxBytes=10240, backupCount=10
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
            )
        )
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info("CleanBox 시작")

    # 데이터베이스 초기화
    db.init_app(app)

    # 로그인 매니저 초기화
    login_manager.init_app(app)

    # 블루프린트 등록
    from .auth.routes import auth_bp
    from .main.routes import main_bp
    from .category.routes import category_bp
    from .email.routes import email_bp
    from .email.webhook_routes import webhook_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp, url_prefix="/main")
    app.register_blueprint(category_bp, url_prefix="/category")
    app.register_blueprint(email_bp, url_prefix="/email")
    app.register_blueprint(webhook_bp, url_prefix="/webhook")

    # 메인 라우트 (루트 URL)
    @app.route("/")
    def index():
        return render_template("landing.html")

    # home 엔드포인트 추가
    @app.route("/home")
    def home():
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
