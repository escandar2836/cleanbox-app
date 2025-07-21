import pytest
from flask_login import login_user
from cleanbox.models import User, UserAccount, db
from cleanbox import create_app
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    app = create_app(testing=True)
    with app.app_context():
        db.drop_all()
        db.create_all()
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_test_user(app, client):
    with app.app_context():
        user = User(id="123", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        account = UserAccount(
            user_id=user.id,
            account_email="test@example.com",
            is_primary=True,
            is_active=True,
        )
        db.session.add(account)
        db.session.commit()
        login_user(user)
        yield user


class TestAuth:
    def test_login_redirects_to_google(self, client):
        # 로그인 페이지 접근 시 Google OAuth로 리다이렉트 되는지
        response = client.get("/auth/login", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "accounts.google.com" in response.location

    @patch("cleanbox.auth.routes.Flow")
    def test_callback_success(self, mock_flow, client, login_test_user):
        # OAuth 콜백 성공 시 대시보드로 이동
        from datetime import datetime, timedelta

        # 실제 구조에 맞는 mock credentials 생성
        mock_creds = MagicMock()
        mock_creds.id_token = "dummy_token"
        mock_creds.token = "access_token"
        mock_creds.refresh_token = "refresh_token"
        mock_creds.token_uri = "https://oauth2.googleapis.com/token"
        mock_creds.client_id = "test-client-id"
        mock_creds.client_secret = "test-client-secret"
        mock_creds.scopes = ["openid", "email"]
        mock_creds.expiry = datetime.utcnow() + timedelta(hours=1)
        mock_flow.from_client_config.return_value = MagicMock()
        mock_flow.from_client_config.return_value.fetch_token.return_value = None
        mock_flow.from_client_config.return_value.credentials = mock_creds
        with patch("cleanbox.auth.routes.id_token.verify_oauth2_token") as mock_verify:
            mock_verify.return_value = {"sub": "123", "email": "test@example.com"}
            # session['state'] 미리 세팅
            with client.session_transaction() as sess:
                sess["state"] = "abc"
            response = client.get(
                "/auth/callback?state=abc&code=xyz", follow_redirects=False
            )
            assert response.status_code in (302, 303)
            # 대시보드로 리다이렉트되는지 확인
            assert "/main/dashboard" in response.location

    def test_callback_state_missing(self, client):
        # state가 없으면 에러 플래시 및 로그인 페이지로 리다이렉트
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/auth/login" in response.location

    @patch("cleanbox.auth.routes.Flow")
    def test_add_account_flow(self, mock_flow, client, login_test_user):
        # 추가 계정 연결 시 Google OAuth로 리다이렉트
        mock_flow.from_client_config.return_value.authorization_url.return_value = (
            "https://accounts.google.com/o/oauth2/auth",
            "mock-state",
        )
        response = client.get("/auth/add-account", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "accounts.google.com" in response.location

    def test_logout(self, client, login_test_user):
        # 로그아웃 시 세션이 정리되고 로그인 페이지로 이동
        response = client.get("/auth/logout", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/auth/login" in response.location

    def test_manage_accounts_requires_login(self, client):
        # 로그인하지 않은 상태에서 계정 관리 접근 시 로그인 페이지로 리다이렉트
        response = client.get("/auth/manage-accounts", follow_redirects=False)
        assert response.status_code in (302, 303)
        assert "/auth/login" in response.location

    # ...추가적으로 remove-account, refresh_token 등도 유사하게 mock/fixture로 테스트 가능
