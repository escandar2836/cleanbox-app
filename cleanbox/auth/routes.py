# Standard library imports
import json
import os
import subprocess
import time
from datetime import datetime

# Third-party imports
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

# Local imports
from ..models import User, UserToken, UserAccount, db


auth_bp = Blueprint("auth", __name__)

# OAuth 2.0 client settings
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


def debug_account_info():
    """Debug print current account info."""
    print("\n" + "=" * 60)
    print("🔍 Debugging current account info")
    print("=" * 60)

    try:
        # 1. gcloud auth list - currently authenticated accounts
        print("\n📋 1. gcloud authenticated account list:")
        try:
            result = subprocess.run(
                ["gcloud", "auth", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                auth_data = json.loads(result.stdout)
                for account in auth_data:
                    print(f"   - Account: {account.get('account', 'N/A')}")
                    print(f"     Status: {account.get('status', 'N/A')}")
                    print(
                        f"     Active: {'✅' if account.get('active', False) else '❌'}"
                    )
            else:
                print(f"   ❌ gcloud auth list failed: {result.stderr}")
        except Exception as e:
            print(f"   ❌ gcloud auth list error: {str(e)}")

        # 2. Check environment variables
        print("\n📋 2. Environment variable info:")
        print(
            f"   GOOGLE_CLOUD_PROJECT: {os.getenv('GOOGLE_CLOUD_PROJECT', 'Not set')}"
        )
        print(
            f"   GOOGLE_APPLICATION_CREDENTIALS: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'Not set')}"
        )
        print(
            f"   GOOGLE_CLIENT_ID: {os.getenv('GOOGLE_CLIENT_ID', 'Not set')[:20]}..."
        )

        # 3. Check service account key file
        print("\n📋 3. Service account key file:")
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if creds_path:
            if os.path.exists(creds_path):
                print(f"   ✅ File exists: {creds_path}")
                try:
                    with open(creds_path, "r") as f:
                        creds_data = json.load(f)
                    print(
                        f"   📧 Service account email: {creds_data.get('client_email', 'N/A')}"
                    )
                    print(f"   🆔 Project ID: {creds_data.get('project_id', 'N/A')}")
                except Exception as e:
                    print(f"   ❌ File read error: {str(e)}")
            else:
                print(f"   ❌ File not found: {creds_path}")
        else:
            print("   ⚠️ GOOGLE_APPLICATION_CREDENTIALS env var not set")

        # 4. Check current project
        print("\n📋 4. Current gcloud project:")
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                print(f"   Project: {result.stdout.strip()}")
            else:
                print(f"   ❌ Project check failed: {result.stderr}")
        except Exception as e:
            print(f"   ❌ Project check error: {str(e)}")

        # 5. Check service account key in env var
        print("\n📋 5. Service account key in env var:")
        service_account_key = os.getenv("GOOGLE_SERVICE_ACCOUNT_KEY")
        if service_account_key:
            try:
                key_data = json.loads(service_account_key)
                print(
                    f"   📧 Service account email: {key_data.get('client_email', 'N/A')}"
                )
                print(f"   🆔 Project ID: {key_data.get('project_id', 'N/A')}")
            except Exception as e:
                print(f"   ❌ JSON parse error: {str(e)}")
        else:
            print("   ⚠️ GOOGLE_SERVICE_ACCOUNT_KEY env var not set")

        print("=" * 60)
        print()

    except Exception as e:
        print(f"❌ Error while printing debug info: {str(e)}")


def check_user_pubsub_permissions(
    user_email: str, project_id: str
) -> tuple[bool, list]:
    """Check user's Pub/Sub permissions."""
    try:
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        # Service account key file path
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            print(f"❌ Service account key file not found: {creds_path}")
            return False, []

        # Create service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        # Resource Manager client
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # Project resource name
        project_name = f"projects/{project_id}"

        # Get IAM policy
        policy = client.get_iam_policy(request={"resource": project_name})

        # Check Pub/Sub related permissions
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
                    print(f"   📋 Found role: {role}")

        # Check if user has Pub/Sub permission
        has_pubsub_permission = any(role in pubsub_roles for role in user_roles)

        if has_pubsub_permission:
            print(f"✅ User {user_email} has Pub/Sub permission. (Roles: {user_roles})")
            return True, user_roles
        else:
            print(
                f"⚠️ User {user_email} does not have Pub/Sub permission. (Current roles: {user_roles})"
            )
            return False, user_roles

    except Exception as e:
        print(f"❌ Error checking user Pub/Sub permissions: {str(e)}")
        return False, []


def grant_pubsub_permissions_to_user(user_email: str, project_id: str) -> bool:
    """Grant Pub/Sub Admin permission to a user."""
    try:
        print(f"🔧 Granting Pub/Sub Admin permission to user {user_email}...")

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

        if result.returncode == 0:
            print(f"✅ gcloud command executed successfully")
            print(f"📋 Command output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ gcloud command execution failed")
            print(f"📋 Error output: {result.stderr.strip()}")
            return False

    except Exception as e:
        print(f"❌ Error granting permission: {str(e)}")
        return False


def is_render_environment():
    """Check if it's a Render environment."""
    return os.path.exists("/etc/secrets/") or os.getenv("RENDER", False)


def check_user_pubsub_permissions_service_account(
    user_email: str, project_id: str
) -> tuple[bool, list]:
    """Check user's Pub/Sub permissions using a service account."""
    try:
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account
        import json

        # Service account key file path
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            print(f"❌ Service account key file not found: {creds_path}")
            return False, []

        # Create service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        # Resource Manager client
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # Project resource name
        project_name = f"projects/{project_id}"

        # Get IAM policy
        policy = client.get_iam_policy(request={"resource": project_name})

        # Check Pub/Sub related permissions
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
                    print(f"   📋 Found role: {role}")

        # Check if user has Pub/Sub permission
        has_pubsub_permission = any(role in pubsub_roles for role in user_roles)

        if has_pubsub_permission:
            print(f"✅ User {user_email} has Pub/Sub permission. (Roles: {user_roles})")
            return True, user_roles
        else:
            print(
                f"⚠️ User {user_email} does not have Pub/Sub permission. (Current roles: {user_roles})"
            )
            return False, user_roles

    except Exception as e:
        print(f"⚠️ Error checking service account permissions: {str(e)}")
        return False, []


def grant_gmail_and_pubsub_permissions_service_account(
    user_email: str, project_id: str
) -> bool:
    """Grant Gmail API and Pub/Sub permissions to a user using a service account."""
    try:
        print(
            f"🔧 Granting Gmail API and Pub/Sub permissions to user {user_email} using a service account..."
        )

        # Service account key file path
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            print(f"❌ Service account key file not found: {creds_path}")
            return False

        # Create Google Cloud IAM API client
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        client = resourcemanager_v3.ProjectsClient(credentials=credentials)
        project_name = f"projects/{project_id}"

        # Get current IAM policy
        policy = client.get_iam_policy(request={"resource": project_name})

        # Required permissions
        required_roles = [
            "roles/pubsub.admin",
            "roles/serviceusage.serviceUsageAdmin",
        ]

        # Add IAM bindings for each permission
        for role in required_roles:
            print(f"🔧 Granting {role} permission...")

            # Find existing binding
            existing_binding = None
            for binding in policy.bindings:
                if binding.role == role:
                    existing_binding = binding
                    break

            if existing_binding:
                # Add member to existing binding
                if f"user:{user_email}" not in existing_binding.members:
                    existing_binding.members.append(f"user:{user_email}")
                    print(f"✅ User added to {role} permission")
            else:
                # Create new binding
                from google.iam.v1 import policy_pb2

                new_binding = policy_pb2.Binding(
                    role=role, members=[f"user:{user_email}"]
                )
                policy.bindings.append(new_binding)
                print(f"✅ {role} permission created")

        # Apply updated policy
        client.set_iam_policy(request={"resource": project_name, "policy": policy})
        print(f"✅ IAM policy updated")

        return True

    except Exception as e:
        print(f"❌ Error granting permission: {str(e)}")
        return False


def check_user_gmail_and_pubsub_permissions_service_account(
    user_email: str, project_id: str
) -> tuple[bool, list]:
    """Check user's Gmail API and Pub/Sub permissions using a service account."""
    try:
        # Service account key file path
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            print(f"❌ Service account key file not found: {creds_path}")
            return False, []

        # Create service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        # Resource Manager client
        client = resourcemanager_v3.ProjectsClient(credentials=credentials)

        # Project resource name
        project_name = f"projects/{project_id}"

        # Get IAM policy
        policy = client.get_iam_policy(request={"resource": project_name})

        # Required permissions (Gmail API permissions are managed separately)
        required_roles = ["roles/pubsub.admin", "roles/serviceusage.serviceUsageAdmin"]

        user_roles = []
        for binding in policy.bindings:
            role = binding.role
            for member in binding.members:
                if member == f"user:{user_email}":
                    user_roles.append(role)
                    print(f"   📋 Found role: {role}")

        # Check if all required permissions are present
        has_all_permissions = all(role in user_roles for role in required_roles)

        if has_all_permissions:
            print(f"✅ User {user_email} has all required permissions.")
            return True, user_roles
        else:
            missing_roles = [role for role in required_roles if role not in user_roles]
            print(f"⚠️ Missing permissions for user {user_email}: {missing_roles}")
            return False, user_roles

    except Exception as e:
        print(f"❌ Error checking user permissions: {str(e)}")
        return False, []


def grant_service_account_pubsub_permissions(project_id: str) -> bool:
    """Grant Pub/Sub permission to a service account."""
    try:
        from google.cloud import resourcemanager_v3
        from google.oauth2 import service_account

        print(f"🔧 Granting Pub/Sub permission to a service account...")
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path or not os.path.exists(creds_path):
            print(f"❌ Service account key file not found: {creds_path}")
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

        # Add IAM bindings for each permission
        for role in required_roles:
            print(f"🔧 Granting {role} permission...")

            # Find existing binding
            existing_binding = None
            for binding in policy.bindings:
                if binding.role == role:
                    existing_binding = binding
                    break

            if existing_binding:
                # Add service account to existing binding
                if (
                    f"serviceAccount:{service_account_email}"
                    not in existing_binding.members
                ):
                    existing_binding.members.append(
                        f"serviceAccount:{service_account_email}"
                    )
                    print(f"✅ Service account added to {role} permission")
            else:
                # Create new binding
                from google.iam.v1 import policy_pb2

                new_binding = policy_pb2.Binding(
                    role=role, members=[f"serviceAccount:{service_account_email}"]
                )
                policy.bindings.append(new_binding)
                print(f"✅ {role} permission created")

        # Apply updated policy
        client.set_iam_policy(request={"resource": project_name, "policy": policy})
        print(f"✅ Service account Pub/Sub permission granted")
        return True

    except Exception as e:
        print(f"❌ Error granting service account permission: {str(e)}")
        return False


def check_and_grant_pubsub_permissions(user_email: str) -> bool:
    """Check user's Pub/Sub permissions and grant if necessary."""
    try:
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            print("❌ GOOGLE_CLOUD_PROJECT environment variable not set.")
            return False

        print(f"🔍 Checking current permissions for user {user_email}...")

        # 1st step: Check permissions
        if is_render_environment():
            print("🌐 Detected Render environment - using service account")
            has_permission, current_roles = (
                check_user_gmail_and_pubsub_permissions_service_account(
                    user_email, project_id
                )
            )
        else:
            print("🏠 Detected local environment - using Google Cloud API")
            has_permission, current_roles = check_user_pubsub_permissions(
                user_email, project_id
            )

        if has_permission:
            print(f"✅ User {user_email} already has required permissions.")
            return True

        # 2nd step: Grant service account permissions
        print(f"🔧 Granting service account permissions and user permissions...")
        service_account_success = grant_service_account_pubsub_permissions(project_id)

        if not service_account_success:
            print(f"⚠️ Service account permission grant failed")

        # 3rd step: Grant user permissions
        print(f"🔧 Granting user {user_email} Gmail API and Pub/Sub permissions...")
        grant_success = grant_gmail_and_pubsub_permissions_service_account(
            user_email, project_id
        )

        if not grant_success:
            print(f"❌ Permission grant failed")
            return False

        # 4th step: Re-check after granting
        print(f"⏳ Waiting for 5 seconds to re-check after granting...")
        time.sleep(5)

        # 5th step: Final permission check
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

        if final_check:
            print(f"✅ User {user_email} Pub/Sub permission setting complete")
            return True
        else:
            print(f"⚠️ User {user_email} Pub/Sub permission setting failed")
            return False

    except Exception as e:
        print(f"❌ Error checking user {user_email} Pub/Sub permissions: {str(e)}")
        return False


@auth_bp.route("/login")
def login():
    """Start Google OAuth login."""
    if current_user.is_authenticated:
        return redirect(url_for("category.list_categories"))

    # Check if there's an ongoing OAuth request
    if "state" in session:
        # Clear session and restart
        session.pop("state", None)
        session.pop("adding_account", None)

    # Prevent infinite redirects: if already on the login page, redirect directly to Google OAuth
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

    # Render the login page (if needed)
    return render_template("auth/login.html")


@auth_bp.route("/callback")
def callback():
    """Handle Google OAuth callback (login and account addition integration)"""
    try:
        # Validate session state
        if "state" not in session:
            flash("OAuth session expired. Please log in again.", "error")
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

        # Exchange authorization code for tokens
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)

        # Get user info
        credentials = flow.credentials
        id_info = id_token.verify_oauth2_token(
            credentials.id_token,
            requests.Request(),
            GOOGLE_CLIENT_CONFIG["web"]["client_id"],
        )

        # Check if it's an account addition request
        is_adding_account = session.get("adding_account", False)

        if is_adding_account:
            # Handle account addition
            return _handle_add_account_callback(credentials, id_info)
        else:
            # Handle normal login
            return _handle_login_callback(credentials, id_info)

    except Exception as e:
        # More detailed error logging
        print(f"OAuth callback error: {str(e)}")
        flash(f"An error occurred during login: {str(e)}", "error")
        return redirect(url_for("auth.login"))


def _handle_login_callback(credentials, id_info):
    """Handle normal login callback."""
    try:
        # Query or create user
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
            # Update existing user info
            user.name = id_info.get("name", user.name)
            user.picture = id_info.get("picture", user.picture)

        # Query or create account
        account = UserAccount.query.filter_by(
            user_id=user.id, account_email=id_info["email"]
        ).first()

        if not account:
            # Create new account
            account = UserAccount(
                user_id=user.id,
                account_email=id_info["email"],
                account_name=id_info.get("name", ""),
                is_primary=True,  # Set as primary account for the first account
            )
            db.session.add(account)
            db.session.flush()  # account.id will be generated
        else:
            # Update existing account info
            account.account_name = id_info.get("name", account.account_name)

        # Save or update token
        user_token = UserToken.query.filter_by(
            user_id=user.id, account_id=account.id
        ).first()

        if not user_token:
            user_token = UserToken(user_id=user.id, account_id=account.id)
            db.session.add(user_token)

        user_token.set_tokens(credentials)

        # Update last_login
        user.last_login = datetime.utcnow()
        db.session.commit()

        # Check and grant Pub/Sub permissions for all users
        try:
            print(f"🔍 Checking Pub/Sub permissions for user {user.email}...")
            permission_granted = check_and_grant_pubsub_permissions(user.email)

            if permission_granted:
                print(f"✅ Pub/Sub permission setting complete for user {user.email}")
            else:
                print(f"⚠️ Pub/Sub permission setting failed for user {user.email}")
        except Exception as e:
            print(f"❌ Error checking user {user.email} Pub/Sub permissions: {str(e)}")

        # Auto-setup webhook for new users
        if is_new_user:
            try:
                from ..email.gmail_service import GmailService
                from ..email.routes import setup_webhook_for_account

                print(f"🔄 Auto-setting up webhook for new user: {user.email}")
                setup_webhook_for_account(user.id, account.id)
                print(f"✅ Auto-setup webhook complete: {user.email}")
            except Exception as e:
                print(f"⚠️ Auto-setup webhook failed: {user.email}, error: {str(e)}")

        # Clear session
        session.pop("state", None)
        session.pop("adding_account", None)

        login_user(user)

        # Check and repair webhooks after login
        try:
            from ..email.routes import check_and_repair_webhooks_for_user

            check_and_repair_webhooks_for_user(user.id)
        except Exception as e:
            print(
                f"⚠️ Failed to repair webhooks after login: {user.email}, error: {str(e)}"
            )

        flash("Successfully logged in to CleanBox!", "success")
        return redirect(url_for("main.dashboard"))

    except Exception as e:
        print(f"Error handling login callback: {str(e)}")
        flash(f"An error occurred during login: {str(e)}", "error")
        return redirect(url_for("auth.login"))


def _handle_add_account_callback(credentials, id_info):
    """Handle account addition callback."""
    try:
        # Check if user is logged in
        if not current_user.is_authenticated:
            flash("Login is required.", "error")
            return redirect(url_for("auth.login"))

        # Check if account is already linked
        existing_account = UserAccount.query.filter_by(
            user_id=current_user.id, account_email=id_info["email"]
        ).first()

        if existing_account:
            # Check if the account is inactive
            if not existing_account.is_active:
                # Re-activate the inactive account
                existing_account.is_active = True
                existing_account.account_name = id_info.get(
                    "name", existing_account.account_name
                )
                db.session.commit()

                flash(
                    f"Deactivated account {id_info['email']} re-activated!",
                    "success",
                )

                # Add header for cache invalidation
                response = redirect(url_for("auth.manage_accounts"))
                response.headers["Cache-Control"] = (
                    "no-cache, no-store, must-revalidate"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"

                return response
            else:
                flash("Gmail account already linked.", "warning")
                response = redirect(url_for("auth.manage_accounts"))
                # Invalidate cache
                response.headers["Cache-Control"] = (
                    "no-cache, no-store, must-revalidate"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response

        # Create new account
        account = UserAccount(
            user_id=current_user.id,
            account_email=id_info["email"],
            account_name=id_info.get("name", ""),
            is_primary=False,
        )
        db.session.add(account)
        db.session.flush()  # account.id will be generated

        # Save token
        user_token = UserToken(user_id=current_user.id, account_id=account.id)
        user_token.set_tokens(credentials)
        db.session.add(user_token)

        db.session.commit()

        # Check and grant Pub/Sub permissions for the new account
        try:
            print(
                f"🔍 Checking Pub/Sub permissions for new account {account.account_email}..."
            )
            permission_granted = check_and_grant_pubsub_permissions(
                account.account_email
            )

            if permission_granted:
                print(
                    f"✅ Pub/Sub permission setting complete for new account {account.account_email}"
                )
            else:
                print(
                    f"⚠️ Pub/Sub permission setting failed for new account {account.account_email}"
                )
        except Exception as e:
            print(
                f"❌ Error checking new account {account.account_email} Pub/Sub permissions: {str(e)}"
            )

        # Auto-setup Gmail webhook (optional)
        try:
            from ..email.gmail_service import GmailService

            gmail_service = GmailService(current_user.id, account.id)

            # Get topic name from environment variables
            topic_name = os.environ.get("GMAIL_WEBHOOK_TOPIC")
            if topic_name:
                gmail_service.setup_gmail_watch(topic_name)
                print(f"✅ Auto-setup Gmail webhook complete: {account.account_email}")
        except Exception as e:
            print(f"⚠️ Auto-setup Gmail webhook failed: {e}")
            # Webhook setting failure is not critical, continue

        # Clear session
        session.pop("state", None)
        session.pop("adding_account", None)

        flash(f"Gmail account {id_info['email']} successfully linked!", "success")

        # Add header for cache invalidation
        response = redirect(url_for("auth.manage_accounts"))
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response

    except Exception as e:
        print(f"Error handling add account callback: {str(e)}")
        flash(f"An error occurred during account addition: {str(e)}", "error")
        return redirect(url_for("auth.manage_accounts"))


@auth_bp.route("/add-account")
@login_required
def add_account():
    """Add a new Gmail account connection."""
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
    """Manage accounts page."""
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    return render_template(
        "auth/manage_accounts.html", user=current_user, accounts=accounts
    )


@auth_bp.route("/remove-account/<int:account_id>", methods=["POST"])
@login_required
def remove_account(account_id):
    """Disconnect account."""
    account = UserAccount.query.filter_by(
        id=account_id, user_id=current_user.id
    ).first()

    if not account:
        flash("Account not found.", "error")
        return redirect(url_for("auth.manage_accounts"))

    if account.is_primary:
        flash("Primary account cannot be disconnected.", "error")
        return redirect(url_for("auth.manage_accounts"))

    # Deactivate account
    account.is_active = False
    db.session.commit()

    flash(f"{account.account_email} account disconnected.", "success")

    # Add header for cache invalidation
    response = redirect(url_for("auth.manage_accounts"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response


@auth_bp.route("/logout")
@login_required
def logout():
    """Logout."""
    try:
        # Clear user session info
        current_user.is_online = False
        current_user.session_id = None
        db.session.commit()
    except Exception as e:
        print(f"Failed to clear session on logout: {str(e)}")

    logout_user()
    session.clear()
    flash("Logged out of CleanBox.", "info")
    return redirect(url_for("auth.login"))


def get_user_credentials(user_id, account_id=None):
    """Helper function to get user's OAuth tokens."""
    if account_id:
        user_token = UserToken.query.filter_by(
            user_id=user_id, account_id=account_id
        ).first()
    else:
        # Get token for the currently active account
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
    """Get the ID of the currently active account."""
    # Return None if not logged in
    if not current_user.is_authenticated:
        return None

    # Return the ID of the primary account
    primary_account = UserAccount.query.filter_by(
        user_id=current_user.id, is_primary=True, is_active=True
    ).first()

    if primary_account:
        return primary_account.id

    # If no active account, return the ID of the first active account
    first_account = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).first()

    if first_account:
        return first_account.id

    return None


def refresh_user_token(user_id, account_id):
    """Automatically refresh user's OAuth token."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import Flow

        # Get user token
        user_token = UserToken.query.filter_by(
            user_id=user_id, account_id=account_id
        ).first()

        if not user_token:
            print(
                f"❌ User token not found: user_id={user_id}, account_id={account_id}"
            )
            return False

        # Get current token info
        tokens = user_token.get_tokens()

        if not tokens.get("refresh_token"):
            print(
                f"❌ Refresh token not found: user_id={user_id}, account_id={account_id}"
            )
            return False

        # Create Credentials object
        credentials = Credentials(
            token=tokens.get("token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=tokens.get("scopes", []),
            expiry=tokens.get("expiry"),
        )

        # Check if token is expired
        if credentials.expired and credentials.refresh_token:
            print(
                f"🔄 Attempting to refresh token: user_id={user_id}, account_id={account_id}"
            )

            # Refresh token
            credentials.refresh(Request())

            # Save refreshed token
            user_token.set_tokens(credentials)
            db.session.commit()

            print(
                f"✅ Token refreshed successfully: user_id={user_id}, account_id={account_id}"
            )
            return True
        else:
            print(f"ℹ️ Token is still valid: user_id={user_id}, account_id={account_id}")
            return True

    except Exception as e:
        print(
            f"❌ Token refresh failed: user_id={user_id}, account_id={account_id}, error={str(e)}"
        )
        return False


def check_and_refresh_token(user_id, account_id):
    """Check token status and refresh if necessary."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        # Get user token
        user_token = UserToken.query.filter_by(
            user_id=user_id, account_id=account_id
        ).first()

        if not user_token:
            return False

        # Get current token info
        tokens = user_token.get_tokens()

        if not tokens.get("refresh_token"):
            return False

        # Create Credentials object
        credentials = Credentials(
            token=tokens.get("token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri=tokens.get("token_uri"),
            client_id=tokens.get("client_id"),
            client_secret=tokens.get("client_secret"),
            scopes=tokens.get("scopes", []),
            expiry=tokens.get("expiry"),
        )

        # Check if token is expired
        if credentials.expired and credentials.refresh_token:
            return refresh_user_token(user_id, account_id)
        else:
            return True

    except Exception as e:
        print(
            f"❌ Failed to check token status: user_id={user_id}, account_id={account_id}, error={str(e)}"
        )
        return False
