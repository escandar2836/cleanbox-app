from cleanbox import create_app, init_db
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
    app.run(debug=True, port=port)
