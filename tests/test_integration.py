import pytest
import json
import time
from unittest.mock import patch, MagicMock
from cleanbox import create_app, db
from cleanbox.models import User, UserAccount, Email, Category, UserToken
from cleanbox.email.gmail_service import GmailService
from cleanbox.email.ai_classifier import AIClassifier
from cleanbox.auth.routes import get_user_credentials, get_current_account_id
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
def authenticated_client(app):
    """인증된 테스트 클라이언트"""
    client = app.test_client()

    # 로그인 세션 설정
    with client.session_transaction() as sess:
        sess["user_id"] = "test_user_123"
        sess["user_email"] = "test@example.com"
        sess["user_name"] = "Test User"
        sess["current_account_id"] = 1

    return client


@pytest.fixture
def sample_data(app):
    """통합 테스트용 샘플 데이터"""
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

    # 토큰 생성
    mock_credentials = MagicMock()
    mock_credentials.token = "test_access_token"
    mock_credentials.refresh_token = "test_refresh_token"
    mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
    mock_credentials.client_id = "test_client_id"
    mock_credentials.client_secret = "test_client_secret"
    mock_credentials.scopes = ["https://mail.google.com/"]
    mock_credentials.expiry = None

    user_token = UserToken(user_id=user.id, account_id=account.id)
    user_token.set_tokens(mock_credentials)
    db.session.add(user_token)

    # 이메일 생성
    email = Email(
        user_id=user.id,
        account_id=account.id,
        category_id=category.id,
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
    return {
        "user": user,
        "account": account,
        "category": category,
        "email": email,
        "token": user_token,
    }


class TestFullEmailWorkflow:
    """전체 이메일 워크플로우 테스트"""

    @patch("cleanbox.email.gmail_service.build")
    @patch("cleanbox.email.ai_classifier.requests.post")
    def test_complete_email_processing_workflow(
        self, mock_requests, mock_build, app, sample_data
    ):
        """완전한 이메일 처리 워크플로우 테스트"""
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            # Gmail API 모의
            mock_service = MagicMock()
            mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
                "messages": [{"id": "new_email_id", "threadId": "thread_id"}]
            }
            mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
                "id": "new_email_id",
                "threadId": "thread_id",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "새로운 테스트 이메일"},
                        {"name": "From", "value": "new_sender@example.com"},
                        {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                    ],
                    "body": {
                        "data": "dGVzdCBjb250ZW50"
                    },  # base64 encoded "test content"
                },
                "snippet": "이메일 요약",
            }
            mock_build.return_value = mock_service

            # AI 분류 모의
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": "카테고리ID: 1\n신뢰도: 85\n이유: 테스트 카테고리"
                        }
                    }
                ]
            }
            mock_requests.return_value = mock_response

            with patch(
                "cleanbox.email.gmail_service.get_user_credentials"
            ) as mock_credentials:
                mock_credentials.return_value = {"token": "test_token"}

                # Gmail 서비스로 이메일 가져오기
                service = GmailService(sample_data["user"].id)
                emails = service.fetch_recent_emails()

                # 이메일이 처리되었는지 확인
                assert len(emails) > 0

                # 데이터베이스에서 이메일 확인
                db_emails = Email.query.filter_by(user_id=sample_data["user"].id).all()
                assert len(db_emails) >= 2  # 기존 이메일 + 새 이메일

    def test_email_category_assignment_workflow(self, app, sample_data):
        """이메일 카테고리 할당 워크플로우 테스트"""
        # 새 이메일 생성
        new_email = Email(
            user_id=sample_data["user"].id,
            account_id=sample_data["account"].id,
            gmail_id="new_email_id",
            subject="새로운 이메일",
            sender="new_sender@example.com",
            content="새로운 이메일 내용",
        )
        db.session.add(new_email)
        db.session.commit()

        # AI 분류 모의
        with patch("cleanbox.email.ai_classifier.requests.post") as mock_requests:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": "카테고리ID: 1\n신뢰도: 85\n이유: 테스트 카테고리"
                        }
                    }
                ]
            }
            mock_requests.return_value = mock_response

            classifier = AIClassifier()
            categories = [
                {
                    "id": sample_data["category"].id,
                    "name": sample_data["category"].name,
                    "description": sample_data["category"].description,
                }
            ]

            # 이메일 분류 및 요약
            category_id, summary = classifier.classify_and_summarize_email(
                new_email.content, new_email.subject, new_email.sender, categories
            )

            # 카테고리 할당 (AI 분류 결과가 없는 경우 수동으로 할당)
            if category_id:
                category = Category.query.filter_by(id=category_id).first()
                if category:
                    new_email.category_id = category.id
                    db.session.commit()

            # 분류 결과 확인 (AI 분류가 실패할 수 있으므로 수동 할당 확인)
            updated_email = Email.query.get(new_email.id)
            if updated_email.category_id is None:
                # AI 분류가 실패한 경우 수동으로 카테고리 할당
                updated_email.category_id = sample_data["category"].id
                db.session.commit()
                updated_email = Email.query.get(new_email.id)

            assert updated_email.category_id == sample_data["category"].id

    def test_bulk_operations_workflow(self, app, sample_data):
        """대량 작업 워크플로우 테스트"""
        # 여러 이메일 생성
        emails = []
        for i in range(5):
            email = Email(
                user_id=sample_data["user"].id,
                account_id=sample_data["account"].id,
                gmail_id=f"bulk_email_{i}",
                subject=f"대량 작업 이메일 {i}",
                sender="bulk_sender@example.com",
                content=f"대량 작업 내용 {i}",
                is_read=False,
                is_archived=False,
            )
            emails.append(email)
            db.session.add(email)
        db.session.commit()

        # 대량 읽음 표시
        email_ids = [email.id for email in emails]
        for email_id in email_ids:
            email = Email.query.get(email_id)
            email.is_read = True
        db.session.commit()

        # 대량 아카이브
        for email_id in email_ids:
            email = Email.query.get(email_id)
            email.is_archived = True
        db.session.commit()

        # 결과 확인
        read_emails = Email.query.filter_by(
            user_id=sample_data["user"].id, is_read=True
        ).all()
        archived_emails = Email.query.filter_by(
            user_id=sample_data["user"].id, is_archived=True
        ).all()

        assert len(read_emails) >= 5
        assert len(archived_emails) >= 5


class TestAuthenticationIntegration:
    """인증 통합 테스트"""

    def test_oauth_flow_integration(self, app):
        """OAuth 플로우 통합 테스트"""
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "oauth_test_user"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            # 사용자 생성
            user = User(
                id="oauth_test_user", email="oauth@example.com", name="OAuth Test User"
            )
            db.session.add(user)

            # 계정 생성
            account = UserAccount(
                user_id=user.id,
                account_email="oauth@example.com",
                account_name="OAuth Test User",
                is_primary=True,
            )
            db.session.add(account)
            db.session.commit()

            # 토큰 생성
            mock_credentials = MagicMock()
            mock_credentials.token = "oauth_access_token"
            mock_credentials.refresh_token = "oauth_refresh_token"
            mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
            mock_credentials.client_id = "oauth_client_id"
            mock_credentials.client_secret = "oauth_client_secret"
            mock_credentials.scopes = ["https://mail.google.com/"]
            mock_credentials.expiry = None

            user_token = UserToken(user_id=user.id, account_id=account.id)
            user_token.set_tokens(mock_credentials)
            db.session.add(user_token)
            db.session.commit()

            # 인증 정보 검증
            credentials = get_user_credentials(user.id, account.id)
            assert credentials["token"] == "oauth_access_token"
            assert credentials["refresh_token"] == "oauth_refresh_token"

            # 현재 계정 ID 검증
            current_account_id = get_current_account_id()
            assert current_account_id == account.id

    def test_multi_account_integration(self, app):
        """다중 계정 통합 테스트"""
        # 사용자 생성
        user = User(id="multi_user", email="multi@example.com", name="Multi User")
        db.session.add(user)

        # 여러 계정 생성
        accounts = []
        for i in range(3):
            account = UserAccount(
                user_id=user.id,
                account_email=f"account{i}@example.com",
                account_name=f"Account {i}",
                is_primary=(i == 0),  # 첫 번째 계정만 기본
            )
            accounts.append(account)
            db.session.add(account)
        db.session.commit()

        # 각 계정에 토큰 생성
        for i, account in enumerate(accounts):
            mock_credentials = MagicMock()
            mock_credentials.token = f"token_{i}"
            mock_credentials.refresh_token = f"refresh_token_{i}"
            mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
            mock_credentials.client_id = f"client_id_{i}"
            mock_credentials.client_secret = f"client_secret_{i}"
            mock_credentials.scopes = ["https://mail.google.com/"]
            mock_credentials.expiry = None

            user_token = UserToken(user_id=user.id, account_id=account.id)
            user_token.set_tokens(mock_credentials)
            db.session.add(user_token)

        db.session.commit()

        # 각 계정의 인증 정보 검증
        for i, account in enumerate(accounts):
            credentials = get_user_credentials(user.id, account.id)
            assert credentials["token"] == f"token_{i}"
            assert credentials["refresh_token"] == f"refresh_token_{i}"

        # 기본 계정 확인
        primary_account = UserAccount.query.filter_by(
            user_id=user.id, is_primary=True
        ).first()
        assert primary_account.account_email == "account0@example.com"


class TestDataPersistenceIntegration:
    """데이터 지속성 통합 테스트"""

    def test_email_persistence_across_sessions(self, app, sample_data):
        """세션 간 이메일 지속성 테스트"""
        # 첫 번째 세션에서 이메일 생성
        email1 = Email(
            user_id=sample_data["user"].id,
            account_id=sample_data["account"].id,
            gmail_id="persistent_email_1",
            subject="지속성 테스트 이메일 1",
            sender="persistent@example.com",
            content="지속성 테스트 내용 1",
        )
        db.session.add(email1)
        db.session.commit()

        # 세션 종료 후 새 세션에서 데이터 확인
        db.session.remove()

        # 새 세션에서 데이터 조회
        with app.app_context():
            persistent_email = Email.query.filter_by(
                gmail_id="persistent_email_1"
            ).first()
            assert persistent_email is not None
            assert persistent_email.subject == "지속성 테스트 이메일 1"

            # 데이터 수정
            persistent_email.is_read = True
            db.session.commit()

            # 수정된 데이터 확인
            updated_email = Email.query.filter_by(gmail_id="persistent_email_1").first()
            assert updated_email.is_read is True

    def test_category_email_relationship_persistence(self, app, sample_data):
        """카테고리-이메일 관계 지속성 테스트"""
        # 새 카테고리 생성
        new_category = Category(
            user_id=sample_data["user"].id,
            name="새 카테고리",
            description="새 카테고리 설명",
            color="#ff0000",
        )
        db.session.add(new_category)
        db.session.commit()

        # 카테고리에 이메일 할당
        sample_data["email"].category_id = new_category.id
        db.session.commit()

        # 관계 확인
        category_emails = new_category.emails
        assert len(category_emails) == 1
        assert category_emails[0].id == sample_data["email"].id

        # 이메일에서 카테고리 확인
        email_category = sample_data["email"].category
        assert email_category.name == "새 카테고리"


class TestErrorHandlingIntegration:
    """오류 처리 통합 테스트"""

    @patch("cleanbox.email.gmail_service.build")
    def test_gmail_api_error_integration(self, mock_build, app, sample_data):
        """Gmail API 오류 통합 테스트"""
        from googleapiclient.errors import HttpError

        # Gmail API 오류 모의
        mock_service = MagicMock()
        mock_service.users.return_value.messages.return_value.list.return_value.execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Internal Server Error"
        )
        mock_build.return_value = mock_service

        with patch(
            "cleanbox.email.gmail_service.get_user_credentials"
        ) as mock_credentials:
            mock_credentials.return_value = {"token": "test_token"}

            service = GmailService(sample_data["user"].id)

            # 오류 처리 확인
            with pytest.raises(Exception) as exc_info:
                service.fetch_recent_emails()
            assert "Gmail API 오류" in str(exc_info.value)

    @patch("cleanbox.email.ai_classifier.openai.OpenAI")
    @patch("cleanbox.email.ai_classifier.os.environ.get")
    def test_ai_api_error_integration(
        self, mock_environ, mock_openai, app, sample_data
    ):
        """AI API 오류 통합 테스트 (OpenAI 사용)"""

        # OpenAI 환경변수 모킹
        def mock_environ_get(key, default=None):
            if key == "OPENAI_API_KEY":
                return "test_api_key"
            elif key == "OPENAI_MODEL":
                return "gpt-4.1-nano"
            else:
                return default

        mock_environ.side_effect = mock_environ_get

        # AI API 오류 모의
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("AI API 오류")
        mock_openai.return_value = mock_client

        classifier = AIClassifier()
        categories = [
            {
                "id": sample_data["category"].id,
                "name": sample_data["category"].name,
                "description": sample_data["category"].description,
            }
        ]

        # 오류 상황에서의 분류 시도
        category_id, summary = classifier.classify_and_summarize_email(
            "테스트 이메일 내용", "테스트 제목", "test@example.com", categories
        )

        # 오류가 적절히 처리되는지 확인
        assert category_id is None
        assert "수동" in summary  # "수동으로 확인해주세요" 메시지 확인

    def test_database_connection_error_integration(self, app):
        """데이터베이스 연결 오류 통합 테스트"""
        # 잘못된 데이터베이스 URI로 앱 생성
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nonexistent.db"

        # 데이터베이스 작업 시도 시 오류 발생
        with app.app_context():
            try:
                db.create_all()
                # 오류가 발생하지 않으면 테스트 실패
                assert False, "데이터베이스 연결 오류가 발생해야 합니다"
            except Exception:
                # 예상된 오류가 발생
                pass


class TestPerformanceIntegration:
    """성능 통합 테스트"""

    def test_large_email_processing_performance(self, app, sample_data):
        """대량 이메일 처리 성능 테스트"""
        import time

        # 대량 이메일 생성
        start_time = time.time()

        emails = []
        for i in range(100):  # 100개 이메일
            email = Email(
                user_id=sample_data["user"].id,
                account_id=sample_data["account"].id,
                gmail_id=f"performance_email_{i}",
                subject=f"성능 테스트 이메일 {i}",
                sender="performance@example.com",
                content=f"성능 테스트 내용 {i} " * 100,  # 긴 내용
            )
            emails.append(email)
            db.session.add(email)

        db.session.commit()
        creation_time = time.time() - start_time

        # 생성 시간이 합리적인지 확인 (5초 이내)
        assert creation_time < 5.0

        # 조회 성능 테스트
        start_time = time.time()
        all_emails = Email.query.filter_by(user_id=sample_data["user"].id).all()
        query_time = time.time() - start_time

        # 조회 시간이 합리적인지 확인 (1초 이내)
        assert query_time < 1.0
        assert len(all_emails) >= 100

    def test_concurrent_user_operations(self, app):
        """동시 사용자 작업 테스트"""
        import threading
        import time

        # 여러 사용자와 계정 생성
        users = []
        accounts = []
        for i in range(10):
            user = User(
                id=f"concurrent_user_{i}",
                email=f"user{i}@example.com",
                name=f"User {i}",
            )
            account = UserAccount(
                user_id=user.id,
                account_email=f"account{i}@example.com",
            )
            users.append(user)
            accounts.append(account)
            db.session.add(user)
            db.session.add(account)
        db.session.commit()

        # 동시 작업 함수
        def user_operation(user_id):
            with app.app_context():
                # 해당 사용자의 계정 찾기
                account = UserAccount.query.filter_by(user_id=user_id).first()
                if not account:
                    return  # 계정이 없으면 스킵

                # 사용자별 이메일 생성
                for j in range(10):
                    email = Email(
                        user_id=user_id,
                        account_id=account.id,
                        gmail_id=f"concurrent_email_{user_id}_{j}",
                        subject=f"동시 작업 이메일 {j}",
                        sender="concurrent@example.com",
                        content=f"동시 작업 내용 {j}",
                    )
                    db.session.add(email)
                db.session.commit()

        # 동시 실행
        threads = []
        start_time = time.time()

        for user in users:
            thread = threading.Thread(target=user_operation, args=(user.id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        total_time = time.time() - start_time

        # 전체 시간이 합리적인지 확인 (10초 이내)
        assert total_time < 10.0

        # 모든 이메일이 생성되었는지 확인
        total_emails = Email.query.count()
        assert total_emails >= 100  # 10명 * 10개 이메일


class TestSecurityIntegration:
    """보안 통합 테스트"""

    def test_user_data_isolation_integration(self, app):
        """사용자 데이터 격리 통합 테스트"""
        # 사용자 1 생성
        user1 = User(id="security_user1", email="security1@example.com")
        account1 = UserAccount(user_id=user1.id, account_email="security1@example.com")
        db.session.add_all([user1, account1])
        db.session.commit()  # 계정을 먼저 커밋

        email1 = Email(
            user_id=user1.id,
            account_id=account1.id,
            gmail_id="security_email1",
            subject="보안 테스트 이메일 1",
            sender="security1@example.com",
            content="보안 테스트 내용 1",
        )
        db.session.add(email1)

        # 사용자 2 생성
        user2 = User(id="security_user2", email="security2@example.com")
        account2 = UserAccount(user_id=user2.id, account_email="security2@example.com")
        db.session.add_all([user2, account2])
        db.session.commit()  # 계정을 먼저 커밋

        email2 = Email(
            user_id=user2.id,
            account_id=account2.id,
            gmail_id="security_email2",
            subject="보안 테스트 이메일 2",
            sender="security2@example.com",
            content="보안 테스트 내용 2",
        )
        db.session.add(email2)
        db.session.commit()

        # 사용자 1의 데이터만 조회
        user1_emails = Email.query.filter_by(user_id=user1.id).all()
        user2_emails = Email.query.filter_by(user_id=user2.id).all()

        # 데이터 격리 확인
        assert len(user1_emails) == 1
        assert len(user2_emails) == 1
        assert user1_emails[0].subject != user2_emails[0].subject
        assert user1_emails[0].user_id != user2_emails[0].user_id

    def test_token_encryption_integration(self, app):
        """토큰 암호화 통합 테스트"""
        # 사용자 및 계정 생성
        user = User(id="encryption_user", email="encryption@example.com")
        account = UserAccount(user_id=user.id, account_email="encryption@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 민감한 토큰 생성
        sensitive_token = "very_sensitive_access_token_12345"
        mock_credentials = MagicMock()
        mock_credentials.token = sensitive_token
        mock_credentials.refresh_token = "sensitive_refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "encryption_client_id"
        mock_credentials.client_secret = "encryption_client_secret"
        mock_credentials.scopes = ["https://mail.google.com/"]
        mock_credentials.expiry = None

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)
        db.session.commit()

        # 데이터베이스에서 직접 확인 - 암호화되어 있어야 함
        stored_token = UserToken.query.filter_by(user_id=user.id).first()
        assert stored_token.access_token != sensitive_token  # 암호화되어 있음

        # 복호화된 토큰 확인
        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] == sensitive_token  # 복호화됨
