# Third-party imports
from flask import Blueprint, render_template
from flask_login import login_required, current_user

# Local imports
from ..models import Category, UserAccount

main_bp = Blueprint("main", __name__)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """메인 대시보드"""
    # 사용자의 활성 계정 확인 (최신 데이터)
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    if not accounts:
        response = render_template(
            "main/dashboard.html", user=current_user, accounts=[], categories=[]
        )
        # 캐시 무효화
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # 사용자의 활성 카테고리 목록 (최신 데이터)
    categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()

    response = render_template(
        "main/dashboard.html",
        user=current_user,
        accounts=accounts,
        categories=categories,
    )

    # 캐시 무효화
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response
