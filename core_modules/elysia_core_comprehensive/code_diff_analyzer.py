# code_diff_analyzer.py

class CodeDiffAnalyzer:
    def analyze_diff(self, diff_lines):
        insertions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        total = insertions + deletions
        return {
            "insertions": insertions,
            "deletions": deletions,
            "impact_score": round((insertions + deletions) / 10, 2)
        }
