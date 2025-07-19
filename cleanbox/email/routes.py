from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from ..models import Email, Category, UserAccount, db
from .gmail_service import GmailService
from .ai_classifier import AIClassifier
from datetime import datetime
import traceback

email_bp = Blueprint("email", __name__)


@email_bp.route("/")
@login_required
def list_emails():
    """이메일 목록 페이지 (모든 계정 통합)"""
    try:
        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            flash("연결된 계정이 없습니다.", "error")
            return render_template(
                "email/list.html", user=current_user, emails=[], stats={}, accounts=[]
            )

        # 모든 계정의 이메일 통합 조회
        emails = (
            Email.query.filter(
                Email.user_id == current_user.id,
                Email.account_id.in_([acc.id for acc in accounts]),
            )
            .order_by(Email.created_at.desc())
            .limit(100)  # 더 많은 이메일 표시
            .all()
        )

        # 계정 정보를 이메일에 추가
        account_dict = {acc.id: acc for acc in accounts}
        for email in emails:
            email.account_info = account_dict.get(email.account_id)

        # 계정별 이메일 수 계산
        account_stats = {}
        for account in accounts:
            account_emails = [e for e in emails if e.account_id == account.id]
            account_stats[account.id] = {
                "email": account.account_email,
                "name": account.account_name,
                "count": len(account_emails),
                "unread": sum(1 for e in account_emails if not e.is_read),
                "archived": sum(1 for e in account_emails if e.is_archived),
            }

        # 통계 정보
        stats = {
            "total": len(emails),
            "unread": sum(1 for e in emails if not e.is_read),
            "archived": sum(1 for e in emails if e.is_archived),
            "account_stats": account_stats,
        }

        return render_template(
            "email/list.html",
            user=current_user,
            emails=emails,
            stats=stats,
            accounts=accounts,
        )

    except Exception as e:
        flash(f"이메일 목록을 불러오는 중 오류가 발생했습니다: {str(e)}", "error")
        return render_template(
            "email/list.html", user=current_user, emails=[], stats={}, accounts=[]
        )


@email_bp.route("/<int:category_id>")
@login_required
def category_emails(category_id):
    """카테고리별 이메일 목록 (모든 계정 통합)"""
    try:
        # 사용자별 카테고리 확인
        category = Category.query.filter_by(
            id=category_id, user_id=current_user.id
        ).first()
        if not category:
            flash("카테고리를 찾을 수 없습니다.", "error")
            return redirect(url_for("email.list_emails"))

        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        # 해당 카테고리의 모든 계정 이메일 조회
        emails = (
            Email.query.filter(
                Email.user_id == current_user.id,
                Email.category_id == category_id,
                Email.account_id.in_([acc.id for acc in accounts]),
            )
            .order_by(Email.created_at.desc())
            .all()
        )

        # 계정 정보를 이메일에 추가
        account_dict = {acc.id: acc for acc in accounts}
        for email in emails:
            email.account_info = account_dict.get(email.account_id)

        # 계정별 이메일 수 계산
        account_stats = {}
        for account in accounts:
            account_emails = [e for e in emails if e.account_id == account.id]
            account_stats[account.id] = {
                "email": account.account_email,
                "name": account.account_name,
                "count": len(account_emails),
            }

        return render_template(
            "email/category.html",
            user=current_user,
            category=category,
            emails=emails,
            accounts=accounts,
            account_stats=account_stats,
        )

    except Exception as e:
        flash(f"카테고리 이메일을 불러오는 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


@email_bp.route("/process-new", methods=["POST"])
@login_required
def process_new_emails():
    """최초 서비스 접속 시간 이후의 새 이메일 처리"""
    try:
        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        total_processed = 0
        total_classified = 0
        account_results = []

        # 최초 서비스 접속 시간 이후의 이메일만 처리
        first_access_time = current_user.first_service_access

        # 모든 계정에 대해 새 이메일 처리
        for account in accounts:
            try:
                print(f"🔍 새 이메일 처리 - 계정: {account.account_email}")

                gmail_service = GmailService(current_user.id, account.id)
                ai_classifier = AIClassifier()

                # 최근 이메일 가져오기 (최초 접속 시간 이후만)
                recent_emails = gmail_service.fetch_emails_after_date(first_access_time)

                if not recent_emails:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "processed": 0,
                            "classified": 0,
                            "status": "no_new_emails",
                        }
                    )
                    continue

                # 사용자 카테고리 가져오기
                categories = gmail_service.get_user_categories()

                account_processed = 0
                account_classified = 0

                for email_data in recent_emails:
                    try:
                        # 이미 처리된 이메일인지 확인
                        existing_email = Email.query.filter_by(
                            user_id=current_user.id,
                            account_id=account.id,
                            gmail_id=email_data["gmail_id"],
                        ).first()

                        if existing_email:
                            continue  # 이미 처리된 이메일은 건너뛰기

                        # DB에 저장
                        email_obj = gmail_service.save_email_to_db(email_data)

                        if email_obj:
                            account_processed += 1
                            total_processed += 1

                            # AI 분류 및 요약 시도
                            if categories:
                                category_id, summary = (
                                    ai_classifier.classify_and_summarize_email(
                                        email_data["body"],
                                        email_data["subject"],
                                        email_data["sender"],
                                        categories,
                                    )
                                )

                                if category_id:
                                    gmail_service.update_email_category(
                                        email_data["gmail_id"], category_id
                                    )
                                    account_classified += 1
                                    total_classified += 1

                                # 요약 저장
                                if (
                                    summary
                                    and summary
                                    != "AI 처리를 사용할 수 없습니다. 수동으로 확인해주세요."
                                ):
                                    email_obj.summary = summary
                                    db.session.commit()

                    except Exception as e:
                        print(f"이메일 처리 실패: {str(e)}")
                        continue

                account_results.append(
                    {
                        "account": account.account_email,
                        "processed": account_processed,
                        "classified": account_classified,
                        "status": "success",
                    }
                )

            except Exception as e:
                print(f"계정 {account.account_email} 처리 실패: {str(e)}")
                account_results.append(
                    {
                        "account": account.account_email,
                        "processed": 0,
                        "classified": 0,
                        "status": "error",
                        "error": str(e),
                    }
                )

        flash(
            f"새 이메일 처리 완료: {total_processed}개 처리, {total_classified}개 AI 분류",
            "success",
        )

        return jsonify(
            {
                "success": True,
                "processed": total_processed,
                "classified": total_classified,
                "account_results": account_results,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"새 이메일 처리 중 오류: {str(e)}"}
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
    """이메일 AI 분석 (경량화)"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            return jsonify({"success": False, "message": "이메일을 찾을 수 없습니다."})

        ai_classifier = AIClassifier()

        # 구독해지 링크 추출
        unsubscribe_links = ai_classifier.extract_unsubscribe_links(email_obj.content)

        analysis = {
            "summary": email_obj.summary or "요약 없음",
            "unsubscribe_links": unsubscribe_links,
            "has_unsubscribe": len(unsubscribe_links) > 0,
        }

        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        return jsonify({"success": False, "message": f"분석 중 오류: {str(e)}"})


@email_bp.route("/statistics")
@login_required
def email_statistics():
    """이메일 통계 (모든 계정 합산)"""
    try:
        from ..auth.routes import get_current_account_id

        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify(
                {
                    "success": True,
                    "statistics": {
                        "total": 0,
                        "unread": 0,
                        "archived": 0,
                        "categories": {},
                    },
                }
            )

        # 모든 계정의 통계 합산
        total_stats = {"total": 0, "unread": 0, "archived": 0, "categories": {}}

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)
                account_stats = gmail_service.get_email_statistics()

                # 기본 통계 합산
                total_stats["total"] += account_stats.get("total", 0)
                total_stats["unread"] += account_stats.get("unread", 0)
                total_stats["archived"] += account_stats.get("archived", 0)

                # 카테고리별 통계 합산
                for category_id, count in account_stats.get("categories", {}).items():
                    if category_id in total_stats["categories"]:
                        total_stats["categories"][category_id] += count
                    else:
                        total_stats["categories"][category_id] = count

            except Exception as e:
                print(f"계정 {account.account_email} 통계 조회 실패: {str(e)}")
                continue

        return jsonify({"success": True, "statistics": total_stats})

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
            # 대량 구독해지 (경량화)
            ai_classifier = AIClassifier()

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()
                    if email_obj:
                        # 구독해지 링크 추출
                        unsubscribe_links = ai_classifier.extract_unsubscribe_links(
                            email_obj.content
                        )

                        if unsubscribe_links:
                            # 첫 번째 링크로 구독해지 시도
                            page_analysis = ai_classifier.analyze_unsubscribe_page(
                                unsubscribe_links[0]
                            )

                            if page_analysis["success"]:
                                processed_count += 1
                                print(
                                    f"구독해지 성공 (ID: {email_id}): {unsubscribe_links[0]}"
                                )
                            else:
                                print(
                                    f"구독해지 페이지 분석 실패 (ID: {email_id}): {page_analysis['message']}"
                                )
                        else:
                            print(f"구독해지 링크 없음 (ID: {email_id})")

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
