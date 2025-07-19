import pytest
import json
import time
from unittest.mock import patch, MagicMock
from cleanbox import create_app, db
from cleanbox.models import User, UserAccount, Email, Category
from cleanbox.email.gmail_service import GmailService
from cleanbox.email.ai_classifier import AIClassifier
from cleanbox.email.advanced_unsubscribe import AdvancedUnsubscribeService
from cleanbox.config import TestConfig


@pytest.fixture
def app():
    """테스트용 Flask 앱 생성"""
    app = create_app(TestConfig)

    with app.app_context():
        # 모든 테이블 삭제 후 재생성
        db.drop_all()
        db.create_all()

        yield app

        # 정리
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

    db.session.commit()  # account, category id 할당

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
    @patch("cleanbox.email.gmail_service.get_current_account_id")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    def test_gmail_service_initialization(
        self, mock_get_credentials, mock_get_account_id, mock_build, app
    ):
        """Gmail 서비스 초기화 테스트"""
        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"

        with patch("cleanbox.auth.routes.current_user", mock_user):
            mock_get_account_id.return_value = 1
            # Google API Credentials 객체 모킹
            mock_credentials_obj = MagicMock()
            mock_credentials_obj.authorize.return_value = MagicMock()
            mock_get_credentials.return_value = mock_credentials_obj

            service = GmailService("test_user")
            assert service.user_id == "test_user"
            assert service.account_id == 1

    def test_email_statistics(self, app, sample_data):
        """이메일 통계 테스트"""
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            with patch(
                "cleanbox.email.gmail_service.get_current_account_id"
            ) as mock_account_id:
                mock_account_id.return_value = sample_data["account"].id

                with patch(
                    "cleanbox.email.gmail_service.get_user_credentials"
                ) as mock_credentials:
                    # Google API Credentials 객체 모킹
                    mock_credentials_obj = MagicMock()
                    mock_credentials_obj.authorize.return_value = MagicMock()
                    mock_credentials.return_value = mock_credentials_obj

                    service = GmailService(sample_data["user"].id)
                    stats = service.get_email_statistics()

                    assert stats["total"] == 1
                    assert stats["unread"] == 1
                    assert stats["archived"] == 0
                    assert "테스트 카테고리" in stats["categories"]

    @patch("cleanbox.email.gmail_service.build")
    @patch("cleanbox.email.gmail_service.get_current_account_id")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    def test_gmail_api_quota_exceeded(
        self, mock_get_credentials, mock_get_account_id, mock_build, app
    ):
        """Gmail API 할당량 초과 테스트"""
        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"

        with patch("cleanbox.auth.routes.current_user", mock_user):
            mock_get_account_id.return_value = 1
            # Google API Credentials 객체 모킹
            mock_credentials_obj = MagicMock()
            mock_credentials_obj.authorize.return_value = MagicMock()
            mock_get_credentials.return_value = mock_credentials_obj

            # API 할당량 초과 모의
            mock_service = MagicMock()
            mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
                "Quota exceeded"
            )
            mock_build.return_value = mock_service

            service = GmailService("test_user")

            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Quota exceeded" in str(exc_info.value)

    @patch("cleanbox.email.gmail_service.build")
    @patch("cleanbox.email.gmail_service.get_current_account_id")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    def test_gmail_api_authentication_error(
        self, mock_get_credentials, mock_get_account_id, mock_build, app
    ):
        """Gmail API 인증 오류 테스트"""
        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"

        with patch("cleanbox.auth.routes.current_user", mock_user):
            mock_get_account_id.return_value = 1
            # Google API Credentials 객체 모킹
            mock_credentials_obj = MagicMock()
            mock_credentials_obj.authorize.return_value = MagicMock()
            mock_get_credentials.return_value = mock_credentials_obj

            # 인증 오류 모의
            mock_service = MagicMock()
            mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
                "Authentication failed"
            )
            mock_build.return_value = mock_service

            service = GmailService("test_user")

            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Authentication failed" in str(exc_info.value)

    @patch("cleanbox.email.gmail_service.build")
    @patch("cleanbox.email.gmail_service.get_current_account_id")
    @patch("cleanbox.email.gmail_service.get_user_credentials")
    def test_gmail_api_network_timeout(
        self, mock_get_credentials, mock_get_account_id, mock_build, app
    ):
        """Gmail API 네트워크 타임아웃 테스트"""
        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"

        with patch("cleanbox.auth.routes.current_user", mock_user):
            mock_get_account_id.return_value = 1
            # Google API Credentials 객체 모킹
            mock_credentials_obj = MagicMock()
            mock_credentials_obj.authorize.return_value = MagicMock()
            mock_get_credentials.return_value = mock_credentials_obj

            # 타임아웃 모의
            mock_service = MagicMock()
            mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
                "Request timeout"
            )
            mock_build.return_value = mock_service

            service = GmailService("test_user")

            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Request timeout" in str(exc_info.value)

    def test_email_with_malformed_gmail_response(self, app):
        """잘못된 Gmail 응답 처리 테스트"""
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            with patch(
                "cleanbox.email.gmail_service.get_current_account_id"
            ) as mock_account_id:
                mock_account_id.return_value = 1

                with patch(
                    "cleanbox.email.gmail_service.get_user_credentials"
                ) as mock_credentials:
                    # Google API Credentials 객체 모킹
                    mock_credentials_obj = MagicMock()
                    mock_credentials_obj.authorize.return_value = MagicMock()
                    mock_credentials.return_value = mock_credentials_obj

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

            # 사용자와 계정을 먼저 생성
            user = User(id="test_user", email="test@example.com")
            account = UserAccount(user_id=user.id, account_email="test@example.com")
            db.session.add_all([user, account])
            db.session.commit()

            # 이메일 저장 테스트
            email_obj = service.save_email_to_db(malformed_email_data)
            assert email_obj.subject == "제목 없음"  # 기본값
            assert email_obj.sender == "알 수 없는 발신자"  # 기본값


class TestAIClassifier:
    """AI 분류기 테스트"""

    @patch("cleanbox.email.ai_classifier.requests.post")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_email_classification(self, mock_environ, mock_requests, app):
        """이메일 분류 테스트 (Ollama 사용)"""

        # Ollama 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "CLEANBOX_USE_OLLAMA":
                return "true"
            elif key == "OLLAMA_URL":
                return "http://localhost:11434"
            elif key == "OLLAMA_MODEL":
                return "llama2"
            elif key == "OPENAI_API_KEY":
                return "test_api_key"  # OpenAI API 키도 설정
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        # Ollama 모의 응답 설정
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "카테고리ID: 1\n신뢰도: 85\n이유: 업무 관련 이메일"
        }
        mock_requests.return_value = mock_response

        classifier = AIClassifier()
        categories = [MagicMock(id=1, name="업무", description="업무 관련")]

        result = classifier.classify_email(
            "업무 관련 이메일입니다.", "회의 안내", "boss@company.com", categories
        )

        assert result[0] == 1  # 카테고리 ID
        assert "업무" in result[1]  # 이유

    @patch("cleanbox.email.ai_classifier.requests.post")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_email_summarization(self, mock_environ, mock_requests, app):
        """이메일 요약 테스트 (Ollama 사용)"""

        # Ollama 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "CLEANBOX_USE_OLLAMA":
                return "true"
            elif key == "OLLAMA_URL":
                return "http://localhost:11434"
            elif key == "OLLAMA_MODEL":
                return "llama2"
            elif key == "OPENAI_API_KEY":
                return "test_api_key"  # OpenAI API 키도 설정
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        # Ollama 모의 응답 설정
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "회의 일정 안내 이메일입니다."}
        mock_requests.return_value = mock_response

        classifier = AIClassifier()
        summary = classifier.summarize_email(
            "내일 오후 2시에 회의가 있습니다.", "회의 안내"
        )

        assert "회의" in summary

    @patch("cleanbox.email.ai_classifier.requests.post")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_ai_api_error_handling(self, mock_environ, mock_requests, app):
        """AI API 오류 처리 테스트 (Ollama 사용)"""

        # Ollama 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "CLEANBOX_USE_OLLAMA":
                return "true"
            elif key == "OLLAMA_URL":
                return "http://localhost:11434"
            elif key == "OLLAMA_MODEL":
                return "llama2"
            elif key == "OPENAI_API_KEY":
                return "test_api_key"  # OpenAI API 키도 설정
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        # API 오류 모의
        mock_requests.side_effect = Exception("AI API 오류")

        classifier = AIClassifier()
        result = classifier.classify_email(
            "테스트 이메일", "테스트", "test@example.com", []
        )

        assert result[0] is None
        assert "수동" in result[1]  # "수동으로 분류해주세요" 메시지 확인

    @patch("cleanbox.email.ai_classifier.requests.post")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_ai_api_timeout(self, mock_environ, mock_requests, app):
        """AI API 타임아웃 테스트 (Ollama 사용)"""

        # Ollama 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "CLEANBOX_USE_OLLAMA":
                return "true"
            elif key == "OLLAMA_URL":
                return "http://localhost:11434"
            elif key == "OLLAMA_MODEL":
                return "llama2"
            elif key == "OPENAI_API_KEY":
                return "test_api_key"  # OpenAI API 키도 설정
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        import time

        # 타임아웃 모의
        def timeout_request(*args, **kwargs):
            time.sleep(0.1)  # 빠른 테스트를 위해 시간 단축
            raise requests.exceptions.Timeout("요청 시간 초과")

        mock_requests.side_effect = timeout_request

        classifier = AIClassifier()
        result = classifier.classify_email(
            "테스트 이메일", "테스트", "test@example.com", []
        )

        assert result[0] is None
        assert "수동" in result[1]  # "수동으로 분류해주세요" 메시지 확인

    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_ai_with_empty_content(self, mock_environ, app):
        """빈 내용으로 AI 테스트 (Ollama 사용)"""

        # Ollama 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "CLEANBOX_USE_OLLAMA":
                return "true"
            elif key == "OLLAMA_URL":
                return "http://localhost:11434"
            elif key == "OLLAMA_MODEL":
                return "llama2"
            elif key == "OPENAI_API_KEY":
                return "test_api_key"  # OpenAI API 키도 설정
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        classifier = AIClassifier()
        result = classifier.classify_email("", "", "", [])

        assert result[0] is None

    @patch("cleanbox.email.ai_classifier.requests.post")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_ai_with_very_long_content(self, mock_environ, mock_requests, app):
        """매우 긴 내용으로 AI 테스트 (Ollama 사용)"""

        # Ollama 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "CLEANBOX_USE_OLLAMA":
                return "true"
            elif key == "OLLAMA_URL":
                return "http://localhost:11434"
            elif key == "OLLAMA_MODEL":
                return "llama2"
            elif key == "OPENAI_API_KEY":
                return "test_api_key"  # OpenAI API 키도 설정
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        # Ollama 모의 응답 설정
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "카테고리ID: 1\n신뢰도: 80\n이유: 긴 내용 분석 완료"
        }
        mock_requests.return_value = mock_response

        long_content = "A" * 10000  # 10KB 내용
        classifier = AIClassifier()
        result = classifier.classify_email(
            long_content,
            "긴 이메일",
            "test@example.com",
            [MagicMock(id=1, name="테스트")],
        )

        assert result[0] == 1

    def test_extract_unsubscribe_links(self, app):
        """구독해지 링크 추출 테스트"""
        classifier = AIClassifier()

        # HTML 이메일 내용
        html_content = """
        <html>
            <body>
                <a href="https://example.com/unsubscribe">구독해지</a>
                <a href="https://newsletter.com/opt-out">구독 취소</a>
                <p>다른 내용</p>
            </body>
        </html>
        """

        links = classifier.extract_unsubscribe_links(html_content)

        assert len(links) >= 2
        assert "unsubscribe" in links[0]
        assert "opt-out" in links[1]

    @patch("cleanbox.email.ai_classifier.requests.get")
    def test_analyze_unsubscribe_page(self, mock_get, app):
        """구독해지 페이지 분석 테스트"""
        classifier = AIClassifier()

        # 모의 HTML 응답
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = """
        <html>
            <head><title>구독해지</title></head>
            <body>
                <button>구독해지</button>
                <a href="/unsubscribe">구독해지 링크</a>
                <form action="/opt-out" method="post">
                    <input name="email" type="email">
                    <button type="submit">구독해지</button>
                </form>
            </body>
        </html>
        """
        mock_get.return_value = mock_response

        result = classifier.analyze_unsubscribe_page("https://example.com/unsubscribe")

        assert result["success"] == True
        assert len(result["unsubscribe_elements"]) > 0
        assert len(result["forms"]) > 0


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

        # JavaScript 페이지 모의 (구독해지 링크가 없는 경우)
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
            # JavaScript만 있고 실제 링크가 없으면 실패
            assert not result["success"]
            assert "구독해지 링크를 찾을 수 없습니다" in result["message"]

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
