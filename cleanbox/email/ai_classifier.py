# Standard library imports
import os
from typing import Dict, List, Optional, Tuple

# Third-party imports
import openai

# Local imports
from ..models import Category


class AIClassifier:
    """AI Email Classification and Summarization Class (OpenAI-based)"""

    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4.1-nano")
        openai.api_key = self.api_key

    def get_user_categories_for_ai(self, user_id: str) -> List[Dict]:
        """Get user category info for AI classification"""
        try:
            categories = Category.query.filter_by(user_id=user_id, is_active=True).all()
            return [
                {"id": cat.id, "name": cat.name, "description": cat.description or ""}
                for cat in categories
            ]
        except Exception as e:
            print(f"Failed to query user categories: {str(e)}")
            return []

    def classify_and_summarize_email(
        self, email_content: str, subject: str, sender: str, categories: List[Dict]
    ) -> Tuple[Optional[int], str]:
        """Analyze and classify an email, then provide a structured summary

        # Debug: Print category information
        print(f"🔍 AI Classification Start - Number of Categories: {len(categories)}")
        for cat in categories:
            print(f"    Category: {cat['name']} (ID: {cat['id']})")
            print(f"    Description: {cat['description'] if cat['description'] else 'No description'}")
        print(f"    Email Subject: {subject}")
        print(f"    Sender: {sender}")
        print(f"    Content Length: {len(email_content)}")

        Example usage:
        # Get user categories
        from cleanbox.models import Category
        user_categories = Category.query.filter_by(user_id=current_user.id, is_active=True).all()
        categories = [
            {"id": cat.id, "name": cat.name, "description": cat.description or ""}
            for cat in user_categories
        ]

        # Deep classification and summarization
        classifier = AIClassifier()
        category_id, summary = classifier.classify_and_summarize_email(
            email_content="Request for meeting schedule coordination...",
            subject="Team Meeting Schedule",
            sender="manager@company.com",
            categories=categories
        )

        # Result handling
        if category_id:
            # Classify email by category ID
            email.category_id = category_id
        else:
            # Unclassified handling
            email.category_id = None

        # Save structured summary
        email.summary = summary

        # Result: (1, "Core: Meeting schedule coordination request | Key Points: Expected online meeting on next Tuesday afternoon • Share project progress • Request full attendance | Action Items: Confirm meeting attendance • Prepare presentation materials | Date: Next Tuesday afternoon | Location: Online (Zoom)")
        """
        try:
            # Input data validation
            if not email_content or not subject:
                return None, "Email content is insufficient."

            if not categories:
                return None, "No available categories."

            # Build prompt
            prompt = self._build_unified_prompt(
                email_content, subject, sender, categories
            )

            # API call
            response = self._call_openai_api(prompt)
            if not response:
                return None, "Unable to use AI processing. Please check manually."

            # Parse response
            category_id, summary = self._parse_unified_response(
                response, categories, email_content, subject, sender
            )

            # Result validation
            if not summary or summary == "Response parsing failed":
                return (
                    category_id,
                    "Unable to parse AI analysis result. Please check manually.",
                )

            return category_id, summary

        except Exception as e:
            print(f"AI classification and summarization failed: {str(e)}")
            return None, "Unable to use AI processing. Please check manually."

    def _build_unified_prompt(
        self, content: str, subject: str, sender: str, categories: List[Dict]
    ) -> str:
        # Generate user category list (emphasis on description)
        category_list = "\n".join(
            [
                f"- {cat['id']}: {cat['name']} - Description: {cat['description'] if cat['description'] else 'No description'}"
                for cat in categories
            ]
        )

        prompt = f"""CleanBox is an AI-based email organization app. Please analyze the following email and classify it into the most appropriate category, then provide a summary of the core content, considering the context.

Important: If keywords or conditions specified in the category description are found in the email, prioritize selecting that category.

Email Information:
- Subject: {subject}
- Sender: {sender}
- Content: {content[:2000]}...

Available Categories:
{category_list}

Analysis Requirements:

1. Context-based Category Classification:
   - Rate the suitability of each category on a 0-100 scale
   - Prioritize checking keywords or conditions specified in category descriptions
   - If keywords from category descriptions appear in email subject, content, or sender, prioritize that category
   - Consider the overall context and purpose of the email, not just keyword matching
   - Understand the meaning of category names and descriptions accurately for classification
   - Select the category ID with the highest score

2. Context-based Summarization:
   - Summarize the core message of the email, considering the context
   - Do not simply list information, but understand the intent and purpose of the email
   - Exclude unnecessary information and extract meaningful content
   - Write naturally and clearly

Response Format (JSON):
{{
    "category_id": 1,
    "category_reason": "Reason for category classification considering email context",
    "confidence_score": 85,
    "summary": "Context-based core summary"
}}

Analysis Guidelines:
- Prioritize checking keywords or conditions specified in category descriptions
- If keywords from category descriptions appear in email subject, content, or sender, prioritize that category
- Example: If "open ai" is in description, select category when "OpenAI" keyword appears in email
- Consider the overall context and purpose of the email
- Do not rely solely on keyword matching, but find meaningful connections
- Understand the meaning of category names and descriptions accurately for classification
- For categories with no description, classify by name
- Write the summary naturally, capturing the core intent of the email
- Write in Korean"""
        return prompt

    def _parse_unified_response(
        self,
        response: str,
        categories: List[Dict],
        email_content: str = "",
        subject: str = "",
        sender: str = "",
    ) -> Tuple[Optional[int], str]:
        """Parse unified response (supports JSON and text formats)"""
        try:
            import json

            # Try to parse as JSON
            try:
                # Find JSON block
                start_idx = response.find("{")
                end_idx = response.rfind("}") + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = response[start_idx:end_idx]
                    data = json.loads(json_str)

                    # Process category ID
                    category_id = data.get("category_id", 0)
                    confidence_score = data.get("confidence_score", 0)

                    # Validate category ID
                    valid_ids = [cat["id"] for cat in categories]
                    if category_id not in valid_ids:
                        category_id = 0

                    # If there is more than one category and confidence is 20 or higher, classify
                    if len(categories) > 0 and confidence_score >= 20:
                        if category_id == 0:
                            # Use the first category if AI couldn't select one
                            category_id = categories[0]["id"]
                    else:
                        category_id = None

                    # Process summary
                    summary = data.get("summary", "")

                    # Debug: Analyze AI response
                    category_reason = data.get("category_reason", "")
                    print(f"🤖 AI Response Analysis:")
                    print(f"   Selected Category ID: {category_id}")
                    print(f"   Confidence Score: {confidence_score}")
                    print(f"   Classification Reason: {category_reason}")
                    print(
                        f"   Summary: {summary[:100]}..."
                        if summary
                        else "   Summary: None"
                    )

                    return category_id, summary

            except (json.JSONDecodeError, KeyError) as e:
                print(f"JSON parsing failed, trying text format: {str(e)}")
                pass

            # Parse as text format (backward compatibility)
            lines = response.strip().split("\n")
            category_id = None
            summary = ""

            for line in lines:
                if line.startswith("CategoryID:"):
                    try:
                        category_id = int(line.split(":", 1)[1].strip())
                    except:
                        category_id = 0
                elif line.startswith("Summary:"):
                    summary = line.split(":", 1)[1].strip()

            # Validate category ID
            if category_id and category_id != 0:
                valid_ids = [cat["id"] for cat in categories]
                if category_id not in valid_ids:
                    category_id = 0

            # Return None if unclassified
            if category_id == 0:
                category_id = None

            return category_id, summary
        except Exception as e:
            print(f"Failed to parse unified response: {str(e)}")
            return None, "Response parsing failed"

    def _call_openai_api(self, prompt: str) -> Optional[str]:
        try:
            # API key validation
            if not self.api_key:
                print("OpenAI API key not set.")
                return None

            # Initialize OpenAI client (safely)
            try:
                client = openai.OpenAI(api_key=self.api_key)
            except TypeError as e:
                if "proxies" in str(e):
                    # If it's a proxies issue, remove from environment variables
                    import os

                    if "HTTP_PROXY" in os.environ:
                        del os.environ["HTTP_PROXY"]
                    if "HTTPS_PROXY" in os.environ:
                        del os.environ["HTTPS_PROXY"]
                    client = openai.OpenAI(api_key=self.api_key)
                else:
                    raise e

            # API call (modified for newer versions)
            completion = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AI assistant for CleanBox email management system. Consider the context and overall context of the email to provide accurate category classification and meaningful summaries. Do not rely solely on keyword matching, but understand the intent and purpose of the email for analysis. Respond in JSON format, but also provide a text format in case of analysis failure.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"OpenAI API call failed: {str(e)}")
            return None
