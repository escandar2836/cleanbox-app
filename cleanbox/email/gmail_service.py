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
from ..auth.routes import get_user_credentials, get_current_account_id
from .advanced_unsubscribe import AdvancedUnsubscribeService


class GmailService:
    """Gmail API 서비스 클래스"""

    def __init__(self, user_id: str, account_id: Optional[int] = None):
        self.user_id = user_id
        self.account_id = account_id or get_current_account_id()

        if not self.account_id:
            raise Exception("활성 계정을 찾을 수 없습니다.")

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

    def fetch_emails_after_date(self, after_date: datetime) -> List[Dict]:
        """특정 날짜 이후의 이메일 가져오기 (inbox만)"""
        try:
            # 날짜를 RFC 3339 형식으로 변환
            after_date_str = after_date.strftime("%Y/%m/%d")

            # Gmail API로 특정 날짜 이후의 이메일 목록 가져오기 (inbox만)
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=100,  # 최대 100개
                    q=f"after:{after_date_str} is:inbox",  # 특정 날짜 이후 + inbox만
                )
                .execute()
            )

            messages = results.get("messages", [])

            emails = []
            for message in messages:
                email_data = self._get_email_details(message["id"])
                if email_data:
                    # 날짜 필터링 (Gmail API의 after 쿼리는 정확하지 않을 수 있음)
                    email_date = self._parse_date(email_data.get("date"))
                    if email_date and email_date >= after_date:
                        # inbox 라벨이 있는지 확인
                        labels = email_data.get("labels", [])
                        if "INBOX" in labels:
                            emails.append(email_data)

            return emails

        except HttpError as error:
            raise Exception(f"Gmail API 오류: {error}")

    def fetch_recent_emails(
        self,
        max_results: int = 20,
        offset: int = 0,
        after_date: Optional[datetime] = None,
    ) -> List[Dict]:
        """가입 날짜 이후의 이메일 가져오기 (페이지네이션 지원)"""
        try:
            # 가입 날짜 이후의 이메일을 가져오기 위한 쿼리
            if after_date:
                # 가입 날짜 이후의 이메일만 가져오기
                after_date_str = after_date.strftime("%Y/%m/%d")
                query = f"after:{after_date_str} is:inbox"
                print(f"🔍 Gmail API 호출 - 계정: {self.account_id}, 쿼리: {query}")
            else:
                # 기본값: 최근 24시간 (하위 호환성)
                yesterday = datetime.utcnow() - timedelta(hours=24)
                after_date_str = yesterday.strftime("%Y/%m/%d")
                query = f"after:{after_date_str} is:inbox"
                print(
                    f"🔍 Gmail API 호출 - 계정: {self.account_id}, 쿼리: {query} (기본값)"
                )

            # Gmail API로 이메일 목록 가져오기
            results = (
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    maxResults=max_results,
                    q=query,  # 가입 날짜 이후 받은 편지함 이메일
                )
                .execute()
            )

            messages = results.get("messages", [])
            print(
                f"📧 Gmail API 응답 - 계정: {self.account_id}, 메시지 수: {len(messages)}"
            )

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
                            q=query,
                        )
                        .execute()
                    )
                    messages = results.get("messages", [])

            emails = []
            for i, message in enumerate(messages):
                print(
                    f"📨 이메일 처리 중 ({i+1}/{len(messages)}) - ID: {message['id']}"
                )
                email_data = self._get_email_details(message["id"])
                if email_data:
                    emails.append(email_data)
                    print(
                        f"✅ 이메일 데이터 추출 완료 - 제목: {email_data.get('subject', '제목 없음')}"
                    )
                else:
                    print(f"❌ 이메일 상세 정보 가져오기 실패 - ID: {message['id']}")

            print(
                f"🎉 이메일 처리 완료 - 계정: {self.account_id}, 총 {len(emails)}개 처리됨"
            )
            return emails

        except HttpError as error:
            print(f"❌ Gmail API 오류 - 계정: {self.account_id}, 오류: {error}")
            raise Exception(f"Gmail API 오류: {error}")
        except Exception as e:
            print(f"❌ 예상치 못한 오류 - 계정: {self.account_id}, 오류: {e}")
            raise Exception(f"이메일 가져오기 실패: {str(e)}")

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
        """날짜 문자열을 datetime으로 변환 (timezone-naive)"""
        if not date_str:
            return None

        try:
            # RFC 2822 형식 파싱
            parsed_date = email.utils.parsedate_to_datetime(date_str)
            # timezone 정보 제거하여 timezone-naive datetime 반환
            if parsed_date.tzinfo:
                parsed_date = parsed_date.replace(tzinfo=None)
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

    def setup_gmail_watch(self, topic_name: str) -> bool:
        """Gmail 웹훅 설정"""
        try:
            print(f"🔧 웹훅 설정 시작 - 계정: {self.account_id}, 토픽: {topic_name}")

            # Gmail Watch 요청
            request = {
                "labelIds": ["INBOX"],
                "topicName": topic_name,
                "labelFilterAction": "include",
            }

            print(f"📤 Gmail API 요청 - 계정: {self.account_id}")
            print(f"   토픽: {topic_name}")
            print(f"   라벨: {request['labelIds']}")

            response = self.service.users().watch(userId="me", body=request).execute()

            print(f"✅ Gmail API 응답 성공 - 계정: {self.account_id}")
            print(f"   historyId: {response.get('historyId')}")
            print(f"   expiration: {response.get('expiration')}")

            # DB에 웹훅 상태 저장
            from ..models import WebhookStatus
            from datetime import datetime, timedelta

            # 기존 웹훅 상태 비활성화
            WebhookStatus.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_active=True
            ).update({"is_active": False})

            # 새 웹훅 상태 저장 (7일 후 만료)
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

            print(f"✅ Gmail 웹훅 설정 완료: {self.account_id}")
            return True

        except Exception as e:
            print(f"❌ Gmail 웹훅 설정 실패: {self.account_id}")
            print(f"   오류 타입: {type(e).__name__}")
            print(f"   오류 메시지: {str(e)}")

            # HttpError인 경우 더 자세한 정보 출력
            if hasattr(e, "resp") and hasattr(e, "content"):
                print(f"   HTTP 상태 코드: {e.resp.status}")
                print(f"   응답 내용: {e.content}")

            return False

    def stop_gmail_watch(self) -> bool:
        """Gmail 웹훅 중지"""
        try:
            self.service.users().stop(userId="me").execute()

            # DB에서 웹훅 상태 비활성화
            from ..models import WebhookStatus

            WebhookStatus.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_active=True
            ).update({"is_active": False})
            db.session.commit()

            print(f"✅ Gmail 웹훅 중지 완료: {self.account_id}")
            return True

        except Exception as e:
            print(f"❌ Gmail 웹훅 중지 실패: {self.account_id} - {e}")
            return False

    def get_webhook_status(self) -> Dict:
        """웹훅 상태 확인"""
        try:
            from ..models import WebhookStatus

            webhook_status = WebhookStatus.query.filter_by(
                user_id=self.user_id, account_id=self.account_id, is_active=True
            ).first()

            if not webhook_status:
                return {
                    "is_active": False,
                    "status": "not_setup",
                    "message": "웹훅이 설정되지 않았습니다.",
                }

            if webhook_status.is_expired:
                return {
                    "is_active": False,
                    "status": "expired",
                    "message": "웹훅이 만료되었습니다.",
                    "expires_at": webhook_status.expires_at.isoformat(),
                    "setup_at": webhook_status.setup_at.isoformat(),
                }

            if not webhook_status.is_healthy:
                return {
                    "is_active": True,
                    "status": "unhealthy",
                    "message": "웹훅이 비정상 상태입니다.",
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
                "message": "웹훅이 정상 작동 중입니다.",
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
                "message": f"웹훅 상태 확인 실패: {str(e)}",
            }

    def check_and_renew_webhook(self, topic_name: str) -> bool:
        """웹훅 상태 확인 후 필요시 재설정"""
        try:
            status = self.get_webhook_status()

            # 웹훅이 없거나 만료되었거나 비정상이면 재설정
            if status["status"] in ["not_setup", "expired", "unhealthy"]:
                print(f"🔄 웹훅 재설정 필요: {self.account_id} - {status['status']}")

                # 기존 웹훅 중지
                self.stop_gmail_watch()

                # 새 웹훅 설정
                return self.setup_gmail_watch(topic_name)

            return True

        except Exception as e:
            print(f"❌ 웹훅 상태 확인 실패: {self.account_id} - {e}")
            return False
