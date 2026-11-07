from lab import agents


def test_every_role_has_digest():
    for role in list(agents.ROLE_PROMPTS) + ["director"]:
        d = agents.literature_digest(role)
        assert d.startswith("## 최근 문헌 학습 요약"), role
        assert len(d) <= agents.DIGEST_LIMIT + 200, role


def test_digest_in_system_prompts():
    assert "최근 문헌 학습 요약" in agents.system_for("linguist")
    assert "최근 문헌 학습 요약" in agents.director_system(None)


def test_missing_file_returns_empty():
    assert agents.literature_digest("nobody") == ""
