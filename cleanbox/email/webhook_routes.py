# Standard library imports
import base64
import json
import logging
import os
from datetime import datetime

# Third-party imports
from flask import Blueprint, request, jsonify

# Local imports
from ..models import User, UserAccount, Email, WebhookStatus, db
from .gmail_service import GmailService
from .ai_classifier import AIClassifier

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/gmail", methods=["POST"])
def gmail_webhook():
    """Gmail 웹훅 처리"""
    try:
        logger.info("웹훅 요청 수신")

        # 웹훅 검증
        if not _verify_webhook(request):
            logger.warning("웹훅 검증 실패")
            return jsonify({"status": "error", "message": "인증 실패"}), 401

        # 웹훅 데이터 파싱
        data = request.get_json()

        if not data or "message" not in data:
            logger.warning("잘못된 웹훅 데이터 구조")
            return jsonify({"status": "error", "message": "잘못된 웹훅 데이터"}), 400

        # 메시지 디코딩
        message_data = base64.b64decode(data["message"]["data"]).decode("utf-8")
        message = json.loads(message_data)

        # 이메일 주소 추출
        email_address = message.get("emailAddress")
        history_id = message.get("historyId")

        logger.info(f"웹훅 처리: {email_address}, history_id: {history_id}")

        if not email_address or not history_id:
            logger.warning("이메일 정보 누락")
            return jsonify({"status": "error", "message": "이메일 정보 없음"}), 400

        # 해당 계정 찾기
        account = UserAccount.query.filter_by(account_email=email_address).first()
        if not account:
            logger.warning(f"계정을 찾을 수 없음: {email_address}")
            return jsonify({"status": "error", "message": "계정을 찾을 수 없음"}), 404

        # 새 이메일 처리
        process_new_emails_for_account(account)

        # 웹훅 수신 시간 업데이트
        try:
            webhook_status = WebhookStatus.query.filter_by(
                user_id=account.user_id, account_id=account.id, is_active=True
            ).first()

            if webhook_status:
                webhook_status.last_webhook_received = datetime.utcnow()
                db.session.commit()
                logger.info(f"웹훅 수신 시간 업데이트: {email_address}")
        except Exception as e:
            logger.error(f"웹훅 수신 시간 업데이트 실패: {e}")

        logger.info(f"웹훅 처리 완료: {email_address}")
        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"웹훅 처리 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@webhook_bp.route("/gmail/test", methods=["GET"])
def gmail_webhook_test():
    """Gmail 웹훅 테스트 엔드포인트"""
    try:
        # 연결된 계정 정보도 함께 반환
        accounts = UserAccount.query.filter_by(is_active=True).all()
        account_info = [
            {
                "id": acc.id,
                "email": acc.account_email,
                "name": acc.account_name,
                "is_primary": acc.is_primary,
            }
            for acc in accounts
        ]

        return jsonify(
            {
                "status": "success",
                "message": "웹훅 엔드포인트가 정상 작동합니다",
                "timestamp": datetime.utcnow().isoformat(),
                "connected_accounts": account_info,
                "webhook_url": "/webhook/gmail",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _verify_webhook(request):
    """웹훅 검증 (완화된 버전)"""
    try:
        # Content-Type 확인
        if request.content_type != "application/json":
            logger.warning("잘못된 Content-Type")
            return False

        # User-Agent 확인 (Google Cloud Pub/Sub) - 완화된 검증
        user_agent = request.headers.get("User-Agent", "")
        # Google Cloud Pub/Sub의 실제 User-Agent는 다양할 수 있으므로 완화
        if not user_agent or "Google" not in user_agent:
            logger.warning(f"의심스러운 User-Agent: {user_agent}")
            # 개발 환경에서는 더 관대하게 처리
            if os.environ.get("FLASK_ENV") == "development":
                logger.info("개발 환경에서 User-Agent 검증 건너뜀")
            else:
                return False

        # 기본적인 요청 구조 확인
        data = request.get_json()
        if not data or "message" not in data:
            logger.warning("잘못된 웹훅 데이터 구조")
            return False

        return True

    except Exception as e:
        logger.error(f"웹훅 검증 오류: {e}")
        return False


def process_new_emails_for_account(account):
    """계정의 새 이메일 처리 (가입 날짜 이후만)"""
    try:
        gmail_service = GmailService(account.user_id, account.id)
        ai_classifier = AIClassifier()

        # 사용자 정보 가져오기
        user = User.query.get(account.user_id)
        if not user:
            logger.error(f"사용자 정보를 찾을 수 없음: {account.user_id}")
            return

        # 가입 날짜 이후의 이메일만 가져오기
        after_date = user.first_service_access
        logger.info(
            f"웹훅 이메일 처리 - 계정: {account.account_email}, 가입일: {after_date}"
        )

        # 새 이메일 가져오기 (가입 날짜 이후만)
        recent_emails = gmail_service.fetch_recent_emails(
            max_results=10, after_date=after_date
        )

        if not recent_emails:
            logger.info(f"새 이메일 없음: {account.account_email}")
            return

        # 사용자 카테고리 가져오기
        categories = gmail_service.get_user_categories()

        processed_count = 0
        classified_count = 0
        archived_count = 0

        for email_data in recent_emails:
            try:
                # 이미 처리된 이메일인지 확인
                existing_email = Email.query.filter_by(
                    user_id=account.user_id,
                    account_id=account.id,
                    gmail_id=email_data["gmail_id"],
                ).first()

                if existing_email:
                    continue

                # DB에 저장
                email_obj = gmail_service.save_email_to_db(email_data)

                if email_obj:
                    processed_count += 1

                    # AI 분류 및 요약
                    if categories:
                        category_id, summary = (
                            ai_classifier.classify_and_summarize_email(
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

                        # 요약 저장
                        if (
                            summary
                            and summary
                            != "AI 처리를 사용할 수 없습니다. 수동으로 확인해주세요."
                        ):
                            email_obj.summary = summary

                            # AI 분석 완료 후 Gmail에서 아카이브 처리
                            try:
                                gmail_service.archive_email(email_data["gmail_id"])
                                email_obj.is_archived = True
                                archived_count += 1
                                logger.info(
                                    f"✅ 웹훅 이메일 아카이브 완료: {email_data.get('subject', '제목 없음')}"
                                )
                            except Exception as e:
                                logger.error(f"❌ 웹훅 이메일 아카이브 실패: {str(e)}")

                            db.session.commit()

                logger.info(
                    f"웹훅 이메일 처리 완료 - 제목: {email_data.get('subject', '제목 없음')}"
                )

            except Exception as e:
                logger.error(f"웹훅 이메일 처리 실패: {str(e)}")
                continue

        logger.info(
            f"웹훅 처리 완료 - 계정: {account.account_email}, 처리: {processed_count}개, 분류: {classified_count}개, 아카이브: {archived_count}개"
        )

    except Exception as e:
        logger.error(f"웹훅 이메일 처리 중 오류: {str(e)}")
