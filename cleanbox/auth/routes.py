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
from google.cloud import resourcemanager_v3
from google.oauth2 import service_account

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


def grant_pubsub_permissions_to_user(user_email: str) -> bool:
    """사용자에게 Pub/Sub 권한을 부여합니다."""
    try:
        # 서비스 계정 키 파일 경로
        service_account_key_path = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", "cleanbox-webhook-key.json"
        )

        if not os.path.exists(service_account_key_path):
            print(
                f"⚠️ 서비스 계정 키 파일을 찾을 수 없습니다: {service_account_key_path}"
            )
            return False

        # 서비스 계정 자격 증명으로 Resource Manager 클라이언트 생성
        credentials = service_account.Credentials.from_service_account_file(
            service_account_key_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

        client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "cleanbox-466314")

        # 사용자에게 Pub/Sub 편집자 역할 부여
        project_name = f"projects/{project_id}"
        policy = client.get_iam_policy(request={"resource": project_name})

        # 사용자에게 Pub/Sub 편집자 역할 추가
        member = f"user:{user_email}"
        role = "roles/pubsub.editor"

        # 이미 권한이 있는지 확인
        for binding in policy.bindings:
            if binding.role == role and member in binding.members:
                print(
                    f"✅ 사용자 {user_email}에게 이미 Pub/Sub 권한이 부여되어 있습니다."
                )
                return True

        # 권한 추가
        from google.cloud.resourcemanager_v3.types import Policy, Binding

        new_binding = Binding()
        new_binding.role = role
        new_binding.members.append(member)
        policy.bindings.append(new_binding)

        # 정책 업데이트
        client.set_iam_policy(request={"resource": project_name, "policy": policy})

        print(f"✅ 사용자 {user_email}에게 Pub/Sub 권한을 부여했습니다.")
        return True

    except Exception as e:
        print(f"❌ 사용자 {user_email}에게 Pub/Sub 권한 부여 실패: {str(e)}")
        return False


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
        is_new_user = False

        if not user:
            user = User(
                id=id_info["sub"],
                email=id_info["email"],
                name=id_info.get("name", ""),
                picture=id_info.get("picture"),
            )
            db.session.add(user)
            is_new_user = True
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
            db.session.flush()  # account.id 생성
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

        # 새 사용자인 경우 자동 웹훅 설정
        if is_new_user:
            try:
                from ..email.gmail_service import GmailService
                from ..email.routes import setup_webhook_for_account

                print(f"🔄 새 사용자 웹훅 자동 설정: {user.email}")
                setup_webhook_for_account(user.id, account.id)
                print(f"✅ 웹훅 자동 설정 완료: {user.email}")

                # 새 사용자에게 Pub/Sub 권한 부여
                grant_pubsub_permissions_to_user(user.email)
                print(f"✅ 새 사용자 {user.email}에게 Pub/Sub 권한 부여 완료")
            except Exception as e:
                print(f"⚠️ 웹훅 자동 설정 실패: {user.email}, 오류: {str(e)}")

        # 세션 정리
        session.pop("state", None)
        session.pop("adding_account", None)

        login_user(user)

        # 로그인 후 웹훅 상태 확인 및 자동 복구
        try:
            from ..email.routes import check_and_repair_webhooks_for_user

            check_and_repair_webhooks_for_user(user.id)
        except Exception as e:
            print(f"⚠️ 로그인 후 웹훅 복구 실패: {user.email}, 오류: {str(e)}")

        flash("CleanBox에 성공적으로 로그인했습니다!", "success")
        return redirect(url_for("main.dashboard"))

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
        db.session.flush()  # account.id 생성

        # 토큰 저장
        user_token = UserToken(user_id=current_user.id, account_id=account.id)
        user_token.set_tokens(credentials)
        db.session.add(user_token)

        db.session.commit()

        # Gmail 웹훅 자동 설정 (선택사항)
        try:
            from ..email.gmail_service import GmailService

            gmail_service = GmailService(current_user.id, account.id)

            # 환경변수에서 토픽 이름 가져오기
            topic_name = os.environ.get("GMAIL_WEBHOOK_TOPIC")
            if topic_name:
                gmail_service.setup_gmail_watch(topic_name)
                print(f"✅ Gmail 웹훅 자동 설정 완료: {account.account_email}")

                # 추가 계정에 Pub/Sub 권한 부여
                grant_pubsub_permissions_to_user(account.account_email)
                print(
                    f"✅ 추가 계정 {account.account_email}에게 Pub/Sub 권한 부여 완료"
                )
        except Exception as e:
            print(f"⚠️ Gmail 웹훅 자동 설정 실패: {e}")
            # 웹훅 설정 실패는 치명적이지 않으므로 계속 진행

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
