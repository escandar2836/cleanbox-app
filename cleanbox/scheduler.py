import os
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from flask import current_app
from .models import User, UserAccount, db
from .email.gmail_service import GmailService
from .email.ai_classifier import AIClassifier


class CleanBoxScheduler:
    """CleanBox 백그라운드 작업 스케줄러"""

    def __init__(self, app=None):
        self.app = app
        self.scheduler = BackgroundScheduler()
        self.logger = logging.getLogger(__name__)

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Flask 앱 초기화"""
        self.app = app

        # 스케줄러 설정
        self.scheduler.configure(job_defaults={"coalesce": False, "max_instances": 3})

        # 작업 등록
        self._register_jobs()

        # 스케줄러 시작
        self.scheduler.start()
        self.logger.info("CleanBox 스케줄러가 시작되었습니다.")

    def _register_jobs(self):
        """백그라운드 작업 등록"""

        # 스케줄러가 활성화된 경우에만 작업 등록
        if not self.app.config.get("ENABLE_SCHEDULER", True):
            self.logger.info("스케줄러가 비활성화되어 있습니다.")
            return

        # 1. 주기적 이메일 동기화 (설정 가능한 간격)
        sync_interval = self.app.config.get("SYNC_INTERVAL_MINUTES", 5)
        self.scheduler.add_job(
            func=self._sync_emails_for_active_users,
            trigger=IntervalTrigger(minutes=sync_interval),
            id="email_sync_job",
            name="이메일 동기화",
            replace_existing=True,
        )

        # 2. 토큰 갱신 체크 (설정 가능한 간격)
        token_check_interval = self.app.config.get("TOKEN_CHECK_INTERVAL_HOURS", 1)
        self.scheduler.add_job(
            func=self._check_token_refresh,
            trigger=IntervalTrigger(hours=token_check_interval),
            id="token_refresh_job",
            name="토큰 갱신 체크",
            replace_existing=True,
        )

        # 3. 세션 정리 (10분마다)
        self.scheduler.add_job(
            func=self._cleanup_inactive_sessions,
            trigger=IntervalTrigger(minutes=10),
            id="session_cleanup_job",
            name="세션 정리",
            replace_existing=True,
        )

        # 4. 데이터베이스 정리 (매일 새벽 2시)
        self.scheduler.add_job(
            func=self._cleanup_old_data,
            trigger=CronTrigger(hour=2, minute=0),
            id="cleanup_job",
            name="데이터베이스 정리",
            replace_existing=True,
        )

        self.logger.info(
            f"스케줄러 작업 등록 완료: 이메일 동기화({sync_interval}분), 토큰 체크({token_check_interval}시간)"
        )

    def _sync_emails_for_active_users(self):
        """활성 사용자들의 이메일 동기화"""
        try:
            with self.app.app_context():
                # 활동 추적 미들웨어에서 활성 사용자 조회
                from .middleware import activity_tracker

                active_users = activity_tracker.get_active_users(minutes=30)

                self.logger.info(
                    f"활성 사용자 {len(active_users)}명의 이메일 동기화 시작"
                )

                for user in active_users:
                    try:
                        self._sync_user_emails(user)
                    except Exception as e:
                        self.logger.error(
                            f"사용자 {user.id} 이메일 동기화 실패: {str(e)}"
                        )
                        continue

                self.logger.info("이메일 동기화 완료")

        except Exception as e:
            self.logger.error(f"이메일 동기화 작업 실패: {str(e)}")

    def _sync_user_emails(self, user):
        """특정 사용자의 이메일 동기화"""
        try:
            # 사용자의 모든 계정에 대해 동기화
            accounts = UserAccount.query.filter_by(user_id=user.id).all()

            for account in accounts:
                try:
                    gmail_service = GmailService(user.id, account.id)
                    ai_classifier = AIClassifier()

                    # 최근 이메일 가져오기 (최대 50개)
                    recent_emails = gmail_service.fetch_recent_emails(max_results=50)

                    if not recent_emails:
                        continue

                    # 사용자 카테고리 가져오기
                    categories = gmail_service.get_user_categories()

                    processed_count = 0
                    classified_count = 0

                    for email_data in recent_emails:
                        try:
                            # DB에 저장
                            email_obj = gmail_service.save_email_to_db(email_data)

                            if email_obj:
                                processed_count += 1

                                # AI 분류 시도
                                if categories:
                                    category_id, reasoning = (
                                        ai_classifier.classify_email(
                                            email_data["body"],
                                            email_data["subject"],
                                            email_data["sender"],
                                            categories,
                                        )
                                    )

                                    if category_id:
                                        gmail_service.update_email_category(
                                            email_data["gmail_id"], category_id
                                        )
                                        classified_count += 1

                                # AI 요약 생성
                                summary = ai_classifier.summarize_email(
                                    email_data["body"], email_data["subject"]
                                )
                                if (
                                    summary
                                    and summary
                                    != "AI 요약을 사용할 수 없습니다. 이메일 내용을 직접 확인해주세요."
                                ):
                                    email_obj.summary = summary
                                    db.session.commit()

                        except Exception as e:
                            self.logger.error(f"이메일 처리 실패: {str(e)}")
                            continue

                    self.logger.info(
                        f"사용자 {user.id} 계정 {account.id}: "
                        f"{processed_count}개 처리, {classified_count}개 분류"
                    )

                except Exception as e:
                    self.logger.error(f"계정 {account.id} 동기화 실패: {str(e)}")
                    continue

        except Exception as e:
            self.logger.error(f"사용자 {user.id} 동기화 실패: {str(e)}")

    def _check_token_refresh(self):
        """토큰 갱신 필요성 체크"""
        try:
            with self.app.app_context():
                # 토큰 만료가 임박한 계정들 체크
                accounts = UserAccount.query.all()

                for account in accounts:
                    try:
                        # 토큰 만료 시간 체크 (1시간 전에 갱신)
                        if account.token_expiry:
                            expiry_time = account.token_expiry
                            refresh_threshold = expiry_time - timedelta(hours=1)

                            if datetime.utcnow() >= refresh_threshold:
                                self.logger.info(f"계정 {account.id} 토큰 갱신 필요")
                                # 토큰 갱신 로직은 auth 모듈에서 처리

                    except Exception as e:
                        self.logger.error(f"계정 {account.id} 토큰 체크 실패: {str(e)}")
                        continue

        except Exception as e:
            self.logger.error(f"토큰 갱신 체크 실패: {str(e)}")

    def _cleanup_inactive_sessions(self):
        """비활성 세션 정리"""
        try:
            with self.app.app_context():
                from .middleware import activity_tracker

                cleaned_count = activity_tracker.cleanup_inactive_sessions()

                if cleaned_count > 0:
                    self.logger.info(f"{cleaned_count}개의 비활성 세션 정리됨")

        except Exception as e:
            self.logger.error(f"세션 정리 실패: {str(e)}")

    def _cleanup_old_data(self):
        """오래된 데이터 정리"""
        try:
            with self.app.app_context():
                # 30일 이상 된 읽은 이메일 아카이브
                cleanup_threshold = datetime.utcnow() - timedelta(days=30)

                from .models import Email

                old_emails = Email.query.filter(
                    Email.is_read == True, Email.created_at <= cleanup_threshold
                ).all()

                for email in old_emails:
                    email.is_archived = True

                db.session.commit()
                self.logger.info(f"{len(old_emails)}개의 오래된 이메일 아카이브됨")

        except Exception as e:
            self.logger.error(f"데이터 정리 실패: {str(e)}")

    def shutdown(self):
        """스케줄러 종료"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.logger.info("CleanBox 스케줄러가 종료되었습니다.")


# 전역 스케줄러 인스턴스
scheduler = CleanBoxScheduler()
