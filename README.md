# CleanBox - 이메일 관리 및 구독 해지 자동화 서비스

CleanBox는 이메일 관리와 함께 웹 스크래핑을 통한 구독 해지 자동화 기능을 제공하는 Flask 기반 웹 애플리케이션입니다.

## 🚀 주요 기능

### 이메일 관리
- Gmail API를 통한 이메일 수신 및 처리
- AI 기반 이메일 분류 및 카테고리 관리
- 웹훅을 통한 실시간 이메일 알림
- 구독 해지 이메일 자동 감지

### 구독 해지 자동화
- **Selenium** 기반 headless 브라우저 자동화
- 이메일에서 구독해지 링크 자동 추출
- JavaScript 지원으로 동적 콘텐츠 처리
- AI 연동으로 지능형 페이지 분석
- 다단계 구독해지 플로우 지원

## 🛠️ 기술 스택

- **Backend**: Flask, Python 3.11
- **Database**: PostgreSQL
- **Browser Automation**: Selenium
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
# 프로덕션용
pip install -r requirements.txt

# 개발용 (테스트 포함)
pip install -r requirements-dev.txt
```

4. **환경 변수 설정**
```bash
cp env.example .env
# .env 파일을 편집하여 필요한 환경 변수 설정
```

5. **데이터베이스 초기화**
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
3. 구독 해지 기능은 이메일 카테고리에서 자동 처리

### 이메일 기반 구독 해지

1. **이메일 수신**: Gmail API를 통해 이메일 수신
2. **자동 분류**: AI가 이메일을 카테고리별로 분류
3. **구독해지 감지**: 구독해지 링크가 포함된 이메일 자동 감지
4. **자동 처리**: Selenium을 사용한 자동 구독해지 실행

## 🔧 구독 해지 시스템

### Selenium 기반 시스템
- **범용 처리**: 이메일에서 추출한 구독해지 링크 처리
- **JavaScript 지원**: 동적 콘텐츠 및 SPA 처리
- **AI 연동**: OpenAI API를 통한 지능형 페이지 분석
- **다단계 처리**: 복잡한 구독해지 플로우 지원
- **에러 처리**: 실패 시 재시도 및 로깅

### 주요 기능
- **링크 추출**: 이메일 헤더 및 본문에서 구독해지 링크 자동 추출
- **페이지 분석**: AI를 통한 페이지 구조 분석
- **자동 클릭**: 구독해지 버튼/링크 자동 클릭
- **폼 처리**: 이메일 입력 및 폼 제출 자동화
- **결과 확인**: 구독해지 성공/실패 결과 확인

## 📊 모니터링 및 로깅

- 구독해지 시도 및 결과 로깅
- 성공률 및 처리 시간 통계
- 실패 케이스 분석
- 시스템 상태 모니터링

## 🚀 배포

### Render 배포

1. **Render 대시보드에서 새 서비스 생성**
2. **GitHub 저장소 연결**
3. **환경 변수 설정**
4. **Docker 이미지 자동 빌드 및 배포**

### 환경 변수

```bash
# 필수 환경 변수
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
OPENAI_API_KEY=your-openai-api-key
DATABASE_URL=your-postgresql-url

# 선택적 환경 변수
CLEANBOX_SECRET_KEY=your-secret-key
CLEANBOX_ENCRYPTION_KEY=your-encryption-key
```

## 🧪 테스트

```bash
# 전체 테스트 실행
pytest

# 특정 테스트 실행
pytest tests/test_unsubscribe.py

# 커버리지 리포트
pytest --cov=cleanbox --cov-report=html
```

## 📝 라이센스

MIT License

## 🤝 기여

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📞 지원

문제가 발생하거나 질문이 있으시면 이슈를 생성해주세요.
