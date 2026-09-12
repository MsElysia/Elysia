"""context_pipeline.embedding_backend: Ollama embedding HTTP compatibility."""

from unittest.mock import patch

from project_guardian.context_pipeline.embedding_backend import _embed_ollama_multi_input


class _Response:
    def __init__(self, payload, *, fail=False):
        self._payload = payload
        self._fail = fail

    def raise_for_status(self):
        if self._fail:
            raise RuntimeError("request failed")

    def json(self):
        return self._payload


def test_ollama_embedding_uses_modern_batch_endpoint():
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return _Response({"embeddings": [[1, 2], [3, 4]]})

    with patch("requests.post", side_effect=fake_post):
        out = _embed_ollama_multi_input(["alpha", "beta"], "m", timeout=1.5)

    assert out == [[1.0, 2.0], [3.0, 4.0]]
    assert calls[0][0].endswith("/api/embed")
    assert calls[0][1]["input"] == ["alpha", "beta"]


def test_ollama_embedding_falls_back_to_legacy_prompt_endpoint():
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        if url.endswith("/api/embed"):
            return _Response({}, fail=True)
        val = 1.0 if "alpha" in json["prompt"] else 2.0
        return _Response({"embedding": [val, 0.0]})

    with patch("requests.post", side_effect=fake_post):
        out = _embed_ollama_multi_input(["alpha", "beta"], "m", timeout=1.5)

    assert out == [[1.0, 0.0], [2.0, 0.0]]
    assert calls[0][0].endswith("/api/embed")
    assert [c[0].endswith("/api/embeddings") for c in calls[1:]] == [True, True]
