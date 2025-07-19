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

    def extract_unsubscribe_links(self, content: str) -> List[str]:
        """이메일에서 구독해지 링크 추출"""
        try:
            import re
            from urllib.parse import urljoin, urlparse

            # HTML 링크에서 구독해지 패턴 찾기
            unsubscribe_patterns = [
                r'href=["\']([^"\']*unsubscribe[^"\']*)["\']',
                r'href=["\']([^"\']*opt.?out[^"\']*)["\']',
                r'href=["\']([^"\']*cancel[^"\']*)["\']',
                r'href=["\']([^"\']*remove[^"\']*)["\']',
                r'href=["\']([^"\']*unsub[^"\']*)["\']',
            ]

            links = []
            for pattern in unsubscribe_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                links.extend(matches)

            # 텍스트에서 구독해지 링크 찾기
            text_patterns = [
                r'https?://[^\s<>"]*unsubscribe[^\s<>"]*',
                r'https?://[^\s<>"]*opt.?out[^\s<>"]*',
                r'https?://[^\s<>"]*cancel[^\s<>"]*',
            ]

            for pattern in text_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                links.extend(matches)

            # 중복 제거 및 유효한 URL만 필터링
            valid_links = []
            for link in set(links):
                try:
                    parsed = urlparse(link)
                    if parsed.scheme and parsed.netloc:
                        valid_links.append(link)
                except:
                    continue

            return valid_links[:5]  # 최대 5개 링크 반환

        except Exception as e:
            print(f"구독해지 링크 추출 실패: {str(e)}")
            return []

    def analyze_unsubscribe_page(self, url: str) -> Dict:
        """구독해지 페이지 분석"""
        try:
            import requests
            from bs4 import BeautifulSoup

            # 페이지 가져오기
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return {"success": False, "message": "페이지 접근 실패"}

            soup = BeautifulSoup(response.content, "html.parser")

            # 구독해지 관련 요소 찾기
            unsubscribe_elements = []

            # 버튼과 링크 찾기
            for element in soup.find_all(["button", "a", "input"]):
                text = element.get_text().lower()
                if any(
                    keyword in text
                    for keyword in ["unsubscribe", "opt out", "cancel", "remove"]
                ):
                    unsubscribe_elements.append(
                        {
                            "type": element.name,
                            "text": element.get_text().strip(),
                            "id": element.get("id", ""),
                            "class": element.get("class", []),
                            "href": element.get("href", ""),
                            "action": element.get("action", ""),
                        }
                    )

            # 폼 찾기
            forms = soup.find_all("form")
            form_info = []
            for form in forms:
                action = form.get("action", "")
                method = form.get("method", "get")
                if any(
                    keyword in action.lower()
                    for keyword in ["unsubscribe", "opt", "cancel"]
                ):
                    form_info.append(
                        {
                            "action": action,
                            "method": method,
                            "fields": [
                                field.get("name", "")
                                for field in form.find_all("input")
                            ],
                        }
                    )

            return {
                "success": True,
                "url": url,
                "unsubscribe_elements": unsubscribe_elements,
                "forms": form_info,
                "page_title": soup.title.get_text() if soup.title else "",
            }

        except Exception as e:
            return {"success": False, "message": f"페이지 분석 실패: {str(e)}"}
