import os
import openai
from typing import Dict, List, Optional, Tuple


class AIClassifier:
    """AI 이메일 분류 및 요약 클래스 (OpenAI 전용)"""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")
        openai.api_key = self.api_key

    def classify_email(
        self, email_content: str, subject: str, sender: str, categories: List[Dict]
    ) -> Tuple[Optional[int], str]:
        """이메일을 AI로 분류"""
        try:
            category_info = [
                {
                    "id": cat.id,
                    "name": cat.name,
                    "description": cat.description or "",
                }
                for cat in categories
            ]
            prompt = self._build_classification_prompt(
                email_content, subject, sender, category_info
            )
            response = self._call_openai_api(prompt)
            if response:
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
            prompt = self._build_summary_prompt(email_content, subject)
            response = self._call_openai_api(prompt)
            if response:
                return response.strip()
            return "AI 요약을 사용할 수 없습니다. 이메일 내용을 직접 확인해주세요."
        except Exception as e:
            return f"요약 오류: {str(e)}"

    def _build_classification_prompt(
        self, content: str, subject: str, sender: str, categories: List[Dict]
    ) -> str:
        category_list = "\n".join(
            [
                f"- {cat['id']}: {cat['name']} ({cat['description']})"
                for cat in categories
            ]
        )
        prompt = f"""CleanBox는 AI 기반 이메일 정리 앱입니다. 다음 이메일을 가장 적절한 카테고리로 분류해주세요.\n\n이메일 정보:\n- 제목: {subject}\n- 발신자: {sender}\n- 내용: {content[:1000]}...\n\n사용 가능한 카테고리:\n{category_list}\n\n분류 규칙:\n1. 이메일의 내용, 제목, 발신자를 종합적으로 분석하세요\n2. 가장 적합한 카테고리 ID를 선택하세요\n3. 분류 이유를 간단히 설명하세요\n4. 적합한 카테고리가 없으면 \"미분류\"로 처리하세요\n\n응답 형식:\n카테고리ID: [선택한 카테고리 ID 또는 0(미분류)]\n신뢰도: [0-100 사이의 숫자]\n이유: [분류 이유]\n\n예시:\n카테고리ID: 1\n신뢰도: 85\n이유: 회사 업무 관련 이메일로 보이며, 업무 카테고리에 적합합니다."""
        return prompt

    def _build_summary_prompt(self, content: str, subject: str) -> str:
        prompt = f"""CleanBox 이메일 요약 시스템입니다. 다음 이메일을 간결하게 요약해주세요.\n\n제목: {subject}\n내용: {content[:1500]}...\n\n요약 요구사항:\n1. 핵심 내용을 2-3문장으로 요약\n2. 중요한 정보나 액션 아이템이 있다면 포함\n3. 한국어로 작성\n4. 100자 이내로 작성\n\n요약:"""
        return prompt

    def _call_openai_api(self, prompt: str) -> Optional[str]:
        try:
            client = openai.OpenAI(api_key=self.api_key)
            completion = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 CleanBox 이메일 관리 시스템의 AI 어시스턴트입니다.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.3,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API 호출 실패: {str(e)}")
            return None

    def _parse_classification_response(
        self, response: str, categories: List[Dict]
    ) -> Tuple[Optional[int], int, str]:
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
            if category_id and category_id != 0:
                valid_ids = [cat["id"] for cat in categories]
                if category_id not in valid_ids:
                    category_id = 0
            return category_id, confidence, reasoning
        except Exception as e:
            print(f"분류 응답 파싱 실패: {str(e)}")
            return 0, 0, "응답 파싱 실패"
