# CleanBox - 이메일 관리 및 구독 해지 자동화 서비스

CleanBox는 이메일 관리와 함께 웹 스크래핑을 통한 구독 해지 자동화 기능을 제공하는 Flask 기반 웹 애플리케이션입니다.

## 🚀 주요 기능

### 이메일 관리
- Gmail API를 통한 이메일 수신 및 처리
- AI 기반 이메일 분류 및 카테고리 관리
- 웹훅을 통한 실시간 이메일 알림
- 구독 해지 이메일 자동 감지

### 구독 해지 자동화 (신규 기능)
- **Playwright** 기반 headless 브라우저 자동화
- 지원 서비스:
  - Netflix
  - Spotify  
  - YouTube Premium
  - Amazon Prime
  - Disney+
  - Hulu
- 웹 인터페이스를 통한 간편한 구독 해지
- 비동기 작업 처리로 안정적인 실행

## 🛠️ 기술 스택

- **Backend**: Flask, Python 3.11
- **Database**: PostgreSQL
- **Browser Automation**: Playwright
- **Deployment**: Docker, Render
- **Frontend**: Bootstrap, JavaScript

## 📦 설치 및 실행

### 로컬 개발 환경

1. **저장소 클론**
```bash
git clone https://github.com/your-username/cleanbox-app.git
cd cleanbox-app
```

2. **가상환경 생성 및 활성화**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **의존성 설치**
```bash
pip install -r requirements.txt
```

4. **Playwright 브라우저 설치**
```bash
playwright install --with-deps chromium
```

5. **환경 변수 설정**
```bash
cp env.example .env
# .env 파일을 편집하여 필요한 환경 변수 설정
```

6. **데이터베이스 초기화**
```bash
python app.py
```

### Docker를 통한 실행

1. **Docker 이미지 빌드**
```bash
docker build -t cleanbox-app .
```

2. **컨테이너 실행**
```bash
docker run -p 8000:8000 cleanbox-app
```

## 🌐 사용 방법

### 웹 인터페이스

1. 브라우저에서 `http://localhost:8000` 접속
2. 로그인 후 대시보드에서 이메일 관리 기능 사용
3. 구독 해지 기능은 `/unsubscribe` 페이지에서 사용

### API 사용

#### 구독 해지 요청
```bash
curl -X POST http://localhost:8000/api/unsubscribe \
  -H "Content-Type: application/json" \
  -d '{
    "service": "netflix",
    "email": "user@example.com",
    "password": "password123"
  }'
```

#### 작업 상태 확인
```bash
curl http://localhost:8000/api/unsubscribe/status/task_1
```

#### 지원 서비스 목록 조회
```bash
curl http://localhost:8000/api/unsubscribe/services
```

## 🔧 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `DATABASE_URI` | PostgreSQL 연결 문자열 | - |
| `GMAIL_CLIENT_ID` | Gmail API 클라이언트 ID | - |
| `GMAIL_CLIENT_SECRET` | Gmail API 클라이언트 시크릿 | - |
| `FLASK_SECRET_KEY` | Flask 시크릿 키 | - |

## 🚀 Render 배포

이 프로젝트는 Docker 기반으로 Render에 배포됩니다.

1. Render 대시보드에서 새 Web Service 생성
2. GitHub 저장소 연결
3. 환경 변수 설정
4. 자동 배포 완료

## 🔒 보안 고려사항

- 계정 정보는 메모리에만 임시 저장되며 영구 저장되지 않습니다
- HTTPS를 통한 안전한 통신
- 환경 변수를 통한 민감한 정보 관리
- Docker 컨테이너 격리

## 📝 라이선스

MIT License

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 이슈를 생성해주세요.
