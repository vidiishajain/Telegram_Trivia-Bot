"""Integration test: question_generator — hits the real OpenRouter API.

Verifies that:
  - generate_theme() returns a non-empty string.
  - generate_questions() returns exactly the requested count of questions,
    each with valid fields and a correct_choice in {A, B, C, D}.

    uv run pytest -m integration scripts/tests/test_question_generator.py -v

Skips automatically if OPENROUTER_API_KEY isn't set in .env.
"""

import pytest

from agent.config import get_settings


def _llm_ready() -> bool:
    try:
        return bool(get_settings().openrouter_api_key)
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _llm_ready(), reason="OPENROUTER_API_KEY not set in .env"),
]


async def test_generate_theme() -> None:
    from agent.services.question_generator import generate_theme

    theme = await generate_theme()
    assert isinstance(theme, str)
    assert len(theme) > 3, f"Theme too short: {theme!r}"
    print(f"\n  Generated theme: {theme!r}")


async def test_generate_theme_avoids_recent() -> None:
    from agent.services.question_generator import generate_theme

    recent = ["Ancient Rome", "90s Cartoons", "The Solar System"]
    theme = await generate_theme(recent_themes=recent)
    assert theme not in recent, f"Theme {theme!r} was in the avoid list"
    print(f"\n  Generated theme (avoiding {recent}): {theme!r}")


async def test_generate_questions_count() -> None:
    from agent.services.question_generator import generate_questions

    questions = await generate_questions("Ancient Egypt", count=3)
    assert len(questions) == 3, f"Expected 3 questions, got {len(questions)}"


async def test_generate_questions_schema() -> None:
    """Every field of every question must be present and valid."""
    from agent.services.question_generator import generate_questions

    questions = await generate_questions("Space Exploration", count=3)

    for i, q in enumerate(questions):
        assert q.question_text.endswith("?"), f"Q{i + 1} doesn't end with '?': {q.question_text!r}"
        assert q.correct_choice in {"A", "B", "C", "D"}, (
            f"Q{i + 1} bad correct_choice: {q.correct_choice!r}"
        )
        assert len(q.choice_a) > 0, f"Q{i + 1} choice_a is empty"
        assert len(q.choice_b) > 0, f"Q{i + 1} choice_b is empty"
        assert len(q.choice_c) > 0, f"Q{i + 1} choice_c is empty"
        assert len(q.choice_d) > 0, f"Q{i + 1} choice_d is empty"
        assert len(q.explanation) > 10, f"Q{i + 1} explanation too short: {q.explanation!r}"

    # Print for manual review — quality matters here
    print("\n  Generated questions:")
    for i, q in enumerate(questions, 1):
        print(f"  Q{i}: {q.question_text}")
        print(f"       A) {q.choice_a}  B) {q.choice_b}  C) {q.choice_c}  D) {q.choice_d}")
        print(f"       Correct: {q.correct_choice} — {q.explanation}")


async def test_generate_questions_choices_are_distinct() -> None:
    """All four choices should be different from each other."""
    from agent.services.question_generator import generate_questions

    questions = await generate_questions("World Capitals", count=3)

    for i, q in enumerate(questions):
        choices = {q.choice_a, q.choice_b, q.choice_c, q.choice_d}
        all_choices = [q.choice_a, q.choice_b, q.choice_c, q.choice_d]
        assert len(choices) == 4, f"Q{i + 1} has duplicate choices: {all_choices}"
