# Standard library imports
import logging
import os
from logging.handlers import RotatingFileHandler

# Third-party imports
from flask import Flask, render_template, redirect, url_for, flash
from flask_login import LoginManager, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from sqlalchemy.exc import OperationalError, DisconnectionError

# psycopg3 설정
import os

if os.environ.get("DATABASE_URI") or os.environ.get("DATABASE_URL"):
    # psycopg3 사용 설정
    os.environ.setdefault("PSYCOPG_IMPL", "binary")

# Local imports
from .config import Config
from .models import db, User

# 확장 초기화
login_manager = LoginManager()

# 스케줄러 초기화
scheduler = APScheduler()


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

    # 스케줄러 초기화
    scheduler.init_app(app)
    scheduler.start()

    # 주기적 웹훅 모니터링 스케줄러 설정
    @scheduler.task("interval", id="webhook_monitor", hours=6)
    def scheduled_webhook_monitoring():
        """6시간마다 모든 사용자의 웹훅 상태를 모니터링"""
        try:
            from .email.routes import monitor_and_renew_webhooks

            print("🕐 스케줄된 웹훅 모니터링 시작...")

            result = monitor_and_renew_webhooks()

            if result["success"]:
                print(
                    f"✅ 스케줄된 웹훅 모니터링 완료 - 갱신: {result['renewed_count']}개, 실패: {result['failed_count']}개"
                )
            else:
                print(
                    f"❌ 스케줄된 웹훅 모니터링 실패: {result.get('error', 'Unknown error')}"
                )

        except Exception as e:
            print(f"❌ 스케줄된 웹훅 모니터링 중 오류: {str(e)}")

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
