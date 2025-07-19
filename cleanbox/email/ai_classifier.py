# Standard library imports
import os
from typing import Dict, List, Optional, Tuple

# Third-party imports
import openai

# Local imports
from ..models import Category


class AIClassifier:
    """AI 이메일 분류 및 요약 클래스 (OpenAI 전용)"""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")
        openai.api_key = self.api_key

    def get_user_categories_for_ai(self, user_id: str) -> List[Dict]:
        """AI 분류용 사용자 카테고리 정보 가져오기"""
        try:
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
        """이메일을 심층 분석하여 분류하고 구조화된 요약 제공

        사용 예시:
        # 사용자 카테고리 가져오기
        from cleanbox.models import Category
        user_categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()
        categories = [
            {"id": cat.id, "name": cat.name, "description": cat.description or ""}
            for cat in user_categories
        ]

        # 심층 분류 및 요약
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

        # 구조화된 요약 저장
        email.summary = summary

        # 결과: (1, "핵심: 팀 미팅 일정 조율 요청 | 주요 포인트: 다음 주 화요일 오후 2시 온라인 회의 예정 • 프로젝트 진행상황 공유 • 팀원 전체 참석 요청 | 액션 아이템: 회의 참석 확인 • 발표 자료 준비 | 일정: 다음 주 화요일 오후 2시 | 장소: 온라인 (Zoom)")
        """
        try:
            # 입력 데이터 검증
            if not email_content or not subject:
                return None, "이메일 내용이 부족합니다."

            if not categories:
                return None, "사용 가능한 카테고리가 없습니다."

            # 프롬프트 생성
            prompt = self._build_unified_prompt(
                email_content, subject, sender, categories
            )

            # API 호출
            response = self._call_openai_api(prompt)
            if not response:
                return None, "AI 처리를 사용할 수 없습니다. 수동으로 확인해주세요."

            # 응답 파싱
            category_id, summary = self._parse_unified_response(response, categories)

            # 결과 검증
            if not summary or summary == "응답 파싱 실패":
                return (
                    category_id,
                    "AI 분석 결과를 파싱할 수 없습니다. 수동으로 확인해주세요.",
                )

            return category_id, summary

        except Exception as e:
            print(f"AI 분류 및 요약 실패: {str(e)}")
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

        prompt = f"""CleanBox는 AI 기반 이메일 정리 앱입니다. 다음 이메일을 심층 분석하여 가장 적절한 카테고리로 분류하고 상세히 요약해주세요.

이메일 정보:
- 제목: {subject}
- 발신자: {sender}
- 내용: {content[:2000]}...

사용 가능한 카테고리:
{category_list}

분석 요구사항:

1. 이메일 유형 분석:
   - 회의/미팅, 알림, 요청, 보고서, 마케팅, 개인, 업무, 기타
   - 이메일의 주요 목적과 성격 파악

2. 중요도 및 긴급성 평가:
   - 중요도: 높음/보통/낮음
   - 긴급성: 긴급/보통/낮음
   - 평가 근거 설명

3. 구조화된 요약:
   - 핵심 내용 (1-2문장으로 이메일의 핵심 메시지)
   - 주요 포인트 (3-5개의 중요한 정보)
   - 액션 아이템 (필요한 행동이 있다면)
   - 관련 날짜/시간/장소 (있는 경우)

4. 카테고리 분류:
   - 가장 적합한 카테고리 ID 선택
   - 분류 근거 설명
   - 신뢰도 점수 (0-100)

응답 형식 (JSON):
{{
    "email_type": "회의/미팅",
    "importance": "높음",
    "urgency": "보통",
    "category_id": 1,
    "category_reason": "팀 미팅 관련 이메일이므로 회의 카테고리로 분류",
    "confidence_score": 85,
    "summary": {{
        "core_content": "팀 미팅 일정 조율 요청",
        "key_points": [
            "다음 주 화요일 오후 2시 온라인 회의 예정",
            "프로젝트 진행상황 공유",
            "팀원 전체 참석 요청"
        ],
        "action_items": [
            "회의 참석 확인",
            "발표 자료 준비"
        ],
        "dates_times": "다음 주 화요일 오후 2시",
        "locations": "온라인 (Zoom)"
    }}
}}

분석 가이드라인:
- 이메일의 전체 맥락을 고려하여 분석하세요
- 발신자, 제목, 내용을 종합적으로 판단하세요
- 구체적이고 실용적인 정보를 추출하세요
- 한국어로 작성하세요"""
        return prompt

    def _parse_unified_response(
        self, response: str, categories: List[Dict]
    ) -> Tuple[Optional[int], str]:
        """통합 응답 파싱 (JSON 및 텍스트 형식 지원)"""
        try:
            import json

            # JSON 형식으로 파싱 시도
            try:
                # JSON 블록 찾기
                start_idx = response.find("{")
                end_idx = response.rfind("}") + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = response[start_idx:end_idx]
                    data = json.loads(json_str)

                    # 카테고리 ID 처리
                    category_id = data.get("category_id", 0)
                    if category_id == 0:
                        category_id = None
                    else:
                        # 카테고리 ID 유효성 검사
                        valid_ids = [cat["id"] for cat in categories]
                        if category_id not in valid_ids:
                            category_id = None

                    # 구조화된 요약 생성
                    summary_data = data.get("summary", {})
                    core_content = summary_data.get("core_content", "")
                    key_points = summary_data.get("key_points", [])
                    action_items = summary_data.get("action_items", [])
                    dates_times = summary_data.get("dates_times", "")
                    locations = summary_data.get("locations", "")

                    # 요약 텍스트 구성
                    summary_parts = []
                    if core_content:
                        summary_parts.append(f"핵심: {core_content}")

                    if key_points:
                        points_text = " • ".join(key_points)
                        summary_parts.append(f"주요 포인트: {points_text}")

                    if action_items:
                        actions_text = " • ".join(action_items)
                        summary_parts.append(f"액션 아이템: {actions_text}")

                    if dates_times:
                        summary_parts.append(f"일정: {dates_times}")

                    if locations:
                        summary_parts.append(f"장소: {locations}")

                    summary = " | ".join(summary_parts)

                    return category_id, summary

            except (json.JSONDecodeError, KeyError) as e:
                print(f"JSON 파싱 실패, 텍스트 형식으로 시도: {str(e)}")
                pass

            # 기존 텍스트 형식으로 파싱 (하위 호환성)
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
                        "content": "당신은 CleanBox 이메일 관리 시스템의 AI 어시스턴트입니다. 이메일을 심층 분석하여 구조화된 요약과 정확한 카테고리 분류를 제공합니다. JSON 형식으로 응답하되, 분석이 실패할 경우 텍스트 형식으로도 응답할 수 있습니다.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API 호출 실패: {str(e)}")
            return None
