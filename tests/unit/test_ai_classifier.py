import pytest
from unittest.mock import patch, MagicMock
from cleanbox.email.ai_classifier import AIClassifier


class TestAIClassifier:
    @patch("cleanbox.email.ai_classifier.Category")
    def test_get_user_categories_for_ai(self, mock_category):
        mock_cat1 = MagicMock()
        mock_cat1.id = 1
        mock_cat1.name = "Work"
        mock_cat1.description = "업무"
        mock_cat2 = MagicMock()
        mock_cat2.id = 2
        mock_cat2.name = "Personal"
        mock_cat2.description = "개인"
        mock_category.query.filter_by.return_value.all.return_value = [
            mock_cat1,
            mock_cat2,
        ]
        ai = AIClassifier()
        cats = ai.get_user_categories_for_ai("user1")
        assert len(cats) == 2
        assert cats[0]["name"] == "Work"

    @patch.object(AIClassifier, "_call_openai_api")
    def test_classify_and_summarize_email_success(self, mock_call):
        mock_call.return_value = (
            '{"category_id": 1, "summary": "요약", "confidence_score": 90}'
        )
        ai = AIClassifier()
        cats = [{"id": 1, "name": "Work", "description": "업무"}]
        cat_id, summary = ai.classify_and_summarize_email(
            "본문", "제목", "a@b.com", cats
        )
        assert cat_id == 1
        assert summary == "요약"

    def test_parse_unified_response_json(self):
        ai = AIClassifier()
        cats = [{"id": 1, "name": "Work", "description": "업무"}]
        response = '{"category_id": 1, "summary": "요약", "confidence_score": 90}'
        cat_id, summary = ai._parse_unified_response(response, cats)
        assert cat_id == 1
        assert summary == "요약"

    def test_parse_unified_response_text(self):
        ai = AIClassifier()
        cats = [{"id": 1, "name": "Work", "description": "업무"}]
        response = "카테고리ID: 1\n요약: 테스트 요약"
        cat_id, summary = ai._parse_unified_response(response, cats)
        assert cat_id == 1
        assert summary == "테스트 요약"
