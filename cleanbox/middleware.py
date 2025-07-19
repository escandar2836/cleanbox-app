import time
from datetime import datetime, timedelta
from flask import request, session, g
from flask_login import current_user
from .models import User, db


class ActivityTracker:
    """사용자 활동 추적 미들웨어"""

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Flask 앱에 미들웨어 등록"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)

    def before_request(self):
        """요청 전 처리"""
        # 정적 파일이나 API 요청은 제외
        if request.endpoint and not request.endpoint.startswith("static"):
            self._update_user_activity()

    def after_request(self, response):
        """요청 후 처리"""
        return response

    def _update_user_activity(self):
        """사용자 활동 업데이트"""
        try:
            if current_user.is_authenticated:
                # 현재 시간
                now = datetime.utcnow()

                # 사용자 정보 업데이트
                current_user.last_activity = now
                current_user.is_online = True
                current_user.session_id = session.get("_id", None)

                # 세션 ID가 없으면 생성
                if not session.get("_id"):
                    session["_id"] = f"session_{int(time.time())}_{current_user.id}"
                    current_user.session_id = session["_id"]

                db.session.commit()

        except Exception as e:
            # 에러가 발생해도 요청 처리는 계속
            print(f"활동 추적 에러: {str(e)}")

    @staticmethod
    def get_active_users(minutes=30):
        """활성 사용자 목록 조회"""
        try:
            # 지정된 시간 내에 활동한 사용자들
            active_threshold = datetime.utcnow() - timedelta(minutes=minutes)

            active_users = User.query.filter(
                User.last_activity >= active_threshold, User.is_online == True
            ).all()

            return active_users

        except Exception as e:
            print(f"활성 사용자 조회 에러: {str(e)}")
            return []

    @staticmethod
    def cleanup_inactive_sessions():
        """비활성 세션 정리"""
        try:
            # 30분 이상 활동이 없는 사용자를 오프라인으로 설정
            inactive_threshold = datetime.utcnow() - timedelta(minutes=30)

            inactive_users = User.query.filter(
                User.last_activity < inactive_threshold, User.is_online == True
            ).all()

            for user in inactive_users:
                user.is_online = False
                user.session_id = None

            db.session.commit()

            return len(inactive_users)

        except Exception as e:
            print(f"비활성 세션 정리 에러: {str(e)}")
            return 0


# 전역 인스턴스
activity_tracker = ActivityTracker()
