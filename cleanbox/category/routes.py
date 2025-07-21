# Standard library imports
import os

# Third-party imports
from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    session,
    flash,
    render_template,
    jsonify,
    make_response,
)
from flask_login import login_user, logout_user, login_required, current_user

# Local imports
from ..models import User, UserToken, UserAccount, Category, db

category_bp = Blueprint("category", __name__)


@category_bp.route("/")
@login_required
def list_categories():
    """Category management page"""
    # Re-check authentication status
    if not current_user.is_authenticated:
        flash("Login required.", "error")
        return redirect(url_for("auth.login"))

    # Check user's active accounts (latest data)
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    if not accounts:
        flash("No connected Gmail accounts.", "warning")
        response = redirect(url_for("auth.manage_accounts"))
        # Invalidate cache
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    # User's active category list (latest data)
    categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()

    response = make_response(
        render_template(
            "category/manage.html",
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


@category_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_category():
    """Add new category"""
    if request.method == "POST":
        try:
            name = request.form.get("name")
            description = request.form.get("description")
            color = request.form.get("color", "#007bff")
            icon = request.form.get("icon", "fas fa-tag")

            if not name:
                flash("Please enter a category name.", "error")
                return render_template("category/add.html", user=current_user)

            # Check for duplicate name
            existing = Category.query.filter_by(
                user_id=current_user.id, name=name
            ).first()
            if existing:
                flash("Category name already exists.", "error")
                return render_template("category/add.html", user=current_user)

            # Create new category
            category = Category(
                user_id=current_user.id,
                name=name,
                description=description,
                color=color,
                icon=icon,
                is_active=True,
            )

            db.session.add(category)
            db.session.commit()

            flash("Category added successfully.", "success")
            return redirect(url_for("category.list_categories"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error occurred while adding category: {str(e)}", "error")
            return render_template("category/add.html", user=current_user)

    return render_template("category/add.html", user=current_user)


@category_bp.route("/edit/<int:category_id>", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    """Edit category"""
    category = Category.query.filter_by(id=category_id, user_id=current_user.id).first()

    if not category:
        flash("Category not found.", "error")
        return redirect(url_for("category.list_categories"))

    if request.method == "POST":
        try:
            name = request.form.get("name")
            description = request.form.get("description")
            color = request.form.get("color", "#007bff")
            icon = request.form.get("icon", "fas fa-tag")

            if not name:
                flash("Please enter a category name.", "error")
                return render_template(
                    "category/edit.html", user=current_user, category=category
                )

            # Check for duplicate name (excluding self)
            existing = (
                Category.query.filter_by(user_id=current_user.id, name=name)
                .filter(Category.id != category_id)
                .first()
            )
            if existing:
                flash("Category name already exists.", "error")
                return render_template(
                    "category/edit.html", user=current_user, category=category
                )

            # Update category
            category.name = name
            category.description = description
            category.color = color
            category.icon = icon

            db.session.commit()

            flash("Category updated successfully.", "success")
            return redirect(url_for("category.list_categories"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error occurred while updating category: {str(e)}", "error")
            return render_template(
                "category/edit.html", user=current_user, category=category
            )

    return render_template("category/edit.html", user=current_user, category=category)


@category_bp.route("/delete/<int:category_id>", methods=["POST"])
@login_required
def delete_category(category_id):
    """Delete category"""
    try:
        category = Category.query.filter_by(
            id=category_id, user_id=current_user.id
        ).first()

        if not category:
            flash("Category not found.", "error")
            return redirect(url_for("category.list_categories"))

        # Deactivate category (instead of actual delete)
        category.is_active = False
        db.session.commit()

        flash("Category deleted successfully.", "success")
        return redirect(url_for("category.list_categories"))

    except Exception as e:
        db.session.rollback()
        flash(f"Error occurred while deleting category: {str(e)}", "error")
        return redirect(url_for("category.list_categories"))
