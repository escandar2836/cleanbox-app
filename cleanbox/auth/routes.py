from datetime import datetime
import os
from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    session,
    flash,
    render_template,
)
from flask_login import login_user, logout_user, login_required, current_user
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests
from googleapiclient.discovery import build
from ..models import User, UserToken, UserAccount, db


auth_bp = Blueprint("auth", __name__)

# OAuth 2.0 클라이언트 설정
GOOGLE_CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID"),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [
            os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:5001/auth/callback")
        ],
    }
}


@auth_bp.route("/login")
def login():
    """Google OAuth 로그인 시작"""
    if current_user.is_authenticated:
        return redirect(url_for("category.list_categories"))

    # 이미 진행 중인 OAuth 요청이 있는지 확인
    if "state" in session:
        # 세션 정리 후 다시 시작
        session.pop("state", None)
        session.pop("adding_account", None)

    # 무한 리다이렉트 방지: 이미 로그인 페이지에 있다면 Google OAuth로 바로 이동
    if request.endpoint == "auth.login":
        flow = Flow.from_client_config(
            GOOGLE_CLIENT_CONFIG,
            scopes=[
                "openid",
                "https://mail.google.com/",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
        )
        flow.redirect_uri = GOOGLE_CLIENT_CONFIG["web"]["redirect_uris"][0]

        authorization_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true", prompt="consent"
        )

        session["state"] = state
        return redirect(authorization_url)

    # 일반적인 로그인 페이지 렌더링 (필요시)
    return render_template("auth/login.html")


@auth_bp.route("/callback")
def callback():
    """Google OAuth 콜백 처리 (로그인 및 계정 추가 통합)"""
    try:
        # 세션 state 검증
        if "state" not in session:
            flash("OAuth 세션이 만료되었습니다. 다시 로그인해주세요.", "error")
            return redirect(url_for("auth.login"))

        flow = Flow.from_client_config(
            GOOGLE_CLIENT_CONFIG,
            scopes=[
                "openid",
                "https://mail.google.com/",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
            state=session["state"],
        )
        flow.redirect_uri = GOOGLE_CLIENT_CONFIG["web"]["redirect_uris"][0]

        # 인증 코드로 토큰 교환
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)

        # 사용자 정보 가져오기
        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            requests.Request(),
            GOOGLE_CLIENT_CONFIG["web"]["client_id"],
        )

        # 추가 계정 연결인지 확인
        is_adding_account = session.get("adding_account", False)

        if is_adding_account:
            # 추가 계정 연결 처리
            return _handle_add_account_callback(credentials, id_info)
        else:
            # 일반 로그인 처리
            return _handle_login_callback(credentials, id_info)

    except Exception as e:
        # 더 자세한 에러 로깅
        print(f"OAuth 콜백 에러: {str(e)}")
        flash(f"로그인 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("auth.login"))


def _handle_login_callback(credentials, id_info):
    """일반 로그인 콜백 처리"""
    try:
        # 사용자 조회 또는 생성
        user = User.query.get(id_info["sub"])
        if not user:
            user = User(
                id=id_info["sub"],
                email=id_info["email"],
                name=id_info.get("name", ""),
                picture=id_info.get("picture"),
            )
            db.session.add(user)
        else:
            # 기존 사용자 정보 업데이트
            user.name = id_info.get("name", user.name)
            user.picture = id_info.get("picture", user.picture)

        # 계정 조회 또는 생성
        account = UserAccount.query.filter_by(
            user_id=user.id, account_email=id_info["email"]
        ).first()

        if not account:
            # 새 계정 생성
            account = UserAccount(
                user_id=user.id,
                account_email=id_info["email"],
                account_name=id_info.get("name", ""),
                is_primary=True,  # 첫 번째 계정은 기본 계정으로 설정
            )
            db.session.add(account)
        else:
            # 기존 계정 정보 업데이트
            account.account_name = id_info.get("name", account.account_name)

        # 토큰 저장 또는 업데이트
        user_token = UserToken.query.filter_by(
            user_id=user.id, account_id=account.id
        ).first()

        if not user_token:
            user_token = UserToken(user_id=user.id, account_id=account.id)
            db.session.add(user_token)

        user_token.set_tokens(credentials)

        # last_login 업데이트
        user.last_login = datetime.utcnow()
        db.session.commit()

        # 세션 정리
        session.pop("state", None)
        session.pop("adding_account", None)

        login_user(user)
        flash("CleanBox에 성공적으로 로그인했습니다!", "success")
        return redirect(url_for("category.list_categories"))

    except Exception as e:
        print(f"로그인 콜백 처리 에러: {str(e)}")
        flash(f"로그인 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("auth.login"))


def _handle_add_account_callback(credentials, id_info):
    """추가 계정 연결 콜백 처리"""
    try:
        # 로그인된 사용자 확인
        if not current_user.is_authenticated:
            flash("로그인이 필요합니다.", "error")
            return redirect(url_for("auth.login"))

        # 이미 연결된 계정인지 확인
        existing_account = UserAccount.query.filter_by(
            user_id=current_user.id, account_email=id_info["email"]
        ).first()

        if existing_account:
            flash("이미 연결된 Gmail 계정입니다.", "warning")
            return redirect(url_for("auth.manage_accounts"))

        # 새 계정 생성
        account = UserAccount(
            user_id=current_user.id,
            account_email=id_info["email"],
            account_name=id_info.get("name", ""),
            is_primary=False,
        )
        db.session.add(account)

        # 토큰 저장
        user_token = UserToken(user_id=current_user.id, account_id=account.id)
        user_token.set_tokens(credentials)
        db.session.add(user_token)

        db.session.commit()

        # 세션 정리
        session.pop("state", None)
        session.pop("adding_account", None)

        flash(f"Gmail 계정 {id_info['email']}이 성공적으로 연결되었습니다!", "success")
        return redirect(url_for("auth.manage_accounts"))

    except Exception as e:
        print(f"추가 계정 콜백 처리 에러: {str(e)}")
        flash(f"계정 추가 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("auth.manage_accounts"))


@auth_bp.route("/add-account")
@login_required
def add_account():
    """추가 Gmail 계정 연결"""
    flow = Flow.from_client_config(
        GOOGLE_CLIENT_CONFIG,
        scopes=[
            "openid",
            "https://mail.google.com/",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ],
    )
    flow.redirect_uri = GOOGLE_CLIENT_CONFIG["web"]["redirect_uris"][0]

    authorization_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )

    session["state"] = state
    session["adding_account"] = True
    return redirect(authorization_url)


@auth_bp.route("/manage-accounts")
@login_required
def manage_accounts():
    """계정 관리 페이지"""
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    return render_template(
        "auth/manage_accounts.html", user=current_user, accounts=accounts
    )


@auth_bp.route("/remove-account/<int:account_id>", methods=["POST"])
@login_required
def remove_account(account_id):
    """계정 연결 해제"""
    account = UserAccount.query.filter_by(
        id=account_id, user_id=current_user.id
    ).first()

    if not account:
        flash("계정을 찾을 수 없습니다.", "error")
        return redirect(url_for("auth.manage_accounts"))

    if account.is_primary:
        flash("기본 계정은 연결 해제할 수 없습니다.", "error")
        return redirect(url_for("auth.manage_accounts"))

    # 계정 비활성화
    account.is_active = False
    db.session.commit()

    flash(f"{account.account_email} 계정 연결이 해제되었습니다.", "success")
    return redirect(url_for("auth.manage_accounts"))


@auth_bp.route("/logout")
@login_required
def logout():
    """로그아웃"""
    try:
        # 사용자 세션 정보 정리
        current_user.is_online = False
        current_user.session_id = None
        db.session.commit()
    except Exception as e:
        print(f"로그아웃 시 세션 정리 실패: {str(e)}")

    logout_user()
    session.clear()
    flash("CleanBox에서 로그아웃되었습니다.", "info")
    return redirect(url_for("auth.login"))


def get_user_credentials(user_id, account_id=None):
    """사용자의 OAuth 토큰을 가져오는 헬퍼 함수"""
    if account_id:
        user_token = UserToken.query.filter_by(
            user_id=user_id, account_id=account_id
        ).first()
    else:
        # 현재 활성 계정의 토큰 가져오기
        current_account = UserAccount.query.filter_by(
            user_id=user_id, is_primary=True, is_active=True
        ).first()
        if current_account:
            user_token = UserToken.query.filter_by(
                user_id=user_id, account_id=current_account.id
            ).first()
        else:
            return None

    if user_token:
        return user_token.get_tokens()
    return None


def get_current_account_id():
    """현재 활성 계정 ID 가져오기"""
    # 로그인되지 않은 경우 None 반환
    if not current_user.is_authenticated:
        return None

    # 기본 계정 ID 반환
    primary_account = UserAccount.query.filter_by(
        user_id=current_user.id, is_primary=True, is_active=True
    ).first()

    if primary_account:
        return primary_account.id

    # 활성 계정이 없으면 첫 번째 활성 계정 반환
    first_account = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).first()

    if first_account:
        return first_account.id

    return None
