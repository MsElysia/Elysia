# feedback.py

class FeedbackEvaluator:
    def __init__(self):
        self.records = []

    def score_response(self, prompt: str, response: str, expected_keywords: list) -> dict:
        match_score = sum(1 for word in expected_keywords if word in response) / max(1, len(expected_keywords))
        drift_score = 1.0 - match_score
        result = {
            "prompt": prompt,
            "response": response,
            "match_score": round(match_score, 2),
            "drift_score": round(drift_score, 2)
        }
        self.records.append(result)
        return result
