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

        # 디버깅: 카테고리 정보 출력
        print(f"🔍 AI 분류 시작 - 카테고리 수: {len(categories)}")
        for cat in categories:
            print(f"   카테고리: {cat['name']} (ID: {cat['id']})")
            print(f"   설명: {cat['description'] if cat['description'] else '설명 없음'}")
        print(f"   이메일 제목: {subject}")
        print(f"   발신자: {sender}")
        print(f"   내용 길이: {len(email_content)}")

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
            category_id, summary = self._parse_unified_response(
                response, categories, email_content, subject, sender
            )

            # 결과 검증
            if not summary or summary == "응답 파싱 실패":
                return (
                    category_id,
                    "AI 분석 결과를 파싱할 수 없습니다. 수동으로 확인해주세요.",
                )

            return category_id, summary

        except Exception as e:
            print(f"AI 분류 및 요약 실패: {str(e)}")
            return None, "AI 처리를 사용할 수 없습니다. 수동으로 확인해주세요."

    def _build_unified_prompt(
        self, content: str, subject: str, sender: str, categories: List[Dict]
    ) -> str:
        # 사용자 카테고리 리스트 생성 (description 강조)
        category_list = "\n".join(
            [
                f"- {cat['id']}: {cat['name']} - 설명: {cat['description'] if cat['description'] else '설명 없음'}"
                for cat in categories
            ]
        )

        prompt = f"""CleanBox는 AI 기반 이메일 정리 앱입니다. 다음 이메일을 문맥을 고려하여 분석하고 가장 적절한 카테고리로 분류한 후 핵심 내용을 요약해주세요.

이메일 정보:
- 제목: {subject}
- 발신자: {sender}
- 내용: {content[:2000]}...

사용 가능한 카테고리:
{category_list}

분석 요구사항:

1. 문맥 기반 카테고리 분류:
   - 각 카테고리별로 이메일과의 적합도를 0-100점으로 평가
   - 단순한 키워드 매칭이 아닌 이메일의 전체적인 맥락과 목적을 고려
   - 카테고리 이름과 설명의 의미를 정확히 이해하여 분류
   - 카테고리 설명(description)을 우선적으로 참고하여 분류
   - 가장 높은 점수의 카테고리 ID 선택

2. 문맥 기반 요약:
   - 이메일의 핵심 메시지를 문맥을 고려하여 한 문장으로 요약
   - 단순한 정보 나열이 아닌 이메일의 의도와 목적을 파악
   - 불필요한 정보는 제외하고 의미있는 내용만 추출
   - 자연스럽고 이해하기 쉽게 작성

응답 형식 (JSON):
{{
    "category_id": 1,
    "category_reason": "이메일의 문맥과 목적을 고려한 분류 근거",
    "confidence_score": 85,
    "summary": "문맥을 고려한 핵심 요약"
}}

분석 가이드라인:
- 이메일의 전체적인 맥락과 목적을 우선적으로 고려하세요
- 단순한 키워드 매칭이 아닌 의미적 연결을 찾으세요
- 카테고리 이름과 설명의 의미를 정확히 이해하여 분류하세요
- 카테고리 설명(description)이 있는 경우 이를 우선적으로 참고하세요
- 설명이 없는 카테고리는 이름만으로 분류하세요
- 요약은 이메일의 핵심 의도를 담아 자연스럽게 작성하세요
- 한국어로 작성하세요"""
        return prompt

    def _parse_unified_response(
        self,
        response: str,
        categories: List[Dict],
        email_content: str = "",
        subject: str = "",
        sender: str = "",
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
                    confidence_score = data.get("confidence_score", 0)

                    # 카테고리 ID 유효성 검사
                    valid_ids = [cat["id"] for cat in categories]
                    if category_id not in valid_ids:
                        category_id = 0

                    # 카테고리가 1개 이상 존재하고 신뢰도가 20 이상이면 분류
                    if len(categories) > 0 and confidence_score >= 20:
                        if category_id == 0:
                            # AI가 선택하지 못한 경우 첫 번째 카테고리 사용
                            category_id = categories[0]["id"]
                    else:
                        category_id = None

                    # 요약 처리
                    summary = data.get("summary", "")

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
            # API 키 검증
            if not self.api_key:
                print("OpenAI API 키가 설정되지 않았습니다.")
                return None

            # OpenAI 클라이언트 초기화 (안전한 방식)
            try:
                client = openai.OpenAI(api_key=self.api_key)
            except TypeError as e:
                if "proxies" in str(e):
                    # proxies 매개변수 문제인 경우, 환경변수에서 제거
                    import os

                    if "HTTP_PROXY" in os.environ:
                        del os.environ["HTTP_PROXY"]
                    if "HTTPS_PROXY" in os.environ:
                        del os.environ["HTTPS_PROXY"]
                    client = openai.OpenAI(api_key=self.api_key)
                else:
                    raise e

            # API 호출 (최신 버전에 맞게 수정)
            completion = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 CleanBox 이메일 관리 시스템의 AI 어시스턴트입니다. 이메일의 문맥과 전체적인 맥락을 고려하여 정확한 카테고리 분류와 의미있는 요약을 제공합니다. 단순한 키워드 매칭이 아닌 이메일의 의도와 목적을 파악하여 분석합니다. JSON 형식으로 응답하되, 분석이 실패할 경우 텍스트 형식으로도 응답할 수 있습니다.",
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
