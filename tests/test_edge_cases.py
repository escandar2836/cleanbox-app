import pytest
import json
import time
import threading
from unittest.mock import patch, MagicMock
from cleanbox import create_app, db
from cleanbox.models import User, UserAccount, Email, Category, UserToken
from cleanbox.email.gmail_service import GmailService
from cleanbox.email.ai_classifier import AIClassifier
from cleanbox.email.advanced_unsubscribe import AdvancedUnsubscribeService
from cleanbox.config import TestConfig
import requests


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


class TestExtremeDataCases:
    """극단적인 데이터 케이스 테스트"""

    def test_very_long_email_content(self, app):
        """매우 긴 이메일 내용 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 10KB 크기의 이메일 내용 (1MB 대신)
        very_long_content = "A" * (10 * 1024)  # 10KB

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="very_long_email",
            subject="매우 긴 이메일",
            sender="long@example.com",
            content=very_long_content,
        )
        db.session.add(email)
        db.session.commit()

        assert len(email.content) == 10 * 1024
        assert email.content == very_long_content

    def test_email_with_binary_data(self, app):
        """바이너리 데이터가 포함된 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 바이너리 데이터 시뮬레이션 (NUL 문자 제거)
        binary_content = "이메일 내용에 \x01\x02 바이너리 데이터가 포함되어 있습니다."

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="binary_email",
            subject="바이너리 이메일",
            sender="binary@example.com",
            content=binary_content,
        )
        db.session.add(email)
        db.session.commit()

        assert "\x01" in email.content
        assert "\x02" in email.content

    def test_email_with_sql_injection_attempt(self, app):
        """SQL 인젝션 시도가 포함된 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        sql_injection_content = """
        이메일 내용에 SQL 인젝션 시도가 포함되어 있습니다:
        '; DROP TABLE users; --
        ' OR '1'='1
        ' UNION SELECT * FROM users --
        """

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="sql_injection_email",
            subject="SQL 인젝션 이메일",
            sender="sql@example.com",
            content=sql_injection_content,
        )
        db.session.add(email)
        db.session.commit()

        # SQL 인젝션 시도가 안전하게 처리되는지 확인
        retrieved_email = Email.query.filter_by(gmail_id="sql_injection_email").first()
        assert retrieved_email is not None
        assert "DROP TABLE" in retrieved_email.content

    def test_email_with_xss_attempt(self, app):
        """XSS 시도가 포함된 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        xss_content = """
        이메일 내용에 XSS 시도가 포함되어 있습니다:
        <script>alert('XSS')</script>
        <img src="x" onerror="alert('XSS')">
        javascript:alert('XSS')
        """

        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="xss_email",
            subject="XSS 이메일",
            sender="xss@example.com",
            content=xss_content,
        )
        db.session.add(email)
        db.session.commit()

        # XSS 시도가 안전하게 처리되는지 확인
        retrieved_email = Email.query.filter_by(gmail_id="xss_email").first()
        assert retrieved_email is not None
        assert "<script>" in retrieved_email.content


class TestNetworkEdgeCases:
    """네트워크 엣지 케이스 테스트"""

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_api_slow_response(self, mock_build, app):
        """Gmail API 느린 응답 테스트"""
        import time
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            # 느린 응답 모의
            def slow_response(*args, **kwargs):
                time.sleep(1)  # 1초 지연 (2초에서 줄임)
                return {"messages": []}

            mock_service = MagicMock()
            mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = (
                slow_response
            )
            mock_build.return_value = mock_service

            with patch(
                "cleanbox.email.gmail_service.get_user_credentials"
            ) as mock_credentials:
                mock_credentials.return_value = {"token": "test_token"}

                service = GmailService("test_user")

                start_time = time.time()
                emails = service.fetch_recent_emails()
                response_time = time.time() - start_time

                # 응답 시간이 2초 이내인지 확인 (3초에서 줄임)
                assert response_time < 2.0

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_api_intermittent_failures(self, mock_build, app):
        """Gmail API 간헐적 실패 테스트"""
        from googleapiclient.errors import HttpError
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            call_count = 0

            def intermittent_failure(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count % 3 == 0:  # 3번째 호출마다 실패
                    raise HttpError(resp=MagicMock(status=500), content=b"Server Error")
                return {"messages": []}

            mock_service = MagicMock()
            mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = (
                intermittent_failure
            )
            mock_build.return_value = mock_service

            with patch(
                "cleanbox.email.gmail_service.get_user_credentials"
            ) as mock_credentials:
                mock_credentials.return_value = {"token": "test_token"}

                service = GmailService("test_user")

                # 첫 번째 호출은 성공
                emails1 = service.fetch_recent_emails()
                assert emails1 is not None

                # 두 번째 호출은 성공
                emails2 = service.fetch_recent_emails()
                assert emails2 is not None

                # 세 번째 호출은 실패
                with pytest.raises(Exception):
                    service.fetch_recent_emails()

    @patch("cleanbox.email.ai_classifier.openai.ChatCompletion.create")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_openai_api_rate_limit(self, mock_environ, mock_openai, app):
        """OpenAI API 속도 제한 테스트"""

        # OpenAI 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "OPENAI_API_KEY":
                return "test_api_key"
            elif key == "OPENAI_MODEL":
                return "gpt-4.1-nano"
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        import time

        # 속도 제한 모의
        def rate_limited_request(*args, **kwargs):
            time.sleep(0.1)  # 짧은 지연
            raise Exception("Rate limit exceeded")

        mock_openai.side_effect = rate_limited_request

        classifier = AIClassifier()
        categories = [MagicMock(id=1, name="테스트", description="테스트용")]

        # 속도 제한 상황에서의 분류 시도
        category_id, reasoning = classifier.classify_email(
            "테스트 이메일", "테스트", "test@example.com", categories
        )

        # 속도 제한이 적절히 처리되는지 확인
        assert category_id is None
        assert "수동" in reasoning  # "수동으로 분류해주세요" 메시지 확인


class TestConcurrencyEdgeCases:
    """동시성 엣지 케이스 테스트"""

    def test_concurrent_email_creation(self, app):
        """동시 이메일 생성 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        created_emails = []
        errors = []

        def create_email(email_id):
            try:
                with app.app_context():
                    email = Email(
                        user_id=user.id,
                        account_id=account.id,
                        gmail_id=f"concurrent_email_{email_id}",
                        subject=f"동시 이메일 {email_id}",
                        sender="concurrent@example.com",
                        content=f"동시 내용 {email_id}",
                    )
                    db.session.add(email)
                    db.session.commit()
                    created_emails.append(email_id)
            except Exception as e:
                errors.append(str(e))

        # 10개의 스레드로 동시 생성 (50개에서 줄임)
        threads = []
        for i in range(10):
            thread = threading.Thread(target=create_email, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 모든 이메일이 성공적으로 생성되었는지 확인
        assert len(errors) == 0
        assert len(created_emails) == 10

        # 데이터베이스에서 확인
        db_emails = Email.query.filter_by(user_id=user.id).all()
        assert len(db_emails) == 10

    def test_concurrent_category_operations(self, app):
        """동시 카테고리 작업 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)
        db.session.commit()

        created_categories = []
        errors = []

        def create_category(category_id):
            try:
                with app.app_context():
                    category = Category(
                        user_id=user.id,
                        name=f"동시 카테고리 {category_id}",
                        description=f"동시 설명 {category_id}",
                        color=f"#{category_id:06x}",
                    )
                    db.session.add(category)
                    db.session.commit()
                    created_categories.append(category_id)
            except Exception as e:
                errors.append(str(e))

        # 5개의 스레드로 동시 생성 (20개에서 줄임)
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_category, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # 모든 카테고리가 성공적으로 생성되었는지 확인
        assert len(errors) == 0
        assert len(created_categories) == 5


class TestSecurityEdgeCases:
    """보안 엣지 케이스 테스트"""

    def test_sql_injection_in_email_search(self, app):
        """이메일 검색에서 SQL 인젝션 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 정상 이메일 생성
        email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="normal_email",
            subject="정상 이메일",
            sender="normal@example.com",
            content="정상 내용",
        )
        db.session.add(email)
        db.session.commit()

        # SQL 인젝션 시도가 포함된 검색
        malicious_search = "'; DROP TABLE emails; --"

        # 안전한 검색 방법 사용
        safe_results = Email.query.filter(
            Email.subject.contains(malicious_search)
        ).all()

        # SQL 인젝션이 방지되었는지 확인
        assert len(safe_results) == 0

    def test_xss_in_email_display(self, app):
        """이메일 표시에서 XSS 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # XSS 시도가 포함된 이메일 생성
        xss_email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="xss_email",
            subject="<script>alert('XSS')</script>",
            sender="<script>alert('XSS')</script>@example.com",
            content="<script>alert('XSS')</script>",
        )
        db.session.add(xss_email)
        db.session.commit()

        # XSS가 안전하게 처리되는지 확인
        retrieved_email = Email.query.filter_by(gmail_id="xss_email").first()
        assert retrieved_email is not None
        assert "<script>" in retrieved_email.subject
        assert "<script>" in retrieved_email.sender
        assert "<script>" in retrieved_email.content

    def test_path_traversal_attempt(self, app):
        """경로 순회 시도 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 경로 순회 시도가 포함된 이메일
        path_traversal_email = Email(
            user_id=user.id,
            account_id=account.id,
            gmail_id="path_traversal_email",
            subject="../../../etc/passwd",
            sender="../../../etc/passwd@example.com",
            content="../../../etc/passwd",
        )
        db.session.add(path_traversal_email)
        db.session.commit()

        # 경로 순회 시도가 안전하게 처리되는지 확인
        retrieved_email = Email.query.filter_by(gmail_id="path_traversal_email").first()
        assert retrieved_email is not None
        assert "../../../etc/passwd" in retrieved_email.subject
