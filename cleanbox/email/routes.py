# Standard library imports
import os
import traceback
import logging
from datetime import datetime, timedelta

# Third-party imports
from flask import (
    Blueprint,
    render_template,
    request,
    jsonify,
    flash,
    redirect,
    url_for,
    session,
)
from flask_login import login_required, current_user
from flask_apscheduler import APScheduler

# Local imports
from ..models import Email, Category, UserAccount, WebhookStatus, db
from .. import cache
from .gmail_service import GmailService
from .ai_classifier import AIClassifier
from ..auth.routes import (
    check_and_refresh_token,
    get_current_account_id,
    grant_service_account_pubsub_permissions,
)

logger = logging.getLogger(__name__)

email_bp = Blueprint("email", __name__)


# Lazy imports to avoid circular import issues
def get_scheduler():
    """Get scheduler instance lazily to avoid circular imports"""
    from app import scheduler

    return scheduler


def get_scheduled_webhook_monitoring():
    """Get scheduled webhook monitoring function lazily to avoid circular imports"""
    from app import scheduled_webhook_monitoring

    return scheduled_webhook_monitoring


@email_bp.route("/")
@login_required
def list_emails():
    """이메일 목록 페이지 (모든 계정 통합)"""
    try:
        # 세션에서 bulk action 메시지 복원
        if "bulk_action_message" in session:
            flash(
                session["bulk_action_message"], session.get("bulk_action_type", "info")
            )
            del session["bulk_action_message"]
            del session["bulk_action_type"]

        # 새 이메일 처리 알림 확인
        new_emails_notification = None
        notification_file = f"notifications/{current_user.id}_new_emails.txt"

        if os.path.exists(notification_file):
            try:
                with open(notification_file, "r") as f:
                    content = f.read().strip()
                    if content:
                        timestamp_str, count_str = content.split(",")
                        notification_time = datetime.fromisoformat(timestamp_str)

                        # 1시간 이내의 알림만 표시
                        if datetime.utcnow() - notification_time < timedelta(hours=1):
                            new_emails_notification = {
                                "count": int(count_str),
                                "timestamp": notification_time,
                            }

                # 알림 파일 삭제 (한 번만 표시)
                os.remove(notification_file)
            except Exception as e:
                print(f"알림 파일 처리 실패: {str(e)}")

        # 모든 활성 계정 가져오기
        accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not accounts:
            flash("연결된 계정이 없습니다.", "error")
            return render_template(
                "email/list.html",
                user=current_user,
                emails=[],
                stats={},
                accounts=[],
                new_emails_notification=new_emails_notification,
            )

        # 토큰 상태 확인 및 갱신 시도
        for account in accounts:
            try:
                token_valid = check_and_refresh_token(current_user.id, account.id)

                if not token_valid:
                    flash(
                        f"계정 {account.account_email}의 인증이 만료되었습니다. 다시 로그인해주세요.",
                        "warning",
                    )
            except Exception as e:
                print(f"토큰 확인 실패: {str(e)}")

        # 모든 계정의 이메일 통합 조회 (생성 시간 기준 내림차순)
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
            account_analyzed = (
                Email.query.filter_by(user_id=current_user.id, account_id=account.id)
                .filter(Email.summary.isnot(None))
                .count()
            )

            account_stats[account.id] = {
                "email": account.account_email,
                "name": account.account_name,
                "count": account_emails,
                "unread": account_unread,
                "archived": account_archived,
                "analyzed": account_analyzed,
            }

        # 통계 정보
        stats = {
            "total": len(emails),
            "unread": sum(1 for e in emails if not e.is_read),
            "archived": sum(1 for e in emails if e.is_archived),
            "analyzed": sum(1 for e in emails if e.summary),
            "account_stats": account_stats,
        }

        return render_template(
            "email/list.html",
            user=current_user,
            emails=emails,
            stats=stats,
            accounts=accounts,
            new_emails_notification=new_emails_notification,
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
        # 세션에서 bulk action 메시지 복원
        if "bulk_action_message" in session:
            flash(
                session["bulk_action_message"], session.get("bulk_action_type", "info")
            )
            del session["bulk_action_message"]
            del session["bulk_action_type"]

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
    """새 이메일 처리"""
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
        new_emails_processed = False  # 신규 이메일 처리 여부

        for account in accounts:
            try:
                print(f"🔍 계정 {account.account_email} 새 이메일 처리 시작")
                gmail_service = GmailService(current_user.id, account.id)

                # 새 이메일 가져오기
                new_emails = gmail_service.get_new_emails()
                print(
                    f"📧 계정 {account.account_email}에서 {len(new_emails)}개의 새 이메일 발견"
                )

                if not new_emails:
                    account_results.append(
                        {
                            "account": account.account_email,
                            "status": "no_new_emails",
                            "processed": 0,
                            "classified": 0,
                        }
                    )
                    continue

                # 새 이메일 처리
                processed_count = 0
                classified_count = 0

                for email_data in new_emails:
                    try:
                        # 이메일을 DB에 저장
                        email_obj = gmail_service.save_email_to_db(email_data)
                        processed_count += 1

                        # AI 분류
                        ai_classifier = AIClassifier()
                        classification_result = ai_classifier.classify_email(
                            email_obj.content, email_obj.subject, email_obj.sender
                        )

                        if classification_result["category_id"]:
                            # 카테고리 업데이트
                            gmail_service.update_email_category(
                                email_obj.gmail_id, classification_result["category_id"]
                            )
                            classified_count += 1

                    except Exception as e:
                        print(f"❌ 이메일 처리 실패: {str(e)}")
                        continue

                total_processed += processed_count
                total_classified += classified_count

                if processed_count > 0:
                    new_emails_processed = True  # 신규 이메일이 처리됨

                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "success",
                        "processed": processed_count,
                        "classified": classified_count,
                    }
                )

                print(
                    f"✅ 계정 {account.account_email} 처리 완료 - 처리: {processed_count}개, 분류: {classified_count}개"
                )

            except Exception as e:
                print(f"❌ 계정 {account.account_email} 처리 실패: {str(e)}")
                account_results.append(
                    {
                        "account": account.account_email,
                        "status": "error",
                        "error": str(e),
                    }
                )

        # 결과 반환
        if total_processed == 0:
            flash("새로운 이메일이 없습니다.", "info")
            return redirect(url_for("email.list_emails"))

        # 캐시 무효화 (새 이메일이 처리되었으므로 최대 email id 재계산 필요)
        cache_key = f"max_email_id_{current_user.id}"
        cache.delete(cache_key)
        print(f"✅ 캐시 무효화: {cache_key}")

        # 성공 메시지 생성
        success_message = f"새 이메일 처리 완료: {total_processed}개 처리, {total_classified}개 AI 분류"

        if account_results and len(account_results) > 0:
            success_message += "\n\n계정별 결과:"
            for result in account_results:
                if result["status"] == "success":
                    success_message += f"\n• {result['account']}: {result['processed']}개 처리, {result['classified']}개 분류"
                elif result["status"] == "no_new_emails":
                    success_message += f"\n• {result['account']}: 새 이메일 없음"
                else:
                    success_message += (
                        f"\n• {result['account']}: 오류 - {result['error']}"
                    )

        flash(success_message, "success")
        return redirect(url_for("email.list_emails"))

    except Exception as e:
        print(f"❌ 새 이메일 처리 중 오류: {str(e)}")
        flash(f"새 이메일 처리 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(url_for("email.list_emails"))


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

        # 직접 데이터베이스 업데이트
        email_obj.category_id = category_id
        email_obj.updated_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"success": True, "message": "이메일이 분류되었습니다."})

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": f"오류: {str(e)}"})


@email_bp.route("/<int:email_id>/analyze")
@login_required
def analyze_email(email_id):
    """이메일 AI 분석 - 분류 및 요약"""
    try:
        email_obj = Email.query.filter_by(id=email_id, user_id=current_user.id).first()
        if not email_obj:
            return jsonify({"success": False, "message": "이메일을 찾을 수 없습니다."})

        ai_classifier = AIClassifier()

        # 사용자 카테고리 가져오기
        categories = ai_classifier.get_user_categories_for_ai(current_user.id)

        if not categories:
            return jsonify(
                {"success": False, "message": "사용 가능한 카테고리가 없습니다."}
            )

        # 디버깅 정보 출력
        print(f"🔍 AI 분석 시작 - 이메일 ID: {email_id}")
        print(f"   제목: {email_obj.subject}")
        print(f"   발신자: {email_obj.sender}")
        print(f"   내용 길이: {len(email_obj.content) if email_obj.content else 0}")
        print(f"   카테고리 수: {len(categories)}")

        # AI 분류 및 요약 수행
        category_id, summary = ai_classifier.classify_and_summarize_email(
            email_obj.content, email_obj.subject, email_obj.sender, categories
        )

        print(f"📊 AI 분석 결과:")
        print(f"   카테고리 ID: {category_id}")
        print(f"   요약: {summary[:100]}..." if summary else "   요약: 없음")

        # 결과 업데이트
        if category_id:
            email_obj.category_id = category_id
        else:
            email_obj.category_id = None

        if (
            summary
            and summary != "AI 처리를 사용할 수 없습니다. 수동으로 확인해주세요."
        ):
            email_obj.summary = summary

        # AI 분석 완료 후 Gmail에서 아카이브 처리
        try:
            gmail_service = GmailService(current_user.id, email_obj.account_id)
            gmail_service.archive_email(email_obj.gmail_id)
            email_obj.is_archived = True
            print(f"✅ 이메일 아카이브 완료: {email_obj.subject}")
        except Exception as e:
            print(f"❌ 이메일 아카이브 실패: {str(e)}")

        db.session.commit()

        # 카테고리 정보 가져오기
        category_name = "미분류"
        if category_id:
            category = Category.query.filter_by(
                id=category_id, user_id=current_user.id
            ).first()
            if category:
                category_name = category.name

        analysis = {
            "category_id": category_id,
            "category_name": category_name,
            "summary": summary,
            "archived": email_obj.is_archived,
            "success": True,
        }

        return jsonify({"success": True, "analysis": analysis})

    except Exception as e:
        return jsonify({"success": False, "message": f"분석 중 오류: {str(e)}"})


@email_bp.route("/statistics")
@login_required
def email_statistics():
    """이메일 통계 (모든 계정 합산)"""
    try:
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

        # 이메일 상세보기 시 자동 읽음 처리
        if not email_obj.is_read:
            email_obj.is_read = True
            email_obj.updated_at = datetime.utcnow()
            db.session.commit()

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
            # 대량 삭제 (개선된 버전)
            print(f"🔍 대량 삭제 시작 - 선택된 이메일 수: {len(email_ids)}")

            # 결과 수집을 위한 변수들
            success_count = 0
            failed_emails = []
            result_message = ""

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ 이메일 {email_id}를 찾을 수 없음")
                        failed_emails.append(
                            {
                                "id": email_id,
                                "subject": "알 수 없음",
                                "error": "이메일을 찾을 수 없습니다",
                                "error_type": "not_found",
                            }
                        )
                        continue

                    # Gmail에서 삭제
                    gmail_service = GmailService(current_user.id, email_obj.account_id)
                    gmail_service.delete_email(email_obj.gmail_id)

                    # DB에서 삭제
                    db.session.delete(email_obj)
                    success_count += 1
                    print(f"✅ 이메일 {email_id} 삭제 성공")

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ 이메일 삭제 실패 (ID: {email_id}): {error_msg}")

                    # 에러 타입 분류
                    error_type = "unknown"
                    if "404" in error_msg and "not found" in error_msg.lower():
                        error_type = "not_found"
                        error_details = "이미 삭제되었거나 메시지를 찾을 수 없습니다"
                    elif "403" in error_msg:
                        error_type = "forbidden"
                        error_details = "삭제 권한이 없습니다"
                    elif "401" in error_msg:
                        error_type = "unauthorized"
                        error_details = "인증에 실패했습니다"
                    elif "500" in error_msg:
                        error_type = "server_error"
                        error_details = "서버 오류가 발생했습니다"
                    elif (
                        "network" in error_msg.lower()
                        or "connection" in error_msg.lower()
                    ):
                        error_type = "network_error"
                        error_details = "네트워크 연결 오류"
                    else:
                        error_details = error_msg

                    failed_emails.append(
                        {
                            "id": email_id,
                            "subject": email_obj.subject if email_obj else "알 수 없음",
                            "error": error_details,
                            "error_type": error_type,
                        }
                    )

            # DB 커밋
            db.session.commit()

            # 에러 타입별로 그룹화
            error_groups = {}
            for email in failed_emails:
                error_type = email.get("error_type", "unknown")
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append(email)

            # 결과 메시지 생성
            total_processed = success_count + len(failed_emails)
            message_parts = []

            # 성공 개수는 항상 표시 (0이어도)
            message_parts.append(f"✅ 성공: {success_count}개")

            # 에러 타입별로 실제 발생한 것만 표시
            for error_type, emails in error_groups.items():
                if emails:  # 실제 발생한 에러만 표시
                    error_name = {
                        "not_found": "이미 삭제됨",
                        "forbidden": "권한 없음",
                        "unauthorized": "인증 실패",
                        "server_error": "서버 오류",
                        "network_error": "네트워크 오류",
                        "unknown": "알 수 없는 오류",
                    }.get(error_type, error_type)

                    message_parts.append(f"❌ {error_name}: {len(emails)}개")

            result_message = f"삭제 완료 ({total_processed}개):\n" + "\n".join(
                message_parts
            )

            print(f"🎉 대량 삭제 완료 - {result_message}")

            # Flash 메시지와 함께 redirect 반환 (세션에 저장하여 새로고침 후에도 유지)
            flash(result_message, "success" if success_count > 0 else "warning")
            # 세션에 flash 메시지 저장
            session["bulk_action_message"] = result_message
            session["bulk_action_type"] = "success" if success_count > 0 else "warning"
            return redirect(request.referrer or url_for("email.list_emails"))

        elif action == "archive":
            # 대량 아카이브 (개선된 버전)
            print(f"🔍 대량 아카이브 시작 - 선택된 이메일 수: {len(email_ids)}")

            # 결과 수집을 위한 변수들
            success_count = 0
            failed_emails = []
            result_message = ""

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ 이메일 {email_id}를 찾을 수 없음")
                        failed_emails.append(
                            {
                                "id": email_id,
                                "subject": "알 수 없음",
                                "error": "이메일을 찾을 수 없습니다",
                                "error_type": "not_found",
                            }
                        )
                        continue

                    gmail_service = GmailService(current_user.id, email_obj.account_id)
                    gmail_service.archive_email(email_obj.gmail_id)
                    success_count += 1
                    print(f"✅ 이메일 {email_id} 아카이브 성공")

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ 이메일 아카이브 실패 (ID: {email_id}): {error_msg}")

                    # 에러 타입 분류
                    error_type = "unknown"
                    if "404" in error_msg and "not found" in error_msg.lower():
                        error_type = "not_found"
                        error_details = "이미 삭제되었거나 메시지를 찾을 수 없습니다"
                    elif "403" in error_msg:
                        error_type = "forbidden"
                        error_details = "아카이브 권한이 없습니다"
                    elif "401" in error_msg:
                        error_type = "unauthorized"
                        error_details = "인증에 실패했습니다"
                    elif "500" in error_msg:
                        error_type = "server_error"
                        error_details = "서버 오류가 발생했습니다"
                    elif (
                        "network" in error_msg.lower()
                        or "connection" in error_msg.lower()
                    ):
                        error_type = "network_error"
                        error_details = "네트워크 연결 오류"
                    else:
                        error_details = error_msg

                    failed_emails.append(
                        {
                            "id": email_id,
                            "subject": email_obj.subject if email_obj else "알 수 없음",
                            "error": error_details,
                            "error_type": error_type,
                        }
                    )

            # 에러 타입별로 그룹화
            error_groups = {}
            for email in failed_emails:
                error_type = email.get("error_type", "unknown")
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append(email)

            # 결과 메시지 생성
            total_processed = success_count + len(failed_emails)
            message_parts = []

            # 성공 개수는 항상 표시 (0이어도)
            message_parts.append(f"✅ 성공: {success_count}개")

            # 에러 타입별로 실제 발생한 것만 표시
            for error_type, emails in error_groups.items():
                if emails:  # 실제 발생한 에러만 표시
                    error_name = {
                        "not_found": "이미 삭제됨",
                        "forbidden": "권한 없음",
                        "unauthorized": "인증 실패",
                        "server_error": "서버 오류",
                        "network_error": "네트워크 오류",
                        "unknown": "알 수 없는 오류",
                    }.get(error_type, error_type)

                    message_parts.append(f"❌ {error_name}: {len(emails)}개")

            result_message = f"아카이브 완료 ({total_processed}개):\n" + "\n".join(
                message_parts
            )

            print(f"🎉 대량 아카이브 완료 - {result_message}")

            # Flash 메시지와 함께 redirect 반환 (세션에 저장하여 새로고침 후에도 유지)
            flash(result_message, "success" if success_count > 0 else "warning")
            # 세션에 flash 메시지 저장
            session["bulk_action_message"] = result_message
            session["bulk_action_type"] = "success" if success_count > 0 else "warning"
            return redirect(request.referrer or url_for("email.list_emails"))

        elif action == "mark_read":
            # 대량 읽음 표시 (개선된 버전)
            print(f"🔍 대량 읽음 표시 시작 - 선택된 이메일 수: {len(email_ids)}")

            # 결과 수집을 위한 변수들
            success_count = 0
            failed_emails = []

            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ 이메일 {email_id}를 찾을 수 없음")
                        failed_emails.append(
                            {
                                "id": email_id,
                                "subject": "알 수 없음",
                                "error": "이메일을 찾을 수 없습니다",
                                "error_type": "not_found",
                            }
                        )
                        continue

                    gmail_service = GmailService(current_user.id, email_obj.account_id)
                    gmail_service.mark_as_read(email_obj.gmail_id)
                    success_count += 1
                    print(f"✅ 이메일 {email_id} 읽음 표시 성공")

                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ 이메일 읽음 표시 실패 (ID: {email_id}): {error_msg}")

                    # 에러 타입 분류
                    error_type = "unknown"
                    if "404" in error_msg and "not found" in error_msg.lower():
                        error_type = "not_found"
                        error_details = "이미 삭제되었거나 메시지를 찾을 수 없습니다"
                    elif "403" in error_msg:
                        error_type = "forbidden"
                        error_details = "읽음 표시 권한이 없습니다"
                    elif "401" in error_msg:
                        error_type = "unauthorized"
                        error_details = "인증에 실패했습니다"
                    elif "500" in error_msg:
                        error_type = "server_error"
                        error_details = "서버 오류가 발생했습니다"
                    elif (
                        "network" in error_msg.lower()
                        or "connection" in error_msg.lower()
                    ):
                        error_type = "network_error"
                        error_details = "네트워크 연결 오류"
                    else:
                        error_details = error_msg

                    failed_emails.append(
                        {
                            "id": email_id,
                            "subject": email_obj.subject if email_obj else "알 수 없음",
                            "error": error_details,
                            "error_type": error_type,
                        }
                    )

            # 에러 타입별로 그룹화
            error_groups = {}
            for email in failed_emails:
                error_type = email.get("error_type", "unknown")
                if error_type not in error_groups:
                    error_groups[error_type] = []
                error_groups[error_type].append(email)

            # 결과 메시지 생성
            total_processed = success_count + len(failed_emails)
            message_parts = []

            # 성공 개수는 항상 표시 (0이어도)
            message_parts.append(f"✅ 성공: {success_count}개")

            # 에러 타입별로 실제 발생한 것만 표시
            for error_type, emails in error_groups.items():
                if emails:  # 실제 발생한 에러만 표시
                    error_name = {
                        "not_found": "이미 삭제됨",
                        "forbidden": "권한 없음",
                        "unauthorized": "인증 실패",
                        "server_error": "서버 오류",
                        "network_error": "네트워크 오류",
                        "unknown": "알 수 없는 오류",
                    }.get(error_type, error_type)

                    message_parts.append(f"❌ {error_name}: {len(emails)}개")

            result_message = f"읽음 표시 완료 ({total_processed}개):\n" + "\n".join(
                message_parts
            )

            print(f"🎉 대량 읽음 표시 완료 - {result_message}")

            # Flash 메시지와 함께 redirect 반환 (세션에 저장하여 새로고침 후에도 유지)
            flash(result_message, "success" if success_count > 0 else "warning")
            # 세션에 flash 메시지 저장
            session["bulk_action_message"] = result_message
            session["bulk_action_type"] = "success" if success_count > 0 else "warning"
            return redirect(request.referrer or url_for("email.list_emails"))

        elif action == "unsubscribe":
            # 대량 구독해지 (발신자별 그룹화 처리)
            print(f"🔍 대량 구독해지 시작 - 선택된 이메일 수: {len(email_ids)}")

            # 선택된 이메일들을 발신자별로 그룹화
            sender_groups = {}
            for email_id in email_ids:
                try:
                    email_obj = Email.query.filter_by(
                        id=int(email_id), user_id=current_user.id
                    ).first()

                    if not email_obj:
                        print(f"❌ 이메일 {email_id}를 찾을 수 없음")
                        continue

                    sender = email_obj.sender
                    if sender not in sender_groups:
                        sender_groups[sender] = []
                    sender_groups[sender].append(email_obj)

                except Exception as e:
                    print(f"❌ 이메일 {email_id} 조회 중 예외 발생: {str(e)}")
                    continue

            print(f"📝 발신자별 그룹화 완료 - {len(sender_groups)}개 발신자")

            # 결과 수집을 위한 변수들
            successful_senders = []  # 성공한 발신자 목록
            failed_senders = []  # 실패한 발신자 목록 (발신자, 실패 이유)
            already_unsubscribed_senders = []  # 이미 구독해지된 발신자 목록

            # 각 발신자 그룹별로 처리
            for sender, emails in sender_groups.items():
                print(f"📝 발신자 '{sender}' 처리 시작 - {len(emails)}개 이메일")

                # 이미 구독해지된 이메일이 있는지 확인
                unsubscribed_count = sum(1 for email in emails if email.is_unsubscribed)
                if unsubscribed_count == len(emails):
                    print(f"⏭️ 발신자 '{sender}'의 모든 이메일이 이미 구독해지됨")
                    already_unsubscribed_senders.append(sender)
                    continue

                # 대표 이메일 선택 (구독해지되지 않은 첫 번째 이메일)
                representative_email = None
                for email in emails:
                    if not email.is_unsubscribed:
                        representative_email = email
                        break

                if not representative_email:
                    print(f"⏭️ 발신자 '{sender}'의 모든 이메일이 이미 구독해지됨")
                    already_unsubscribed_senders.append(sender)
                    continue

                print(
                    f"📝 발신자 '{sender}' 대표 이메일 선택: {representative_email.subject}"
                )

                try:
                    # 구독해지 처리
                    gmail_service = GmailService(
                        current_user.id, representative_email.account_id
                    )
                    print(
                        f"📝 GmailService 초기화 완료 - 계정: {representative_email.account_id}"
                    )

                    result = gmail_service.process_unsubscribe(representative_email)
                    print(f"📝 process_unsubscribe 결과: {result}")

                    if result["success"]:
                        print(f"✅ 발신자 '{sender}' 구독해지 성공")
                        successful_senders.append(
                            {
                                "sender": sender,
                                "email_count": len(emails),
                                "bulk_updated_count": result.get(
                                    "bulk_updated_count", 0
                                ),
                                "representative_subject": representative_email.subject,
                            }
                        )
                    else:
                        # 실패 이유 분석
                        error_type = result.get("error_type", "unknown")
                        error_details = result.get("error_details", "알 수 없는 오류")
                        error_message = result.get(
                            "message", "구독해지 처리에 실패했습니다."
                        )

                        if error_type == "personal_email":
                            error_message = "개인 이메일로 감지됨"
                        elif error_type == "already_unsubscribed":
                            already_unsubscribed_senders.append(sender)
                            continue

                        print(f"❌ 발신자 '{sender}' 구독해지 실패: {error_message}")
                        failed_senders.append(
                            {
                                "sender": sender,
                                "email_count": len(emails),
                                "error": error_message,
                                "error_type": error_type,
                                "representative_subject": representative_email.subject,
                            }
                        )

                except Exception as e:
                    print(f"❌ 발신자 '{sender}' 처리 중 예외 발생: {str(e)}")
                    failed_senders.append(
                        {
                            "sender": sender,
                            "email_count": len(emails),
                            "error": f"처리 오류: {str(e)}",
                            "error_type": "processing_error",
                            "representative_subject": (
                                representative_email.subject
                                if representative_email
                                else "알 수 없음"
                            ),
                        }
                    )

            # 결과 메시지 생성
            message_parts = []
            total_senders = len(sender_groups)

            # 성공한 발신자 목록
            if successful_senders:
                message_parts.append(f"✅ 성공한 발신자 ({len(successful_senders)}개):")
                for sender_info in successful_senders:
                    bulk_info = (
                        f" (일괄 업데이트: {sender_info['bulk_updated_count']}개)"
                        if sender_info["bulk_updated_count"] > 0
                        else ""
                    )
                    message_parts.append(
                        f"  • {sender_info['sender']} - {sender_info['email_count']}개 이메일{bulk_info}"
                    )

            # 실패한 발신자 목록
            if failed_senders:
                message_parts.append(f"❌ 실패한 발신자 ({len(failed_senders)}개):")
                for sender_info in failed_senders:
                    error_name = {
                        "no_unsubscribe_link": "구독해지 링크 없음",
                        "all_links_failed": "모든 링크 실패",
                        "processing_error": "처리 오류",
                        "network_error": "네트워크 오류",
                        "timeout_error": "시간 초과",
                        "personal_email": "개인 이메일",
                        "unknown": "알 수 없는 오류",
                    }.get(sender_info["error_type"], sender_info["error_type"])

                    message_parts.append(
                        f"  • {sender_info['sender']} - {sender_info['email_count']}개 이메일 ({error_name}: {sender_info['error']})"
                    )

            # 이미 구독해지된 발신자 목록
            if already_unsubscribed_senders:
                message_parts.append(
                    f"⏭️ 이미 구독해지된 발신자 ({len(already_unsubscribed_senders)}개):"
                )
                for sender in already_unsubscribed_senders:
                    message_parts.append(f"  • {sender}")

            # 전체 요약
            total_processed = (
                len(successful_senders)
                + len(failed_senders)
                + len(already_unsubscribed_senders)
            )
            result_message = (
                f"처리 완료 ({total_processed}/{total_senders}개 발신자):\n"
                + "\n".join(message_parts)
            )

            print(f"🎉 대량 구독해지 완료 - {result_message}")

            # Flash 메시지와 함께 redirect 반환 (세션에 저장하여 새로고침 후에도 유지)
            flash(
                result_message, "success" if len(successful_senders) > 0 else "warning"
            )
            # 세션에 flash 메시지 저장
            session["bulk_action_message"] = result_message
            session["bulk_action_type"] = (
                "success" if len(successful_senders) > 0 else "warning"
            )
            return redirect(request.referrer or url_for("email.list_emails"))

        else:
            flash("지원하지 않는 작업입니다.", "error")
            return redirect(request.referrer or url_for("email.list_emails"))

    except Exception as e:
        flash(f"대량 작업 중 오류가 발생했습니다: {str(e)}", "error")
        return redirect(request.referrer or url_for("email.list_emails"))


@email_bp.route("/<int:email_id>/unsubscribe")
@login_required
def unsubscribe_email(email_id):
    """개별 이메일 구독해지 (개선된 버전)"""
    print(f"🔍 개별 구독해지 시작 - 이메일 ID: {email_id}")
    try:
        # 이메일 조회
        email = Email.query.filter_by(id=email_id, user_id=current_user.id).first()

        if not email:
            print(f"❌ 이메일 {email_id}를 찾을 수 없음")
            return (
                jsonify({"success": False, "message": "이메일을 찾을 수 없습니다."}),
                404,
            )

        print(
            f"📝 이메일 {email_id} 조회 성공 - 제목: {email.subject}, 발신자: {email.sender}"
        )

        # 이미 구독해지된 이메일인지 확인
        if email.is_unsubscribed:
            print(f"⏭️ 이메일 {email_id}는 이미 구독해지됨")
            return jsonify(
                {
                    "success": True,
                    "message": "이미 구독해지된 이메일입니다.",
                    "steps": ["이미 구독해지됨"],
                }
            )

        print(f"📝 이메일 {email_id} 구독해지 처리 시작")
        # Gmail 서비스 초기화
        gmail_service = GmailService(current_user.id, email.account_id)
        print(f"📝 GmailService 초기화 완료 - 계정: {email.account_id}")

        # 구독해지 처리
        result = gmail_service.process_unsubscribe(email)
        print(f"📝 process_unsubscribe 결과: {result}")

        # 결과 반환
        if result["success"]:
            print(f"✅ 이메일 {email_id} 구독해지 성공")

            # 일괄 업데이트 정보 포함
            response_data = {
                "success": True,
                "message": "구독해지가 성공적으로 처리되었습니다.",
                "steps": result.get("steps", []),
                "email_id": email_id,
            }

            # 일괄 업데이트 정보가 있으면 추가
            if "bulk_updated_count" in result:
                response_data["bulk_updated_count"] = result["bulk_updated_count"]
                response_data["bulk_updated_message"] = result["bulk_updated_message"]
                print(
                    f"📝 일괄 업데이트 정보 추가: {result['bulk_updated_count']}개 이메일"
                )

            return jsonify(response_data)
        else:
            error_message = result.get("message", "구독해지 처리에 실패했습니다.")
            error_type = result.get("error_type", "unknown")
            error_details = result.get("error_details", "")

            print(f"❌ 이메일 {email_id} 구독해지 실패: {error_message}")
            print(f"📝 에러 타입: {error_type}")
            print(f"📝 에러 상세: {error_details}")

            return (
                jsonify(
                    {
                        "success": False,
                        "message": error_message,
                        "error_type": error_type,
                        "error_details": error_details,
                        "steps": result.get("steps", []),
                        "email_id": email_id,
                        "is_personal_email": result.get("is_personal_email", False),
                    }
                ),
                400,
            )

    except Exception as e:
        print(f"❌ 구독해지 처리 중 예외 발생: {str(e)}")
        return (
            jsonify(
                {
                    "success": False,
                    "message": f"구독해지 처리 중 오류가 발생했습니다: {str(e)}",
                    "steps": [f"오류 발생: {str(e)}"],
                }
            ),
            500,
        )


@email_bp.route("/clear-bulk-result", methods=["POST"])
@login_required
def clear_bulk_result():
    """대량 처리 결과 세션 클리어"""
    session.pop("bulk_unsubscribe_result", None)
    return jsonify({"success": True})


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

        # 사용자 카테고리 가져오기 (AI 분류용 딕셔너리 형태로 변환)
        category_objects = gmail_service.get_user_categories()
        categories = [
            {"id": cat.id, "name": cat.name, "description": cat.description or ""}
            for cat in category_objects
        ]

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


def setup_gmail_webhook(
    account_id: int, topic_name: str, label_ids: list = None
) -> dict:
    """Gmail 웹훅을 설정합니다."""
    try:
        account = UserAccount.query.get(account_id)
        if not account:
            return {"success": False, "error": f"계정 {account_id}를 찾을 수 없습니다."}
        gmail_service = GmailService(account.user_id, account_id)
        success = gmail_service.setup_gmail_watch(topic_name)
        if success:
            return {
                "success": True,
                "message": f"계정 {account.account_email}의 웹훅 설정 완료",
            }
        else:
            return {
                "success": False,
                "error": f"계정 {account.account_email}의 웹훅 설정 실패",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def setup_gmail_webhook_with_permissions(
    account_id: int, topic_name: str, label_ids: list = None
) -> dict:
    """Gmail 웹훅을 설정합니다. (권한 확인 포함)"""
    try:
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
        # 스케줄러 작업 상태 확인
        jobs = get_scheduler().get_jobs()
        webhook_job = None

        for job in jobs:
            if job.id == "webhook_monitor":
                webhook_job = job
                break

        if webhook_job:
            status = {
                "scheduler_running": get_scheduler().running,
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
                "scheduler_running": get_scheduler().running,
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
        print("🔄 수동 스케줄된 웹훅 모니터링 트리거...")

        # 스케줄된 함수 직접 호출
        get_scheduled_webhook_monitoring()

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
                "webhook_url": "https://cleanbox-app-1.onrender.com/webhook/gmail",
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


@email_bp.route("/ai-analysis-stats")
@login_required
def ai_analysis_statistics():
    """AI 분석 통계"""
    try:
        # AI 분석 완료된 이메일 수 (summary가 있는 이메일)
        analyzed_count = (
            Email.query.filter_by(user_id=current_user.id)
            .filter(Email.summary.isnot(None))
            .count()
        )

        # 전체 이메일 수
        total_count = Email.query.filter_by(user_id=current_user.id).count()

        # AI 분석 완료율
        analysis_rate = (analyzed_count / total_count * 100) if total_count > 0 else 0

        # 카테고리별 AI 분석 통계
        category_stats = (
            db.session.query(Category.name, db.func.count(Email.id).label("count"))
            .join(Email, Category.id == Email.category_id)
            .filter(
                Email.user_id == current_user.id,
                Email.summary.isnot(None),  # AI 분석 완료된 이메일만
            )
            .group_by(Category.id, Category.name)
            .all()
        )

        # 아카이브된 AI 분석 이메일 수
        archived_analyzed_count = (
            Email.query.filter_by(user_id=current_user.id, is_archived=True)
            .filter(Email.summary.isnot(None))
            .count()
        )

        stats = {
            "analyzed_count": analyzed_count,
            "total_count": total_count,
            "analysis_rate": round(analysis_rate, 2),
            "archived_analyzed_count": archived_analyzed_count,
            "category_stats": [
                {"category_name": stat.name, "count": stat.count}
                for stat in category_stats
            ],
        }

        return jsonify({"success": True, "statistics": stats})

    except Exception as e:
        return jsonify({"success": False, "message": f"통계 조회 중 오류: {str(e)}"})


@email_bp.route("/ai-analyzed-emails")
@login_required
def get_ai_analyzed_emails():
    """AI 분석 완료된 이메일 목록"""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)

        # AI 분석 완료된 이메일 조회 (summary가 있는 이메일)
        emails = (
            Email.query.filter_by(user_id=current_user.id)
            .filter(Email.summary.isnot(None))
            .order_by(Email.updated_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

        # 카테고리 정보 추가
        for email in emails.items:
            if email.category_id:
                email.category_info = Category.query.filter_by(
                    id=email.category_id, user_id=current_user.id
                ).first()

        result = {
            "emails": [
                {
                    "id": email.id,
                    "subject": email.subject,
                    "sender": email.sender,
                    "summary": email.summary,
                    "category_name": (
                        email.category_info.name
                        if hasattr(email, "category_info") and email.category_info
                        else "미분류"
                    ),
                    "is_archived": email.is_archived,
                    "is_read": email.is_read,
                    "updated_at": (
                        email.updated_at.isoformat() if email.updated_at else None
                    ),
                }
                for email in emails.items
            ],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": emails.total,
                "pages": emails.pages,
            },
        }

        return jsonify({"success": True, "data": result})

    except Exception as e:
        return jsonify({"success": False, "message": f"이메일 조회 중 오류: {str(e)}"})


@email_bp.route("/api/check-new-emails", methods=["GET"])
@login_required
def check_new_emails():
    """새 이메일 존재 여부 체크 (email id 기반 비교)"""
    try:
        # 클라이언트에서 마지막으로 본 email id 받기
        last_seen_email_id = request.args.get("last_seen_email_id", type=int)

        # 캐시 키 생성
        cache_key = f"max_email_id_{current_user.id}"

        # 캐시된 최대 email id가 있으면 사용
        cached_max_id = cache.get(cache_key)

        if cached_max_id is not None:
            # 캐시된 최대 email id와 클라이언트의 마지막으로 본 email id 비교
            has_new_emails = (
                last_seen_email_id is None or cached_max_id > last_seen_email_id
            )

            result = {
                "has_new_emails": has_new_emails,
                "max_email_id": cached_max_id,
                "last_seen_email_id": last_seen_email_id,
                "new_count": (
                    cached_max_id - (last_seen_email_id or 0) if has_new_emails else 0
                ),
                "last_check": datetime.utcnow().isoformat(),
                "cached_until": (datetime.utcnow() + timedelta(seconds=10)).isoformat(),
            }

            return jsonify(result)

        # 캐시가 없으면 DB에서 최대 email id 계산
        active_accounts = UserAccount.query.filter_by(
            user_id=current_user.id, is_active=True
        ).all()

        if not active_accounts:
            return jsonify(
                {
                    "has_new_emails": False,
                    "max_email_id": 0,
                    "last_seen_email_id": last_seen_email_id,
                    "new_count": 0,
                    "last_check": datetime.utcnow().isoformat(),
                }
            )

        # 사용자의 모든 계정에서 최대 email id 찾기
        max_email_id = 0
        for account in active_accounts:
            max_id_for_account = (
                db.session.query(db.func.max(Email.id))
                .filter(
                    Email.user_id == current_user.id, Email.account_id == account.id
                )
                .scalar()
            )

            if max_id_for_account and max_id_for_account > max_email_id:
                max_email_id = max_id_for_account

        # 결과 캐시 (10초)
        cache.set(cache_key, max_email_id, timeout=10)

        # 새 이메일 여부 확인
        has_new_emails = last_seen_email_id is None or max_email_id > last_seen_email_id

        result = {
            "has_new_emails": has_new_emails,
            "max_email_id": max_email_id,
            "last_seen_email_id": last_seen_email_id,
            "new_count": (
                max_email_id - (last_seen_email_id or 0) if has_new_emails else 0
            ),
            "last_check": datetime.utcnow().isoformat(),
            "cached_until": (datetime.utcnow() + timedelta(seconds=10)).isoformat(),
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"새 이메일 체크 오류: {e}")
        return (
            jsonify({"has_new_emails": False, "error": "체크 중 오류가 발생했습니다"}),
            500,
        )


@email_bp.route("/api/update-last-seen-email", methods=["POST"])
@login_required
def update_last_seen_email():
    """클라이언트의 마지막으로 본 email id 업데이트"""
    try:
        data = request.get_json()
        last_seen_email_id = data.get("last_seen_email_id", type=int)

        if last_seen_email_id is None:
            return (
                jsonify(
                    {"success": False, "message": "last_seen_email_id가 필요합니다"}
                ),
                400,
            )

        # 캐시 키 생성
        cache_key = f"last_seen_email_id_{current_user.id}"

        # 클라이언트의 마지막으로 본 email id를 캐시에 저장
        cache.set(cache_key, last_seen_email_id, timeout=3600)  # 1시간 캐시

        logger.info(
            f"사용자 {current_user.id}의 마지막으로 본 email id 업데이트: {last_seen_email_id}"
        )

        return jsonify(
            {
                "success": True,
                "last_seen_email_id": last_seen_email_id,
                "updated_at": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"마지막으로 본 email id 업데이트 오류: {e}")
        return (
            jsonify({"success": False, "message": "업데이트 중 오류가 발생했습니다"}),
            500,
        )
