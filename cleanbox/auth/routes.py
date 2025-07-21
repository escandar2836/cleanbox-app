"""CleanBox 인증 관련 라우트 모듈."""

import json
import os
import subprocess
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
from google.oauth2 import id_token, service_account
from google.auth.transport import requests
from googleapiclient.discovery import build
from google.cloud import resourcemanager_v3

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


def is_render_environment() -> bool:
    """Render 환경인지 확인합니다."""
    return os.path.exists("/etc/secrets/") or os.getenv("RENDER", False)


def check_user_pubsub_permissions(
    user_email: str, project_id: str
) -> Tuple[bool, List[str]]:
    """사용자의 Pub/Sub 권한을 확인합니다."""
    try:
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        # 서비스 계정 키 파일 경로
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            return False, []

        # 서비스 계정 자격 증명 생성
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        # Resource Manager 클라이언트 생성
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # 프로젝트 리소스 이름
        project_name = f"projects/{project_id}"

        # IAM 정책 가져오기
        policy = client.get_iam_policy(request={"resource": project_name})

        # Pub/Sub 관련 권한 확인
        pubsub_roles = [
            "roles/pubsub.admin",
            "roles/pubsub.editor",
            "roles/pubsub.publisher",
            "roles/pubsub.subscriber",
        ]

        user_roles = []
        for binding in policy.bindings:
            role = binding.role
            for member in binding.members:
                if member == f"user:{user_email}":
                    user_roles.append(role)

        # Pub/Sub 권한이 있는지 확인
        has_pubsub_permission = any(role in pubsub_roles for role in user_roles)

        return has_pubsub_permission, user_roles

    except Exception as e:
        return False, []


def grant_pubsub_permissions_to_user(user_email: str, project_id: str) -> bool:
    """사용자에게 Pub/Sub Admin 권한을 부여합니다."""
    try:
        result = subprocess.run(
            [
                "gcloud",
                "projects",
                "add-iam-policy-binding",
                project_id,
                "--member=user:" + user_email,
                "--role=roles/pubsub.admin",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        return result.returncode == 0

    except Exception as e:
        return False


def check_user_pubsub_permissions_service_account(
    user_email: str, project_id: str
) -> Tuple[bool, List[str]]:
    """서비스 계정을 사용해서 사용자의 Pub/Sub 권한을 확인합니다."""
    try:
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        # 서비스 계정 키 파일 경로
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            return False, []

        # 서비스 계정 자격 증명 생성
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        # Resource Manager 클라이언트 생성
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # 프로젝트 리소스 이름
        project_name = f"projects/{project_id}"

        # IAM 정책 가져오기
        policy = client.get_iam_policy(request={"resource": project_name})

        # Pub/Sub 관련 권한 확인
        pubsub_roles = [
            "roles/pubsub.admin",
            "roles/pubsub.editor",
            "roles/pubsub.publisher",
            "roles/pubsub.subscriber",
        ]

        user_roles = []
        for binding in policy.bindings:
            role = binding.role
            for member in binding.members:
                if member == f"user:{user_email}":
                    user_roles.append(role)

        # Pub/Sub 권한이 있는지 확인
        has_pubsub_permission = any(role in pubsub_roles for role in user_roles)

        return has_pubsub_permission, user_roles

    except Exception as e:
        return False, []


def grant_gmail_and_pubsub_permissions_service_account(
    user_email: str, project_id: str
) -> bool:
    """서비스 계정을 사용해서 사용자에게 Gmail API와 Pub/Sub 권한을 부여합니다."""
    try:
        # 서비스 계정 키 파일 경로
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            return False

        # Google Cloud IAM API 클라이언트 생성
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        project_name = f"projects/{project_id}"

        # 현재 IAM 정책 가져오기
        policy = client.get_iam_policy(request={"resource": project_name})

        # 필요한 권한들
        required_roles = [
            "roles/pubsub.admin",
            "roles/serviceusage.serviceUsageAdmin",
        ]

        # 각 권한에 대해 IAM 바인딩 추가
        for role in required_roles:
            # 기존 바인딩 찾기
            existing_binding = None
            for binding in policy.bindings:
                if binding.role == role:
                    existing_binding = binding
                    break

            if existing_binding:
                # 기존 바인딩에 멤버 추가
                if f"user:{user_email}" not in existing_binding.members:
                    existing_binding.members.append(f"user:{user_email}")
            else:
                # 새 바인딩 생성
                from google.iam.v1 import policy_pb2

                new_binding = policy_pb2.Binding(
                    role=role, members=[f"user:{user_email}"]
                )
                policy.bindings.append(new_binding)

        # 업데이트된 정책 적용
        client.set_iam_policy(request={"resource": project_name, "policy": policy})

        return True

    except Exception as e:
        return False


def check_user_gmail_and_pubsub_permissions_service_account(
    user_email: str, project_id: str
) -> Tuple[bool, List[str]]:
    """서비스 계정을 사용해서 사용자의 Gmail API와 Pub/Sub 권한을 확인합니다."""
    try:
        # 서비스 계정 키 파일 경로
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            return False, []

        # 서비스 계정 자격 증명 생성
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        # Resource Manager 클라이언트 생성
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # 프로젝트 리소스 이름
        project_name = f"projects/{project_id}"

        # IAM 정책 가져오기
        policy = client.get_iam_policy(request={"resource": project_name})

        # 필요한 권한들 (Gmail API 권한은 별도로 관리)
        required_roles = ["roles/pubsub.admin", "roles/serviceusage.serviceUsageAdmin"]

        user_roles = []
        for binding in policy.bindings:
            role = binding.role
            for member in binding.members:
                if member == f"user:{user_email}":
                    user_roles.append(role)

        # 필요한 권한이 모두 있는지 확인
        has_all_permissions = all(role in user_roles for role in required_roles)

        return has_all_permissions, user_roles

    except Exception as e:
        return False, []


def grant_service_account_pubsub_permissions(project_id: str) -> bool:
    """서비스 계정에 Pub/Sub 권한을 부여합니다."""
    try:
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            return False

        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        project_name = f"projects/{project_id}"
        policy = client.get_iam_policy(request={"resource": project_name})
        service_account_email = (
            "cleanbox-webhook@cleanbox-466314.iam.gserviceaccount.com"
        )
        required_roles = ["roles/pubsub.publisher", "roles/pubsub.subscriber"]

        # 각 권한에 대해 IAM 바인딩 추가
        for role in required_roles:
            # 기존 바인딩 찾기
            existing_binding = None
            for binding in policy.bindings:
                if binding.role == role:
                    existing_binding = binding
                    break

            if existing_binding:
                # 기존 바인딩에 서비스 계정 추가
                if (
                    f"serviceAccount:{service_account_email}"
                    not in existing_binding.members
                ):
                    existing_binding.members.append(
                        f"serviceAccount:{service_account_email}"
                    )
            else:
                # 새 바인딩 생성
                from google.iam.v1 import policy_pb2

                new_binding = policy_pb2.Binding(
                    role=role, members=[f"serviceAccount:{service_account_email}"]
                )
                policy.bindings.append(new_binding)

        # 업데이트된 정책 적용
        client.set_iam_policy(request={"resource": project_name, "policy": policy})
        return True

    except Exception as e:
        return False


def check_and_grant_pubsub_permissions(user_email: str) -> bool:
    """사용자의 Pub/Sub 권한을 확인하고 필요시 부여합니다."""
    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            return False

        # 1단계: 권한 확인
        if is_render_environment():
            has_permission, current_roles = (
                check_user_gmail_and_pubsub_permissions_service_account(
                    user_email, project_id
                )
            )
        else:
            has_permission, current_roles = check_user_pubsub_permissions(
                user_email, project_id
            )

        if has_permission:
            return True

        # 2단계: 서비스 계정 권한 확인 및 부여
        service_account_success = grant_service_account_pubsub_permissions(project_id)

        # 3단계: 사용자 권한 부여
        grant_success = grant_gmail_and_pubsub_permissions_service_account(
            user_email, project_id
        )

        if not grant_success:
            return False

        # 4단계: 권한 부여 후 재확인
        time.sleep(5)

        # 5단계: 최종 권한 확인
        if is_render_environment():
            final_check, final_roles = (
                check_user_gmail_and_pubsub_permissions_service_account(
                    user_email, project_id
                )
            )
        else:
            final_check, final_roles = check_user_pubsub_permissions(
                user_email, project_id
            )

        return final_check

    except Exception as e:
        return False


@auth_bp.route("/login")
def login() -> Any:
    """Google OAuth 로그인 시작."""
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
def callback() -> Any:
    """Google OAuth 콜백 처리 (로그인 및 계정 추가 통합)."""
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
        flash(f"로그인 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("auth.login"))


def _handle_login_callback(credentials: Any, id_info: Dict[str, Any]) -> Any:
    """일반 로그인 콜백 처리."""
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

        # 모든 사용자에게 Pub/Sub 권한 확인 및 부여
        try:
            permission_granted = check_and_grant_pubsub_permissions(user.email)
        except Exception as e:
            pass  # 권한 부여 실패는 치명적이지 않음

        # 새 사용자인 경우 자동 웹훅 설정
        if is_new_user:
            try:
                from ..email.gmail_service import GmailService
                from ..email.routes import setup_webhook_for_account

                setup_webhook_for_account(user.id, account.id)
            except Exception as e:
                pass  # 웹훅 설정 실패는 치명적이지 않음

        # 세션 정리
        session.pop("state", None)
        session.pop("adding_account", None)

        login_user(user)

        # 로그인 후 웹훅 상태 확인 및 자동 복구
        try:
            from ..email.routes import check_and_repair_webhooks_for_user

            check_and_repair_webhooks_for_user(user.id)
        except Exception as e:
            pass  # 웹훅 복구 실패는 치명적이지 않음

        flash("CleanBox에 성공적으로 로그인했습니다!", "success")
        return redirect(url_for("main.dashboard"))

    except Exception as e:
        flash(f"로그인 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("auth.login"))


def _handle_add_account_callback(credentials: Any, id_info: Dict[str, Any]) -> Any:
    """추가 계정 연결 콜백 처리."""
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
            # 계정이 비활성화 상태인지 확인
            if not existing_account.is_active:
                # 비활성화된 계정을 다시 활성화
                existing_account.is_active = True
                existing_account.account_name = id_info.get(
                    "name", existing_account.account_name
                )
                db.session.commit()

                flash(
                    f"비활성화된 계정 {id_info['email']}이 다시 활성화되었습니다!",
                    "success",
                )

                # 캐시 무효화를 위한 헤더 추가
                response = redirect(url_for("auth.manage_accounts"))
                response.headers["Cache-Control"] = (
                    "no-cache, no-store, must-revalidate"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"

                return response
            else:
                flash("이미 연결된 Gmail 계정입니다.", "warning")
                response = redirect(url_for("auth.manage_accounts"))
                # 캐시 무효화
                response.headers["Cache-Control"] = (
                    "no-cache, no-store, must-revalidate"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response

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

        # 추가 계정에 Pub/Sub 권한 확인 및 부여
        try:
            permission_granted = check_and_grant_pubsub_permissions(
                account.account_email
            )
        except Exception as e:
            pass  # 권한 부여 실패는 치명적이지 않음

        # Gmail 웹훅 자동 설정 (선택사항)
        try:
            from ..email.gmail_service import GmailService

            gmail_service = GmailService(current_user.id, account.id)

            # 환경변수에서 토픽 이름 가져오기
            topic_name = os.environ.get("GMAIL_WEBHOOK_TOPIC")
            if topic_name:
                gmail_service.setup_gmail_watch(topic_name)
        except Exception as e:
            pass  # 웹훅 설정 실패는 치명적이지 않으므로 계속 진행

        # 세션 정리
        session.pop("state", None)
        session.pop("adding_account", None)

        flash(f"Gmail 계정 {id_info['email']}이 성공적으로 연결되었습니다!", "success")

        # 캐시 무효화를 위한 헤더 추가
        response = redirect(url_for("auth.manage_accounts"))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response

    except Exception as e:
        flash(f"계정 추가 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("auth.manage_accounts"))


@auth_bp.route("/add-account")
@login_required
def add_account() -> Any:
    """추가 Gmail 계정 연결."""
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
def manage_accounts() -> Any:
    """계정 관리 페이지."""
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    return render_template(
        "auth/manage_accounts.html", user=current_user, accounts=accounts
    )


@auth_bp.route("/remove-account/<int:account_id>", methods=["POST"])
@login_required
def remove_account(account_id: int) -> Any:
    """계정 연결 해제."""
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

    # 캐시 무효화를 위한 헤더 추가
    response = redirect(url_for("auth.manage_accounts"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@auth_bp.route("/logout")
@login_required
def logout() -> Any:
    """로그아웃."""
    try:
        # 사용자 세션 정보 정리
        current_user.is_online = False
        current_user.session_id = None
        db.session.commit()
    except Exception as e:
        pass  # 로그아웃 시 세션 정리 실패는 치명적이지 않음

    logout_user()
    session.clear()
    flash("CleanBox에서 로그아웃되었습니다.", "info")
    return redirect(url_for("auth.login"))


def get_user_credentials(
    user_id: str, account_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """사용자의 OAuth 토큰을 가져오는 헬퍼 함수."""
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


def get_current_account_id() -> Optional[int]:
    """현재 활성 계정 ID 가져오기."""
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


def refresh_user_token(user_id: str, account_id: int) -> bool:
    """사용자의 OAuth 토큰을 자동으로 갱신합니다."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import Flow

        # 사용자 토큰 가져오기
        user_token = UserToken.query.filter_by(
            user_id=user_id, account_id=account_id
        ).first()

        if not user_token:
            return False

        # 현재 토큰 정보 가져오기
        tokens = user_token.get_tokens()

        if not tokens.get("refresh_token"):
            return False

        # Credentials 객체 생성
        credentials = Credentials(
            token=tokens.get("token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=tokens.get("scopes", []),
            expiry=tokens.get("expiry"),
        )

        # 토큰이 만료되었는지 확인
        if credentials.expired and credentials.refresh_token:
            # 토큰 갱신
            credentials.refresh(Request())

            # 갱신된 토큰 저장
            user_token.set_tokens(credentials)
            db.session.commit()

            return True
        else:
            return True

    except Exception as e:
        return False


def check_and_refresh_token(user_id: str, account_id: int) -> bool:
    """토큰 상태를 확인하고 필요시 갱신합니다."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        # 사용자 토큰 가져오기
        user_token = UserToken.query.filter_by(
            user_id=user_id, account_id=account_id
        ).first()

        if not user_token:
            return False

        # 현재 토큰 정보 가져오기
        tokens = user_token.get_tokens()

        if not tokens.get("refresh_token"):
            return False

        # Credentials 객체 생성
        credentials = Credentials(
            token=tokens.get("token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=tokens.get("scopes", []),
            expiry=tokens.get("expiry"),
        )

        # 토큰이 만료되었는지 확인
        if credentials.expired and credentials.refresh_token:
            return refresh_user_token(user_id, account_id)
        else:
            return True

    except Exception as e:
        return False
