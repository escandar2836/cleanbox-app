# Standard library imports
import os
import traceback
import logging
from datetime import datetime, timedelta
import asyncio

# Third-party imports
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    session,
)
from flask_login import login_required, current_user
from flask_apscheduler import APScheduler

# Local imports
from ..models import Email, Category, UserAccount, WebhookStatus, db
from .. import cache
from .gmail_service import GmailService
from .ai_classifier import AIClassifier
from ..auth.routes import (
    check_and_refresh_token,
    get_current_account_id,
    grant_service_account_pubsub_permissions,
)

logger = logging.getLogger(__name__)

email_bp = Blueprint("email", __name__)


# Lazy imports to avoid circular import issues
def get_scheduler():
    """Get scheduler instance lazily to avoid circular imports"""
    from app import scheduler

    return scheduler


def get_scheduled_webhook_monitoring():
    """Get scheduled webhook monitoring function lazily to avoid circular imports"""
    from app import scheduled_webhook_monitoring

    return scheduled_webhook_monitoring


@email_bp.route("/")
@login_required
def list_emails():
    """Email list page (all accounts combined)"""
    try:
        # Check for new email notification
        new_emails_notification = None
        notification_file = f"notifications/{current_user.id}_new_emails.txt"

        if os.path.exists(notification_file):
            try:
                with open(notification_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        timestamp_str, count_str = content.split(",")
                        notification_time = datetime.fromisoformat(timestamp_str)

                        # Show notification only within 1 hour
                        if datetime.utcnow() - notification_time < timedelta(hours=1):
                            new_emails_notification = {
                                "count": int(count_str),
                                "timestamp": notification_time,
                            }

                # Delete notification file (show only once)
                os.remove(notification_file)
            except Exception as e:
                print(f"Notification file handling failed: {str(e)}")

        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            flash("No connected accounts.", "error")
            return render_template(
                "email/list.html",
                user=current_user,
                emails=[],
                stats={},
                accounts=[],
                new_emails_notification=new_emails_notification,
            )

        # Check and refresh token for each account
        for account in accounts:
            try:
                token_valid = check_and_refresh_token(current_user.id, account.id)

                if not token_valid:
                    flash(
                        f"Authentication for account {account.account_email} has expired. Please log in again.",
                        "warning",
                    )
            except Exception as e:
                print(f"Token check failed: {str(e)}")

        # Query emails for all accounts (sorted by creation time desc)
        emails = (
            Email.query.filter(
                Email.user_id == current_user.id,
                Email.account_id.in_([acc.id for acc in accounts]),
            )
            .order_by(Email.created_at.desc())
            .limit(100)
            .all()
        )

        # Add account info to emails
        account_dict = {acc.id: acc for acc in accounts}
        for email in emails:
            email.account_info = account_dict.get(email.account_id)

        # Calculate email count per account
        account_stats = {}
        for account in accounts:
            account_emails = Email.query.filter_by(
                user_id=current_user.id, account_id=account.id
            ).count()
            account_unread = Email.query.filter_by(
                user_id=current_user.id, account_id=account.id, is_read=False
            ).count()
            account_archived = Email.query.filter_by(
                user_id=current_user.id, account_id=account.id, is_archived=True
            ).count()
            account_analyzed = (
                Email.query.filter_by(user_id=current_user.id, account_id=account.id)
                .filter(Email.summary.isnot(None))
                .count()
            )

            account_stats[account.id] = {
                "email": account.account_email,
                "name": account.account_name,
                "count": account_emails,
                "unread": account_unread,
                "archived": account_archived,
                "analyzed": account_analyzed,
            }

        # Stats info
        stats = {
            "total": len(emails),
            "unread": sum(1 for e in emails if not e.is_read),
            "archived": sum(1 for e in emails if e.is_archived),
            "analyzed": sum(1 for e in emails if e.summary),
            "account_stats": account_stats,
        }

        return render_template(
            "email/list.html",
            user=current_user,
            emails=emails,
            stats=stats,
            accounts=accounts,
            new_emails_notification=new_emails_notification,
        )

    except Exception as e:
        flash(f"Error loading email list: {str(e)}", "error")
        return render_template(
            "email/list.html", user=current_user, emails=[], stats={}, accounts=[]
        )


@email_bp.route("/category/<int:category_id>")
@login_required
def category_emails(category_id):
    """Email list by category (all accounts combined)"""
    try:
        # Check user's category
        category = Category.query.filter_by(
            id=category_id, user_id=current_user.id
        ).first()
        if not category:
            flash("Category not found.", "error")
            return redirect(url_for("email.list_emails"))

        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        # Query emails for the category from all accounts
        emails = (
            Email.query.filter(
                Email.user_id == current_user.id,
                Email.category_id == category_id,
                Email.account_id.in_([acc.id for acc in accounts]),
            )
            .order_by(Email.created_at.desc())
            .all()
        )

        # Add account info to emails
        account_dict = {acc.id: acc for acc in accounts}
        for email in emails:
            email.account_info = account_dict.get(email.account_id)

        # Calculate email count per account
        account_stats = {}
        for account in accounts:
            account_emails = [e for e in emails if e.account_id == account.id]
            account_stats[account.id] = {
                "email": account.account_email,
                "name": account.account_name,
                "count": len(account_emails),
            }

        return render_template(
            "email/category.html",
            user=current_user,
            category=category,
            emails=emails,
            accounts=accounts,
            account_stats=account_stats,
        )

    except Exception as e:
        flash(f"Error loading category emails: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/process-new", methods=["POST"])
@login_required
def process_new_emails():
    """Process new emails"""
    try:
        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        total_processed = 0
        total_classified = 0
        account_results = []
        new_emails_processed = False  # Whether new emails were processed

        for account in accounts:
            try:
                print(f"🔍 Processing new emails for account {account.account_email}")
                gmail_service = GmailService(current_user.id, account.id)

                # Get new emails
                new_emails = gmail_service.get_new_emails()
                print(
                    f"📧 Found {len(new_emails)} new emails in account {account.account_email}"
                )

                if not new_emails:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "no_new_emails",
                            "processed": 0,
                            "classified": 0,
                        }
                    )
                    continue

                # Process new emails
                processed_count = 0
                classified_count = 0

                for email_data in new_emails:
                    try:
                        # Save email to DB
                        email_obj = gmail_service.save_email_to_db(email_data)
                        processed_count += 1

                        # AI classification
                        ai_classifier = AIClassifier()
                        categories = ai_classifier.get_user_categories_for_ai(
                            current_user.id
                        )
                        category_id, summary = (
                            ai_classifier.classify_and_summarize_email(
                                email_obj.content,
                                email_obj.subject,
                                email_obj.sender,
                                categories,
                            )
                        )

                        if category_id:
                            # Update category
                            gmail_service.update_email_category(
                                email_obj.gmail_id, category_id
                            )
                            classified_count += 1

                    except Exception as e:
                        print(f"❌ Failed to process email: {str(e)}")
                        continue

                total_processed += processed_count
                total_classified += classified_count

                if processed_count > 0:
                    new_emails_processed = True

                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "success",
                        "processed": processed_count,
                        "classified": classified_count,
                    }
                )

                print(
                    f"✅ Finished processing account {account.account_email} - Processed: {processed_count}, Classified: {classified_count}"
                )

            except Exception as e:
                print(f"❌ Failed to process account {account.account_email}: {str(e)}")
                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "error",
                        "error": str(e),
                    }
                )

        # Return result
        if total_processed == 0:
            flash("No new emails.", "info")
            return redirect(url_for("email.list_emails"))

        # Invalidate cache (recalculate max email id since new emails were processed)
        cache_key = f"max_email_id_{current_user.id}"
        cache.delete(cache_key)
        print(f"✅ Cache invalidated: {cache_key}")

        # Create success message
        success_message = f"New email processing complete: {total_processed} processed, {total_classified} AI classified"

        if account_results and len(account_results) > 0:
            success_message += "\n\nResults by account:"
            for result in account_results:
                if result["status"] == "success":
                    success_message += f"\n• {result['account']}: {result['processed']} processed, {result['classified']} classified"
                elif result["status"] == "no_new_emails":
                    success_message += f"\n• {result['account']}: No new emails"
                else:
                    success_message += (
                        f"\n• {result['account']}: Error - {result['error']}"
                    )

        flash(success_message, "success")
        return redirect(url_for("email.list_emails"))

    except Exception as e:
        print(f"❌ Error processing new emails: {str(e)}")
        flash(f"Error occurred while processing new emails: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/read")
@login_required
def mark_as_read(email_id):
    """Mark email as read"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("Email not found.", "error")
            return redirect(url_for("email.list_emails"))

        gmail_service = GmailService(current_user.id)
        gmail_service.mark_as_read(email_obj.gmail_id)

        flash("Marked as read.", "success")
        return redirect(url_for("email.list_emails"))

    except Exception as e:
        flash(f"Error occurred while changing email status: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/archive")
@login_required
def archive_email(email_id):
    """Archive email"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("Email not found.", "error")
            return redirect(url_for("email.list_emails"))

        gmail_service = GmailService(current_user.id)
        gmail_service.archive_email(email_obj.gmail_id)

        flash("Email archived.", "success")
        return redirect(url_for("email.list_emails"))

    except Exception as e:
        flash(f"Error occurred while archiving email: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/classify", methods=["POST"])
@login_required
def classify_email(email_id):
    """Manual email classification"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            return jsonify({"success": False, "message": "Email not found."})

        category_id = request.form.get("category_id")
        if category_id:
            category_id = int(category_id)
            if category_id == 0:  # Unclassified
                category_id = None

        # Direct database update
        email_obj.category_id = category_id
        email_obj.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"success": True, "message": "Email classified."})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"Error: {str(e)}"})


@email_bp.route("/<int:email_id>/analyze")
@login_required
def analyze_email(email_id):
    """Email AI analysis - classification and summary"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            return jsonify({"success": False, "message": "Email not found."})

        ai_classifier = AIClassifier()

        # Get user categories for AI
        categories = ai_classifier.get_user_categories_for_ai(current_user.id)

        if not categories:
            return jsonify({"success": False, "message": "No available categories."})

        # Debug information output
        print(f"🔍 AI analysis started - Email ID: {email_id}")
        print(f"   Subject: {email_obj.subject}")
        print(f"   Sender: {email_obj.sender}")
        print(
            f"   Content length: {len(email_obj.content) if email_obj.content else 0}"
        )
        print(f"   Number of categories: {len(categories)}")

        # AI classification and summarization
        category_id, summary = ai_classifier.classify_and_summarize_email(
            email_obj.content, email_obj.subject, email_obj.sender, categories
        )

        print(f"📊 AI analysis result:")
        print(f"   Category ID: {category_id}")
        print(f"   Summary: {summary[:100]}..." if summary else "   Summary: None")

        # Update result
        if category_id:
            email_obj.category_id = category_id
        else:
            email_obj.category_id = None

        if (
            summary
            and summary != "AI processing is not available. Please check manually."
        ):
            email_obj.summary = summary

        # AI analysis completed, archive email in Gmail
        try:
            gmail_service = GmailService(current_user.id, email_obj.account_id)
            gmail_service.archive_email(email_obj.gmail_id)
            email_obj.is_archived = True
            print(f"✅ Email archived: {email_obj.subject}")
        except Exception as e:
            print(f"❌ Failed to archive email: {str(e)}")

        db.session.commit()

        # Get category information
        category_name = "Unclassified"
        if category_id:
            category = Category.query.filter_by(
                id=category_id, user_id=current_user.id
            ).first()
            if category:
                category_name = category.name

        analysis = {
            "category_id": category_id,
            "category_name": category_name,
            "summary": summary,
            "archived": email_obj.is_archived,
            "success": True,
        }

        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error occurred during analysis: {str(e)}"}
        )


@email_bp.route("/statistics")
@login_required
def email_statistics():
    """Email statistics (all accounts combined)"""
    try:
        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify(
                {
                    "success": True,
                    "statistics": {
                        "total": 0,
                        "unread": 0,
                        "archived": 0,
                        "categories": {},
                    },
                }
            )

        # Sum statistics for all accounts
        total_stats = {"total": 0, "unread": 0, "archived": 0, "categories": {}}

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)
                account_stats = gmail_service.get_email_statistics()

                # Basic statistics addition
                total_stats["total"] += account_stats.get("total", 0)
                total_stats["unread"] += account_stats.get("unread", 0)
                total_stats["archived"] += account_stats.get("archived", 0)

                # Category-wise statistics addition
                for category_id, count in account_stats.get("categories", {}).items():
                    if category_id in total_stats["categories"]:
                        total_stats["categories"][category_id] += count
                    else:
                        total_stats["categories"][category_id] = count

            except Exception as e:
                print(
                    f"Failed to retrieve statistics for account {account.account_email}: {str(e)}"
                )
                continue

        return jsonify({"success": True, "statistics": total_stats})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error retrieving statistics: {str(e)}"}
        )


@email_bp.route("/<int:email_id>")
@login_required
def view_email(email_id):
    """View email details"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("Email not found.", "error")
            return redirect(url_for("email.list_emails"))

        # When viewing email details, automatically mark as read
        if not email_obj.is_read:
            email_obj.is_read = True
            email_obj.updated_at = datetime.utcnow()
            db.session.commit()

        # Category information (cover case of unclassified and no category)
        category = None
        if email_obj.category_id:
            # Check user permissions to retrieve category
            category = Category.query.filter_by(
                id=email_obj.category_id, user_id=current_user.id
            ).first()
            # If category is not found or deleted, set category_id to None
            if not category:
                email_obj.category_id = None
                db.session.commit()

        # User category list (for changing categories)
        user_categories = Category.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        return render_template(
            "email/view.html",
            user=current_user,
            email=email_obj,
            category=category,
            categories=user_categories,
        )

    except Exception as e:
        flash(f"Error loading email: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/bulk-actions", methods=["POST"])
@login_required
def bulk_actions():
    """Bulk email actions"""
    try:
        action = request.form.get("action")
        email_ids = request.form.getlist("email_ids")

        if not email_ids:
            return (
                jsonify({"success": False, "message": "No emails selected."}),
                400,
            )

        gmail_service = GmailService(current_user.id)
        processed_count = 0

        if action == "delete":
            # Bulk deletion (improved version)
            print(
                f"🔍 Bulk deletion started - Number of selected emails: {len(email_ids)}"
            )

            # Variables for collecting results
            success_count = 0
            failed_emails = []
            result_message = ""

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ Email {email_id} not found")
                        failed_emails.append(
                            {
                                "id": email_id,
                                "subject": "Unknown",
                                "error": "Email not found",
                                "error_type": "not_found",
                            }
                        )
                        continue

                    # Delete from Gmail
                    gmail_service = GmailService(current_user.id, email_obj.account_id)
                    gmail_service.delete_email(email_obj.gmail_id)

                    # Delete from DB
                    db.session.delete(email_obj)
                    success_count += 1
                    print(f"✅ Email {email_id} deletion successful")

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Failed to delete email (ID: {email_id}): {error_msg}")

                    # Classify error type
                    error_type = "unknown"
                    if "404" in error_msg and "not found" in error_msg.lower():
                        error_type = "not_found"
                        error_details = "Email already deleted or not found"
                    elif "403" in error_msg:
                        error_type = "forbidden"
                        error_details = "No permission to delete"
                    elif "401" in error_msg:
                        error_type = "unauthorized"
                        error_details = "Authentication failed"
                    elif "500" in error_msg:
                        error_type = "server_error"
                        error_details = "Server error occurred"
                    elif (
                        "network" in error_msg.lower()
                        or "connection" in error_msg.lower()
                    ):
                        error_type = "network_error"
                        error_details = "Network connection error"
                    else:
                        error_details = error_msg

                    failed_emails.append(
                        {
                            "id": email_id,
                            "subject": email_obj.subject if email_obj else "Unknown",
                            "error": error_details,
                            "error_type": error_type,
                        }
                    )

            # Commit DB changes
            db.session.commit()

            # Group errors by type
            error_groups = {}
            for email in failed_emails:
                error_type = email.get("error_type", "unknown")
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append(email)

            # Generate result message
            total_processed = success_count + len(failed_emails)
            message_parts = []

            # Success count is always displayed (even if 0)
            message_parts.append(f"✅ Success: {success_count} emails")

            # Display only actual errors
            for error_type, emails in error_groups.items():
                if emails:  # Only display actual errors
                    error_name = {
                        "not_found": "Already deleted",
                        "forbidden": "No permission",
                        "unauthorized": "Authentication failed",
                        "server_error": "Server error",
                        "network_error": "Network error",
                        "unknown": "Unknown error",
                    }.get(error_type, error_type)

                    message_parts.append(f"❌ {error_name}: {len(emails)} emails")

            result_message = (
                f"Deletion complete ({total_processed} emails):\n"
                + "\n".join(message_parts)
            )

            print(f"🎉 Bulk deletion completed - {result_message}")

            return jsonify({"success": True, "message": result_message})

        elif action == "archive":
            # Bulk archiving (improved version)
            print(
                f"🔍 Bulk archiving started - Number of selected emails: {len(email_ids)}"
            )

            # Variables for collecting results
            success_count = 0
            failed_emails = []
            result_message = ""

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ Email {email_id} not found")
                        failed_emails.append(
                            {
                                "id": email_id,
                                "subject": "Unknown",
                                "error": "Email not found",
                                "error_type": "not_found",
                            }
                        )
                        continue

                    gmail_service = GmailService(current_user.id, email_obj.account_id)
                    gmail_service.archive_email(email_obj.gmail_id)
                    success_count += 1
                    print(f"✅ Email {email_id} archiving successful")

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Failed to archive email (ID: {email_id}): {error_msg}")

                    # Classify error type
                    error_type = "unknown"
                    if "404" in error_msg and "not found" in error_msg.lower():
                        error_type = "not_found"
                        error_details = "Email already deleted or not found"
                    elif "403" in error_msg:
                        error_type = "forbidden"
                        error_details = "No permission to archive"
                    elif "401" in error_msg:
                        error_type = "unauthorized"
                        error_details = "Authentication failed"
                    elif "500" in error_msg:
                        error_type = "server_error"
                        error_details = "Server error occurred"
                    elif (
                        "network" in error_msg.lower()
                        or "connection" in error_msg.lower()
                    ):
                        error_type = "network_error"
                        error_details = "Network connection error"
                    else:
                        error_details = error_msg

                    failed_emails.append(
                        {
                            "id": email_id,
                            "subject": email_obj.subject if email_obj else "Unknown",
                            "error": error_details,
                            "error_type": error_type,
                        }
                    )

            # Group errors by type
            error_groups = {}
            for email in failed_emails:
                error_type = email.get("error_type", "unknown")
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append(email)

            # Generate result message
            total_processed = success_count + len(failed_emails)
            message_parts = []

            # Success count is always displayed (even if 0)
            message_parts.append(f"✅ Success: {success_count} emails")

            # Display only actual errors
            for error_type, emails in error_groups.items():
                if emails:  # Only display actual errors
                    error_name = {
                        "not_found": "Already deleted",
                        "forbidden": "No permission",
                        "unauthorized": "Authentication failed",
                        "server_error": "Server error",
                        "network_error": "Network error",
                        "unknown": "Unknown error",
                    }.get(error_type, error_type)

                    message_parts.append(f"❌ {error_name}: {len(emails)} emails")

            result_message = (
                f"Archiving complete ({total_processed} emails):\n"
                + "\n".join(message_parts)
            )

            print(f"🎉 Bulk archiving completed - {result_message}")

            return jsonify({"success": True, "message": result_message})

        elif action == "mark_read":
            # Bulk marking as read (improved version)
            print(
                f"🔍 Bulk marking as read started - Number of selected emails: {len(email_ids)}"
            )

            # Variables for collecting results
            success_count = 0
            failed_emails = []

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ Email {email_id} not found")
                        failed_emails.append(
                            {
                                "id": email_id,
                                "subject": "Unknown",
                                "error": "Email not found",
                                "error_type": "not_found",
                            }
                        )
                        continue

                    gmail_service = GmailService(current_user.id, email_obj.account_id)
                    gmail_service.mark_as_read(email_obj.gmail_id)
                    success_count += 1
                    print(f"✅ Email {email_id} marking as read successful")

                except Exception as e:
                    error_msg = str(e)
                    print(
                        f"❌ Failed to mark email as read (ID: {email_id}): {error_msg}"
                    )

                    # Classify error type
                    error_type = "unknown"
                    if "404" in error_msg and "not found" in error_msg.lower():
                        error_type = "not_found"
                        error_details = "Email already deleted or not found"
                    elif "403" in error_msg:
                        error_type = "forbidden"
                        error_details = "No permission to mark as read"
                    elif "401" in error_msg:
                        error_type = "unauthorized"
                        error_details = "Authentication failed"
                    elif "500" in error_msg:
                        error_type = "server_error"
                        error_details = "Server error occurred"
                    elif (
                        "network" in error_msg.lower()
                        or "connection" in error_msg.lower()
                    ):
                        error_type = "network_error"
                        error_details = "Network connection error"
                    else:
                        error_details = error_msg

                    failed_emails.append(
                        {
                            "id": email_id,
                            "subject": email_obj.subject if email_obj else "Unknown",
                            "error": error_details,
                            "error_type": error_type,
                        }
                    )

            # Group errors by type
            error_groups = {}
            for email in failed_emails:
                error_type = email.get("error_type", "unknown")
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append(email)

            # Generate result message
            total_processed = success_count + len(failed_emails)
            message_parts = []

            # Success count is always displayed (even if 0)
            message_parts.append(f"✅ Success: {success_count} emails")

            # Display only actual errors
            for error_type, emails in error_groups.items():
                if emails:  # Only display actual errors
                    error_name = {
                        "not_found": "Already deleted",
                        "forbidden": "No permission",
                        "unauthorized": "Authentication failed",
                        "server_error": "Server error",
                        "network_error": "Network error",
                        "unknown": "Unknown error",
                    }.get(error_type, error_type)

                    message_parts.append(f"❌ {error_name}: {len(emails)} emails")

            result_message = (
                f"Marking as read complete ({total_processed} emails):\n"
                + "\n".join(message_parts)
            )

            print(f"🎉 Bulk marking as read completed - {result_message}")

            return jsonify({"success": True, "message": result_message})

        elif action == "unsubscribe":
            # Bulk unsubscription (grouped by sender)
            print(
                f"🔍 Bulk unsubscription started - Number of selected emails: {len(email_ids)}"
            )

            # Group selected emails by sender
            sender_groups = {}
            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ Email {email_id} not found")
                        continue

                    sender = email_obj.sender
                    if sender not in sender_groups:
                        sender_groups[sender] = []
                    sender_groups[sender].append(email_obj)

                except Exception as e:
                    print(
                        f"❌ Exception occurred while retrieving email {email_id}: {str(e)}"
                    )
                    continue

            print(
                f"📝 Grouping emails by sender completed - {len(sender_groups)} senders"
            )

            # Variables for collecting results
            successful_senders = []  # List of successful senders
            failed_senders = []  # List of failed senders (sender, reason)
            already_unsubscribed_senders = []  # List of already unsubscribed senders

            # Process each sender group
            for sender, emails in sender_groups.items():
                print(f"📝 Processing sender '{sender}' - {len(emails)} emails")

                # Check if any email has already been unsubscribed
                unsubscribed_count = sum(1 for email in emails if email.is_unsubscribed)
                if unsubscribed_count == len(emails):
                    print(
                        f"⏭️ All emails for sender '{sender}' have already been unsubscribed"
                    )
                    already_unsubscribed_senders.append(sender)
                    continue

                # Select a representative email (first non-unsubscribed email)
                representative_email = None
                for email in emails:
                    if not email.is_unsubscribed:
                        representative_email = email
                        break

                if not representative_email:
                    print(
                        f"⏭️ All emails for sender '{sender}' have already been unsubscribed"
                    )
                    already_unsubscribed_senders.append(sender)
                    continue

                print(
                    f"📝 Selecting representative email for sender '{sender}': {representative_email.subject}"
                )

                try:
                    # Process unsubscription
                    gmail_service = GmailService(
                        current_user.id, representative_email.account_id
                    )
                    print(
                        f"📝 GmailService initialized - Account: {representative_email.account_id}"
                    )

                    result = asyncio.run(
                        gmail_service.process_unsubscribe(representative_email)
                    )
                    print(f"📝 process_unsubscribe result: {result}")

                    if result["success"]:
                        print(f"✅ Successfully unsubscribed sender '{sender}'")
                        successful_senders.append(
                            {
                                "sender": sender,
                                "email_count": len(emails),
                                "bulk_updated_count": result.get(
                                    "bulk_updated_count", 0
                                ),
                                "representative_subject": representative_email.subject,
                            }
                        )
                    else:
                        # Analyze failure reason
                        error_type = result.get("error_type", "unknown")
                        error_details = result.get("error_details", "Unknown error")
                        error_message = result.get("message", "Failed to unsubscribe")

                        if error_type == "already_unsubscribed":
                            already_unsubscribed_senders.append(sender)
                            continue

                        print(
                            f"❌ Failed to unsubscribe sender '{sender}': {error_message}"
                        )
                        failed_senders.append(
                            {
                                "sender": sender,
                                "email_count": len(emails),
                                "error": error_message,
                                "error_type": error_type,
                                "representative_subject": representative_email.subject,
                            }
                        )

                except Exception as e:
                    print(
                        f"❌ Exception occurred while processing sender '{sender}': {str(e)}"
                    )
                    failed_senders.append(
                        {
                            "sender": sender,
                            "email_count": len(emails),
                            "error": f"Processing error: {str(e)}",
                            "error_type": "processing_error",
                            "representative_subject": (
                                representative_email.subject
                                if representative_email
                                else "Unknown"
                            ),
                        }
                    )

            # Generate result message
            message_parts = []
            total_senders = len(sender_groups)

            # Successful senders
            if successful_senders:
                message_parts.append(
                    f"✅ Successful senders ({len(successful_senders)} senders):"
                )
                for sender_info in successful_senders:
                    bulk_info = (
                        f" (Bulk update: {sender_info['bulk_updated_count']} emails)"
                        if sender_info["bulk_updated_count"] > 0
                        else ""
                    )
                    message_parts.append(
                        f"  • {sender_info['sender']} - {sender_info['email_count']} emails{bulk_info}"
                    )

            # Failed senders
            if failed_senders:
                message_parts.append(
                    f"❌ Failed senders ({len(failed_senders)} senders):"
                )
                for sender_info in failed_senders:
                    error_name = {
                        "no_unsubscribe_link": "Unsubscribe link not found",
                        "all_links_failed": "All links failed",
                        "processing_error": "Processing error",
                        "network_error": "Network error",
                        "timeout_error": "Timeout",
                        "unknown": "Unknown error",
                    }.get(sender_info["error_type"], sender_info["error_type"])

                    message_parts.append(
                        f"  • {sender_info['sender']} - {sender_info['email_count']} emails ({error_name}: {sender_info['error']})"
                    )

            # Already unsubscribed senders
            if already_unsubscribed_senders:
                message_parts.append(
                    f"⏭️ Already unsubscribed senders ({len(already_unsubscribed_senders)} senders):"
                )
                for sender in already_unsubscribed_senders:
                    message_parts.append(f"  • {sender}")

            # Generate summary
            total_processed = (
                len(successful_senders)
                + len(failed_senders)
                + len(already_unsubscribed_senders)
            )
            result_message = (
                f"Processing complete ({total_processed}/{total_senders} senders):\n"
                + "\n".join(message_parts)
            )

            print(f"🎉 Bulk unsubscription completed - {result_message}")

            return jsonify({"success": True, "message": result_message})

        else:
            return (
                jsonify({"success": False, "message": "Unsupported action."}),
                400,
            )

    except Exception as e:
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"Error occurred while performing bulk actions: {str(e)}",
                }
            ),
            500,
        )


@email_bp.route("/<int:email_id>/unsubscribe")
@login_required
def unsubscribe_email(email_id):
    """Individual email unsubscription (improved version)"""
    print(f"🔍 Individual unsubscription started - Email ID: {email_id}")
    try:
        # Retrieve email
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first()

        if not email:
            print(f"❌ Email {email_id} not found")
            return (
                jsonify({"success": False, "message": "Email not found."}),
                404,
            )

        print(
            f"📝 Retrieved email {email_id} successfully - Subject: {email.subject}, Sender: {email.sender}"
        )

        # Check if email has already been unsubscribed
        if email.is_unsubscribed:
            print(f"⏭️ Email {email_id} has already been unsubscribed")
            return jsonify(
                {
                    "success": True,
                    "message": f"Email already unsubscribed. (Sender: {email.sender})",
                    "steps": ["Email already unsubscribed"],
                    "email_id": email_id,
                    "sender": email.sender,
                    "subject": email.subject,
                }
            )

        print(f"📝 Starting unsubscription process for email {email_id}")
        # Initialize Gmail service
        gmail_service = GmailService(current_user.id, email.account_id)
        print(f"📝 GmailService initialized - Account: {email.account_id}")

        # Process unsubscription
        result = asyncio.run(gmail_service.process_unsubscribe(email))
        print(f"📝 process_unsubscribe result: {result}")

        # Return result
        if result["success"]:
            print(f"✅ Successfully unsubscribed email {email_id}")

            # Generate success message
            success_message = "Unsubscription successful."

            # Include bulk update information if available
            if "bulk_updated_count" in result and result["bulk_updated_count"] > 0:
                success_message += f" (Unsubscribed from {result['bulk_updated_count']} emails from the same sender)"

            # Include bulk update information in response
            response_data = {
                "success": True,
                "message": success_message,
                "steps": result.get("steps", []),
                "email_id": email_id,
                "sender": email.sender,
                "subject": email.subject,
            }

            # Include bulk update information if available
            if "bulk_updated_count" in result:
                response_data["bulk_updated_count"] = result["bulk_updated_count"]
                response_data["bulk_updated_message"] = result["bulk_updated_message"]
                print(
                    f"📝 Added bulk update information: {result['bulk_updated_count']} emails"
                )

            return jsonify(response_data)
        else:
            error_message = result.get("message", "Failed to unsubscribe")
            error_type = result.get("error_type", "unknown")
            error_details = result.get("error_details", "")

            print(f"❌ Failed to unsubscribe email {email_id}: {error_message}")
            print(f"�� Error type: {error_type}")
            print(f"📝 Error details: {error_details}")

            # Generate error message with user-friendly language
            error_name = {
                "no_unsubscribe_link": "Unsubscribe link not found",
                "all_links_failed": "All links failed",
                "processing_error": "Processing error",
                "network_error": "Network error",
                "timeout_error": "Timeout",
                "captcha_required": "CAPTCHA required",
                "email_confirmation_required": "Email confirmation required",
                "already_unsubscribed": "Already unsubscribed",
                "unknown": "Unknown error",
            }.get(error_type, error_type)

            # Generate detailed error message
            detailed_message = f"Unsubscription failed: {error_name}"
            if error_details:
                detailed_message += f" - {error_details}"
            elif error_message and error_message != "Failed to unsubscribe":
                detailed_message += f" - {error_message}"

            return (
                jsonify(
                    {
                        "success": False,
                        "message": detailed_message,
                        "error_type": error_type,
                        "error_details": error_details,
                        "steps": result.get("steps", []),
                        "email_id": email_id,
                        "sender": email.sender,
                        "subject": email.subject,
                    }
                ),
                400,
            )

    except Exception as e:
        print(f"❌ Exception occurred while processing unsubscription: {str(e)}")

        # Generate error message with user-friendly language
        error_message = str(e)
        error_type = "system_error"

        if "404" in error_message and "not found" in error_message.lower():
            error_type = "not_found"
            detailed_message = (
                "Email not found - It might have been deleted or no longer exists."
            )
        elif "403" in error_message:
            error_type = "forbidden"
            detailed_message = (
                "No permission to unsubscribe - Please check your account permissions."
            )
        elif "401" in error_message:
            error_type = "unauthorized"
            detailed_message = "Authentication failed - Please try logging in again."
        elif "500" in error_message:
            error_type = "server_error"
            detailed_message = "Server error occurred - Please try again later."
        elif (
            "network" in error_message.lower() or "connection" in error_message.lower()
        ):
            error_type = "network_error"
            detailed_message = (
                "Network connection error - Please check your internet connection."
            )
        elif "timeout" in error_message.lower():
            error_type = "timeout_error"
            detailed_message = "Request timed out - Please try again later."
        else:
            detailed_message = f"System error occurred: {error_message}"

        return (
            jsonify(
                {
                    "success": False,
                    "message": detailed_message,
                    "error_type": error_type,
                    "error_details": error_message,
                    "steps": [f"Error: {error_message}"],
                    "email_id": email_id,
                }
            ),
            500,
        )


@email_bp.route("/clear-bulk-result", methods=["POST"])
@login_required
def clear_bulk_result():
    """Clear bulk processing session"""
    session.pop("bulk_unsubscribe_result", None)
    return jsonify({"success": True})


def process_missed_emails_for_account(
    user_id: str, account_id: int, from_date: datetime
) -> dict:
    """Process missed emails for a specific account"""
    try:
        from .gmail_service import GmailService
        from .ai_classifier import AIClassifier

        print(
            f"📧 Processing missed emails started - Account: {account_id}, Start date: {from_date}"
        )

        # Initialize Gmail service and AI classifier
        gmail_service = GmailService(user_id, account_id)
        ai_classifier = AIClassifier()

        # Fetch missed emails from the specified period
        missed_emails = gmail_service.fetch_recent_emails(
            max_results=100, after_date=from_date  # Process up to 100 emails
        )

        if not missed_emails:
            print(f"�� No missed emails - Account: {account_id}")
            return {
                "success": True,
                "processed_count": 0,
                "classified_count": 0,
                "message": "No missed emails.",
            }

        print(f"📥 Found {len(missed_emails)} missed emails - Account: {account_id}")

        # Get user categories (AI classification format)
        category_objects = gmail_service.get_user_categories()
        categories = [
            {"id": cat.id, "name": cat.name, "description": cat.description or ""}
            for cat in category_objects
        ]

        processed_count = 0
        classified_count = 0

        for email_data in missed_emails:
            try:
                # Check if email already exists in DB
                existing_email = Email.query.filter_by(
                    user_id=user_id,
                    account_id=account_id,
                    gmail_id=email_data.get("gmail_id"),
                ).first()

                if existing_email:
                    print(
                        f"⏭️ Skipping already processed email: {email_data.get('subject', 'No subject')}"
                    )
                    continue

                # Classify email
                ai_classifier = AIClassifier()
                category_id, summary = ai_classifier.classify_and_summarize_email(
                    email_data.get("body", ""),
                    email_data.get("subject", ""),
                    email_data.get("sender", ""),
                    categories,
                )

                # Category name 쿼리
                category = Category.query.filter_by(id=category_id).first()
                category_name = category.name if category else "Unclassified"

                # Save email to DB
                email = Email(
                    user_id=user_id,
                    account_id=account_id,
                    gmail_id=email_data.get("gmail_id"),
                    subject=email_data.get("subject", ""),
                    sender=email_data.get("sender", ""),
                    recipient=email_data.get("recipient", ""),
                    date=email_data.get("date"),
                    snippet=email_data.get("snippet", ""),
                    body=email_data.get("body", ""),
                    category_id=category_id,
                    is_read=False,
                    is_archived=False,
                    created_at=datetime.utcnow(),
                )

                db.session.add(email)
                processed_count += 1

                if category_id:
                    classified_count += 1

                print(
                    f"✅ Missed emails processed: {email_data.get('subject', 'No subject')} -> {category_name}"
                )

            except Exception as e:
                print(
                    f"❌ Failed to process missed email: {email_data.get('subject', 'No subject')}, Error: {str(e)}"
                )
                continue

        db.session.commit()

        result = {
            "success": True,
            "processed_count": processed_count,
            "classified_count": classified_count,
            "total_missed": len(missed_emails),
            "message": f"Processed {processed_count} missed emails (classified: {classified_count} emails)",
        }

        print(
            f"🎉 Missed emails processed successfully - Account: {account_id}, Processed: {processed_count}, Classified: {classified_count}"
        )

        return result

    except Exception as e:
        print(f"❌ Failed to process missed emails: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to process missed emails: {str(e)}",
        }


def setup_gmail_webhook(
    account_id: int, topic_name: str, label_ids: list = None
) -> dict:
    """Set up Gmail webhook"""
    try:
        account = UserAccount.query.get(account_id)
        if not account:
            return {"success": False, "error": f"Account {account_id} not found."}
        gmail_service = GmailService(account.user_id, account_id)
        success = gmail_service.setup_gmail_watch(topic_name)
        if success:
            return {
                "success": True,
                "message": f"Webhook set up successfully for account {account.account_email}",
            }
        else:
            return {
                "success": False,
                "error": f"Failed to set up webhook for account {account.account_email}",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def setup_gmail_webhook_with_permissions(
    account_id: int, topic_name: str, label_ids: list = None
) -> dict:
    """Set up Gmail webhook (includes permission check)"""
    try:
        import os

        # 1st step: Check service account permissions and grant them
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            print(
                f"🔧 Checking service account permissions before setting up webhook..."
            )
            service_account_success = grant_service_account_pubsub_permissions(
                project_id
            )
            if not service_account_success:
                print(f"⚠️ Service account permission grant failed, continuing setup.")

        # 2nd step: Existing webhook setup logic
        return setup_gmail_webhook(account_id, topic_name, label_ids)

    except Exception as e:
        print(f"❌ Error setting up webhook: {str(e)}")
        return {"success": False, "error": str(e)}


def setup_webhook_for_account(user_id: str, account_id: int) -> bool:
    """Set up webhook for an account"""
    try:
        # Get account information
        account = UserAccount.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            print(f"❌ Account {account_id} not found.")
            return False

        # Set topic name
        topic_name = os.getenv("GMAIL_WEBHOOK_TOPIC", "gmail-notifications")
        full_topic_name = (
            f"projects/{os.getenv('GOOGLE_CLOUD_PROJECT')}/topics/{topic_name}"
        )

        print(
            f"🔧 Starting webhook setup - Account: {account_id}, Topic: {full_topic_name}"
        )

        # Make Gmail API request
        print(f"📤 Making Gmail API request - Account: {account_id}")
        print(f"    Topic: {full_topic_name}")
        print(f"    Label: {['INBOX']}")

        # Set webhook with permission check
        result = setup_gmail_webhook_with_permissions(
            account_id, full_topic_name, ["INBOX"]
        )

        if result.get("success"):
            print(f"✅ Webhook set up successfully for account {account_id}")
            return True
        else:
            print(f"❌ Failed to set up webhook for account {account_id}")
            print(f"    Error type: {type(result.get('error')).__name__}")
            print(f"    Error message: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Error setting up webhook: {str(e)}")
        return False


@email_bp.route("/setup-webhook", methods=["POST"])
@login_required
def setup_webhook():
    """Set up Gmail webhook"""
    try:
        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        success_count = 0
        failed_accounts = []

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)

                # Stop webhook and reset it
                gmail_service.stop_gmail_watch()

                # Set webhook (topic_name is fetched from environment variables or default value)
                topic_name = os.environ.get(
                    "GMAIL_WEBHOOK_TOPIC",
                    "projects/cleanbox-466314/topics/gmail-notifications",
                )

                if gmail_service.setup_gmail_watch(topic_name):
                    success_count += 1
                else:
                    failed_accounts.append(account.account_email)

            except Exception as e:
                print(
                    f"Failed to set up webhook for account {account.account_email}: {str(e)}"
                )
                failed_accounts.append(account.account_email)

        if success_count > 0:
            message = f"Webhook set up successfully: {success_count} accounts"
            if failed_accounts:
                message += f", Failed: {', '.join(failed_accounts)}"

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "success_count": success_count,
                    "failed_accounts": failed_accounts,
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"Failed to set up webhook for all accounts: {', '.join(failed_accounts)}",
                }
            )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error setting up webhook: {str(e)}"}
        )


@email_bp.route("/webhook-status")
@login_required
def webhook_status():
    """Check webhook status (includes automatic recovery)"""
    try:
        # First, check the webhook status of the user and automatically recover
        repair_result = check_and_repair_webhooks_for_user(current_user.id)

        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        webhook_statuses = []
        total_accounts = len(accounts)
        healthy_accounts = 0

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)
                status = gmail_service.get_webhook_status()

                webhook_statuses.append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        **status,
                    }
                )

                if status["status"] == "healthy":
                    healthy_accounts += 1

            except Exception as e:
                webhook_statuses.append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "is_active": False,
                        "status": "error",
                        "message": f"Failed to retrieve status: {str(e)}",
                    }
                )

        # Add repair message
        repair_message = ""
        if repair_result["success"]:
            if repair_result["repaired_count"] > 0:
                repair_message = f"Automatic recovery completed: {repair_result['repaired_count']} accounts"
            elif repair_result["healthy_count"] > 0:
                repair_message = f"All webhooks are in good condition ({repair_result['healthy_count']} accounts)"

        return jsonify(
            {
                "success": True,
                "total_accounts": total_accounts,
                "healthy_accounts": healthy_accounts,
                "webhook_statuses": webhook_statuses,
                "repair_result": repair_result,
                "repair_message": repair_message,
            }
        )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Failed to retrieve webhook status: {str(e)}",
            }
        )


@email_bp.route("/auto-renew-webhook", methods=["POST"])
@login_required
def auto_renew_webhook():
    """Automatically renew expired webhook (automatic renewal of expired webhook)"""
    try:
        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        renewed_count = 0
        failed_count = 0
        account_results = []

        for account in accounts:
            try:
                print(
                    f"🔄 Automatically renewing webhook - Account: {account.account_email}"
                )

                # Check webhook status
                webhook_status = WebhookStatus.query.filter_by(
                    user_id=current_user.id, account_id=account.id, is_active=True
                ).first()

                # If webhook is not set up or expired, set it up again
                if not webhook_status or webhook_status.is_expired:
                    success = setup_webhook_for_account(current_user.id, account.id)

                    if success:
                        renewed_count += 1
                        account_results.append(
                            {
                                "account": account.account_email,
                                "status": "renewed",
                                "message": "Webhook reset successfully",
                            }
                        )
                    else:
                        failed_count += 1
                        account_results.append(
                            {
                                "account": account.account_email,
                                "status": "failed",
                                "message": "Failed to reset webhook",
                            }
                        )
                else:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "healthy",
                            "message": "Webhook is in good condition",
                        }
                    )

            except Exception as e:
                print(
                    f"Failed to reset webhook for account {account.account_email}: {str(e)}"
                )
                failed_count += 1
                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "error",
                        "message": str(e),
                    }
                )

        # Generate result message
        if renewed_count > 0:
            message = f"{renewed_count} accounts' webhooks have been reset."
            if failed_count > 0:
                message += f" {failed_count} accounts failed."
        elif failed_count > 0:
            message = f"{failed_count} accounts failed to reset webhook."
        else:
            message = "All webhooks are in good condition."

        return jsonify(
            {
                "success": True,
                "message": message,
                "renewed_count": renewed_count,
                "failed_count": failed_count,
                "account_results": account_results,
            }
        )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Error automatically renewing webhook: {str(e)}",
            }
        )


def check_and_repair_webhooks_for_user(user_id: str) -> dict:
    """Check user's webhook status and automatically recover expired webhooks (includes handling missed emails)"""
    try:
        from datetime import datetime, timedelta

        print(f"🔍 Checking user's webhook status: {user_id}")

        # Get all active accounts of the user
        accounts = UserAccount.query.filter_by(user_id=user_id, is_active=True).all()

        if not accounts:
            print(f"⚠️ User {user_id} has no active accounts")
            return {"success": False, "message": "No active accounts."}

        repaired_count = 0
        failed_count = 0
        healthy_count = 0
        missed_emails_processed = 0
        missed_emails_classified = 0

        for account in accounts:
            try:
                # Check webhook status
                webhook_status = WebhookStatus.query.filter_by(
                    user_id=user_id, account_id=account.id, is_active=True
                ).first()

                # If webhook is not set up or expired, recover it
                if not webhook_status or webhook_status.is_expired:
                    print(
                        f"🔄 Trying to recover webhook - Account: {account.account_email}"
                    )

                    success = setup_webhook_for_account(user_id, account.id)

                    if success:
                        repaired_count += 1
                        print(
                            f"✅ Webhook recovery successful - Account: {account.account_email}"
                        )

                        # Check missed emails processing result (already handled in setup_webhook_for_account)
                        # Here, we just log the result
                        print(
                            f"📧 Missed emails processed - Account: {account.account_email}"
                        )
                    else:
                        failed_count += 1
                        print(
                            f"❌ Failed to recover webhook - Account: {account.account_email}"
                        )
                else:
                    # Check if it's time to renew (within 48 hours)
                    expiry_threshold = datetime.utcnow() + timedelta(hours=48)
                    if webhook_status.expires_at <= expiry_threshold:
                        print(
                            f"🔄 Preventive renewal - Account: {account.account_email}"
                        )

                        success = setup_webhook_for_account(user_id, account.id)

                        if success:
                            repaired_count += 1
                            print(
                                f"✅ Preventive renewal successful - Account: {account.account_email}"
                            )
                        else:
                            failed_count += 1
                            print(
                                f"❌ Failed to preventively renew webhook - Account: {account.account_email}"
                            )
                    else:
                        healthy_count += 1
                        print(
                            f"✅ Webhook is in good condition - Account: {account.account_email}"
                        )

            except Exception as e:
                failed_count += 1
                print(
                    f"❌ Error occurred while recovering webhook - Account: {account.account_email}, Error: {str(e)}"
                )

        result = {
            "success": True,
            "repaired_count": repaired_count,
            "failed_count": failed_count,
            "healthy_count": healthy_count,
            "total_accounts": len(accounts),
            "missed_emails_processed": missed_emails_processed,
            "missed_emails_classified": missed_emails_classified,
        }

        print(
            f"🎉 User's webhook status check completed - Recovered: {repaired_count}, Failed: {failed_count}, Healthy: {healthy_count}"
        )

        return result

    except Exception as e:
        print(f"❌ Error checking user's webhook status: {str(e)}")
        return {"success": False, "error": str(e)}


def monitor_and_renew_webhooks():
    """Monitor all users' webhook status and automatically renew expired webhooks + automatically handle missed emails"""
    try:
        from datetime import datetime, timedelta
        from ..models import User

        print("🔄 Starting webhook monitoring...")

        # Get webhooks expiring within 48 hours (earlier preventive renewal)
        expiry_threshold = datetime.utcnow() + timedelta(hours=48)

        expiring_webhooks = WebhookStatus.query.filter(
            WebhookStatus.is_active == True,
            WebhookStatus.expires_at <= expiry_threshold,
        ).all()

        renewed_count = 0
        failed_count = 0
        missed_email_total = 0
        missed_email_results = []

        for webhook in expiring_webhooks:
            try:
                print(
                    f"🔄 Automatically renewing webhook - User: {webhook.user_id}, Account: {webhook.account_id}"
                )

                success = setup_webhook_for_account(webhook.user_id, webhook.account_id)

                if success:
                    renewed_count += 1
                    print(
                        f"✅ Webhook renewal successful - User: {webhook.user_id}, Account: {webhook.account_id}"
                    )

                    # Missed email processing criteria: after expiration, if none, use service join date
                    from_date = None
                    if webhook.expires_at:
                        from_date = webhook.expires_at
                    else:
                        user = User.query.get(webhook.user_id)
                        from_date = (
                            user.first_service_access
                            if user
                            else datetime.utcnow() - timedelta(days=7)
                        )

                    missed_result = process_missed_emails_for_account(
                        webhook.user_id, webhook.account_id, from_date
                    )
                    missed_email_total += missed_result.get("processed_count", 0)
                    missed_email_results.append(
                        {
                            "user_id": webhook.user_id,
                            "account_id": webhook.account_id,
                            "missed_result": missed_result,
                        }
                    )
                else:
                    failed_count += 1
                    print(
                        f"❌ Failed to renew webhook - User: {webhook.user_id}, Account: {webhook.account_id}"
                    )

            except Exception as e:
                failed_count += 1
                print(
                    f"❌ Error occurred while renewing webhook - User: {webhook.user_id}, Account: {webhook.account_id}, Error: {str(e)}"
                )

        print(
            f"🎉 Webhook monitoring completed - Renewed: {renewed_count} webhooks, Failed: {failed_count}, Missed email processing: {missed_email_total} emails"
        )

        return {
            "success": True,
            "renewed_count": renewed_count,
            "failed_count": failed_count,
            "total_checked": len(expiring_webhooks),
            "missed_email_total": missed_email_total,
            "missed_email_results": missed_email_results,
        }

    except Exception as e:
        print(f"❌ Error occurred while monitoring webhooks: {str(e)}")
        return {"success": False, "error": str(e)}


@email_bp.route("/monitor-webhooks", methods=["POST"])
@login_required
def trigger_webhook_monitoring():
    """Manual trigger for webhook monitoring (admin use)"""
    try:
        result = monitor_and_renew_webhooks()

        if result["success"]:
            message = f"Webhook monitoring completed - Renewed: {result['renewed_count']} webhooks, Failed: {result['failed_count']}"
            return jsonify({"success": True, "message": message, "result": result})
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"Failed to monitor webhooks: {result['error']}",
                }
            )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Error occurred while monitoring webhooks: {str(e)}",
            }
        )


@email_bp.route("/process-missed-emails", methods=["POST"])
@login_required
def process_missed_emails():
    """Manual processing of missed emails"""
    try:
        from datetime import datetime, timedelta

        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        total_processed = 0
        total_classified = 0
        account_results = []

        for account in accounts:
            try:
                # Check webhook status
                webhook_status = WebhookStatus.query.filter_by(
                    user_id=current_user.id, account_id=account.id, is_active=True
                ).first()

                # Calculate missed period
                missed_period_start = None
                if webhook_status and webhook_status.is_expired:
                    missed_period_start = webhook_status.expires_at
                else:
                    # If webhook is not set up or not expired, process from 7 days ago
                    missed_period_start = datetime.utcnow() - timedelta(days=7)

                print(
                    f"📧 Processing missed emails - Account: {account.account_email}, Start date: {missed_period_start}"
                )

                # Process missed emails
                result = process_missed_emails_for_account(
                    current_user.id, account.id, missed_period_start
                )

                if result["success"]:
                    total_processed += result["processed_count"]
                    total_classified += result["classified_count"]

                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "success",
                            "processed": result["processed_count"],
                            "classified": result["classified_count"],
                            "message": result["message"],
                        }
                    )
                else:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "failed",
                            "message": result["message"],
                        }
                    )

            except Exception as e:
                print(
                    f"Failed to process missed emails for account {account.account_email}: {str(e)}"
                )
                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "error",
                        "message": str(e),
                    }
                )

        # Generate result message
        if total_processed > 0:
            message = f"Processed {total_processed} missed emails (classified: {total_classified} emails)"
        else:
            message = "No missed emails to process."

        return jsonify(
            {
                "success": True,
                "message": message,
                "total_processed": total_processed,
                "total_classified": total_classified,
                "account_results": account_results,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error processing missed emails: {str(e)}"}
        )


@email_bp.route("/scheduler-status")
@login_required
def scheduler_status():
    """Check scheduler status"""
    try:
        # Check scheduler job status
        jobs = get_scheduler().get_jobs()
        webhook_job = None

        for job in jobs:
            if job.id == "webhook_monitor":
                webhook_job = job
                break

        if webhook_job:
            status = {
                "scheduler_running": get_scheduler().running,
                "webhook_job_active": webhook_job.next_run_time is not None,
                "next_run_time": (
                    webhook_job.next_run_time.isoformat()
                    if webhook_job.next_run_time
                    else None
                ),
                "job_interval": str(webhook_job.trigger),
            }
        else:
            status = {
                "scheduler_running": get_scheduler().running,
                "webhook_job_active": False,
                "next_run_time": None,
                "job_interval": "Not found",
            }

        return jsonify({"success": True, "status": status})

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Failed to retrieve scheduler status: {str(e)}",
            }
        )


@email_bp.route("/trigger-scheduled-monitoring", methods=["POST"])
@login_required
def trigger_scheduled_monitoring():
    """Manual trigger for scheduled webhook monitoring"""
    try:
        print("�� Manual trigger for scheduled webhook monitoring...")

        # Directly call the scheduled function
        get_scheduled_webhook_monitoring()

        return jsonify(
            {
                "success": True,
                "message": "Scheduled webhook monitoring has been executed.",
            }
        )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Failed to execute scheduled webhook monitoring: {str(e)}",
            }
        )


def get_user_emails(user_id, limit=50):
    """Helper function to retrieve user's emails"""
    return (
        Email.query.filter_by(user_id=user_id)
        .order_by(Email.created_at.desc())
        .limit(limit)
        .all()
    )


@email_bp.route("/debug-info")
@login_required
def debug_info():
    """Check debug information"""
    try:
        # User information
        user_info = {
            "user_id": current_user.id,
            "email": current_user.email,
            "first_service_access": (
                current_user.first_service_access.isoformat()
                if current_user.first_service_access
                else None
            ),
            "created_at": (
                current_user.created_at.isoformat() if current_user.created_at else None
            ),
        }

        # Account information
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        account_info = []
        for account in accounts:
            # Check recent emails for each account
            gmail_service = GmailService(current_user.id, account.id)

            try:
                # Try to retrieve recent emails
                recent_emails = gmail_service.fetch_recent_emails(max_results=5)

                account_data = {
                    "account_id": account.id,
                    "account_email": account.account_email,
                    "account_name": account.account_name,
                    "is_primary": account.is_primary,
                    "is_active": account.is_active,
                    "recent_emails_count": len(recent_emails) if recent_emails else 0,
                    "recent_emails": [],
                }

                # Detailed information about recent emails
                if recent_emails:
                    for email in recent_emails[:3]:  # Only up to 3 emails
                        account_data["recent_emails"].append(
                            {
                                "gmail_id": email.get("gmail_id"),
                                "subject": email.get("subject"),
                                "sender": email.get("sender"),
                                "date": email.get("date"),
                                "snippet": (
                                    email.get("snippet", "")[:100] + "..."
                                    if email.get("snippet")
                                    else ""
                                ),
                            }
                        )

                account_info.append(account_data)

            except Exception as e:
                account_data = {
                    "account_id": account.id,
                    "account_email": account.account_email,
                    "account_name": account.account_name,
                    "is_primary": account.is_primary,
                    "is_active": account.is_active,
                    "error": str(e),
                }
                account_info.append(account_data)

        return jsonify(
            {
                "success": True,
                "user_info": user_info,
                "accounts": account_info,
                "current_time": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Failed to retrieve debug information: {str(e)}",
            }
        )


@email_bp.route("/debug-webhook-setup")
@login_required
def debug_webhook_setup():
    """Check debug information about webhook setup"""
    try:
        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        debug_info = {
            "environment": {
                "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT"),
                "topic_name": os.environ.get("GMAIL_WEBHOOK_TOPIC"),
                "webhook_url": "https://cleanbox-app-1.onrender.com/webhook/gmail",
            },
            "accounts": [],
        }

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)

                # Check webhook status
                webhook_status = gmail_service.get_webhook_status()

                # Test Gmail API connection
                try:
                    # Simple test call to Gmail API
                    profile = (
                        gmail_service.service.users().getProfile(userId="me").execute()
                    )
                    gmail_connection = {
                        "success": True,
                        "email": profile.get("emailAddress"),
                        "messagesTotal": profile.get("messagesTotal"),
                        "threadsTotal": profile.get("threadsTotal"),
                    }
                except Exception as e:
                    gmail_connection = {"success": False, "error": str(e)}

                account_info = {
                    "account_email": account.account_email,
                    "account_name": account.account_name,
                    "is_primary": account.is_primary,
                    "webhook_status": webhook_status,
                    "gmail_connection": gmail_connection,
                }

                debug_info["accounts"].append(account_info)

            except Exception as e:
                debug_info["accounts"].append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "error": str(e),
                    }
                )

        return jsonify({"success": True, "debug_info": debug_info})

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Failed to retrieve debug information: {str(e)}",
            }
        )


@email_bp.route("/check-oauth-scopes")
@login_required
def check_oauth_scopes():
    """Check OAuth scopes"""
    try:
        # Get all active accounts
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "No connected accounts."})

        scope_info = {
            "required_scopes": [
                "https://mail.google.com/",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
            "accounts": [],
        }

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)

                # Test Gmail API connection
                try:
                    profile = (
                        gmail_service.service.users().getProfile(userId="me").execute()
                    )

                    # Check token information (if available)
                    try:
                        # Check scope information of the current token
                        token_info = (
                            gmail_service.service.users()
                            .getProfile(userId="me")
                            .execute()
                        )
                        scopes_available = True
                    except:
                        scopes_available = False

                    account_info = {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "gmail_connected": True,
                        "email_address": profile.get("emailAddress"),
                        "messages_total": profile.get("messagesTotal"),
                        "threads_total": profile.get("threadsTotal"),
                        "scopes_available": scopes_available,
                    }

                except Exception as e:
                    account_info = {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "gmail_connected": False,
                        "error": str(e),
                    }

                scope_info["accounts"].append(account_info)

            except Exception as e:
                scope_info["accounts"].append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "error": str(e),
                    }
                )

        return jsonify({"success": True, "scope_info": scope_info})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Failed to check OAuth scopes: {str(e)}"}
        )


@email_bp.route("/ai-analysis-stats")
@login_required
def ai_analysis_statistics():
    """AI analysis statistics"""
    try:
        # Number of emails with AI analysis completed (emails with summary)
        analyzed_count = (
            Email.query.filter_by(user_id=current_user.id)
            .filter(Email.summary.isnot(None))
            .count()
        )

        # Total number of emails
        total_count = Email.query.filter_by(user_id=current_user.id).count()

        # AI analysis completion rate
        analysis_rate = (analyzed_count / total_count * 100) if total_count > 0 else 0

        # Category-wise AI analysis statistics
        category_stats = (
            db.session.query(Category.name, db.func.count(Email.id).label("count"))
            .join(Email, Category.id == Email.category_id)
            .filter(
                Email.user_id == current_user.id,
                Email.summary.isnot(None),  # Only emails with AI analysis completed
            )
            .group_by(Category.id, Category.name)
            .all()
        )

        # Number of archived AI analysis emails
        archived_analyzed_count = (
            Email.query.filter_by(user_id=current_user.id, is_archived=True)
            .filter(Email.summary.isnot(None))
            .count()
        )

        stats = {
            "analyzed_count": analyzed_count,
            "total_count": total_count,
            "analysis_rate": round(analysis_rate, 2),
            "archived_analyzed_count": archived_analyzed_count,
            "category_stats": [
                {"category_name": stat.name, "count": stat.count}
                for stat in category_stats
            ],
        }

        return jsonify({"success": True, "statistics": stats})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error retrieving statistics: {str(e)}"}
        )


@email_bp.route("/ai-analyzed-emails")
@login_required
def get_ai_analyzed_emails():
    """List of emails with AI analysis completed"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        # Get emails with AI analysis completed (emails with summary)
        emails = (
            Email.query.filter_by(user_id=current_user.id)
            .filter(Email.summary.isnot(None))
            .order_by(Email.updated_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        # Add category information
        for email in emails.items:
            if email.category_id:
                email.category_info = Category.query.filter_by(
                    id=email.category_id, user_id=current_user.id
                ).first()

        result = {
            "emails": [
                {
                    "id": email.id,
                    "subject": email.subject,
                    "sender": email.sender,
                    "summary": email.summary,
                    "category_name": (
                        email.category_info.name
                        if hasattr(email, "category_info") and email.category_info
                        else "Unclassified"
                    ),
                    "is_archived": email.is_archived,
                    "is_read": email.is_read,
                    "updated_at": (
                        email.updated_at.isoformat() if email.updated_at else None
                    ),
                }
                for email in emails.items
            ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": emails.total,
                "pages": emails.pages,
            },
        }

        return jsonify({"success": True, "data": result})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error retrieving emails: {str(e)}"}
        )


@email_bp.route("/api/check-new-emails", methods=["GET"])
@login_required
def check_new_emails():
    """Check if new emails exist (comparison based on email id)"""
    try:
        # Get the last seen email id from the client
        last_seen_email_id = request.args.get("last_seen_email_id", type=int)

        # Generate cache key
        cache_key = f"max_email_id_{current_user.id}"

        # Use cached max email id if available
        cached_max_id = cache.get(cache_key)

        if cached_max_id is not None:
            # Compare cached max email id with the client's last seen email id
            has_new_emails = (
                last_seen_email_id is None or cached_max_id > last_seen_email_id
            )

            result = {
                "has_new_emails": has_new_emails,
                "max_email_id": cached_max_id,
                "last_seen_email_id": last_seen_email_id,
                "new_count": (
                    cached_max_id - (last_seen_email_id or 0) if has_new_emails else 0
                ),
                "last_check": datetime.utcnow().isoformat(),
                "cached_until": (datetime.utcnow() + timedelta(seconds=10)).isoformat(),
            }

            return jsonify(result)

        # If cache is empty, calculate max email id from DB
        active_accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not active_accounts:
            return jsonify(
                {
                    "has_new_emails": False,
                    "max_email_id": 0,
                    "last_seen_email_id": last_seen_email_id,
                    "new_count": 0,
                    "last_check": datetime.utcnow().isoformat(),
                }
            )

        # Find max email id across all user's accounts
        max_email_id = 0
        for account in active_accounts:
            max_id_for_account = (
                db.session.query(db.func.max(Email.id))
                .filter(
                    Email.user_id == current_user.id, Email.account_id == account.id
                )
                .scalar()
            )

            if max_id_for_account and max_id_for_account > max_email_id:
                max_email_id = max_id_for_account

        # Cache result (10 seconds)
        cache.set(cache_key, max_email_id, timeout=10)

        # Check for new emails
        has_new_emails = last_seen_email_id is None or max_email_id > last_seen_email_id

        result = {
            "has_new_emails": has_new_emails,
            "max_email_id": max_email_id,
            "last_seen_email_id": last_seen_email_id,
            "new_count": (
                max_email_id - (last_seen_email_id or 0) if has_new_emails else 0
            ),
            "last_check": datetime.utcnow().isoformat(),
            "cached_until": (datetime.utcnow() + timedelta(seconds=10)).isoformat(),
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error checking for new emails: {e}")
        return (
            jsonify({"has_new_emails": False, "error": "An error occurred"}),
            500,
        )


@email_bp.route("/api/update-last-seen-email", methods=["POST"])
@login_required
def update_last_seen_email():
    """Update the last seen email id for the client"""
    try:
        data = request.get_json()
        last_seen_email_id = data.get("last_seen_email_id", type=int)

        if last_seen_email_id is None:
            return (
                jsonify(
                    {"success": False, "message": "last_seen_email_id is required"}
                ),
                400,
            )

        # Generate cache key
        cache_key = f"last_seen_email_id_{current_user.id}"

        # Save the client's last seen email id in cache
        cache.set(cache_key, last_seen_email_id, timeout=3600)  # Cache for 1 hour

        logger.info(
            f"User {current_user.id}'s last seen email id updated: {last_seen_email_id}"
        )

        return jsonify(
            {
                "success": True,
                "last_seen_email_id": last_seen_email_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error updating last seen email id: {e}")
        return (
            jsonify({"success": False, "message": "An error occurred"}),
            500,
        )
