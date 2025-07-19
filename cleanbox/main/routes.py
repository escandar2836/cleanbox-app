from flask import Blueprint, render_template
from flask_login import login_required, current_user
from ..models import Category, UserAccount

main_bp = Blueprint("main", __name__)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """메인 대시보드"""
    # 사용자의 활성 계정 확인
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    if not accounts:
        return render_template(
            "main/dashboard.html", user=current_user, accounts=[], categories=[]
        )

    # 사용자의 활성 카테고리 목록
    categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()

    return render_template(
        "main/dashboard.html",
        user=current_user,
        accounts=accounts,
        categories=categories,
    )
