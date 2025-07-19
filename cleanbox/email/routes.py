# Standard library imports
import os
import traceback
from datetime import datetime, timedelta

# Third-party imports
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

# Local imports
from ..models import Email, Category, UserAccount, WebhookStatus, db
from .gmail_service import GmailService
from .ai_classifier import AIClassifier

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
            .limit(100)
            .all()
        )

        # 계정 정보를 이메일에 추가
        account_dict = {acc.id: acc for acc in accounts}
        for email in emails:
            email.account_info = account_dict.get(email.account_id)

        # 계정별 이메일 수 계산
        account_stats = {}
        for account in accounts:
            account_emails = Email.query.filter_by(
                user_id=current_user.id, account_id=account.id
            ).count()
            account_unread = Email.query.filter_by(
                user_id=current_user.id, account_id=account.id, is_read=False
            ).count()
            account_archived = Email.query.filter_by(
                user_id=current_user.id, account_id=account.id, is_archived=True
            ).count()

            account_stats[account.id] = {
                "email": account.account_email,
                "name": account.account_name,
                "count": account_emails,
                "unread": account_unread,
                "archived": account_archived,
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


@email_bp.route("/category/<int:category_id>")
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
    """가입 날짜 이후의 새 이메일 처리"""
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
        all_accounts_no_emails = True  # 모든 계정에서 새 이메일이 없는지 확인

        # 사용자의 가입 날짜 이후의 이메일만 처리
        after_date = current_user.first_service_access

        # 모든 계정에 대해 새 이메일 처리
        for account in accounts:
            try:
                print(
                    f"🔍 새 이메일 처리 - 계정: {account.account_email}, 가입일: {after_date}"
                )

                gmail_service = GmailService(current_user.id, account.id)
                ai_classifier = AIClassifier()

                # 가입 날짜 이후의 이메일 가져오기
                recent_emails = gmail_service.fetch_recent_emails(
                    max_results=50, after_date=after_date
                )

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

                # 이메일이 있으면 all_accounts_no_emails를 False로 설정
                all_accounts_no_emails = False

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

        # 모든 계정에서 새 이메일이 없는 경우
        if all_accounts_no_emails:
            return jsonify(
                {
                    "success": True,
                    "processed": 0,
                    "classified": 0,
                    "account_results": account_results,
                    "no_new_emails": True,
                    "message": "새로운 이메일이 없습니다.",
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
                "no_new_emails": False,
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


def process_missed_emails_for_account(
    user_id: str, account_id: int, from_date: datetime
) -> dict:
    """특정 계정의 누락된 이메일 처리"""
    try:
        from .gmail_service import GmailService
        from .ai_classifier import AIClassifier

        print(f"📧 누락된 이메일 처리 시작 - 계정: {account_id}, 시작일: {from_date}")

        # Gmail 서비스 및 AI 분류기 초기화
        gmail_service = GmailService(user_id, account_id)
        ai_classifier = AIClassifier()

        # 누락된 기간의 이메일 가져오기
        missed_emails = gmail_service.fetch_recent_emails(
            max_results=100, after_date=from_date  # 최대 100개 이메일 처리
        )

        if not missed_emails:
            print(f"📭 누락된 이메일 없음 - 계정: {account_id}")
            return {
                "success": True,
                "processed_count": 0,
                "classified_count": 0,
                "message": "누락된 이메일이 없습니다.",
            }

        print(f"📥 누락된 이메일 {len(missed_emails)}개 발견 - 계정: {account_id}")

        # 사용자 카테고리 가져오기
        categories = gmail_service.get_user_categories()

        processed_count = 0
        classified_count = 0

        for email_data in missed_emails:
            try:
                # 이메일이 이미 DB에 있는지 확인
                existing_email = Email.query.filter_by(
                    user_id=user_id,
                    account_id=account_id,
                    gmail_id=email_data.get("gmail_id"),
                ).first()

                if existing_email:
                    print(
                        f"⏭️ 이미 처리된 이메일 건너뛰기: {email_data.get('subject', 'No subject')}"
                    )
                    continue

                # 이메일 분류
                classification_result = ai_classifier.classify_email(
                    email_data.get("subject", ""),
                    email_data.get("snippet", ""),
                    email_data.get("sender", ""),
                    categories,
                )

                # 이메일 DB에 저장
                email = Email(
                    user_id=user_id,
                    account_id=account_id,
                    gmail_id=email_data.get("gmail_id"),
                    subject=email_data.get("subject", ""),
                    sender=email_data.get("sender", ""),
                    recipient=email_data.get("recipient", ""),
                    date=email_data.get("date"),
                    snippet=email_data.get("snippet", ""),
                    body=email_data.get("body", ""),
                    category_id=classification_result.get("category_id"),
                    category_name=classification_result.get("category_name"),
                    confidence_score=classification_result.get("confidence_score", 0.0),
                    is_read=False,
                    is_archived=False,
                    created_at=datetime.utcnow(),
                )

                db.session.add(email)
                processed_count += 1

                if classification_result.get("category_id"):
                    classified_count += 1

                print(
                    f"✅ 누락된 이메일 처리 완료: {email_data.get('subject', 'No subject')} -> {classification_result.get('category_name', '미분류')}"
                )

            except Exception as e:
                print(
                    f"❌ 누락된 이메일 처리 실패: {email_data.get('subject', 'No subject')}, 오류: {str(e)}"
                )
                continue

        db.session.commit()

        result = {
            "success": True,
            "processed_count": processed_count,
            "classified_count": classified_count,
            "total_missed": len(missed_emails),
            "message": f"누락된 이메일 {processed_count}개 처리 완료 (분류: {classified_count}개)",
        }

        print(
            f"🎉 누락된 이메일 처리 완료 - 계정: {account_id}, 처리: {processed_count}개, 분류: {classified_count}개"
        )

        return result

    except Exception as e:
        print(f"❌ 누락된 이메일 처리 중 오류 - 계정: {account_id}, 오류: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": f"누락된 이메일 처리 실패: {str(e)}",
        }


def setup_gmail_webhook_with_permissions(
    account_id: int, topic_name: str, label_ids: list = None
) -> dict:
    """Gmail 웹훅을 설정합니다. (권한 확인 포함)"""
    try:
        from ..auth.routes import grant_service_account_pubsub_permissions
        import os

        # 1단계: 서비스 계정 권한 확인 및 부여
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            print(f"🔧 Gmail 웹훅 설정 전 서비스 계정 권한 확인 중...")
            service_account_success = grant_service_account_pubsub_permissions(
                project_id
            )
            if not service_account_success:
                print(f"⚠️ 서비스 계정 권한 부여 실패, 웹훅 설정을 계속 진행합니다.")

        # 2단계: 기존 웹훅 설정 로직
        return setup_gmail_webhook(account_id, topic_name, label_ids)

    except Exception as e:
        print(f"❌ Gmail 웹훅 설정 중 오류: {str(e)}")
        return {"success": False, "error": str(e)}


def setup_webhook_for_account(user_id: str, account_id: int) -> bool:
    """계정에 대한 웹훅을 설정합니다."""
    try:
        # 계정 정보 가져오기
        account = UserAccount.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            print(f"❌ 계정 {account_id}를 찾을 수 없습니다.")
            return False

        # 토픽 이름 설정
        topic_name = os.getenv("GMAIL_WEBHOOK_TOPIC", "gmail-notifications")
        full_topic_name = (
            f"projects/{os.getenv('GOOGLE_CLOUD_PROJECT')}/topics/{topic_name}"
        )

        print(f"🔧 웹훅 설정 시작 - 계정: {account_id}, 토픽: {full_topic_name}")

        # Gmail API 요청
        print(f"📤 Gmail API 요청 - 계정: {account_id}")
        print(f"   토픽: {full_topic_name}")
        print(f"   라벨: {['INBOX']}")

        # 권한 확인을 포함한 웹훅 설정
        result = setup_gmail_webhook_with_permissions(
            account_id, full_topic_name, ["INBOX"]
        )

        if result.get("success"):
            print(f"✅ 계정 {account_id}의 웹훅 설정 완료")
            return True
        else:
            print(f"❌ Gmail 웹훅 설정 실패: {account_id}")
            print(f"   오류 타입: {type(result.get('error')).__name__}")
            print(f"   오류 메시지: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ 웹훅 설정 중 오류: {str(e)}")
        return False


@email_bp.route("/setup-webhook", methods=["POST"])
@login_required
def setup_webhook():
    """Gmail 웹훅 설정"""
    try:
        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        success_count = 0
        failed_accounts = []

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)

                # 웹훅 중지 후 재설정
                gmail_service.stop_gmail_watch()

                # 웹훅 설정 (topic_name은 환경변수에서 가져오거나 기본값 사용)
                topic_name = os.environ.get(
                    "GMAIL_WEBHOOK_TOPIC",
                    "projects/cleanbox-466314/topics/gmail-notifications",
                )

                if gmail_service.setup_gmail_watch(topic_name):
                    success_count += 1
                else:
                    failed_accounts.append(account.account_email)

            except Exception as e:
                print(f"웹훅 설정 실패 - 계정 {account.account_email}: {str(e)}")
                failed_accounts.append(account.account_email)

        if success_count > 0:
            message = f"웹훅 설정 완료: {success_count}개 계정"
            if failed_accounts:
                message += f", 실패: {', '.join(failed_accounts)}"

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "success_count": success_count,
                    "failed_accounts": failed_accounts,
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "message": f"모든 계정에서 웹훅 설정 실패: {', '.join(failed_accounts)}",
                }
            )

    except Exception as e:
        return jsonify({"success": False, "message": f"웹훅 설정 중 오류: {str(e)}"})


@email_bp.route("/webhook-status")
@login_required
def webhook_status():
    """웹훅 상태 확인 (자동 복구 포함)"""
    try:
        # 먼저 사용자의 웹훅 상태 확인 및 자동 복구
        repair_result = check_and_repair_webhooks_for_user(current_user.id)

        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        webhook_statuses = []
        total_accounts = len(accounts)
        healthy_accounts = 0

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)
                status = gmail_service.get_webhook_status()

                webhook_statuses.append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        **status,
                    }
                )

                if status["status"] == "healthy":
                    healthy_accounts += 1

            except Exception as e:
                webhook_statuses.append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "is_active": False,
                        "status": "error",
                        "message": f"상태 확인 실패: {str(e)}",
                    }
                )

        # 복구 결과 메시지 추가
        repair_message = ""
        if repair_result["success"]:
            if repair_result["repaired_count"] > 0:
                repair_message = (
                    f"웹훅 자동 복구 완료: {repair_result['repaired_count']}개 계정"
                )
            elif repair_result["healthy_count"] > 0:
                repair_message = f"모든 웹훅이 정상 상태입니다 ({repair_result['healthy_count']}개 계정)"

        return jsonify(
            {
                "success": True,
                "total_accounts": total_accounts,
                "healthy_accounts": healthy_accounts,
                "webhook_statuses": webhook_statuses,
                "repair_result": repair_result,
                "repair_message": repair_message,
            }
        )

    except Exception as e:
        return jsonify({"success": False, "message": f"웹훅 상태 확인 실패: {str(e)}"})


@email_bp.route("/auto-renew-webhook", methods=["POST"])
@login_required
def auto_renew_webhook():
    """웹훅 자동 재설정 (만료된 웹훅 자동 갱신)"""
    try:
        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        renewed_count = 0
        failed_count = 0
        account_results = []

        for account in accounts:
            try:
                print(f"🔄 웹훅 자동 재설정 - 계정: {account.account_email}")

                # 웹훅 상태 확인
                webhook_status = WebhookStatus.query.filter_by(
                    user_id=current_user.id, account_id=account.id, is_active=True
                ).first()

                # 웹훅이 없거나 만료된 경우 재설정
                if not webhook_status or webhook_status.is_expired:
                    success = setup_webhook_for_account(current_user.id, account.id)

                    if success:
                        renewed_count += 1
                        account_results.append(
                            {
                                "account": account.account_email,
                                "status": "renewed",
                                "message": "웹훅 재설정 완료",
                            }
                        )
                    else:
                        failed_count += 1
                        account_results.append(
                            {
                                "account": account.account_email,
                                "status": "failed",
                                "message": "웹훅 재설정 실패",
                            }
                        )
                else:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "healthy",
                            "message": "웹훅 정상 상태",
                        }
                    )

            except Exception as e:
                print(f"계정 {account.account_email} 웹훅 재설정 실패: {str(e)}")
                failed_count += 1
                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "error",
                        "message": str(e),
                    }
                )

        # 결과 메시지 생성
        if renewed_count > 0:
            message = f"{renewed_count}개 계정의 웹훅을 재설정했습니다."
            if failed_count > 0:
                message += f" {failed_count}개 계정에서 실패했습니다."
        elif failed_count > 0:
            message = f"{failed_count}개 계정에서 웹훅 재설정에 실패했습니다."
        else:
            message = "모든 웹훅이 정상 상태입니다."

        return jsonify(
            {
                "success": True,
                "message": message,
                "renewed_count": renewed_count,
                "failed_count": failed_count,
                "account_results": account_results,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"웹훅 자동 재설정 중 오류: {str(e)}"}
        )


def check_and_repair_webhooks_for_user(user_id: str) -> dict:
    """사용자의 웹훅 상태를 확인하고 만료된 웹훅을 자동 복구 (누락된 이메일 처리 포함)"""
    try:
        from datetime import datetime, timedelta

        print(f"🔍 사용자 웹훅 상태 확인: {user_id}")

        # 사용자의 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(user_id=user_id, is_active=True).all()

        if not accounts:
            print(f"⚠️ 사용자 {user_id}의 활성 계정이 없음")
            return {"success": False, "message": "활성 계정이 없습니다."}

        repaired_count = 0
        failed_count = 0
        healthy_count = 0
        missed_emails_processed = 0
        missed_emails_classified = 0

        for account in accounts:
            try:
                # 웹훅 상태 확인
                webhook_status = WebhookStatus.query.filter_by(
                    user_id=user_id, account_id=account.id, is_active=True
                ).first()

                # 웹훅이 없거나 만료된 경우 복구
                if not webhook_status or webhook_status.is_expired:
                    print(f"🔄 웹훅 복구 시도 - 계정: {account.account_email}")

                    success = setup_webhook_for_account(user_id, account.id)

                    if success:
                        repaired_count += 1
                        print(f"✅ 웹훅 복구 성공 - 계정: {account.account_email}")

                        # 누락된 이메일 처리 결과 확인 (setup_webhook_for_account에서 이미 처리됨)
                        # 여기서는 로그만 확인
                        print(
                            f"📧 누락된 이메일 처리 완료 - 계정: {account.account_email}"
                        )
                    else:
                        failed_count += 1
                        print(f"❌ 웹훅 복구 실패 - 계정: {account.account_email}")
                else:
                    # 만료 예정인지 확인 (48시간 이내)
                    expiry_threshold = datetime.utcnow() + timedelta(hours=48)
                    if webhook_status.expires_at <= expiry_threshold:
                        print(f"🔄 웹훅 예방적 갱신 - 계정: {account.account_email}")

                        success = setup_webhook_for_account(user_id, account.id)

                        if success:
                            repaired_count += 1
                            print(
                                f"✅ 웹훅 예방적 갱신 성공 - 계정: {account.account_email}"
                            )
                        else:
                            failed_count += 1
                            print(
                                f"❌ 웹훅 예방적 갱신 실패 - 계정: {account.account_email}"
                            )
                    else:
                        healthy_count += 1
                        print(f"✅ 웹훅 정상 상태 - 계정: {account.account_email}")

            except Exception as e:
                failed_count += 1
                print(
                    f"❌ 웹훅 복구 중 오류 - 계정: {account.account_email}, 오류: {str(e)}"
                )

        result = {
            "success": True,
            "repaired_count": repaired_count,
            "failed_count": failed_count,
            "healthy_count": healthy_count,
            "total_accounts": len(accounts),
            "missed_emails_processed": missed_emails_processed,
            "missed_emails_classified": missed_emails_classified,
        }

        print(
            f"🎉 사용자 웹훅 상태 확인 완료 - 복구: {repaired_count}개, 실패: {failed_count}개, 정상: {healthy_count}개"
        )

        return result

    except Exception as e:
        print(f"❌ 사용자 웹훅 상태 확인 중 오류: {str(e)}")
        return {"success": False, "error": str(e)}


def monitor_and_renew_webhooks():
    """모든 사용자의 웹훅 상태를 모니터링하고 만료된 웹훅을 자동 재설정"""
    try:
        from datetime import datetime, timedelta

        print("🔄 웹훅 모니터링 시작...")

        # 만료 예정인 웹훅들 조회 (48시간 이내 만료 - 더 일찍 예방적 갱신)
        expiry_threshold = datetime.utcnow() + timedelta(hours=48)

        expiring_webhooks = WebhookStatus.query.filter(
            WebhookStatus.is_active == True,
            WebhookStatus.expires_at <= expiry_threshold,
        ).all()

        renewed_count = 0
        failed_count = 0

        for webhook in expiring_webhooks:
            try:
                print(
                    f"🔄 웹훅 자동 갱신 - 사용자: {webhook.user_id}, 계정: {webhook.account_id}"
                )

                success = setup_webhook_for_account(webhook.user_id, webhook.account_id)

                if success:
                    renewed_count += 1
                    print(
                        f"✅ 웹훅 갱신 성공 - 사용자: {webhook.user_id}, 계정: {webhook.account_id}"
                    )
                else:
                    failed_count += 1
                    print(
                        f"❌ 웹훅 갱신 실패 - 사용자: {webhook.user_id}, 계정: {webhook.account_id}"
                    )

            except Exception as e:
                failed_count += 1
                print(
                    f"❌ 웹훅 갱신 중 오류 - 사용자: {webhook.user_id}, 계정: {webhook.account_id}, 오류: {str(e)}"
                )

        print(
            f"🎉 웹훅 모니터링 완료 - 갱신: {renewed_count}개, 실패: {failed_count}개"
        )

        return {
            "success": True,
            "renewed_count": renewed_count,
            "failed_count": failed_count,
            "total_checked": len(expiring_webhooks),
        }

    except Exception as e:
        print(f"❌ 웹훅 모니터링 중 오류: {str(e)}")
        return {"success": False, "error": str(e)}


@email_bp.route("/monitor-webhooks", methods=["POST"])
@login_required
def trigger_webhook_monitoring():
    """웹훅 모니터링 수동 트리거 (관리자용)"""
    try:
        result = monitor_and_renew_webhooks()

        if result["success"]:
            message = f"웹훅 모니터링 완료 - 갱신: {result['renewed_count']}개, 실패: {result['failed_count']}개"
            return jsonify({"success": True, "message": message, "result": result})
        else:
            return jsonify(
                {"success": False, "message": f"웹훅 모니터링 실패: {result['error']}"}
            )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"웹훅 모니터링 중 오류: {str(e)}"}
        )


@email_bp.route("/process-missed-emails", methods=["POST"])
@login_required
def process_missed_emails():
    """누락된 이메일 수동 처리"""
    try:
        from datetime import datetime, timedelta

        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        total_processed = 0
        total_classified = 0
        account_results = []

        for account in accounts:
            try:
                # 웹훅 상태 확인
                webhook_status = WebhookStatus.query.filter_by(
                    user_id=current_user.id, account_id=account.id, is_active=True
                ).first()

                # 누락된 기간 계산
                missed_period_start = None
                if webhook_status and webhook_status.is_expired:
                    missed_period_start = webhook_status.expires_at
                else:
                    # 웹훅이 없거나 만료되지 않은 경우, 7일 전부터 처리
                    missed_period_start = datetime.utcnow() - timedelta(days=7)

                print(
                    f"📧 누락된 이메일 처리 - 계정: {account.account_email}, 시작일: {missed_period_start}"
                )

                # 누락된 이메일 처리
                result = process_missed_emails_for_account(
                    current_user.id, account.id, missed_period_start
                )

                if result["success"]:
                    total_processed += result["processed_count"]
                    total_classified += result["classified_count"]

                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "success",
                            "processed": result["processed_count"],
                            "classified": result["classified_count"],
                            "message": result["message"],
                        }
                    )
                else:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "failed",
                            "message": result["message"],
                        }
                    )

            except Exception as e:
                print(f"계정 {account.account_email} 누락된 이메일 처리 실패: {str(e)}")
                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "error",
                        "message": str(e),
                    }
                )

        # 결과 메시지 생성
        if total_processed > 0:
            message = f"누락된 이메일 {total_processed}개 처리 완료 (분류: {total_classified}개)"
        else:
            message = "처리할 누락된 이메일이 없습니다."

        return jsonify(
            {
                "success": True,
                "message": message,
                "total_processed": total_processed,
                "total_classified": total_classified,
                "account_results": account_results,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"누락된 이메일 처리 중 오류: {str(e)}"}
        )


@email_bp.route("/scheduler-status")
@login_required
def scheduler_status():
    """스케줄러 상태 확인"""
    try:
        from flask_apscheduler import APScheduler
        from app import scheduler

        # 스케줄러 작업 상태 확인
        jobs = scheduler.get_jobs()
        webhook_job = None

        for job in jobs:
            if job.id == "webhook_monitor":
                webhook_job = job
                break

        if webhook_job:
            status = {
                "scheduler_running": scheduler.running,
                "webhook_job_active": webhook_job.next_run_time is not None,
                "next_run_time": (
                    webhook_job.next_run_time.isoformat()
                    if webhook_job.next_run_time
                    else None
                ),
                "job_interval": str(webhook_job.trigger),
            }
        else:
            status = {
                "scheduler_running": scheduler.running,
                "webhook_job_active": False,
                "next_run_time": None,
                "job_interval": "Not found",
            }

        return jsonify({"success": True, "status": status})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"스케줄러 상태 확인 실패: {str(e)}"}
        )


@email_bp.route("/trigger-scheduled-monitoring", methods=["POST"])
@login_required
def trigger_scheduled_monitoring():
    """스케줄된 웹훅 모니터링 수동 트리거"""
    try:
        from app import scheduled_webhook_monitoring

        print("🔄 수동 스케줄된 웹훅 모니터링 트리거...")

        # 스케줄된 함수 직접 호출
        scheduled_webhook_monitoring()

        return jsonify(
            {"success": True, "message": "스케줄된 웹훅 모니터링이 실행되었습니다."}
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"스케줄된 웹훅 모니터링 실행 실패: {str(e)}"}
        )


def get_user_emails(user_id, limit=50):
    """사용자의 이메일을 가져오는 헬퍼 함수"""
    return (
        Email.query.filter_by(user_id=user_id)
        .order_by(Email.created_at.desc())
        .limit(limit)
        .all()
    )


@email_bp.route("/debug-info")
@login_required
def debug_info():
    """디버깅 정보 확인"""
    try:
        # 사용자 정보
        user_info = {
            "user_id": current_user.id,
            "email": current_user.email,
            "first_service_access": (
                current_user.first_service_access.isoformat()
                if current_user.first_service_access
                else None
            ),
            "created_at": (
                current_user.created_at.isoformat() if current_user.created_at else None
            ),
        }

        # 계정 정보
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        account_info = []
        for account in accounts:
            # 각 계정의 최근 이메일 확인
            gmail_service = GmailService(current_user.id, account.id)

            try:
                # 최근 이메일 가져오기 시도
                recent_emails = gmail_service.fetch_recent_emails(max_results=5)

                account_data = {
                    "account_id": account.id,
                    "account_email": account.account_email,
                    "account_name": account.account_name,
                    "is_primary": account.is_primary,
                    "is_active": account.is_active,
                    "recent_emails_count": len(recent_emails) if recent_emails else 0,
                    "recent_emails": [],
                }

                # 최근 이메일 상세 정보
                if recent_emails:
                    for email in recent_emails[:3]:  # 최대 3개만
                        account_data["recent_emails"].append(
                            {
                                "gmail_id": email.get("gmail_id"),
                                "subject": email.get("subject"),
                                "sender": email.get("sender"),
                                "date": email.get("date"),
                                "snippet": (
                                    email.get("snippet", "")[:100] + "..."
                                    if email.get("snippet")
                                    else ""
                                ),
                            }
                        )

                account_info.append(account_data)

            except Exception as e:
                account_data = {
                    "account_id": account.id,
                    "account_email": account.account_email,
                    "account_name": account.account_name,
                    "is_primary": account.is_primary,
                    "is_active": account.is_active,
                    "error": str(e),
                }
                account_info.append(account_data)

        return jsonify(
            {
                "success": True,
                "user_info": user_info,
                "accounts": account_info,
                "current_time": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"디버깅 정보 조회 실패: {str(e)}"}
        )


@email_bp.route("/debug-webhook-setup")
@login_required
def debug_webhook_setup():
    """웹훅 설정 디버깅 정보"""
    try:
        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        debug_info = {
            "environment": {
                "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT"),
                "topic_name": os.environ.get("GMAIL_WEBHOOK_TOPIC"),
                "webhook_url": "https://cleanbox-app.onrender.com/webhook/gmail",
            },
            "accounts": [],
        }

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)

                # 웹훅 상태 확인
                webhook_status = gmail_service.get_webhook_status()

                # Gmail API 연결 테스트
                try:
                    # 간단한 Gmail API 호출 테스트
                    profile = (
                        gmail_service.service.users().getProfile(userId="me").execute()
                    )
                    gmail_connection = {
                        "success": True,
                        "email": profile.get("emailAddress"),
                        "messagesTotal": profile.get("messagesTotal"),
                        "threadsTotal": profile.get("threadsTotal"),
                    }
                except Exception as e:
                    gmail_connection = {"success": False, "error": str(e)}

                account_info = {
                    "account_email": account.account_email,
                    "account_name": account.account_name,
                    "is_primary": account.is_primary,
                    "webhook_status": webhook_status,
                    "gmail_connection": gmail_connection,
                }

                debug_info["accounts"].append(account_info)

            except Exception as e:
                debug_info["accounts"].append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "error": str(e),
                    }
                )

        return jsonify({"success": True, "debug_info": debug_info})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"디버깅 정보 수집 실패: {str(e)}"}
        )


@email_bp.route("/check-oauth-scopes")
@login_required
def check_oauth_scopes():
    """OAuth 스코프 확인"""
    try:
        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            return jsonify({"success": False, "message": "연결된 계정이 없습니다."})

        scope_info = {
            "required_scopes": [
                "https://mail.google.com/",
                "https://www.googleapis.com/auth/userinfo.email",
                "https://www.googleapis.com/auth/userinfo.profile",
            ],
            "accounts": [],
        }

        for account in accounts:
            try:
                gmail_service = GmailService(current_user.id, account.id)

                # Gmail API 연결 테스트
                try:
                    profile = (
                        gmail_service.service.users().getProfile(userId="me").execute()
                    )

                    # 토큰 정보 확인 (가능한 경우)
                    try:
                        # 현재 토큰의 스코프 정보 확인
                        token_info = (
                            gmail_service.service.users()
                            .getProfile(userId="me")
                            .execute()
                        )
                        scopes_available = True
                    except:
                        scopes_available = False

                    account_info = {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "gmail_connected": True,
                        "email_address": profile.get("emailAddress"),
                        "messages_total": profile.get("messagesTotal"),
                        "threads_total": profile.get("threadsTotal"),
                        "scopes_available": scopes_available,
                    }

                except Exception as e:
                    account_info = {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "gmail_connected": False,
                        "error": str(e),
                    }

                scope_info["accounts"].append(account_info)

            except Exception as e:
                scope_info["accounts"].append(
                    {
                        "account_email": account.account_email,
                        "account_name": account.account_name,
                        "is_primary": account.is_primary,
                        "error": str(e),
                    }
                )

        return jsonify({"success": True, "scope_info": scope_info})

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"OAuth 스코프 확인 실패: {str(e)}"}
        )
