import os
import base64
import email
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ..models import Email, Category, UserAccount, db
from ..auth.routes import get_user_credentials, get_current_account_id
from .advanced_unsubscribe import AdvancedUnsubscribeService


class GmailService:
    """Gmail API 서비스 클래스"""

    def __init__(self, user_id: str, account_id: Optional[int] = None):
        self.user_id = user_id
        self.account_id = account_id or get_current_account_id()
        self.service = None
        self.advanced_unsubscribe = AdvancedUnsubscribeService()
        self._initialize_service()

    def _initialize_service(self):
        """Gmail API 서비스 초기화"""
        try:
            credentials_data = get_user_credentials(self.user_id, self.account_id)
            if not credentials_data:
                raise Exception("사용자 인증 정보를 찾을 수 없습니다.")

            # 딕셔너리를 Google OAuth credentials 객체로 변환
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

            # Google API 클라이언트 빌드
            self.service = build("gmail", "v1", credentials=credentials)
        except Exception as e:
            raise Exception(f"Gmail API 서비스 초기화 실패: {str(e)}")

    def fetch_recent_emails(self, max_results: int = 20, offset: int = 0) -> List[Dict]:
        """최근 이메일 가져오기 (페이지네이션 지원)"""
        try:
            # Gmail API로 이메일 목록 가져오기
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=max_results,
                    q="is:unread OR is:inbox",  # 읽지 않은 이메일 또는 받은 편지함
                )
                .execute()
            )

            messages = results.get("messages", [])

            # 오프셋 적용 (Gmail API는 페이지네이션을 자체적으로 처리)
            if offset > 0 and "nextPageToken" in results:
                # 다음 페이지 토큰을 사용하여 오프셋 처리
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
                            q="is:unread OR is:inbox",
                        )
                        .execute()
                    )
                    messages = results.get("messages", [])

            emails = []
            for message in messages:
                email_data = self._get_email_details(message["id"])
                if email_data:
                    # 이메일을 데이터베이스에 저장
                    email_obj = self.save_email_to_db(email_data)
                    emails.append(email_data)

            return emails

        except HttpError as error:
            raise Exception(f"Gmail API 오류: {error}")

    def _get_email_details(self, message_id: str) -> Optional[Dict]:
        """이메일 상세 정보 가져오기"""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            headers = message["payload"]["headers"]
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"), "제목 없음"
            )
            sender = next(
                (h["value"] for h in headers if h["name"] == "From"),
                "알 수 없는 발신자",
            )
            date = next((h["value"] for h in headers if h["name"] == "Date"), None)

            # 이메일 본문 추출
            body = self._extract_email_body(message["payload"])

            # 헤더 정보 추출 (구독해지용)
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
            print(f"이메일 상세 정보 가져오기 실패 (ID: {message_id}): {error}")
            return None

    def _extract_email_body(self, payload: Dict) -> str:
        """이메일 본문 추출"""
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

        return "본문을 추출할 수 없습니다."

    def save_email_to_db(self, email_data: Dict) -> Email:
        """이메일을 DB에 저장"""
        try:
            # 이미 저장된 이메일인지 확인 (계정별로)
            existing_email = Email.query.filter_by(
                user_id=self.user_id,
                account_id=self.account_id,
                gmail_id=email_data["gmail_id"],
            ).first()

            if existing_email:
                return existing_email

            # 새 이메일 생성 (기본값 처리)
            email_obj = Email(
                user_id=self.user_id,
                account_id=self.account_id,
                gmail_id=email_data["gmail_id"],
                thread_id=email_data.get("thread_id"),
                subject=email_data.get("subject") or "제목 없음",
                sender=email_data.get("sender") or "알 수 없는 발신자",
                content=email_data.get("body") or "본문 없음",
                summary=email_data.get("snippet", ""),
                received_at=self._parse_date(email_data.get("date")),
                is_read=False,
                is_archived=False,
            )

            db.session.add(email_obj)
            db.session.commit()

            return email_obj

        except Exception as e:
            db.session.rollback()
            raise Exception(f"이메일 DB 저장 실패: {str(e)}")

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """날짜 문자열을 datetime으로 변환"""
        if not date_str:
            return None

        try:
            # RFC 2822 형식 파싱
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            return parsed_date
        except:
            return datetime.utcnow()

    def archive_email(self, gmail_id: str) -> bool:
        """이메일 아카이브"""
        try:
            # Gmail에서 아카이브 처리
            self.service.users().messages().modify(
                userId="me", id=gmail_id, body={"removeLabelIds": ["INBOX"]}
            ).execute()

            # DB에서 아카이브 상태 업데이트
            email_obj = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, gmail_id=gmail_id
            ).first()

            if email_obj:
                email_obj.is_archived = True
                email_obj.updated_at = datetime.utcnow()
                db.session.commit()

            return True

        except HttpError as error:
            raise Exception(f"이메일 아카이브 실패: {error}")

    def mark_as_read(self, gmail_id: str) -> bool:
        """이메일을 읽음으로 표시"""
        try:
            # Gmail에서 읽음 표시
            self.service.users().messages().modify(
                userId="me", id=gmail_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()

            # DB에서 읽음 상태 업데이트
            email_obj = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, gmail_id=gmail_id
            ).first()

            if email_obj:
                email_obj.is_read = True
                email_obj.updated_at = datetime.utcnow()
                db.session.commit()

            return True

        except HttpError as error:
            raise Exception(f"이메일 읽음 표시 실패: {error}")

    def get_user_categories(self) -> List[Category]:
        """사용자의 카테고리 목록 가져오기"""
        return Category.query.filter_by(user_id=self.user_id, is_active=True).all()

    def update_email_category(self, gmail_id: str, category_id: Optional[int]) -> bool:
        """이메일 카테고리 업데이트"""
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
            raise Exception(f"이메일 카테고리 업데이트 실패: {str(e)}")

    def get_email_statistics(self) -> Dict:
        """이메일 통계 가져오기"""
        try:
            # 현재 계정의 이메일 통계
            total_emails = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id
            ).count()
            unread_emails = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_read=False
            ).count()
            archived_emails = Email.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_archived=True
            ).count()

            # 카테고리별 이메일 수
            categories = self.get_user_categories()
            category_stats = {}

            for category in categories:
                count = Email.query.filter_by(
                    user_id=self.user_id,
                    account_id=self.account_id,
                    category_id=category.id,
                ).count()
                category_stats[category.name] = count

            # 계정 정보
            account = UserAccount.query.get(self.account_id)
            account_info = {
                "email": account.account_email if account else "알 수 없음",
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
            raise Exception(f"이메일 통계 가져오기 실패: {str(e)}")

    def delete_email(self, gmail_id: str) -> bool:
        """이메일 삭제"""
        try:
            # Gmail에서 이메일 삭제
            self.service.users().messages().delete(userId="me", id=gmail_id).execute()
            return True

        except HttpError as error:
            raise Exception(f"이메일 삭제 실패: {error}")

    def process_unsubscribe(self, email_obj) -> Dict:
        """고급 구독해지 처리"""
        try:
            # 고급 구독해지 서비스 사용
            result = self.advanced_unsubscribe.process_unsubscribe_advanced(
                email_obj.content, getattr(email_obj, "headers", {})
            )

            if result["success"]:
                # DB에서 구독해지 상태 업데이트
                email_obj.is_unsubscribed = True
                email_obj.updated_at = datetime.utcnow()
                db.session.commit()

            return result

        except Exception as e:
            return {
                "success": False,
                "message": f"구독해지 처리 실패: {str(e)}",
                "steps": [f"오류 발생: {str(e)}"],
            }
