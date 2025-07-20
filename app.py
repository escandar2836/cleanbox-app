from cleanbox import create_app, socketio, init_db
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

app = create_app()

if __name__ == "__main__":
    # 개발 환경에서 DB 초기화
    init_db(app)

    # 환경변수에서 포트 설정 읽기 (기본값: 5001)
    port = int(os.environ.get("FLASK_PORT", 5001))

    # SocketIO로 서버 실행 (기존 Flask 기능 모두 지원)
    socketio.run(app, debug=True, host="0.0.0.0", port=port)
