# Standard library imports
import base64
import email
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Third-party imports
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Local imports
from ..models import Email, Category, UserAccount, db
from ..auth.routes import (
    get_user_credentials,
    get_current_account_id,
    refresh_user_token,
)
from .advanced_unsubscribe import AdvancedUnsubscribeService


class GmailService:
    """Gmail API Service Class"""

    def __init__(self, user_id: str, account_id: Optional[int] = None):
        self.user_id = user_id
        self.account_id = account_id or get_current_account_id()

        if not self.account_id:
            raise Exception("Active account not found.")

        self.service = None
        self.advanced_unsubscribe = AdvancedUnsubscribeService()
        self._initialize_service()

    def _initialize_service(self):
        """Initialize Gmail API service"""
        try:
            credentials_data = get_user_credentials(self.user_id, self.account_id)
            if not credentials_data:
                raise Exception("User credentials not found.")

            # Convert dictionary to Google OAuth credentials object
            from google.oauth2.credentials import Credentials

            credentials = Credentials(
                token=credentials_data.get("token"),
                refresh_token=credentials_data.get("refresh_token"),
                token_uri=credentials_data.get("token_uri"),
                client_id=credentials_data.get("client_id"),
                client_secret=credentials_data.get("client_secret"),
                scopes=credentials_data.get("scopes", []),
                expiry=credentials_data.get("expiry"),
            )

            # Check if token is expired and try to refresh
            if credentials.expired and credentials.refresh_token:
                print(
                    f"🔄 Token expired. Attempting to refresh: user_id={self.user_id}, account_id={self.account_id}"
                )

                from google.auth.transport.requests import Request

                credentials.refresh(Request())

                # Save refreshed token
                refresh_success = refresh_user_token(self.user_id, self.account_id)

                if not refresh_success:
                    raise Exception("Token refresh failed. Please log in again.")

            # Build Google API client
            self.service = build("gmail", "v1", credentials=credentials)
        except Exception as e:
            raise Exception(f"Failed to initialize Gmail API service: {str(e)}")

    def fetch_emails_after_date(self, after_date: datetime) -> List[Dict]:
        """Get emails after a specific date (only inbox)"""
        try:
            # Convert date to RFC 3339 format
            after_date_str = after_date.strftime("%Y/%m/%d")

            # Get email list from Gmail API for emails after a specific date (only inbox)
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=100,  # Max 100
                    q=f"after:{after_date_str} is:inbox",  # After specific date + only inbox
                )
                .execute()
            )

            messages = results.get("messages", [])

            emails = []
            for message in messages:
                email_data = self._get_email_details(message["id"])
                if email_data:
                    # Date filtering (Gmail API's after query might not be accurate)
                    email_date = self._parse_date(email_data.get("date"))
                    if email_date and email_date >= after_date:
                        # Check if inbox label exists
                        labels = email_data.get("labels", [])
                        if "INBOX" in labels:
                            emails.append(email_data)

            return emails

        except HttpError as error:
            raise Exception(f"Gmail API error: {error}")

    def fetch_recent_emails(
        self,
        max_results: int = 20,
        offset: int = 0,
        after_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get emails after subscription date (pagination supported)"""
        try:
            # Query to get emails after subscription date
            if after_date:
                # Get only emails after subscription date
                after_date_str = after_date.strftime("%Y/%m/%d")
                query = f"after:{after_date_str} is:inbox"
                print(f"🔍 Gmail API call - Account: {self.account_id}, Query: {query}")
            else:
                # Default: last 24 hours (backward compatibility)
                yesterday = datetime.utcnow() - timedelta(hours=24)
                after_date_str = yesterday.strftime("%Y/%m/%d")
                query = f"after:{after_date_str} is:inbox"
                print(
                    f"🔍 Gmail API call - Account: {self.account_id}, Query: {query} (default)"
                )

            # Get email list from Gmail API
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=max_results,
                    q=query,  # Emails received in the inbox after subscription date
                )
                .execute()
            )

            messages = results.get("messages", [])
            print(
                f"📧 Gmail API response - Account: {self.account_id}, Message count: {len(messages)}"
            )

            # Apply offset (Gmail API handles pagination internally)
            if offset > 0 and "nextPageToken" in results:
                # Process offset using nextPageToken
                for _ in range(offset // max_results):
                    if "nextPageToken" not in results:
                        break
                    results = (
                        self.service.users()
                        .messages()
                        .list(
                            userId="me",
                            maxResults=max_results,
                            pageToken=results["nextPageToken"],
                            q=query,
                        )
                        .execute()
                    )
                    messages = results.get("messages", [])

            emails = []
            for i, message in enumerate(messages):
                print(
                    f"📨 Processing email ({i+1}/{len(messages)}) - ID: {message['id']}"
                )
                email_data = self._get_email_details(message["id"])
                if email_data:
                    emails.append(email_data)
                    print(
                        f"✅ Email data extraction complete - Subject: {email_data.get('subject', 'No subject')}"
                    )
                else:
                    print(f"❌ Failed to get email details - ID: {message['id']}")

            print(
                f"🎉 Email processing complete - Account: {self.account_id}, Total {len(emails)} processed"
            )
            return emails

        except HttpError as error:
            print(f"❌ Gmail API error - Account: {self.account_id}, Error: {error}")
            raise Exception(f"Gmail API error: {error}")
        except Exception as e:
            print(f"❌ Unexpected error - Account: {self.account_id}, Error: {e}")
            raise Exception(f"Failed to fetch emails: {str(e)}")

    def _get_email_details(self, message_id: str) -> Optional[Dict]:
        """Get email details"""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            headers = message["payload"]["headers"]
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"), "No subject"
            )
            sender = next(
                (h["value"] for h in headers if h["name"] == "From"),
                "Unknown sender",
            )
            date = next((h["value"] for h in headers if h["name"] == "Date"), None)

            # Extract email body
            body = self._extract_email_body(message["payload"])

            # Extract header information (for unsubscribe)
            email_headers = {}
            for header in headers:
                email_headers[header["name"]] = header["value"]

            return {
                "gmail_id": message_id,
                "thread_id": message.get("threadId"),
                "subject": subject,
                "sender": sender,
                "body": body,
                "date": date,
                "snippet": message.get("snippet", ""),
                "labels": message.get("labelIds", []),
                "headers": email_headers,
            }

        except HttpError as error:
            print(f"Failed to get email details (ID: {message_id}): {error}")
            return None

    def _extract_email_body(self, payload: Dict) -> str:
        """Extract email body"""
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8")

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if part["body"].get("data"):
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8"
                        )
                elif part["mimeType"] == "text/html":
                    if part["body"].get("data"):
                        return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                            "utf-8"
                        )

        return "Could not extract body."

    def save_email_to_db(self, email_data: Dict) -> Email:
        """Save email to DB (improved version)"""
        try:
            # Check if email is already saved (per account)
            existing_email = Email.query.filter_by(
                user_id=self.user_id,
                account_id=self.account_id,
                gmail_id=email_data["gmail_id"],
            ).first()

            if existing_email:
                return existing_email

            # Extract sender information
            sender = email_data.get("sender") or "Unknown sender"

            # Create new email (with default values)
            email_obj = Email(
                user_id=self.user_id,
                account_id=self.account_id,
                gmail_id=email_data["gmail_id"],
                thread_id=email_data.get("thread_id"),
                subject=email_data.get("subject") or "No subject",
                sender=sender,
                content=email_data.get("body") or "No body",
                summary=email_data.get("snippet", ""),
                received_at=self._parse_date(email_data.get("date")),
                is_read=False,
                is_archived=False,
                is_unsubscribed=False,  # New emails are not automatically unsubscribed by default
            )

            db.session.add(email_obj)
            db.session.commit()

            return email_obj

        except Exception as e:
            db.session.rollback()
            raise Exception(f"Failed to save email to DB: {str(e)}")

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Convert date string to datetime (timezone-naive)"""
        if not date_str:
            return None

        try:
            # Parse RFC 2822 format
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            # Remove timezone information to return timezone-naive datetime
            if parsed_date.tzinfo:
                parsed_date = parsed_date.replace(tzinfo=None)
            return parsed_date
        except:
            return datetime.utcnow()

    def archive_email(self, gmail_id: str) -> bool:
        """Archive email"""
        try:
            # Archive in Gmail
            self.service.users().messages().modify(
                userId="me", id=gmail_id, body={"removeLabelIds": ["INBOX"]}
            ).execute()

            # Update archived status in DB
            email_obj = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, gmail_id=gmail_id
            ).first()

            if email_obj:
                email_obj.is_archived = True
                email_obj.updated_at = datetime.utcnow()
                db.session.commit()

            return True

        except HttpError as error:
            raise Exception(f"Failed to archive email: {error}")

    def mark_as_read(self, gmail_id: str) -> bool:
        """Mark email as read"""
        try:
            # Mark as read in Gmail
            self.service.users().messages().modify(
                userId="me", id=gmail_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()

            # Update read status in DB
            email_obj = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, gmail_id=gmail_id
            ).first()

            if email_obj:
                email_obj.is_read = True
                email_obj.updated_at = datetime.utcnow()
                db.session.commit()

            return True

        except HttpError as error:
            raise Exception(f"Failed to mark email as read: {error}")

    def get_user_categories(self) -> List[Category]:
        """Get user's category list"""
        return Category.query.filter_by(user_id=self.user_id, is_active=True).all()

    def update_email_category(self, gmail_id: str, category_id: Optional[int]) -> bool:
        """Update email category"""
        try:
            email_obj = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, gmail_id=gmail_id
            ).first()

            if email_obj:
                email_obj.category_id = category_id
                email_obj.updated_at = datetime.utcnow()
                db.session.commit()
                return True

            return False

        except Exception as e:
            db.session.rollback()
            raise Exception(f"Failed to update email category: {str(e)}")

    def get_email_statistics(self) -> Dict:
        """Get email statistics"""
        try:
            # Email statistics for the current account
            total_emails = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id
            ).count()
            unread_emails = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_read=False
            ).count()
            archived_emails = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_archived=True
            ).count()

            # Email count by category
            categories = self.get_user_categories()
            category_stats = {}

            for category in categories:
                count = Email.query.filter_by(
                    user_id=self.user_id,
                    account_id=self.account_id,
                    category_id=category.id,
                ).count()
                category_stats[category.name] = count

            # Account information
            account = UserAccount.query.get(self.account_id)
            account_info = {
                "email": account.account_email if account else "Unknown",
                "name": account.account_name if account else "",
                "is_primary": account.is_primary if account else False,
            }

            return {
                "total": total_emails,
                "unread": unread_emails,
                "archived": archived_emails,
                "categories": category_stats,
                "account": account_info,
            }

        except Exception as e:
            raise Exception(f"Failed to get email statistics: {str(e)}")

    def delete_email(self, gmail_id: str) -> bool:
        """Delete email"""
        try:
            # Delete email from Gmail
            self.service.users().messages().delete(userId="me", id=gmail_id).execute()
            return True

        except HttpError as error:
            raise Exception(f"Failed to delete email: {error}")

    async def process_unsubscribe(self, email_obj) -> Dict:
        """Process advanced unsubscribe (improved version, async)"""
        print(f"🔍 GmailService.process_unsubscribe started - Email ID: {email_obj.id}")
        print(
            f"📝 Email info - Subject: {email_obj.subject}, Sender: {email_obj.sender}"
        )

        try:
            # Get user email address
            user_email = self._get_user_email()
            print(f"📝 User email address: {user_email}")

            # Use advanced unsubscribe service (pass user email)
            print(f"📝 AdvancedUnsubscribeService call started")
            result = await self.advanced_unsubscribe.process_unsubscribe_advanced(
                email_obj.content, getattr(email_obj, "headers", {}), user_email
            )
            print(f"📝 AdvancedUnsubscribeService result: {result}")

            if result["success"]:
                print(f"�� Starting DB update - is_unsubscribed = True")
                # Update unsubscribed status in DB
                email_obj.is_unsubscribed = True
                email_obj.updated_at = datetime.utcnow()

                # Batch update other emails from the same sender
                print(
                    f"📝 Starting batch update of other emails from the same sender - Sender: {email_obj.sender}"
                )
                from ..models import Email

                # Find other emails from the same user and sender
                related_emails = Email.query.filter(
                    Email.user_id == self.user_id,
                    Email.sender == email_obj.sender,
                    Email.id != email_obj.id,  # Exclude current email
                    Email.is_unsubscribed == False,  # Only emails not yet unsubscribed
                ).all()

                if related_emails:
                    print(f"📝 Number of emails to batch update: {len(related_emails)}")
                    for related_email in related_emails:
                        related_email.is_unsubscribed = True
                        related_email.updated_at = datetime.utcnow()
                        print(
                            f"📝 Updating email ID {related_email.id} - Subject: {related_email.subject}"
                        )

                    # Add batch update results to the result
                    result["bulk_updated_count"] = len(related_emails)
                    result["bulk_updated_message"] = (
                        f"Other emails from the same sender ({len(related_emails)} emails) were also unsubscribed."
                    )
                else:
                    print(f"📝 No emails to batch update")
                    result["bulk_updated_count"] = 0
                    result["bulk_updated_message"] = (
                        "No other emails from the same sender."
                    )

                db.session.commit()
                print(f"✅ DB update complete")
            else:
                # Add error type and details to the result
                result["error_type"] = result.get("error_type", "unknown")
                result["error_details"] = result.get("error_details", "")
                if "failed_links" in result:
                    result["failed_links"] = result["failed_links"]

            return result

        except Exception as e:
            print(f"❌ GmailService.process_unsubscribe exception occurred: {str(e)}")
            return {
                "success": False,
                "message": f"Unsubscribe processing failed: {str(e)}",
                "error_type": "system_error",
                "error_details": f"System error: {str(e)}",
                "steps": [f"Error occurred: {str(e)}"],
            }

    def _get_user_email(self) -> str:
        """Get user email address"""
        try:
            # Get user email address from current account
            account = UserAccount.query.filter_by(id=self.account_id).first()
            if account:
                return account.account_email

            # Return default value
            return "user@example.com"
        except Exception as e:
            print(f"❌ Failed to get user email address: {str(e)}")
            return "user@example.com"

    def setup_gmail_watch(self, topic_name: str) -> bool:
        """Set up Gmail webhook"""
        try:
            print(
                f"🔧 Starting webhook setup - Account: {self.account_id}, Topic: {topic_name}"
            )

            # Gmail Watch request
            request = {
                "labelIds": ["INBOX"],
                "topicName": topic_name,
                "labelFilterAction": "include",
            }

            print(f"📤 Gmail API request - Account: {self.account_id}")
            print(f"   Topic: {topic_name}")
            print(f"   Labels: {request['labelIds']}")

            response = self.service.users().watch(userId="me", body=request).execute()

            print(f"✅ Gmail API response successful - Account: {self.account_id}")
            print(f"   historyId: {response.get('historyId')}")
            print(f"   expiration: {response.get('expiration')}")

            # Save webhook status to DB
            from ..models import WebhookStatus
            from datetime import datetime, timedelta

            # Deactivate existing webhook status
            WebhookStatus.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_active=True
            ).update({"is_active": False})

            # Save new webhook status (expires in 7 days)
            webhook_status = WebhookStatus(
                user_id=self.user_id,
                account_id=self.account_id,
                topic_name=topic_name,
                is_active=True,
                setup_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=7),
            )

            db.session.add(webhook_status)
            db.session.commit()

            print(f"✅ Gmail webhook setup complete: {self.account_id}")
            return True

        except Exception as e:
            print(f"❌ Failed to set up Gmail webhook: {self.account_id}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Error message: {str(e)}")

            # Print more detailed info if it's an HttpError
            if hasattr(e, "resp") and hasattr(e, "content"):
                print(f"   HTTP status code: {e.resp.status}")
                print(f"   Response content: {e.content}")

            return False

    def stop_gmail_watch(self) -> bool:
        """Stop Gmail webhook"""
        try:
            self.service.users().stop(userId="me").execute()

            # Deactivate webhook status in DB
            from ..models import WebhookStatus

            WebhookStatus.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_active=True
            ).update({"is_active": False})
            db.session.commit()

            print(f"✅ Gmail webhook stopped: {self.account_id}")
            return True

        except Exception as e:
            print(f"❌ Failed to stop Gmail webhook: {self.account_id} - {e}")
            return False

    def get_webhook_status(self) -> Dict:
        """Check webhook status"""
        try:
            from ..models import WebhookStatus

            webhook_status = WebhookStatus.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_active=True
            ).first()

            if not webhook_status:
                return {
                    "is_active": False,
                    "status": "not_setup",
                    "message": "Webhook is not set up.",
                }

            if webhook_status.is_expired:
                return {
                    "is_active": False,
                    "status": "expired",
                    "message": "Webhook has expired.",
                    "expires_at": webhook_status.expires_at.isoformat(),
                    "setup_at": webhook_status.setup_at.isoformat(),
                }

            if not webhook_status.is_healthy:
                return {
                    "is_active": True,
                    "status": "unhealthy",
                    "message": "Webhook is in an unhealthy state.",
                    "last_webhook_received": (
                        webhook_status.last_webhook_received.isoformat()
                        if webhook_status.last_webhook_received
                        else None
                    ),
                    "setup_at": webhook_status.setup_at.isoformat(),
                }

            return {
                "is_active": True,
                "status": "healthy",
                "message": "Webhook is functioning normally.",
                "last_webhook_received": (
                    webhook_status.last_webhook_received.isoformat()
                    if webhook_status.last_webhook_received
                    else None
                ),
                "setup_at": webhook_status.setup_at.isoformat(),
                "expires_at": webhook_status.expires_at.isoformat(),
            }

        except Exception as e:
            return {
                "is_active": False,
                "status": "error",
                "message": f"Failed to check webhook status: {str(e)}",
            }

    def check_and_renew_webhook(self, topic_name: str) -> bool:
        """Check webhook status and renew if necessary"""
        try:
            status = self.get_webhook_status()

            # If webhook is not set up, expired, or unhealthy, renew it
            if status["status"] in ["not_setup", "expired", "unhealthy"]:
                print(
                    f"🔄 Webhook needs renewal: {self.account_id} - {status['status']}"
                )

                # Stop existing webhook
                self.stop_gmail_watch()

                # Set up new webhook
                return self.setup_gmail_watch(topic_name)

            return True

        except Exception as e:
            print(f"❌ Failed to check webhook status: {self.account_id} - {e}")
            return False

    def get_new_emails(self) -> List[Dict]:
        """Get new emails after subscription date"""
        try:
            # Get subscription date from user account
            account = UserAccount.query.filter_by(id=self.account_id).first()
            if not account:
                print(f"❌ Account info not found: {self.account_id}")
                return []

            # Get emails after subscription date
            after_date = account.created_at
            print(
                f"🔍 Searching for new emails - Account: {account.account_email}, Subscription date: {after_date}"
            )

            # Use fetch_recent_emails method to get emails after subscription date
            new_emails = self.fetch_recent_emails(
                max_results=50, after_date=after_date  # Max 50
            )

            print(
                f"📧 New emails found - Account: {account.account_email}, Count: {len(new_emails)}"
            )
            return new_emails

        except Exception as e:
            print(
                f"❌ Failed to get new emails - Account: {self.account_id}, Error: {str(e)}"
            )
            return []
