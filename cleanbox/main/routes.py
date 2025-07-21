# Third-party imports
from flask import Blueprint, render_template, make_response
from flask_login import login_required, current_user

# Local imports
from ..models import Category, UserAccount

main_bp = Blueprint("main", __name__)


@main_bp.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard"""
    # Check user's active accounts (latest data)
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    if not accounts:
        response = make_response(
            render_template(
                "main/dashboard.html", user=current_user, accounts=[], categories=[]
            )
        )
        # Invalidate cache
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # User's active category list (latest data)
    categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()

    response = make_response(
        render_template(
            "main/dashboard.html",
            user=current_user,
            accounts=accounts,
            categories=categories,
        )
    )

    # Invalidate cache
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    return response
