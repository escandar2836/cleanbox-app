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
)
from flask_login import login_user, logout_user, login_required, current_user

# Local imports
from ..models import User, UserToken, UserAccount, Category, db

category_bp = Blueprint("category", __name__)


@category_bp.route("/")
@login_required
def list_categories():
    """카테고리 관리 페이지"""
    # 인증 상태 재확인
    if not current_user.is_authenticated:
        flash("로그인이 필요합니다.", "error")
        return redirect(url_for("auth.login"))

    # 사용자의 활성 계정 확인
    accounts = UserAccount.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()

    if not accounts:
        flash("연결된 Gmail 계정이 없습니다.", "warning")
        return redirect(url_for("auth.manage_accounts"))

    # 사용자의 활성 카테고리 목록
    categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()

    return render_template(
        "category/manage.html",
        user=current_user,
        accounts=accounts,
        categories=categories,
    )


@category_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_category():
    """새 카테고리 추가"""
    print(
        f"🔍 카테고리 추가 페이지 접근 - 사용자: {current_user.id if current_user.is_authenticated else 'Not authenticated'}"
    )

    if request.method == "POST":
        try:
            print(f"🔍 카테고리 생성 시작 - 사용자: {current_user.id}")

            name = request.form.get("name")
            description = request.form.get("description")
            color = request.form.get("color", "#007bff")
            icon = request.form.get("icon", "fas fa-tag")

            print(
                f"📝 폼 데이터: name={name}, description={description}, color={color}, icon={icon}"
            )

            if not name:
                print("❌ 카테고리 이름이 없음")
                flash("카테고리 이름을 입력해주세요.", "error")
                return render_template("category/add.html", user=current_user)

            # 중복 이름 확인
            existing = Category.query.filter_by(
                user_id=current_user.id, name=name
            ).first()
            if existing:
                print(f"❌ 중복 카테고리 이름: {name}")
                flash("이미 존재하는 카테고리 이름입니다.", "error")
                return render_template("category/add.html", user=current_user)

            # 새 카테고리 생성
            category = Category(
                user_id=current_user.id,
                name=name,
                description=description,
                color=color,
                icon=icon,
                is_active=True,
            )

            print(f"✅ 카테고리 객체 생성 완료: {category}")

            db.session.add(category)
            print("✅ DB session에 추가됨")

            db.session.commit()
            print(f"✅ DB 커밋 완료 - 카테고리 ID: {category.id}")

            flash("카테고리가 성공적으로 추가되었습니다.", "success")
            return redirect(url_for("category.list_categories"))

        except Exception as e:
            print(f"❌ 카테고리 생성 실패: {str(e)}")
            print(f"❌ 오류 타입: {type(e).__name__}")
            import traceback

            print(f"❌ 상세 오류: {traceback.format_exc()}")

            db.session.rollback()
            flash(f"카테고리 추가 중 오류가 발생했습니다: {str(e)}", "error")
            return render_template("category/add.html", user=current_user)

    return render_template("category/add.html", user=current_user)


@category_bp.route("/edit/<int:category_id>", methods=["GET", "POST"])
@login_required
def edit_category(category_id):
    """카테고리 수정"""
    category = Category.query.filter_by(id=category_id, user_id=current_user.id).first()

    if not category:
        flash("카테고리를 찾을 수 없습니다.", "error")
        return redirect(url_for("category.list_categories"))

    if request.method == "POST":
        try:
            name = request.form.get("name")
            description = request.form.get("description")
            color = request.form.get("color", "#007bff")
            icon = request.form.get("icon", "fas fa-tag")

            if not name:
                flash("카테고리 이름을 입력해주세요.", "error")
                return render_template(
                    "category/edit.html", user=current_user, category=category
                )

            # 중복 이름 확인 (자신 제외)
            existing = (
                Category.query.filter_by(user_id=current_user.id, name=name)
                .filter(Category.id != category_id)
                .first()
            )
            if existing:
                flash("이미 존재하는 카테고리 이름입니다.", "error")
                return render_template(
                    "category/edit.html", user=current_user, category=category
                )

            # 카테고리 업데이트
            category.name = name
            category.description = description
            category.color = color
            category.icon = icon

            db.session.commit()

            flash("카테고리가 성공적으로 수정되었습니다.", "success")
            return redirect(url_for("category.list_categories"))

        except Exception as e:
            db.session.rollback()
            flash(f"카테고리 수정 중 오류가 발생했습니다: {str(e)}", "error")
            return render_template(
                "category/edit.html", user=current_user, category=category
            )

    return render_template("category/edit.html", user=current_user, category=category)


@category_bp.route("/delete/<int:category_id>", methods=["POST"])
@login_required
def delete_category(category_id):
    """카테고리 삭제"""
    try:
        category = Category.query.filter_by(
            id=category_id, user_id=current_user.id
        ).first()

        if not category:
            flash("카테고리를 찾을 수 없습니다.", "error")
            return redirect(url_for("category.list_categories"))

        # 카테고리 비활성화 (실제 삭제 대신)
        category.is_active = False
        db.session.commit()

        flash("카테고리가 성공적으로 삭제되었습니다.", "success")
        return redirect(url_for("category.list_categories"))

    except Exception as e:
        db.session.rollback()
        flash(f"카테고리 삭제 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("category.list_categories"))
