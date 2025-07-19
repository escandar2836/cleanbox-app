from flask import Blueprint, request, jsonify
from ..models import User, UserAccount, Email, db
from .gmail_service import GmailService
from .ai_classifier import AIClassifier
import base64
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/gmail", methods=["POST"])
def gmail_webhook():
    """Gmail 웹훅 처리"""
    try:
        # 웹훅 검증
        if not _verify_webhook(request):
            return jsonify({"status": "error", "message": "인증 실패"}), 401

        # 웹훅 데이터 파싱
        data = request.get_json()

        if not data or "message" not in data:
            return jsonify({"status": "error", "message": "잘못된 웹훅 데이터"}), 400

        # 메시지 디코딩
        message_data = base64.b64decode(data["message"]["data"]).decode("utf-8")
        message = json.loads(message_data)

        # 이메일 주소 추출
        email_address = message.get("emailAddress")
        history_id = message.get("historyId")

        if not email_address or not history_id:
            return jsonify({"status": "error", "message": "이메일 정보 없음"}), 400

        # 해당 계정 찾기
        account = UserAccount.query.filter_by(account_email=email_address).first()
        if not account:
            return jsonify({"status": "error", "message": "계정을 찾을 수 없음"}), 404

        # 새 이메일 처리
        process_new_emails_for_account(account)

        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"웹훅 처리 오류: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@webhook_bp.route("/gmail/test", methods=["GET"])
def gmail_webhook_test():
    """Gmail 웹훅 테스트 엔드포인트"""
    try:
        return jsonify(
            {
                "status": "success",
                "message": "웹훅 엔드포인트가 정상 작동합니다",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _verify_webhook(request):
    """웹훅 검증"""
    try:
        # Content-Type 확인
        if request.content_type != "application/json":
            logger.warning("잘못된 Content-Type")
            return False

        # User-Agent 확인 (Google Cloud Pub/Sub)
        user_agent = request.headers.get("User-Agent", "")
        if "Google-Cloud-PubSub" not in user_agent:
            logger.warning("잘못된 User-Agent")
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
    """계정의 새 이메일 처리"""
    try:
        gmail_service = GmailService(account.user_id, account.id)
        ai_classifier = AIClassifier()

        # 새 이메일 가져오기 (최근 5개만)
        recent_emails = gmail_service.fetch_recent_emails(max_results=5)

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
                            db.session.commit()

                    # 이메일 아카이브 (PROJECT_DESCRIPTION 요구사항)
                    try:
                        gmail_service.archive_email(email_data["gmail_id"])
                        archived_count += 1
                    except Exception as e:
                        logger.error(f"이메일 아카이브 실패: {e}")

            except Exception as e:
                logger.error(f"이메일 처리 오류: {e}")
                continue

        if processed_count > 0:
            logger.info(
                f"웹훅 처리 완료: {account.account_email} - {processed_count}개 처리, {classified_count}개 분류, {archived_count}개 아카이브"
            )

    except Exception as e:
        logger.error(f"계정 처리 오류: {account.account_email} - {e}")
