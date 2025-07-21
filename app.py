"""CleanBox Flask 애플리케이션 메인 모듈."""

import os
from typing import Optional

from dotenv import load_dotenv

from cleanbox import create_app, init_db

# .env 파일 로드
load_dotenv()


def get_port() -> int:
    """환경변수에서 포트 설정을 읽어옵니다."""
    return int(os.environ.get("FLASK_PORT", 5001))


def main() -> None:
    """메인 애플리케이션 실행 함수."""
    app = create_app()

    # 개발 환경에서 DB 초기화
    init_db(app)

    # 환경변수에서 포트 설정 읽기
    port = get_port()

    # Flask 서버 실행 (프로덕션에서는 debug=False)
    app.run(debug=False, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
