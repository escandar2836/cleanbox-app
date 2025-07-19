from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_apscheduler import APScheduler
from cleanbox.config import Config
from cleanbox.models import db, User
from cleanbox.auth.routes import auth_bp
from cleanbox.main.routes import main_bp
from cleanbox.email.routes import email_bp
from cleanbox.category.routes import category_bp
from cleanbox.email.webhook_routes import webhook_bp
import os

# Flask 앱 생성
app = Flask(__name__)
app.config.from_object(Config)

# 데이터베이스 초기화
db.init_app(app)

# 로그인 매니저 초기화
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"

# 스케줄러 초기화
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


# 블루프린트 등록
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(main_bp, url_prefix="/")
app.register_blueprint(email_bp, url_prefix="/email")
app.register_blueprint(category_bp, url_prefix="/category")
app.register_blueprint(webhook_bp, url_prefix="/webhook")


# 주기적 웹훅 모니터링 스케줄러 설정
@scheduler.task("interval", id="webhook_monitor", hours=6)
def scheduled_webhook_monitoring():
    """6시간마다 모든 사용자의 웹훅 상태를 모니터링"""
    try:
        from cleanbox.email.routes import monitor_and_renew_webhooks

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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
