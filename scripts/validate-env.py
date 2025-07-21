#!/usr/bin/env python3
"""
Environment variable validation script
Check if environment variables are properly loaded in Docker environment
"""

import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet


def validate_fernet_key(key):
    """Validate if Fernet key is valid"""
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
    print("🔍 Starting environment variable validation...")

    # Load .env file
    load_dotenv()

    # List of required environment variables
    required_vars = [
        "CLEANBOX_ENCRYPTION_KEY",
        "CLEANBOX_SECRET_KEY",
        "CLEANBOX_DATABASE_URI",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
    ]

    print("\n📋 Environment variable status:")
    print("-" * 50)

    all_valid = True

    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: Set")

            # Special check for Fernet key
            if var == "CLEANBOX_ENCRYPTION_KEY":
                if validate_fernet_key(value):
                    print(f"   🔐 Fernet key is valid")
                else:
                    print(f"   ❌ Fernet key is invalid")
                    all_valid = False
        else:
            print(f"❌ {var}: Not set")
            all_valid = False

    print("-" * 50)

    if all_valid:
        print("🎉 All environment variables are set correctly!")
    else:
        print("⚠️  Some environment variables are missing or incorrectly set.")
        print("\n💡 How to fix:")
        print("1. Check if .env file exists")
        print(
            "2. Check if environment variables are properly passed in docker-compose.yml"
        )
        print("3. Check if CLEANBOX_ENCRYPTION_KEY is a valid Fernet key")

    return all_valid


if __name__ == "__main__":
    main()
