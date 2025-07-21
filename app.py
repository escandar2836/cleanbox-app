"""CleanBox Flask 애플리케이션 메인 모듈."""

import os
from typing import Optional

from dotenv import load_dotenv

from cleanbox import create_app, init_db, scheduler

# .env 파일 로드
load_dotenv()


def get_port() -> int:
    """환경변수에서 포트 설정을 읽어옵니다."""
    return int(os.environ.get("FLASK_PORT", 5001))


def scheduled_webhook_monitoring():
    """스케줄된 웹훅 모니터링 함수."""
    try:
        from cleanbox.email.routes import monitor_and_renew_webhooks

        print("🔄 스케줄된 웹훅 모니터링 실행 중...")
        result = monitor_and_renew_webhooks()

        if result["success"]:
            print(
                f"✅ 스케줄된 웹훅 모니터링 완료 - 갱신: {result['renewed_count']}개, 실패: {result['failed_count']}개"
            )
        else:
            print(
                f"❌ 스케줄된 웹훅 모니터링 실패: {result.get('error', '알 수 없는 오류')}"
            )

        return result
    except Exception as e:
        print(f"❌ 스케줄된 웹훅 모니터링 중 오류: {str(e)}")
        return {"success": False, "error": str(e)}


def setup_scheduler_jobs():
    """스케줄러 작업을 설정합니다."""
    try:
        # 웹훅 모니터링 작업 등록 (30분마다 실행)
        scheduler.add_job(
            func=scheduled_webhook_monitoring,
            trigger="interval",
            minutes=30,
            id="webhook_monitor",
            name="Webhook Monitoring Job",
            replace_existing=True,
        )

        print("✅ 스케줄러 작업 등록 완료 - 웹훅 모니터링 (30분마다)")

    except Exception as e:
        print(f"❌ 스케줄러 작업 등록 실패: {str(e)}")


def main() -> None:
    """메인 애플리케이션 실행 함수."""
    app = create_app()

    # 개발 환경에서 DB 초기화
    init_db(app)

    # 스케줄러 작업 설정
    with app.app_context():
        setup_scheduler_jobs()

    # 환경변수에서 포트 설정 읽기
    port = get_port()

    # Flask 서버 실행 (프로덕션에서는 debug=False)
    app.run(debug=False, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
