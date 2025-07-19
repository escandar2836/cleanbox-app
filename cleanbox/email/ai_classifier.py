import os
import json
import requests
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class AIClassifier:
    """AI 이메일 분류 및 요약 클래스"""

    def __init__(self):
        # Ollama 설정 (기본값: Ollama 사용)
        self.use_ollama = (
            os.environ.get("CLEANBOX_USE_OLLAMA", "true").lower() == "true"
        )
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self.ollama_model = os.environ.get("OLLAMA_MODEL", "llama2:7b-chat-q4_0")

        # Ollama 모델 자동 다운로드
        if self.use_ollama:
            self._ensure_ollama_model()

    def _ensure_ollama_model(self):
        """필요한 Ollama 모델이 있는지 확인하고 없으면 다운로드"""
        try:
            # Ollama 서비스가 준비될 때까지 대기
            max_retries = 30
            retry_count = 0

            while retry_count < max_retries:
                try:
                    response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
                    if response.status_code == 200:
                        break
                except:
                    pass

                print(f"Ollama 서비스 대기 중... ({retry_count + 1}/{max_retries})")
                time.sleep(10)
                retry_count += 1

            if retry_count >= max_retries:
                print("Ollama 서비스에 연결할 수 없습니다.")
                return

            # 모델 목록 확인
            response = requests.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [model.get("name") for model in models]

                if self.ollama_model not in model_names:
                    print(f"모델 다운로드 중: {self.ollama_model}")
                    download_data = {"name": self.ollama_model}
                    download_response = requests.post(
                        f"{self.ollama_url}/api/pull",
                        json=download_data,
                        timeout=300,  # 5분 타임아웃
                    )

                    if download_response.status_code == 200:
                        print(f"✅ 모델 다운로드 완료: {self.ollama_model}")
                    else:
                        print(f"❌ 모델 다운로드 실패: {self.ollama_model}")
                else:
                    print(f"✅ 모델이 이미 존재합니다: {self.ollama_model}")
            else:
                print("Ollama API에 연결할 수 없습니다.")

        except Exception as e:
            print(f"Ollama 모델 확인 중 오류: {str(e)}")

    def classify_email(
        self, email_content: str, subject: str, sender: str, categories: List[Dict]
    ) -> Tuple[Optional[int], str]:
        """이메일을 AI로 분류"""
        try:
            # 카테고리 정보 구성
            category_info = []
            for cat in categories:
                category_info.append(
                    {
                        "id": cat.id,
                        "name": cat.name,
                        "description": cat.description or "",
                    }
                )

            # AI 프롬프트 구성
            prompt = self._build_classification_prompt(
                email_content, subject, sender, category_info
            )

            # Ollama API 호출
            response = self._call_ollama_api(prompt)

            if response:
                # 응답 파싱
                category_id, confidence, reasoning = (
                    self._parse_classification_response(response, category_info)
                )
                return category_id, reasoning

            return None, "AI 분류를 사용할 수 없습니다. 수동으로 분류해주세요."

        except Exception as e:
            return None, f"AI 분류 오류: {str(e)}"

    def summarize_email(self, email_content: str, subject: str) -> str:
        """이메일 요약"""
        try:
            # 요약 프롬프트 구성
            prompt = self._build_summary_prompt(email_content, subject)

            # Ollama API 호출
            response = self._call_ollama_api(prompt)

            if response:
                return response.strip()

            return "AI 요약을 사용할 수 없습니다. 이메일 내용을 직접 확인해주세요."

        except Exception as e:
            return f"요약 오류: {str(e)}"

    def _build_classification_prompt(
        self, content: str, subject: str, sender: str, categories: List[Dict]
    ) -> str:
        """분류 프롬프트 구성"""
        category_list = "\n".join(
            [
                f"- {cat['id']}: {cat['name']} ({cat['description']})"
                for cat in categories
            ]
        )

        prompt = f"""CleanBox는 AI 기반 이메일 정리 앱입니다. 다음 이메일을 가장 적절한 카테고리로 분류해주세요.

이메일 정보:
- 제목: {subject}
- 발신자: {sender}
- 내용: {content[:1000]}...

사용 가능한 카테고리:
{category_list}

분류 규칙:
1. 이메일의 내용, 제목, 발신자를 종합적으로 분석하세요
2. 가장 적합한 카테고리 ID를 선택하세요
3. 분류 이유를 간단히 설명하세요
4. 적합한 카테고리가 없으면 "미분류"로 처리하세요

응답 형식:
카테고리ID: [선택한 카테고리 ID 또는 0(미분류)]
신뢰도: [0-100 사이의 숫자]
이유: [분류 이유]

예시:
카테고리ID: 1
신뢰도: 85
이유: 회사 업무 관련 이메일로 보이며, 업무 카테고리에 적합합니다."""

        return prompt

    def _build_summary_prompt(self, content: str, subject: str) -> str:
        """요약 프롬프트 구성"""
        prompt = f"""CleanBox 이메일 요약 시스템입니다. 다음 이메일을 간결하게 요약해주세요.

제목: {subject}
내용: {content[:1500]}...

요약 요구사항:
1. 핵심 내용을 2-3문장으로 요약
2. 중요한 정보나 액션 아이템이 있다면 포함
3. 한국어로 작성
4. 100자 이내로 작성

요약:"""

        return prompt

    def _call_ollama_api(self, prompt: str) -> Optional[str]:
        """Ollama API 호출"""
        try:
            if not self.use_ollama:
                print("Ollama가 비활성화되어 있습니다.")
                return None

            # Ollama API 요청 데이터
            data = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "top_p": 0.9, "max_tokens": 500},
            }

            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=data,
                timeout=120,  # Ollama는 더 오래 걸릴 수 있음
            )

            if response.status_code == 200:
                result = response.json()
                return result.get("response", "")
            elif response.status_code == 404:
                print(
                    f"Ollama 모델 '{self.ollama_model}'을 찾을 수 없습니다. 모델을 다운로드해주세요."
                )
                return None
            else:
                print(f"Ollama API 오류: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.ConnectionError:
            print(
                "Ollama 서버에 연결할 수 없습니다. Ollama가 실행 중인지 확인해주세요."
            )
            return None
        except Exception as e:
            print(f"Ollama API 호출 실패: {str(e)}")
            return None

    def _parse_classification_response(
        self, response: str, categories: List[Dict]
    ) -> Tuple[Optional[int], int, str]:
        """분류 응답 파싱"""
        try:
            lines = response.strip().split("\n")
            category_id = None
            confidence = 0
            reasoning = ""

            for line in lines:
                if line.startswith("카테고리ID:"):
                    try:
                        category_id = int(line.split(":")[1].strip())
                    except:
                        category_id = 0
                elif line.startswith("신뢰도:"):
                    try:
                        confidence = int(line.split(":")[1].strip())
                    except:
                        confidence = 0
                elif line.startswith("이유:"):
                    reasoning = line.split(":")[1].strip()

            # 유효한 카테고리 ID인지 확인
            if category_id and category_id != 0:
                valid_ids = [cat["id"] for cat in categories]
                if category_id not in valid_ids:
                    category_id = 0

            return category_id, confidence, reasoning

        except Exception as e:
            print(f"분류 응답 파싱 실패: {str(e)}")
            return 0, 0, "응답 파싱 실패"

    def analyze_email_sentiment(self, content: str, subject: str) -> Dict:
        """이메일 감정 분석"""
        try:
            prompt = f"""다음 이메일의 감정을 분석해주세요.

제목: {subject}
내용: {content[:500]}...

감정 분석 결과를 다음 형식으로 응답하세요:
감정: [positive/negative/neutral]
신뢰도: [0-100]
이유: [간단한 설명]"""

            response = self._call_ollama_api(prompt)

            if response:
                return self._parse_sentiment_response(response)

            return {"sentiment": "neutral", "confidence": 0}

        except Exception as e:
            return {"sentiment": "neutral", "confidence": 0, "error": str(e)}

    def _parse_sentiment_response(self, response: str) -> Dict:
        """감정 분석 응답 파싱"""
        try:
            lines = response.strip().split("\n")
            sentiment = "neutral"
            confidence = 0
            reason = ""

            for line in lines:
                if line.startswith("감정:"):
                    sentiment = line.split(":")[1].strip().lower()
                elif line.startswith("신뢰도:"):
                    try:
                        confidence = int(line.split(":")[1].strip())
                    except:
                        confidence = 0
                elif line.startswith("이유:"):
                    reason = line.split(":")[1].strip()

            return {"sentiment": sentiment, "confidence": confidence, "reason": reason}

        except Exception as e:
            return {"sentiment": "neutral", "confidence": 0, "error": str(e)}

    def extract_keywords(self, content: str) -> List[str]:
        """키워드 추출"""
        try:
            prompt = f"""다음 이메일에서 중요한 키워드 5개를 추출해주세요.

내용: {content[:1000]}...

키워드만 쉼표로 구분하여 응답하세요. 예시: 회의, 프로젝트, 마감일, 예산, 팀원"""

            response = self._call_ollama_api(prompt)

            if response:
                keywords = [kw.strip() for kw in response.split(",")]
                return keywords[:5]  # 최대 5개

            return []

        except Exception as e:
            return []

    def is_spam_or_unwanted(self, content: str, subject: str, sender: str) -> Dict:
        """스팸/원하지 않는 이메일 판별"""
        try:
            prompt = f"""다음 이메일이 스팸이거나 원하지 않는 이메일인지 판별해주세요.

제목: {subject}
발신자: {sender}
내용: {content[:500]}...

판별 결과를 다음 형식으로 응답하세요:
스팸여부: [true/false]
신뢰도: [0-100]
이유: [판별 이유]"""

            response = self._call_ollama_api(prompt)

            if response:
                return self._parse_spam_response(response)

            return {"is_spam": False, "confidence": 0}

        except Exception as e:
            return {"is_spam": False, "confidence": 0, "error": str(e)}

    def _parse_spam_response(self, response: str) -> Dict:
        """스팸 판별 응답 파싱"""
        try:
            lines = response.strip().split("\n")
            is_spam = False
            confidence = 0
            reason = ""

            for line in lines:
                if line.startswith("스팸여부:"):
                    is_spam = line.split(":")[1].strip().lower() == "true"
                elif line.startswith("신뢰도:"):
                    try:
                        confidence = int(line.split(":")[1].strip())
                    except:
                        confidence = 0
                elif line.startswith("이유:"):
                    reason = line.split(":")[1].strip()

            return {"is_spam": is_spam, "confidence": confidence, "reason": reason}

        except Exception as e:
            return {"is_spam": False, "confidence": 0, "error": str(e)}
