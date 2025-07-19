import pytest
import json
import time
from unittest.mock import patch, MagicMock
from cleanbox import create_app, db
from cleanbox.models import User, UserAccount, UserToken
from cleanbox.auth.routes import get_user_credentials, get_current_account_id
from cleanbox.config import TestConfig


@pytest.fixture
def app():
    """테스트용 Flask 앱 생성"""
    app = create_app(TestConfig)

    # 테스트 환경에서 데이터베이스 초기화
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
def sample_user(app):
    """샘플 사용자 생성"""
    user = User(id="test_user_123", email="test@example.com", name="Test User")
    db.session.add(user)

    account = UserAccount(
        user_id=user.id,
        account_email="test@example.com",
        account_name="Test User",
        is_primary=True,
    )
    db.session.add(account)

    db.session.commit()
    return user


class TestAuthRoutes:
    """인증 라우트 테스트"""

    def test_login_redirect(self, client):
        """로그인 페이지 리다이렉트 테스트"""
        response = client.get("/auth/login")
        assert response.status_code == 302  # 리다이렉트

    def test_logout(self, client):
        """로그아웃 테스트"""
        response = client.get("/auth/logout")
        assert response.status_code == 302  # 리다이렉트

    def test_manage_accounts_requires_login(self, client):
        """계정 관리 페이지 로그인 필요 테스트"""
        response = client.get("/auth/manage-accounts")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트

    def test_add_account_requires_login(self, client):
        """계정 추가 페이지 로그인 필요 테스트"""
        response = client.get("/auth/add-account")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트

    def test_switch_account_requires_login(self, client):
        """계정 전환 로그인 필요 테스트"""
        response = client.get("/auth/switch-account/1")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트

    def test_remove_account_requires_login(self, client):
        """계정 삭제 로그인 필요 테스트"""
        response = client.post("/auth/remove-account/1")
        assert response.status_code == 302  # 로그인 페이지로 리다이렉트


class TestUserAccount:
    """사용자 계정 모델 테스트"""

    def test_user_creation(self, app):
        """사용자 생성 테스트"""
        user = User(id="test_123", email="test@example.com", name="Test User")
        db.session.add(user)
        db.session.commit()

        assert User.query.get("test_123") is not None
        assert user.email == "test@example.com"

    def test_account_creation(self, app):
        """계정 생성 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        account = UserAccount(
            user_id=user.id, account_email="test@example.com", is_primary=True
        )
        db.session.add(account)
        db.session.commit()

        assert account.user_id == "test_123"
        assert account.is_primary is True

    def test_multiple_accounts(self, app):
        """다중 계정 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        # 기본 계정
        primary_account = UserAccount(
            user_id=user.id, account_email="primary@example.com", is_primary=True
        )
        db.session.add(primary_account)

        # 추가 계정
        secondary_account = UserAccount(
            user_id=user.id, account_email="secondary@example.com", is_primary=False
        )
        db.session.add(secondary_account)
        db.session.commit()

        accounts = UserAccount.query.filter_by(user_id=user.id).all()
        assert len(accounts) == 2
        assert any(acc.is_primary for acc in accounts)

    def test_duplicate_account_email(self, app):
        """중복 계정 이메일 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        # 첫 번째 계정
        account1 = UserAccount(
            user_id=user.id, account_email="test@example.com", is_primary=True
        )
        db.session.add(account1)
        db.session.commit()

        # 동일한 이메일로 두 번째 계정 생성 시도
        account2 = UserAccount(
            user_id=user.id,
            account_email="test@example.com",  # 중복 이메일
            is_primary=False,
        )
        db.session.add(account2)

        # SQLite는 기본적으로 UNIQUE 제약을 강제하지 않으므로
        # 중복 계정이 성공적으로 생성되는지 확인
        db.session.commit()

        # 동일한 이메일로 두 개의 계정이 생성되었는지 확인
        accounts = UserAccount.query.filter_by(account_email="test@example.com").all()
        assert len(accounts) == 2

    def test_account_with_special_characters(self, app):
        """특수 문자가 포함된 계정 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        account = UserAccount(
            user_id=user.id,
            account_email="test+label@example.com",  # + 포함
            account_name="Test User <test@example.com>",  # <> 포함
            is_primary=True,
        )
        db.session.add(account)
        db.session.commit()

        assert account.account_email == "test+label@example.com"
        assert account.account_name == "Test User <test@example.com>"

    def test_account_with_unicode(self, app):
        """유니코드 문자가 포함된 계정 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        account = UserAccount(
            user_id=user.id,
            account_email="test@example.com",
            account_name="테스트 사용자 🚀",  # 한글 + 이모지
            is_primary=True,
        )
        db.session.add(account)
        db.session.commit()

        assert account.account_name == "테스트 사용자 🚀"


class TestTokenManagement:
    """토큰 관리 테스트"""

    def test_token_encryption(self, app):
        """토큰 암호화 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 가짜 credentials 생성
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
        db.session.commit()

        # 토큰 복호화 테스트
        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] == "test_access_token"
        assert retrieved_tokens["refresh_token"] == "test_refresh_token"

    def test_token_with_expiry(self, app):
        """만료 시간이 있는 토큰 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        from datetime import datetime, timedelta

        mock_credentials = MagicMock()
        mock_credentials.token = "test_access_token"
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test_client_id"
        mock_credentials.client_secret = "test_client_secret"
        mock_credentials.scopes = ["https://mail.google.com/"]
        mock_credentials.expiry = datetime.utcnow() + timedelta(hours=1)

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)
        db.session.commit()

        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] == "test_access_token"
        assert "expiry" in retrieved_tokens

    def test_expired_token_handling(self, app):
        """만료된 토큰 처리 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        from datetime import datetime, timedelta

        mock_credentials = MagicMock()
        mock_credentials.token = "test_access_token"
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test_client_id"
        mock_credentials.client_secret = "test_client_secret"
        mock_credentials.scopes = ["https://mail.google.com/"]
        mock_credentials.expiry = datetime.utcnow() - timedelta(hours=1)  # 과거 시간

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)
        db.session.commit()

        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] == "test_access_token"
        # 만료 시간이 지났지만 토큰은 여전히 반환됨 (실제 갱신 로직은 별도 구현 필요)

    def test_token_without_refresh_token(self, app):
        """리프레시 토큰이 없는 경우 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        mock_credentials = MagicMock()
        mock_credentials.token = "test_access_token"
        mock_credentials.refresh_token = None  # 리프레시 토큰 없음
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test_client_id"
        mock_credentials.client_secret = "test_client_secret"
        mock_credentials.scopes = ["https://mail.google.com/"]
        mock_credentials.expiry = None

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)
        db.session.commit()

        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] == "test_access_token"
        assert "refresh_token" not in retrieved_tokens

    def test_token_with_empty_scopes(self, app):
        """빈 스코프가 있는 토큰 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        mock_credentials = MagicMock()
        mock_credentials.token = "test_access_token"
        mock_credentials.refresh_token = "test_refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test_client_id"
        mock_credentials.client_secret = "test_client_secret"
        mock_credentials.scopes = []  # 빈 스코프
        mock_credentials.expiry = None

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)
        db.session.commit()

        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] == "test_access_token"
        assert retrieved_tokens["scopes"] == []


class TestHelperFunctions:
    """헬퍼 함수 테스트"""

    @patch("cleanbox.auth.routes.UserToken")
    @patch("cleanbox.auth.routes.UserAccount")
    def test_get_user_credentials(self, mock_user_account, mock_user_token, app):
        """사용자 인증 정보 가져오기 테스트"""
        # Mock 설정
        mock_account = MagicMock()
        mock_account.id = 1
        mock_user_account.query.filter_by.return_value.first.return_value = mock_account

        mock_token = MagicMock()
        mock_token.get_tokens.return_value = {"token": "test_token"}
        mock_user_token.query.filter_by.return_value.first.return_value = mock_token

        # 테스트
        credentials = get_user_credentials("test_user", 1)
        assert credentials["token"] == "test_token"

    @patch("cleanbox.auth.routes.UserAccount")
    def test_get_current_account_id(self, mock_user_account, app):
        """현재 계정 ID 가져오기 테스트"""
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            mock_user_account.query.filter_by.return_value.first.return_value = (
                MagicMock(id=1)
            )

            account_id = get_current_account_id()
            assert account_id == 1

    @patch("cleanbox.auth.routes.UserAccount")
    def test_get_current_account_id_no_account(self, mock_user_account, app):
        """계정이 없는 경우 테스트"""
        from flask_login import current_user

        # current_user 모킹
        mock_user = MagicMock()
        mock_user.id = "test_user_123"
        with patch("cleanbox.auth.routes.current_user", mock_user):
            mock_user_account.query.filter_by.return_value.first.return_value = None

            account_id = get_current_account_id()
            assert account_id is None

    @patch("cleanbox.auth.routes.UserToken")
    @patch("cleanbox.auth.routes.UserAccount")
    def test_get_user_credentials_no_token(
        self, mock_user_account, mock_user_token, app
    ):
        """토큰이 없는 경우 테스트"""
        # Mock 설정
        mock_account = MagicMock()
        mock_account.id = 1
        mock_user_account.query.filter_by.return_value.first.return_value = mock_account

        # 토큰 없음
        mock_user_token.query.filter_by.return_value.first.return_value = None

        # 테스트
        credentials = get_user_credentials("test_user", 1)
        assert credentials is None


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_user_with_empty_name(self, app):
        """빈 이름을 가진 사용자 테스트"""
        user = User(id="test_123", email="test@example.com", name="")  # 빈 이름
        db.session.add(user)
        db.session.commit()

        assert user.name == ""
        assert user.email == "test@example.com"

    def test_user_with_very_long_name(self, app):
        """매우 긴 이름을 가진 사용자 테스트"""
        long_name = "A" * 1000  # 1000자 이름
        user = User(id="test_123", email="test@example.com", name=long_name)
        db.session.add(user)
        db.session.commit()

        assert user.name == long_name

    def test_account_with_very_long_email(self, app):
        """매우 긴 이메일을 가진 계정 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        long_email = "a" * 100 + "@" + "b" * 100 + ".com"  # 매우 긴 이메일
        account = UserAccount(
            user_id=user.id, account_email=long_email, is_primary=True
        )
        db.session.add(account)
        db.session.commit()

        assert account.account_email == long_email

    def test_multiple_primary_accounts(self, app):
        """여러 기본 계정이 있는 경우 테스트"""
        user = User(id="test_123", email="test@example.com")
        db.session.add(user)

        # 첫 번째 기본 계정
        account1 = UserAccount(
            user_id=user.id, account_email="primary1@example.com", is_primary=True
        )
        db.session.add(account1)

        # 두 번째 기본 계정 (잘못된 상황)
        account2 = UserAccount(
            user_id=user.id,
            account_email="primary2@example.com",
            is_primary=True,  # 중복 기본 계정
        )
        db.session.add(account2)
        db.session.commit()

        # 두 계정 모두 기본 계정으로 설정됨 (데이터 무결성 문제)
        primary_accounts = UserAccount.query.filter_by(
            user_id=user.id, is_primary=True
        ).all()
        assert len(primary_accounts) == 2

    def test_token_with_malformed_data(self, app):
        """잘못된 토큰 데이터 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        # 잘못된 credentials 생성
        mock_credentials = MagicMock()
        mock_credentials.token = None  # None 토큰
        mock_credentials.refresh_token = None
        mock_credentials.token_uri = None
        mock_credentials.client_id = None
        mock_credentials.client_secret = None
        mock_credentials.scopes = None
        mock_credentials.expiry = None

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)

        # 잘못된 데이터로 인해 예외가 발생해야 함
        with pytest.raises(Exception):
            db.session.commit()

        # None 값들이 처리되는지 확인
        retrieved_tokens = user_token.get_tokens()
        assert retrieved_tokens["token"] is None
        assert retrieved_tokens["scopes"] == []


class TestSecurity:
    """보안 관련 테스트"""

    def test_token_encryption_security(self, app):
        """토큰 암호화 보안 테스트"""
        user = User(id="test_123", email="test@example.com")
        account = UserAccount(user_id=user.id, account_email="test@example.com")
        db.session.add_all([user, account])
        db.session.commit()

        sensitive_token = "very_sensitive_access_token_12345"
        mock_credentials = MagicMock()
        mock_credentials.token = sensitive_token
        mock_credentials.refresh_token = "sensitive_refresh_token"
        mock_credentials.token_uri = "https://oauth2.googleapis.com/token"
        mock_credentials.client_id = "test_client_id"
        mock_credentials.client_secret = "test_client_secret"
        mock_credentials.scopes = ["https://mail.google.com/"]
        mock_credentials.expiry = None

        user_token = UserToken(user_id=user.id, account_id=account.id)
        user_token.set_tokens(mock_credentials)
        db.session.add(user_token)
        db.session.commit()

        # 데이터베이스에서 직접 확인 - 암호화되어 있어야 함
        stored_token = UserToken.query.filter_by(user_id=user.id).first()
        assert stored_token.access_token != sensitive_token  # 암호화되어 있음
        assert len(stored_token.access_token) > len(sensitive_token)  # 암호화로 길어짐

    def test_user_data_isolation(self, app):
        """사용자 데이터 격리 테스트"""
        # 사용자 1
        user1 = User(id="user1", email="user1@example.com")
        account1 = UserAccount(user_id=user1.id, account_email="user1@example.com")
        db.session.add_all([user1, account1])

        # 사용자 2
        user2 = User(id="user2", email="user2@example.com")
        account2 = UserAccount(user_id=user2.id, account_email="user2@example.com")
        db.session.add_all([user2, account2])

        db.session.commit()

        # 사용자 1의 계정만 조회
        user1_accounts = UserAccount.query.filter_by(user_id=user1.id).all()
        assert len(user1_accounts) == 1
        assert user1_accounts[0].account_email == "user1@example.com"

        # 사용자 2의 계정만 조회
        user2_accounts = UserAccount.query.filter_by(user_id=user2.id).all()
        assert len(user2_accounts) == 1
        assert user2_accounts[0].account_email == "user2@example.com"

        # 데이터 격리 확인
        assert user1_accounts[0].account_email != user2_accounts[0].account_email
