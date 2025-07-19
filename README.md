# CleanBox: AI Email Sorting App

> **CleanBox**는 AI를 활용한 스마트 이메일 분류 및 관리 애플리케이션입니다.

## 🚀 주요 기능

### ✨ **AI 기반 이메일 분류**
- Gmail 이메일을 AI가 자동으로 카테고리별로 분류
- 사용자 정의 카테고리와 설명을 활용한 정확한 분류
- 실시간 이메일 요약 및 감정 분석

### 🔐 **Google OAuth 인증**
- 안전한 Google 계정 연동
- 다중 Gmail 계정 지원
- 암호화된 토큰 저장

### 📧 **스마트 이메일 관리**
- 자동 Gmail 아카이브 처리
- 대량 이메일 작업 (읽음 표시, 아카이브, 삭제)
- AI 에이전트 구독해지 기능

### 🎯 **사용자 친화적 인터페이스**
- 직관적인 3섹션 메인 대시보드
- 카테고리별 이메일 보기
- 실시간 통계 및 분석

## 🛠️ 기술 스택

- **Backend**: Flask, SQLAlchemy
- **Frontend**: Bootstrap 5, JavaScript
- **AI**: OpenAI GPT-3.5-turbo
- **Email**: Gmail API
- **Authentication**: Google OAuth 2.0
- **Database**: SQLite (개발) / PostgreSQL (프로덕션)
- **Testing**: pytest, pytest-cov

## 📦 설치 및 실행

### 🐳 Docker Compose로 실행 (권장)

#### 1. 저장소 클론
```bash
git clone https://github.com/your-username/cleanbox-app.git
cd cleanbox-app
```

#### 2. 환경변수 설정
```bash
cp env.example .env
# .env 파일을 편집하여 실제 값으로 수정
```

#### 3. Docker Compose로 실행
```bash
docker-compose up -d
```

#### 4. 브라우저에서 접속
`http://localhost:5001`으로 접속하세요.

### 🔧 로컬 개발 환경

#### 1. 가상환경 생성 및 활성화
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

#### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

#### 3. PostgreSQL 설치 및 설정
```bash
# macOS
brew install postgresql
brew services start postgresql

# Ubuntu
sudo apt-get install postgresql postgresql-contrib
```

#### 4. Ollama 설치
```bash
# macOS
brew install ollama
ollama pull llama2
ollama serve
```

#### 5. 환경 변수 설정
`.env` 파일을 생성하고 다음 내용을 추가:
```env
FLASK_APP=run.py
FLASK_ENV=development
FLASK_PORT=5001
CLEANBOX_DATABASE_URI=postgresql://cleanbox_user:cleanbox_password@localhost:5432/cleanbox
CLEANBOX_SECRET_KEY=your-secret-key-here
CLEANBOX_ENCRYPTION_KEY=your-encryption-key-here

# Google OAuth 설정
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5001/auth/callback

# AI 설정 (Ollama 사용)
CLEANBOX_USE_OLLAMA=true
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

#### 6. 데이터베이스 초기화
```bash
python run.py
```

#### 7. 애플리케이션 실행
```bash
python run.py
```

브라우저에서 `http://localhost:5001`으로 접속하세요.

## 🔧 Google OAuth 설정

### 1. Google Cloud Console 설정
1. [Google Cloud Console](https://console.cloud.google.com/)에 접속
2. 새 프로젝트 생성: `CleanBox`
3. Gmail API 활성화
4. OAuth 동의 화면 설정
5. OAuth 클라이언트 ID 생성

### 2. 테스트 사용자 추가
- 개발 단계에서는 테스트 사용자로 Gmail 계정 추가
- 프로덕션 배포 시 보안 검토 필요

## 🧪 테스트 실행

### 기본 테스트 실행
```bash
# 전체 테스트 실행
pytest

# 특정 테스트 파일 실행
pytest tests/test_auth.py

# 특정 테스트 클래스 실행
pytest tests/test_auth.py::TestAuthRoutes

# 특정 테스트 함수 실행
pytest tests/test_auth.py::TestAuthRoutes::test_login_redirect
```

### 테스트 유형별 실행
```bash
# 단위 테스트만 실행
pytest -m unit

# 통합 테스트만 실행
pytest -m integration

# 엣지 케이스 테스트만 실행
pytest -m edge_cases

# 보안 테스트만 실행
pytest -m security
```

### 🧪 테스트 환경 설정

#### 1. 테스트용 Docker 서비스 실행
```bash
# 테스트용 PostgreSQL과 Ollama 실행
docker-compose -f docker-compose.test.yml up -d

# 테스트 환경변수 설정
export CLEANBOX_DATABASE_URI=postgresql://cleanbox_user:cleanbox_password@localhost:5433/cleanbox_test
export OLLAMA_URL=http://localhost:11435
```

#### 2. 테스트 실행
```bash
# 전체 테스트 실행
pytest

# 커버리지 포함 테스트
pytest --cov=cleanbox --cov-report=html

# HTML 리포트 생성 (htmlcov/index.html에서 확인)
pytest --cov=cleanbox --cov-report=html --cov-report=term-missing

# XML 리포트 생성 (CI/CD용)
pytest --cov=cleanbox --cov-report=xml
```

### 테스트 디버깅
```bash
# 실패한 테스트만 다시 실행
pytest --lf

# 가장 최근에 실패한 테스트부터 실행
pytest --ff

# 상세한 출력과 함께 실행
pytest -v -s

# 특정 테스트에서 중단점 설정
pytest tests/test_auth.py -s --pdb
```

## 📁 프로젝트 구조

```
cleanbox-app/
├── cleanbox/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── category/
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── email/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   ├── gmail_service.py
│   │   ├── ai_classifier.py
│   │   └── advanced_unsubscribe.py
│   └── templates/
│       ├── base.html
│       ├── auth/
│       ├── category/
│       └── email/
├── tests/
│   ├── __init__.py
│   ├── test_auth.py          # 인증 관련 테스트
│   ├── test_email.py         # 이메일 관련 테스트
│   ├── test_integration.py   # 통합 테스트
│   └── test_edge_cases.py    # 엣지 케이스 테스트
├── instance/
├── requirements.txt
├── run.py
├── pytest.ini               # pytest 설정
├── README.md
├── TODO.md
└── MANUAL_JOBS.md
```

## 🎯 주요 기능 상세

### AI 이메일 분류
- OpenAI GPT-3.5-turbo를 활용한 지능형 이메일 분류
- 사용자 정의 카테고리 설명을 기반으로 한 정확한 분류
- 실시간 이메일 요약 및 키워드 추출

### 다중 계정 지원
- 여러 Gmail 계정을 하나의 CleanBox에서 관리
- 계정별 독립적인 이메일 분류 및 관리
- 계정 전환 기능

### 고급 구독해지 기능
- Selenium을 활용한 동적 웹 스크래핑
- 다양한 구독해지 패턴 자동 감지
- 자동 폼 제출 및 버튼 클릭

### 대량 작업
- 체크박스를 통한 이메일 선택
- 전체 선택/해제 기능
- 대량 읽음 표시, 아카이브, 삭제, 구독해지

## 🔒 보안 기능

- OAuth 토큰 암호화 저장
- 사용자별 데이터 분리
- 안전한 API 키 관리
- HTTPS 통신 (프로덕션)

## 🚀 배포

### Heroku 배포
```bash
# Heroku CLI 설치 후
heroku create cleanbox-app
heroku config:set SECRET_KEY=your-secret-key
heroku config:set GOOGLE_CLIENT_ID=your-client-id
heroku config:set GOOGLE_CLIENT_SECRET=your-client-secret
heroku config:set OPENAI_API_KEY=your-openai-key
git push heroku main
```

### Docker 배포
```bash
docker build -t cleanbox .
docker run -p 5000:5000 cleanbox
```

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 📞 지원

- 이슈 리포트: [GitHub Issues](https://github.com/your-username/cleanbox-app/issues)
- 이메일: support@cleanbox.app

## 🙏 감사의 말

- OpenAI GPT-3.5-turbo API
- Google Gmail API
- Flask 커뮤니티
- 모든 기여자들

---

**CleanBox** - AI로 이메일을 스마트하게 관리하세요! 🚀
