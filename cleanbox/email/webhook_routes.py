# Standard library imports
import base64
import json
import logging
import os
from datetime import datetime

# Third-party imports
from flask import Blueprint, request, jsonify, session

# Local imports
from ..models import User, UserAccount, Email, WebhookStatus, db
from .gmail_service import GmailService
from .ai_classifier import AIClassifier
from .. import cache

logger = logging.getLogger(__name__)

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/gmail", methods=["POST"])
def gmail_webhook():
    """Gmail webhook handler"""
    try:
        logger.info("Webhook request received")

        # Webhook verification
        if not _verify_webhook(request):
            logger.warning("Webhook verification failed")
            return jsonify({"status": "error", "message": "Authentication failed"}), 401

        # Parse webhook data
        data = request.get_json()

        if not data or "message" not in data:
            logger.warning("Invalid webhook data structure")
            return jsonify({"status": "error", "message": "Invalid webhook data"}), 400

        # Decode message
        message_data = base64.b64decode(data["message"]["data"]).decode("utf-8")
        message = json.loads(message_data)

        # Extract email address
        email_address = message.get("emailAddress")
        history_id = message.get("historyId")

        logger.info(f"Webhook processing: {email_address}, history_id: {history_id}")

        if not email_address or not history_id:
            logger.warning("Missing email information")
            return jsonify({"status": "error", "message": "No email information"}), 400

        # Find account
        account = UserAccount.query.filter_by(account_email=email_address).first()
        if not account:
            logger.warning(f"Account not found: {email_address}")
            return jsonify({"status": "error", "message": "Account not found"}), 404

        # Process new emails
        result = process_new_emails_for_account(account)

        # If new emails processed, invalidate cache and notify
        if result and result.get("processed_count", 0) > 0:
            # Invalidate cache (for real-time notification)
            cache_key = f"max_email_id_{account.user_id}"
            cache.delete(cache_key)
            logger.info(f"Cache invalidated: {cache_key}")

            # Simple notification data for browser notification
            notification_data = {
                "type": "new_emails",
                "user_id": account.user_id,
                "processed_count": result["processed_count"],
                "classified_count": result["classified_count"],
                "archived_count": result["archived_count"],
                "account_email": account.account_email,
                "timestamp": datetime.utcnow().isoformat(),
                "message": f"{result['processed_count']} new emails have been processed.",
            }

            logger.info(
                f"New email processing complete: {account.user_id} - {result['processed_count']} emails"
            )

        # Update webhook received time
        try:
            webhook_status = WebhookStatus.query.filter_by(
                user_id=account.user_id, account_id=account.id, is_active=True
            ).first()

            if webhook_status:
                webhook_status.last_webhook_received = datetime.utcnow()
                db.session.commit()
                logger.info(f"Webhook received time updated: {email_address}")
        except Exception as e:
            logger.error(f"Failed to update webhook received time: {e}")

        logger.info(f"Webhook processing complete: {email_address}")
        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"Error during webhook processing: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@webhook_bp.route("/gmail/test", methods=["GET"])
def gmail_webhook_test():
    """Gmail webhook test endpoint"""
    try:
        # Return connected account info as well
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
                "message": "Webhook endpoint is working properly",
                "timestamp": datetime.utcnow().isoformat(),
                "connected_accounts": account_info,
                "webhook_url": "/webhook/gmail",
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def _verify_webhook(request):
    """Webhook verification (relaxed version)"""
    try:
        # Check Content-Type
        if request.content_type != "application/json":
            logger.warning("Invalid Content-Type")
            return False

        # Check User-Agent (Google Cloud Pub/Sub) - relaxed verification
        user_agent = request.headers.get("User-Agent", "")
        # Google Cloud Pub/Sub's actual User-Agent can vary, so relaxed
        if not user_agent or "Google" not in user_agent:
            logger.warning(f"Suspicious User-Agent: {user_agent}")
            # In development environment, skip User-Agent check
            if os.environ.get("FLASK_ENV") == "development":
                logger.info(
                    "Skipping User-Agent verification in development environment"
                )
            else:
                return False

        # Basic request structure check
        data = request.get_json()
        if not data or "message" not in data:
            logger.warning("Invalid webhook data structure")
            return False

        return True

    except Exception as e:
        logger.error(f"Webhook verification error: {e}")
        return False


def process_new_emails_for_account(account):
    """Process new emails for account (only after signup date)"""
    try:
        gmail_service = GmailService(account.user_id, account.id)
        ai_classifier = AIClassifier()

        # Get user info
        user = User.query.get(account.user_id)
        if not user:
            logger.error(f"User info not found: {account.user_id}")
            return None

        # Only get emails after signup date
        after_date = user.first_service_access
        logger.info(
            f"Webhook email processing - account: {account.account_email}, signup date: {after_date}"
        )

        # Get new emails (only after signup date)
        recent_emails = gmail_service.fetch_recent_emails(
            max_results=10, after_date=after_date
        )

        if not recent_emails:
            logger.info(f"No new emails: {account.account_email}")
            return None

        # Get user categories (for AI classification, as dict)
        category_objects = gmail_service.get_user_categories()
        categories = [
            {"id": cat.id, "name": cat.name, "description": cat.description or ""}
            for cat in category_objects
        ]

        processed_count = 0
        classified_count = 0
        archived_count = 0

        for email_data in recent_emails:
            try:
                # Check if email already processed
                existing_email = Email.query.filter_by(
                    user_id=account.user_id,
                    account_id=account.id,
                    gmail_id=email_data["gmail_id"],
                ).first()

                if existing_email:
                    continue

                # Save to DB
                email_obj = gmail_service.save_email_to_db(email_data)

                if email_obj:
                    processed_count += 1

                    # AI classification and summarization
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

                        # Save summary
                        if (
                            summary
                            and summary
                            != "AI processing not available. Please check manually."
                        ):
                            email_obj.summary = summary

                            # After AI analysis, archive in Gmail
                            try:
                                gmail_service.archive_email(email_data["gmail_id"])
                                email_obj.is_archived = True
                                archived_count += 1
                                logger.info(
                                    f"✅ Webhook email archived: {email_data.get('subject', 'No subject')}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ Webhook email archive failed: {str(e)}"
                                )

                            db.session.commit()

                logger.info(
                    f"Webhook email processing complete - subject: {email_data.get('subject', 'No subject')}"
                )

            except Exception as e:
                logger.error(f"Webhook email processing failed: {str(e)}")
                continue

        logger.info(
            f"Webhook processing complete - account: {account.account_email}, processed: {processed_count}, classified: {classified_count}, archived: {archived_count}"
        )

        # Return processing result
        result = {
            "processed_count": processed_count,
            "classified_count": classified_count,
            "archived_count": archived_count,
        }

        # If new emails processed, log
        if processed_count > 0:
            logger.info(
                f"New emails processed - user: {account.user_id}, processed emails: {processed_count}"
            )

        return result

    except Exception as e:
        logger.error(f"Error during webhook email processing: {str(e)}")
        return None
