# Standard library imports
import logging
import os
from logging.handlers import RotatingFileHandler

# Third-party imports
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from flask_caching import Cache
from sqlalchemy.exc import OperationalError, DisconnectionError

# psycopg3는 자동으로 binary 구현을 사용합니다

# Local imports
from .config import Config
from .models import db, User

# 확장 초기화
login_manager = LoginManager()

# 스케줄러 초기화
scheduler = APScheduler()

# 캐시 초기화
cache = Cache()


@login_manager.user_loader
def load_user(user_id):
    """Flask-Login 사용자 로더"""
    try:
        return User.query.get(user_id)
    except (OperationalError, DisconnectionError) as e:
        # 데이터베이스 연결 오류 시 로그 기록
        logger = logging.getLogger(__name__)
        logger.error(f"데이터베이스 연결 오류 (사용자 로딩): {e}")
        return None
    except Exception as e:
        # 기타 예외 처리
        logger = logging.getLogger(__name__)
        logger.error(f"사용자 로딩 오류: {e}")
        return None


def create_app(config_class=Config, testing=False):
    """CleanBox Flask 애플리케이션 팩토리"""

    app = Flask(__name__)
    app.config.from_object(config_class)
    if testing:
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False  # 테스트 시 CSRF 비활성화(필요시)

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

    # 스케줄러 초기화 (테스트 환경에서는 건너뜀)
    if not testing:
        scheduler.init_app(app)
        scheduler.start()

        # 30분 주기 웹훅 모니터링 작업 등록
        from .email.routes import monitor_and_renew_webhooks

        def scheduled_webhook_monitoring():
            with app.app_context():
                monitor_and_renew_webhooks()

        scheduler.add_job(
            id="webhook_monitor",
            func=scheduled_webhook_monitoring,
            trigger="interval",
            minutes=30,
            replace_existing=True,
        )

    # 캐시 초기화
    cache.init_app(app)

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
        # 로그인된 사용자는 대시보드로 리다이렉트
        if current_user and current_user.is_authenticated:
            return redirect(url_for("main.dashboard"))

        # 로그인되지 않은 사용자는 랜딩 페이지 표시
        return render_template("landing.html")

    # home 엔드포인트 추가
    @app.route("/home")
    def home():
        return redirect(url_for("main.dashboard"))

    # Unauthorized 에러 핸들러
    @app.errorhandler(401)
    def unauthorized(error):
        if current_user and current_user.is_authenticated:
            # 로그인된 사용자지만 권한이 없는 경우
            flash("해당 기능에 대한 권한이 없습니다.", "error")
            return redirect(url_for("main.dashboard"))
        else:
            # 로그인되지 않은 사용자
            flash("로그인이 필요합니다.", "error")
            return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(error):
        flash("해당 기능에 대한 접근 권한이 없습니다.", "error")
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
