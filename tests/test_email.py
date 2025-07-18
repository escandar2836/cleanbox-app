import pytest
import json
import time
from unittest.mock import patch, MagicMock
from cleanbox import create_app
from cleanbox.models import User, UserAccount, Email, Category, db
from cleanbox.email.gmail_service import GmailService
from cleanbox.email.ai_classifier import AIClassifier
from cleanbox.email.advanced_unsubscribe import AdvancedUnsubscribeService


@pytest.fixture
def app():
    """테스트용 Flask 앱 생성"""
    app = create_app()
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """테스트 클라이언트"""
    return app.test_client()


@pytest.fixture
def sample_data(app):
    """샘플 데이터 생성"""
    # 사용자 생성
    user = User(id="test_user_123", email="test@example.com", name="Test User")
    db.session.add(user)

    # 계정 생성
    account = UserAccount(
        user_id=user.id,
        account_email="test@example.com",
        account_name="Test User",
        is_primary=True,
    )
    db.session.add(account)

    # 카테고리 생성
    category = Category(
        user_id=user.id,
        name="테스트 카테고리",
        description="테스트용 카테고리입니다",
        color="#007bff",
    )
    db.session.add(category)

    # 이메일 생성
    email = Email(
        user_id=user.id,
        account_id=account.id,
        gmail_id="test_gmail_id",
        subject="테스트 이메일",
        sender="sender@example.com",
        content="테스트 이메일 내용입니다.",
        summary="테스트 이메일 요약",
        is_read=False,
        is_archived=False,
    )
    db.session.add(email)

    db.session.commit()
    return {"user": user, "account": account, "category": category, "email": email}


class TestEmailModels:
    """이메일 모델 테스트"""

    def test_email_creation(self, app):
        """이메일 생성 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="test_gmail_id",
            subject="테스트 제목",
            sender="sender@example.com",
            content="테스트 내용",
        )
        db.session.add(email)
        db.session.commit()

        assert email.subject == "테스트 제목"
        assert email.sender == "sender@example.com"
        assert email.is_read is False
        assert email.is_archived is False

    def test_email_category_association(self, app):
        """이메일-카테고리 연관관계 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        category = Category(user_id=user.id, name="테스트 카테고리")

        db.session.add_all([user, account, category])
        db.session.commit()

        email = Email(
            user_id=user.id,
            account_id=account.id,
            category_id=category.id,
            gmail_id="test_gmail_id",
            subject="테스트 제목",
            sender="sender@example.com",
            content="테스트 내용",
        )
        db.session.add(email)
        db.session.commit()

        assert email.category.name == "테스트 카테고리"
        assert category.emails[0].subject == "테스트 제목"

    def test_email_with_very_long_content(self, app):
        """매우 긴 내용을 가진 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        long_content = "A" * 100000  # 10만자 내용
        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="test_gmail_id",
            subject="긴 내용 이메일",
            sender="sender@example.com",
            content=long_content,
        )
        db.session.add(email)
        db.session.commit()

        assert len(email.content) == 100000
        assert email.content == long_content

    def test_email_with_special_characters(self, app):
        """특수 문자가 포함된 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        special_content = "특수문자: !@#$%^&*()_+-=[]{}|;':\",./<>?`~ 🚀"
        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="test_gmail_id",
            subject="특수문자 이메일",
            sender="sender@example.com",
            content=special_content,
        )
        db.session.add(email)
        db.session.commit()

        assert email.content == special_content

    def test_email_with_html_content(self, app):
        """HTML 내용을 가진 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        html_content = """
        <html>
        <body>
        <h1>제목</h1>
        <p>이것은 <strong>HTML</strong> 내용입니다.</p>
        <a href="https://example.com">링크</a>
        </body>
        </html>
        """
        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="test_gmail_id",
            subject="HTML 이메일",
            sender="sender@example.com",
            content=html_content,
        )
        db.session.add(email)
        db.session.commit()

        assert "<html>" in email.content
        assert "<strong>HTML</strong>" in email.content


class TestGmailService:
    """Gmail 서비스 테스트"""

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_service_initialization(self, mock_build, app):
        """Gmail 서비스 초기화 테스트"""
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        with patch(
            "cleanbox.email.gmail_service.get_user_credentials"
        ) as mock_credentials:
            mock_credentials.return_value = {"token": "test_token"}

            service = GmailService("test_user")
            assert service.user_id == "test_user"
            assert service.service is not None

    def test_email_statistics(self, app, sample_data):
        """이메일 통계 테스트"""
        with patch(
            "cleanbox.email.gmail_service.get_current_account_id"
        ) as mock_account_id:
            mock_account_id.return_value = sample_data["account"].id

            service = GmailService(sample_data["user"].id)
            stats = service.get_email_statistics()

            assert stats["total"] == 1
            assert stats["unread"] == 1
            assert stats["archived"] == 0
            assert "테스트 카테고리" in stats["categories"]

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_api_quota_exceeded(self, mock_build, app):
        """Gmail API 할당량 초과 테스트"""
        from googleapiclient.errors import HttpError

        # 할당량 초과 에러 모의
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=429), content=b"Quota exceeded"
        )
        mock_build.return_value = mock_service

        with patch(
            "cleanbox.email.gmail_service.get_user_credentials"
        ) as mock_credentials:
            mock_credentials.return_value = {"token": "test_token"}

            service = GmailService("test_user")
            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Gmail API 오류" in str(exc_info.value)

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_api_authentication_error(self, mock_build, app):
        """Gmail API 인증 오류 테스트"""
        from googleapiclient.errors import HttpError

        # 인증 오류 모의
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=401), content=b"Unauthorized"
        )
        mock_build.return_value = mock_service

        with patch(
            "cleanbox.email.gmail_service.get_user_credentials"
        ) as mock_credentials:
            mock_credentials.return_value = {"token": "test_token"}

            service = GmailService("test_user")
            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Gmail API 오류" in str(exc_info.value)

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_api_network_timeout(self, mock_build, app):
        """Gmail API 네트워크 타임아웃 테스트"""
        import requests

        # 네트워크 타임아웃 모의
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = requests.exceptions.Timeout(
            "Request timeout"
        )
        mock_build.return_value = mock_service

        with patch(
            "cleanbox.email.gmail_service.get_user_credentials"
        ) as mock_credentials:
            mock_credentials.return_value = {"token": "test_token"}

            service = GmailService("test_user")
            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Gmail API 오류" in str(exc_info.value)

    def test_email_with_malformed_gmail_response(self, app):
        """잘못된 Gmail 응답 처리 테스트"""
        with patch(
            "cleanbox.email.gmail_service.get_current_account_id"
        ) as mock_account_id:
            mock_account_id.return_value = 1

            service = GmailService("test_user")

            # 잘못된 이메일 데이터로 테스트
            malformed_email_data = {
                "gmail_id": "test_id",
                "subject": None,  # None 값
                "sender": "",  # 빈 문자열
                "body": None,  # None 값
                "date": "invalid_date",  # 잘못된 날짜
                "snippet": None,
                "labels": None,
                "headers": {},
            }

            # 이메일 저장 테스트
            email_obj = service.save_email_to_db(malformed_email_data)
            assert email_obj.subject == "제목 없음"  # 기본값
            assert email_obj.sender == "알 수 없는 발신자"  # 기본값


class TestAIClassifier:
    """AI 분류기 테스트"""

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    def test_email_classification(self, mock_openai, app):
        """이메일 분류 테스트"""
        mock_openai.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="테스트 카테고리"))]
        )

        classifier = AIClassifier()
        categories = [
            Category(name="테스트 카테고리", description="테스트용"),
            Category(name="다른 카테고리", description="다른 용도"),
        ]

        result = classifier.classify_email("테스트 이메일 내용", categories)

        assert result is not None
        assert "테스트 카테고리" in result

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    def test_email_summarization(self, mock_openai, app):
        """이메일 요약 테스트"""
        mock_openai.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="이메일 요약 내용"))]
        )

        classifier = AIClassifier()
        summary = classifier.summarize_email("테스트 이메일 내용")

        assert summary is not None
        assert len(summary) > 0

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    def test_ai_api_error_handling(self, mock_openai, app):
        """AI API 오류 처리 테스트"""
        from openai import APIError

        # API 오류 모의
        mock_openai.side_effect = APIError(
            "API key invalid", response=MagicMock(), body=None
        )

        classifier = AIClassifier()

        with pytest.raises(Exception) as exc_info:
            classifier.classify_email("테스트 내용", [])
        assert "API" in str(exc_info.value)

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    def test_ai_api_timeout(self, mock_openai, app):
        """AI API 타임아웃 테스트"""
        import requests

        # 타임아웃 모의
        mock_openai.side_effect = requests.exceptions.Timeout("Request timeout")

        classifier = AIClassifier()

        with pytest.raises(Exception) as exc_info:
            classifier.classify_email("테스트 내용", [])
        assert "timeout" in str(exc_info.value).lower()

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    def test_ai_with_empty_content(self, mock_openai, app):
        """빈 내용으로 AI 분류 테스트"""
        mock_openai.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="미분류"))]
        )

        classifier = AIClassifier()
        categories = [Category(name="테스트 카테고리", description="테스트용")]

        result = classifier.classify_email("", categories)  # 빈 내용
        assert result is not None

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    def test_ai_with_very_long_content(self, mock_openai, app):
        """매우 긴 내용으로 AI 분류 테스트"""
        mock_openai.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="테스트 카테고리"))]
        )

        classifier = AIClassifier()
        categories = [Category(name="테스트 카테고리", description="테스트용")]

        long_content = "A" * 10000  # 1만자 내용
        result = classifier.classify_email(long_content, categories)
        assert result is not None


class TestAdvancedUnsubscribe:
    """고급 구독해지 테스트"""

    def test_unsubscribe_link_extraction(self, app):
        """구독해지 링크 추출 테스트"""
        unsubscribe_service = AdvancedUnsubscribeService()

        email_content = """
        안녕하세요,
        이 이메일을 구독해지하려면 다음 링크를 클릭하세요:
        <a href="https://example.com/unsubscribe">구독해지</a>
        """

        links = unsubscribe_service.extract_unsubscribe_links(email_content)
        assert len(links) > 0
        assert "unsubscribe" in links[0]

    def test_unsubscribe_with_captcha(self, app):
        """CAPTCHA가 있는 구독해지 테스트"""
        unsubscribe_service = AdvancedUnsubscribeService()

        # CAPTCHA 페이지 모의
        captcha_html = """
        <html>
        <body>
        <form>
        <input type="text" name="captcha" placeholder="CAPTCHA 입력">
        <button type="submit">구독해지</button>
        </form>
        </body>
        </html>
        """

        with patch("cleanbox.email.advanced_unsubscribe.requests.get") as mock_get:
            mock_get.return_value.content = captcha_html.encode()
            mock_get.return_value.status_code = 200

            result = unsubscribe_service.process_unsubscribe_simple(
                "https://example.com/unsubscribe"
            )
            # CAPTCHA가 있으면 구독해지 실패
            assert not result["success"]

    def test_unsubscribe_with_javascript(self, app):
        """JavaScript가 필요한 구독해지 테스트"""
        unsubscribe_service = AdvancedUnsubscribeService()

        # JavaScript 페이지 모의
        js_html = """
        <html>
        <body>
        <script>
        function unsubscribe() {
            // JavaScript로 구독해지 처리
        }
        </script>
        <button onclick="unsubscribe()">구독해지</button>
        </body>
        </html>
        """

        with patch("cleanbox.email.advanced_unsubscribe.requests.get") as mock_get:
            mock_get.return_value.content = js_html.encode()
            mock_get.return_value.status_code = 200

            result = unsubscribe_service.process_unsubscribe_simple(
                "https://example.com/unsubscribe"
            )
            # JavaScript가 있으면 간단한 방법으로는 실패
            assert not result["success"]

    def test_unsubscribe_network_error(self, app):
        """네트워크 오류 시 구독해지 테스트"""
        unsubscribe_service = AdvancedUnsubscribeService()

        with patch("cleanbox.email.advanced_unsubscribe.requests.get") as mock_get:
            mock_get.side_effect = Exception("Network error")

            result = unsubscribe_service.process_unsubscribe_simple(
                "https://example.com/unsubscribe"
            )
            assert not result["success"]
            assert "오류" in result["message"]


class TestEmailRoutes:
    """이메일 라우트 테스트"""

    def test_list_emails_requires_login(self, client):
        """이메일 목록 페이지 로그인 필요 테스트"""
        response = client.get("/email/")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트

    def test_sync_emails_requires_login(self, client):
        """이메일 동기화 로그인 필요 테스트"""
        response = client.post("/email/sync")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트

    def test_view_email_requires_login(self, client):
        """이메일 상세 보기 로그인 필요 테스트"""
        response = client.get("/email/1")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트


class TestBulkActions:
    """대량 작업 테스트"""

    def test_bulk_actions_requires_login(self, client):
        """대량 작업 로그인 필요 테스트"""
        response = client.post("/email/bulk-actions")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트

    def test_unsubscribe_requires_login(self, client):
        """구독해지 로그인 필요 테스트"""
        response = client.get("/email/1/unsubscribe")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트


class TestEmailOperations:
    """이메일 작업 테스트"""

    def test_mark_as_read(self, app, sample_data):
        """읽음 표시 테스트"""
        email = sample_data["email"]
        assert email.is_read is False

        email.is_read = True
        db.session.commit()

        updated_email = Email.query.get(email.id)
        assert updated_email.is_read is True

    def test_archive_email(self, app, sample_data):
        """아카이브 테스트"""
        email = sample_data["email"]
        assert email.is_archived is False

        email.is_archived = True
        db.session.commit()

        updated_email = Email.query.get(email.id)
        assert updated_email.is_archived is True

    def test_unsubscribe_email(self, app, sample_data):
        """구독해지 테스트"""
        email = sample_data["email"]
        assert email.is_unsubscribed is False

        email.is_unsubscribed = True
        db.session.commit()

        updated_email = Email.query.get(email.id)
        assert updated_email.is_unsubscribed is True


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_email_with_null_values(self, app):
        """None 값이 포함된 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="test_gmail_id",
            subject=None,  # None 값
            sender=None,  # None 값
            content=None,  # None 값
            summary=None,  # None 값
            is_read=False,
            is_archived=False,
        )
        db.session.add(email)
        db.session.commit()

        assert email.subject is None
        assert email.sender is None
        assert email.content is None

    def test_email_with_empty_strings(self, app):
        """빈 문자열이 포함된 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="test_gmail_id",
            subject="",  # 빈 문자열
            sender="",  # 빈 문자열
            content="",  # 빈 문자열
            summary="",  # 빈 문자열
            is_read=False,
            is_archived=False,
        )
        db.session.add(email)
        db.session.commit()

        assert email.subject == ""
        assert email.sender == ""
        assert email.content == ""

    def test_concurrent_email_operations(self, app):
        """동시 이메일 작업 테스트"""
        import threading
        import time

        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 여러 이메일 생성
        emails = []
        for i in range(10):
            email = Email(
                user_id=user.id,
                account_id=account.id,
                gmail_id=f"test_gmail_id_{i}",
                subject=f"테스트 이메일 {i}",
                sender="sender@example.com",
                content=f"테스트 내용 {i}",
            )
            emails.append(email)
            db.session.add(email)
        db.session.commit()

        # 동시에 읽음 표시
        def mark_as_read(email_id):
            with app.app_context():
                email = Email.query.get(email_id)
                if email:
                    email.is_read = True
                    db.session.commit()

        threads = []
        for email in emails:
            thread = threading.Thread(target=mark_as_read, args=(email.id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 모든 이메일이 읽음 표시되었는지 확인
        read_emails = Email.query.filter_by(user_id=user.id, is_read=True).all()
        assert len(read_emails) == 10
