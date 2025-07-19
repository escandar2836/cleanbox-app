from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from ..models import Email, Category, db
from .gmail_service import GmailService
from .ai_classifier import AIClassifier
from datetime import datetime
import traceback

email_bp = Blueprint("email", __name__)


@email_bp.route("/")
@login_required
def list_emails():
    """이메일 목록 페이지"""
    try:
        # 사용자별 이메일만 조회
        emails = (
            Email.query.filter_by(user_id=current_user.id)
            .order_by(Email.created_at.desc())
            .limit(50)
            .all()
        )

        # 통계 정보
        stats = {
            "total": len(emails),
            "unread": sum(1 for e in emails if not e.is_read),
            "archived": sum(1 for e in emails if e.is_archived),
        }

        return render_template(
            "email/list.html", user=current_user, emails=emails, stats=stats
        )

    except Exception as e:
        flash(f"이메일 목록을 불러오는 중 오류가 발생했습니다: {str(e)}", "error")
        return render_template(
            "email/list.html", user=current_user, emails=[], stats={}
        )


@email_bp.route("/<int:category_id>")
@login_required
def category_emails(category_id):
    """카테고리별 이메일 목록"""
    try:
        # 사용자별 카테고리 확인
        category = Category.query.filter_by(
            id=category_id, user_id=current_user.id
        ).first()
        if not category:
            flash("카테고리를 찾을 수 없습니다.", "error")
            return redirect(url_for("email.list_emails"))

        # 해당 카테고리의 사용자별 이메일 조회
        emails = (
            Email.query.filter_by(user_id=current_user.id, category_id=category_id)
            .order_by(Email.created_at.desc())
            .all()
        )

        return render_template(
            "email/category.html", user=current_user, category=category, emails=emails
        )

    except Exception as e:
        flash(f"카테고리 이메일을 불러오는 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/sync", methods=["POST"])
@login_required
def sync_emails():
    """Gmail에서 이메일 동기화 (페이지네이션 지원)"""
    try:
        page = request.form.get("page", 1, type=int)
        per_page = 20  # 한 번에 20개씩

        gmail_service = GmailService(current_user.id)
        ai_classifier = AIClassifier()

        # 페이지네이션을 위한 오프셋 계산
        offset = (page - 1) * per_page

        # 최근 이메일 가져오기 (페이지네이션 적용)
        recent_emails = gmail_service.fetch_recent_emails(
            max_results=per_page, offset=offset
        )

        if not recent_emails:
            if page == 1:
                flash("동기화할 새 이메일이 없습니다.", "info")
            else:
                flash("더 이상 가져올 이메일이 없습니다.", "info")
            return redirect(url_for("email.list_emails"))

        # 사용자 카테고리 가져오기
        categories = gmail_service.get_user_categories()

        processed_count = 0
        classified_count = 0

        for email_data in recent_emails:
            try:
                # DB에 저장
                email_obj = gmail_service.save_email_to_db(email_data)

                if email_obj:
                    processed_count += 1

                    # AI 분류 시도
                    if categories:
                        category_id, reasoning = ai_classifier.classify_email(
                            email_data["body"],
                            email_data["subject"],
                            email_data["sender"],
                            categories,
                        )

                        if category_id:
                            gmail_service.update_email_category(
                                email_data["gmail_id"], category_id
                            )
                            classified_count += 1

                    # AI 요약 생성
                    summary = ai_classifier.summarize_email(
                        email_data["body"], email_data["subject"]
                    )
                    if (
                        summary
                        and summary
                        != "AI 요약을 사용할 수 없습니다. 이메일 내용을 직접 확인해주세요."
                    ):
                        email_obj.summary = summary
                        db.session.commit()

            except Exception as e:
                print(f"이메일 처리 실패: {str(e)}")
                continue

        # 다음 페이지가 있는지 확인
        next_page_emails = gmail_service.fetch_recent_emails(
            max_results=per_page, offset=offset + per_page
        )

        has_more = len(next_page_emails) > 0

        flash(
            f"페이지 {page}: {processed_count}개의 이메일을 처리했습니다. (AI 분류: {classified_count}개)",
            "success",
        )

        return jsonify(
            {
                "success": True,
                "processed": processed_count,
                "classified": classified_count,
                "page": page,
                "has_more": has_more,
                "next_page": page + 1 if has_more else None,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"이메일 동기화 중 오류: {str(e)}"}
        )


@email_bp.route("/<int:email_id>/read")
@login_required
def mark_as_read(email_id):
    """이메일을 읽음으로 표시"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("이메일을 찾을 수 없습니다.", "error")
            return redirect(url_for("email.list_emails"))

        gmail_service = GmailService(current_user.id)
        gmail_service.mark_as_read(email_obj.gmail_id)

        flash("이메일을 읽음으로 표시했습니다.", "success")
        return redirect(url_for("email.list_emails"))

    except Exception as e:
        flash(f"이메일 상태 변경 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/archive")
@login_required
def archive_email(email_id):
    """이메일 아카이브"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("이메일을 찾을 수 없습니다.", "error")
            return redirect(url_for("email.list_emails"))

        gmail_service = GmailService(current_user.id)
        gmail_service.archive_email(email_obj.gmail_id)

        flash("이메일을 아카이브했습니다.", "success")
        return redirect(url_for("email.list_emails"))

    except Exception as e:
        flash(f"이메일 아카이브 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/classify", methods=["POST"])
@login_required
def classify_email(email_id):
    """이메일 수동 분류"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            return jsonify({"success": False, "message": "이메일을 찾을 수 없습니다."})

        category_id = request.form.get("category_id")
        if category_id:
            category_id = int(category_id)
            if category_id == 0:  # 미분류
                category_id = None

        gmail_service = GmailService(current_user.id)
        success = gmail_service.update_email_category(email_obj.gmail_id, category_id)

        if success:
            return jsonify({"success": True, "message": "이메일이 분류되었습니다."})
        else:
            return jsonify({"success": False, "message": "이메일 분류에 실패했습니다."})

    except Exception as e:
        return jsonify({"success": False, "message": f"오류: {str(e)}"})


@email_bp.route("/<int:email_id>/analyze")
@login_required
def analyze_email(email_id):
    """이메일 AI 분석"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            return jsonify({"success": False, "message": "이메일을 찾을 수 없습니다."})

        ai_classifier = AIClassifier()

        # 감정 분석
        sentiment = ai_classifier.analyze_email_sentiment(
            email_obj.content, email_obj.subject
        )

        # 키워드 추출
        keywords = ai_classifier.extract_keywords(email_obj.content)

        # 스팸 판별
        spam_check = ai_classifier.is_spam_or_unwanted(
            email_obj.content, email_obj.subject, email_obj.sender
        )

        analysis = {
            "sentiment": sentiment,
            "keywords": keywords,
            "spam_check": spam_check,
            "summary": email_obj.summary or "요약 없음",
        }

        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        return jsonify({"success": False, "message": f"분석 중 오류: {str(e)}"})


@email_bp.route("/statistics")
@login_required
def email_statistics():
    """이메일 통계"""
    try:
        gmail_service = GmailService(current_user.id)
        stats = gmail_service.get_email_statistics()

        return jsonify({"success": True, "statistics": stats})

    except Exception as e:
        return jsonify({"success": False, "message": f"통계 조회 중 오류: {str(e)}"})


@email_bp.route("/<int:email_id>")
@login_required
def view_email(email_id):
    """이메일 상세 보기"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("이메일을 찾을 수 없습니다.", "error")
            return redirect(url_for("email.list_emails"))

        # 카테고리 정보 (미분류 및 카테고리 없음 케이스 커버)
        category = None
        if email_obj.category_id:
            # 사용자 권한 확인하여 카테고리 조회
            category = Category.query.filter_by(
                id=email_obj.category_id, user_id=current_user.id
            ).first()
            # 카테고리가 없거나 삭제된 경우 category_id를 None으로 설정
            if not category:
                email_obj.category_id = None
                db.session.commit()

        # 사용자 카테고리 목록 (분류 변경용)
        user_categories = Category.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        return render_template(
            "email/view.html",
            user=current_user,
            email=email_obj,
            category=category,
            categories=user_categories,
        )

    except Exception as e:
        flash(f"이메일을 불러오는 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/bulk-actions", methods=["POST"])
@login_required
def bulk_actions():
    """이메일 대량 작업"""
    try:
        action = request.form.get("action")
        email_ids = request.form.getlist("email_ids")

        if not email_ids:
            flash("선택된 이메일이 없습니다.", "error")
            return redirect(request.referrer or url_for("email.list_emails"))

        gmail_service = GmailService(current_user.id)
        processed_count = 0

        if action == "delete":
            # 대량 삭제
            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()
                    if email_obj:
                        # Gmail에서 삭제
                        gmail_service.delete_email(email_obj.gmail_id)
                        # DB에서 삭제
                        db.session.delete(email_obj)
                        processed_count += 1
                except Exception as e:
                    print(f"이메일 삭제 실패 (ID: {email_id}): {str(e)}")
                    continue

            db.session.commit()
            flash(f"{processed_count}개의 이메일을 삭제했습니다.", "success")

        elif action == "archive":
            # 대량 아카이브
            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()
                    if email_obj:
                        gmail_service.archive_email(email_obj.gmail_id)
                        processed_count += 1
                except Exception as e:
                    print(f"이메일 아카이브 실패 (ID: {email_id}): {str(e)}")
                    continue

            flash(f"{processed_count}개의 이메일을 아카이브했습니다.", "success")

        elif action == "mark_read":
            # 대량 읽음 표시
            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()
                    if email_obj:
                        gmail_service.mark_as_read(email_obj.gmail_id)
                        processed_count += 1
                except Exception as e:
                    print(f"이메일 읽음 표시 실패 (ID: {email_id}): {str(e)}")
                    continue

            flash(f"{processed_count}개의 이메일을 읽음으로 표시했습니다.", "success")

        elif action == "unsubscribe":
            # 대량 구독해지
            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()
                    if email_obj:
                        # 고급 구독해지 처리
                        unsubscribe_result = gmail_service.process_unsubscribe(
                            email_obj
                        )
                        if unsubscribe_result["success"]:
                            processed_count += 1
                        else:
                            print(
                                f"구독해지 실패 (ID: {email_id}): {unsubscribe_result['message']}"
                            )
                except Exception as e:
                    print(f"구독해지 실패 (ID: {email_id}): {str(e)}")
                    continue

            flash(
                f"{processed_count}개의 이메일에서 구독해지를 처리했습니다.", "success"
            )

        else:
            flash("지원하지 않는 작업입니다.", "error")

        return redirect(request.referrer or url_for("email.list_emails"))

    except Exception as e:
        flash(f"대량 작업 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(request.referrer or url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/unsubscribe")
@login_required
def unsubscribe_email(email_id):
    """개별 이메일 구독해지"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            flash("이메일을 찾을 수 없습니다.", "error")
            return redirect(url_for("email.list_emails"))

        gmail_service = GmailService(current_user.id)
        result = gmail_service.process_unsubscribe(email_obj)

        if result["success"]:
            flash("구독해지가 처리되었습니다.", "success")
        else:
            flash(f"구독해지 처리 실패: {result['message']}", "warning")

        return redirect(url_for("email.list_emails"))

    except Exception as e:
        flash(f"구독해지 처리 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


def get_user_emails(user_id, limit=50):
    """사용자의 이메일을 가져오는 헬퍼 함수"""
    return (
        Email.query.filter_by(user_id=user_id)
        .order_by(Email.created_at.desc())
        .limit(limit)
        .all()
    )
