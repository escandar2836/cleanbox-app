import os
import openai
from typing import Dict, List, Optional, Tuple


class AIClassifier:
    """AI 이메일 분류 및 요약 클래스 (OpenAI 전용)"""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")
        openai.api_key = self.api_key

    def get_user_categories_for_ai(self, user_id: str) -> List[Dict]:
        """AI 분류용 사용자 카테고리 정보 가져오기"""
        try:
            from ..models import Category

            categories = Category.query.filter_by(user_id=user_id, is_active=True).all()
            return [
                {"id": cat.id, "name": cat.name, "description": cat.description or ""}
                for cat in categories
            ]
        except Exception as e:
            print(f"사용자 카테고리 조회 실패: {str(e)}")
            return []

    def classify_and_summarize_email(
        self, email_content: str, subject: str, sender: str, categories: List[Dict]
    ) -> Tuple[Optional[int], str]:
        """이메일을 한 번에 분류하고 요약 (통합 처리)

        사용 예시:
        # 사용자 카테고리 가져오기
        from cleanbox.models import Category
        user_categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()
        categories = [
            {"id": cat.id, "name": cat.name, "description": cat.description or ""}
            for cat in user_categories
        ]

        # 통합 분류 및 요약
        classifier = AIClassifier()
        category_id, summary = classifier.classify_and_summarize_email(
            email_content="회의 일정 조율 요청...",
            subject="팀 미팅 일정",
            sender="manager@company.com",
            categories=categories
        )

        # 결과 처리
        if category_id:
            # 카테고리 ID로 이메일 분류
            email.category_id = category_id
        else:
            # 미분류 처리
            email.category_id = None

        # 요약 저장
        email.summary = summary

        # 결과: (1, "팀 미팅 일정 조율 요청. 다음 주 화요일 오후 2시에 온라인 회의 예정.")
        """
        try:
            prompt = self._build_unified_prompt(
                email_content, subject, sender, categories
            )
            response = self._call_openai_api(prompt)
            if response:
                category_id, summary = self._parse_unified_response(
                    response, categories
                )
                return category_id, summary
            return None, "AI 처리를 사용할 수 없습니다. 수동으로 확인해주세요."
        except Exception as e:
            return None, f"AI 처리 오류: {str(e)}"

    def _build_unified_prompt(
        self, content: str, subject: str, sender: str, categories: List[Dict]
    ) -> str:
        # 사용자 카테고리 리스트 생성
        category_list = "\n".join(
            [
                f"- {cat['id']}: {cat['name']} ({cat['description']})"
                for cat in categories
            ]
        )

        prompt = f"""CleanBox는 AI 기반 이메일 정리 앱입니다. 다음 이메일을 가장 적절한 카테고리로 분류하고 요약해주세요.

이메일 정보:
- 제목: {subject}
- 발신자: {sender}
- 내용: {content[:1500]}...

사용 가능한 카테고리:
{category_list}

분류 및 요약 규칙:
1. 이메일의 내용, 제목, 발신자를 종합적으로 분석하세요
2. 가장 적합한 카테고리 ID를 선택하세요
3. 적합한 카테고리가 없으면 "미분류"로 처리하세요
4. 핵심 내용을 2-3문장으로 요약하세요
5. 한국어로 작성하세요

응답 형식:
카테고리ID: [선택한 카테고리 ID 또는 0(미분류)]
요약: [2-3문장 요약]

예시:
카테고리ID: 1
요약: 팀 미팅 일정 조율 요청. 다음 주 화요일 오후 2시에 온라인 회의 예정."""
        return prompt

    def _parse_unified_response(
        self, response: str, categories: List[Dict]
    ) -> Tuple[Optional[int], str]:
        """통합 응답 파싱"""
        try:
            lines = response.strip().split("\n")
            category_id = None
            summary = ""

            for line in lines:
                if line.startswith("카테고리ID:"):
                    try:
                        category_id = int(line.split(":", 1)[1].strip())
                    except:
                        category_id = 0
                elif line.startswith("요약:"):
                    summary = line.split(":", 1)[1].strip()

            # 카테고리 ID 유효성 검사
            if category_id and category_id != 0:
                valid_ids = [cat["id"] for cat in categories]
                if category_id not in valid_ids:
                    category_id = 0

            # 미분류인 경우 None 반환
            if category_id == 0:
                category_id = None

            return category_id, summary
        except Exception as e:
            print(f"통합 응답 파싱 실패: {str(e)}")
            return None, "응답 파싱 실패"

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
