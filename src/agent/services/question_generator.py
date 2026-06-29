"""LLM-powered trivia question generator.

Two jobs:
  1. generate_theme()     — pick a fresh daily theme, avoiding recent repeats.
  2. generate_questions() — produce N well-formed multiple-choice questions for that theme.

Both use pydantic-ai with a typed output_type, so the LLM is *forced* to return
exactly the right shape. If it doesn't, pydantic-ai retries automatically.

Why typed output matters
────────────────────────
Imagine asking a friend "give me a trivia question" and they say:

  "The capital of France is Paris. A) Rome B) Paris C) Berlin D) Madrid. Answer: B"

Now imagine asking 5 different friends and getting 5 different formats. You'd spend
all your time parsing the text instead of using it. `output_type=` hands the LLM a
blank form to fill in — you always get the same shape back, already validated.
"""

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from agent.config import get_settings
from agent.services.llm import build_model

# ---------------------------------------------------------------------------
# The "form" the LLM fills in for each question
# ---------------------------------------------------------------------------


class QuizQuestion(BaseModel):
    """One multiple-choice trivia question.

    Every field is validated by Pydantic when the LLM response arrives.
    If `correct_choice` isn't A/B/C/D the whole response is rejected and retried.
    """

    question_text: str = Field(description="The question, ending with a question mark.")
    choice_a: str = Field(description="Answer choice A (no label prefix needed).")
    choice_b: str = Field(description="Answer choice B.")
    choice_c: str = Field(description="Answer choice C.")
    choice_d: str = Field(description="Answer choice D.")
    correct_choice: str = Field(description="Which choice is correct: exactly A, B, C, or D.")
    explanation: str = Field(
        description="1–2 sentences explaining why the correct answer is right. Make it interesting."
    )
    difficulty: int = Field(
        default=2,
        description="Difficulty: 1=easy, 2=medium, 3=hard. Ramp across the quiz.",
        ge=1,
        le=3,
    )

    @field_validator("correct_choice")
    @classmethod
    def must_be_abcd(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in {"A", "B", "C", "D"}:
            raise ValueError(f"correct_choice must be A, B, C, or D — got {v!r}")
        return v

    @field_validator("question_text")
    @classmethod
    def must_end_with_question_mark(cls, v: str) -> str:
        v = v.strip()
        if not v.endswith("?"):
            v = v + "?"
        return v


class QuizRound(BaseModel):
    """A full set of questions for one round."""

    questions: list[QuizQuestion] = Field(
        description="Exactly the requested number of trivia questions."
    )


class ThemeChoice(BaseModel):
    """The LLM's chosen theme for today's quiz."""

    theme: str = Field(
        description=(
            "A specific, evocative theme for today's trivia round — e.g. "
            "'90s Cartoon Villains', 'Ancient Greek Mythology', 'Space Exploration 1960–1980'. "
            "2–5 words. Specific beats generic."
        )
    )


# ---------------------------------------------------------------------------
# Agents — one for theme, one for questions
# ---------------------------------------------------------------------------

_theme_agent: Agent[None, ThemeChoice] = Agent(
    build_model("fast"),  # theme is cheap — use the fast model
    output_type=ThemeChoice,
    system_prompt=(
        "You generate creative daily trivia themes. "
        "Themes should be specific and fun — not just 'Science' but '1960s Space Race'. "
        "Vary broadly: pop culture, history, geography, science, sports, food, film, music. "
        "Never repeat a theme that's been used recently."
    ),
)

_question_agent: Agent[None, QuizRound] = Agent(
    build_model("balanced"),  # questions need quality — use the balanced model
    output_type=QuizRound,
    system_prompt=(
        "You are a trivia question writer. For a given theme, write multiple-choice questions "
        "that are: clear and unambiguous, factually correct, appropriately challenging (not too "
        "easy, not impossibly obscure), and have exactly one clearly correct answer. "
        "Wrong choices (distractors) should be plausible — not obviously silly. "
        "Write a 1–2 sentence explanation for each correct answer "
        "that teaches something interesting."
    ),
)


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


async def generate_theme(recent_themes: list[str] | None = None) -> str:
    """Ask the LLM to choose a fresh daily theme.

    `recent_themes` is a list of themes used in the last ~14 days.
    The LLM is asked to avoid them so we don't repeat ourselves.
    """
    avoid_note = ""
    if recent_themes:
        formatted = ", ".join(f"'{t}'" for t in recent_themes)
        avoid_note = f" Avoid these themes that were used recently: {formatted}."

    result = await _theme_agent.run(f"Choose a theme for today's trivia quiz.{avoid_note}")
    return result.output.theme


async def generate_questions(theme: str, count: int | None = None) -> list[QuizQuestion]:
    """Generate `count` multiple-choice trivia questions on the given theme.

    Returns a validated list of QuizQuestion objects ready to save to the DB.
    If `count` is None, reads from settings (default 5).
    """
    if count is None:
        count = get_settings().trivia_questions_per_round

    result = await _question_agent.run(
        f"Write exactly {count} trivia questions on the theme: {theme!r}. "
        f"The questions MUST ramp in difficulty across the set: "
        f"Q1 and Q2 should be easy (difficulty=1), "
        f"Q3 should be medium (difficulty=2), "
        f"Q4 and Q5 should be hard (difficulty=3). "
        f"Set the 'difficulty' field on each question accordingly. "
        f"Wrong answer choices should be plausible — not obviously silly."
    )

    questions = result.output.questions

    # Truncate silently if the model returned extras; log if it returned too few.
    # (Pydantic already validated each question's shape — this is just a count check.)
    if len(questions) < count:
        raise ValueError(
            f"Model returned {len(questions)} questions for theme {theme!r}, expected {count}. "
            "Retry or adjust the prompt."
        )

    return questions[:count]


async def generate_fun_facts(topic: str) -> list[str]:
    """Generate 5 surprising, punchy fun facts about the given topic."""
    from pydantic import BaseModel
    from pydantic_ai import Agent

    from agent.services.llm import build_model

    class FunFacts(BaseModel):
        facts: list[str]

    agent: Agent[None, FunFacts] = Agent(
        build_model("fast"),
        output_type=FunFacts,
        system_prompt=(
            "You are a trivia writer who loves surprising people with facts they've never heard. "
            "Generate exactly 5 short, surprising fun facts about the given topic. "
            "Each fact should be 1-2 sentences, punchy, and end with a twist or surprising number. "
            "Do NOT start with 'Did you know'. "
            "Make them feel like ammunition for a dinner conversation."
        ),
    )
    result = await agent.run(f"Topic: {topic}")
    return result.output.facts
