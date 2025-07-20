"""
구독 해지 API 엔드포인트
웹 스크래핑을 통한 구독 해지 기능을 제공하는 API입니다.
"""

from flask import Blueprint, request, jsonify
from cleanbox.unsubscribe_service import UnsubscribeService, UnsubscribeStatus
import logging
import asyncio
from threading import Thread
import queue

logger = logging.getLogger(__name__)

# Blueprint 생성
unsubscribe_bp = Blueprint("unsubscribe", __name__)

# 비동기 작업을 위한 큐
task_queue = queue.Queue()
results = {}


@unsubscribe_bp.route("/api/unsubscribe", methods=["POST"])
def unsubscribe_endpoint():
    """
    구독 해지 API 엔드포인트

    Request Body:
    {
        "service": "netflix",
        "email": "user@example.com",
        "password": "password123"
    }

    Returns:
    {
        "status": "success",
        "message": "구독 해지가 시작되었습니다.",
        "task_id": "task_123"
    }
    """
    try:
        data = request.get_json()

        if not data:
            return (
                jsonify({"status": "error", "message": "요청 데이터가 없습니다."}),
                400,
            )

        service = data.get("service")
        email = data.get("email")
        password = data.get("password")

        if not service or not email:
            return (
                jsonify(
                    {"status": "error", "message": "service와 email은 필수입니다."}
                ),
                400,
            )

        # 지원하는 서비스 목록
        supported_services = [
            "netflix",
            "spotify",
            "youtube",
            "amazon",
            "disney",
            "hulu",
        ]

        if service.lower() not in supported_services:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": f'지원하지 않는 서비스입니다. 지원 서비스: {", ".join(supported_services)}',
                    }
                ),
                400,
            )

        # 비동기 작업 시작
        task_id = f"task_{len(results) + 1}"

        # 백그라운드에서 구독 해지 실행
        thread = Thread(
            target=run_unsubscribe_task, args=(task_id, service, email, password)
        )
        thread.daemon = True
        thread.start()

        return (
            jsonify(
                {
                    "status": "success",
                    "message": "구독 해지가 시작되었습니다.",
                    "task_id": task_id,
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"구독 해지 API 오류: {str(e)}")
        return (
            jsonify(
                {"status": "error", "message": f"서버 오류가 발생했습니다: {str(e)}"}
            ),
            500,
        )


@unsubscribe_bp.route("/api/unsubscribe/status/<task_id>", methods=["GET"])
def get_unsubscribe_status(task_id):
    """
    구독 해지 작업 상태 확인

    Args:
        task_id: 작업 ID

    Returns:
    {
        "status": "completed",
        "result": {
            "status": "success",
            "message": "Netflix 구독이 성공적으로 해지되었습니다."
        }
    }
    """
    try:
        if task_id not in results:
            return (
                jsonify({"status": "error", "message": "작업을 찾을 수 없습니다."}),
                404,
            )

        result = results[task_id]

        return (
            jsonify(
                {
                    "status": "completed",
                    "result": {
                        "status": result.status.value,
                        "message": result.message,
                        "error_details": result.error_details,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"상태 확인 API 오류: {str(e)}")
        return (
            jsonify(
                {"status": "error", "message": f"서버 오류가 발생했습니다: {str(e)}"}
            ),
            500,
        )


@unsubscribe_bp.route("/api/unsubscribe/services", methods=["GET"])
def get_supported_services():
    """
    지원하는 서비스 목록 조회

    Returns:
    {
        "services": [
            {
                "name": "netflix",
                "display_name": "Netflix",
                "description": "넷플릭스 스트리밍 서비스"
            },
            ...
        ]
    }
    """
    services = [
        {
            "name": "netflix",
            "display_name": "Netflix",
            "description": "넷플릭스 스트리밍 서비스",
        },
        {
            "name": "spotify",
            "display_name": "Spotify",
            "description": "스포티파이 음악 스트리밍 서비스",
        },
        {
            "name": "youtube",
            "display_name": "YouTube Premium",
            "description": "유튜브 프리미엄 서비스",
        },
        {
            "name": "amazon",
            "display_name": "Amazon Prime",
            "description": "아마존 프라임 서비스",
        },
        {
            "name": "disney",
            "display_name": "Disney+",
            "description": "디즈니 플러스 스트리밍 서비스",
        },
        {"name": "hulu", "display_name": "Hulu", "description": "훌루 스트리밍 서비스"},
    ]

    return jsonify({"services": services}), 200


def run_unsubscribe_task(task_id, service, email, password):
    """백그라운드에서 구독 해지 작업 실행"""
    try:

        async def run_async():
            async with UnsubscribeService() as unsubscribe_service:
                result = await unsubscribe_service.unsubscribe_from_service(
                    service, email, password
                )
                results[task_id] = result

        # 새 이벤트 루프에서 비동기 작업 실행
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_async())
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"구독 해지 작업 오류: {str(e)}")
        from cleanbox.unsubscribe_service import UnsubscribeResult

        results[task_id] = UnsubscribeResult(
            status=UnsubscribeStatus.FAILED,
            message=f"구독 해지 작업 중 오류 발생: {str(e)}",
            error_details=str(e),
        )


@unsubscribe_bp.route("/unsubscribe", methods=["GET"])
def unsubscribe_page():
    """구독 해지 웹 인터페이스"""
    from flask import render_template

    return render_template("unsubscribe.html")


# Blueprint 등록 함수
def init_unsubscribe_routes(app):
    """구독 해지 라우트를 Flask 앱에 등록"""
    app.register_blueprint(unsubscribe_bp)
