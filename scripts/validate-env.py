#!/usr/bin/env python3
"""
환경변수 검증 스크립트
Docker 환경에서 환경변수가 제대로 로드되는지 확인
"""

import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet


def validate_fernet_key(key):
    """Fernet 키가 유효한지 검증"""
    try:
        if isinstance(key, str):
            key_bytes = key.encode()
        else:
            key_bytes = key

        Fernet(key_bytes)
        return True
    except Exception as e:
        print(f"❌ Invalid Fernet key: {e}")
        return False


def main():
    print("🔍 환경변수 검증 시작...")

    # .env 파일 로드
    load_dotenv()

    # 필수 환경변수 목록
    required_vars = [
        "CLEANBOX_ENCRYPTION_KEY",
        "CLEANBOX_SECRET_KEY",
        "CLEANBOX_DATABASE_URI",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
    ]

    print("\n📋 환경변수 상태:")
    print("-" * 50)

    all_valid = True

    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: 설정됨")

            # Fernet 키 특별 검증
            if var == "CLEANBOX_ENCRYPTION_KEY":
                if validate_fernet_key(value):
                    print(f"   🔐 Fernet 키 유효함")
                else:
                    print(f"   ❌ Fernet 키 유효하지 않음")
                    all_valid = False
        else:
            print(f"❌ {var}: 설정되지 않음")
            all_valid = False

    print("-" * 50)

    if all_valid:
        print("🎉 모든 환경변수가 올바르게 설정되었습니다!")
    else:
        print("⚠️  일부 환경변수가 누락되었거나 잘못 설정되었습니다.")
        print("\n💡 해결 방법:")
        print("1. .env 파일이 존재하는지 확인")
        print("2. docker-compose.yml에서 환경변수가 제대로 전달되는지 확인")
        print("3. CLEANBOX_ENCRYPTION_KEY가 올바른 Fernet 키인지 확인")

    return all_valid


if __name__ == "__main__":
    main()
