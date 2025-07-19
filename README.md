# CleanBox - AI 기반 이메일 관리 시스템

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 1. 저장소 클론
git clone <repository-url>
cd cleanbox-app

# 2. 환경변수 파일 설정
cp env.example .env
```

**중요**: `.env` 파일에서 다음 값들을 실제 값으로 변경하세요:

```bash
# 보안 키 설정 (실제 값으로 변경하세요)
CLEANBOX_SECRET_KEY=your-secret-key-here
CLEANBOX_ENCRYPTION_KEY=NZnrraDcMdcD7vmY0Gd5YXqkCbm-28MgyZfcaJCAYgc=

# Google OAuth 설정
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

**Fernet 키 생성 방법**:
```bash
python3 -c "from cryptography.fernet import Fernet; print('Generated Fernet Key:', Fernet.generate_key().decode())"
```

### 2. Docker로 실행

```bash
# 3. Docker Compose로 실행
docker-compose up -d

# 4. 로그 확인
docker-compose logs -f cleanbox
```

### 3. 환경변수 검증

```bash
# 환경변수가 올바르게 설정되었는지 확인
python scripts/validate-env.py
```

## 🔧 문제 해결

### Fernet Key 오류 해결

**오류**: `Fernet key must be 32 url-safe base64-encoded bytes`

**해결 방법**:
1. 올바른 Fernet 키 생성:
   ```bash
   python3 -c "from cryptography.fernet import Fernet; print('Generated Fernet Key:', Fernet.generate_key().decode())"
   ```

2. `.env` 파일에서 `CLEANBOX_ENCRYPTION_KEY` 업데이트:
   ```bash
   CLEANBOX_ENCRYPTION_KEY=생성된_키_값
   ```

3. Docker 컨테이너 재시작:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

### 환경변수 로딩 문제 해결

**문제**: Docker 환경에서 환경변수가 제대로 로드되지 않음

**해결 방법**:
1. 환경변수 검증 스크립트 실행:
   ```bash
   python scripts/validate-env.py
   ```

2. Docker Compose 파일에서 환경변수 확인:
   ```yaml
   environment:
     - CLEANBOX_ENCRYPTION_KEY=${CLEANBOX_ENCRYPTION_KEY}
   ```

3. `.env` 파일이 프로젝트 루트에 있는지 확인

## 📋 주요 기능

- 🔐 **보안**: Fernet 암호화로 OAuth 토큰 보안 저장
- 🤖 **AI 분류**: OpenAI를 사용한 이메일 자동 분류
- 📧 **Gmail 연동**: Google OAuth를 통한 안전한 Gmail 접근
- 🗂️ **카테고리 관리**: 사용자 정의 이메일 카테고리
- ⏰ **자동 동기화**: 스케줄러를 통한 정기적인 이메일 동기화

## 🛠️ 개발 환경

### 로컬 개발

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp env.example .env
# .env 파일 편집

# 애플리케이션 실행
python run.py
```

### 테스트 실행

```bash
# 전체 테스트
pytest

# 특정 테스트
pytest tests/test_auth.py
```

## 📁 프로젝트 구조

```
cleanbox-app/
├── cleanbox/           # 메인 애플리케이션
│   ├── auth/          # 인증 관련
│   ├── email/         # 이메일 처리
│   ├── category/      # 카테고리 관리
│   └── main/          # 메인 기능
├── scripts/           # 유틸리티 스크립트
├── tests/            # 테스트 코드
├── docker-compose.yml # Docker 설정
└── requirements.txt   # Python 의존성
```

## 🔒 보안

- **Fernet 암호화**: OAuth 토큰을 안전하게 저장
- **환경변수**: 민감한 정보는 환경변수로 관리
- **OAuth 2.0**: Google API 안전한 접근

## �� 라이선스

MIT License
