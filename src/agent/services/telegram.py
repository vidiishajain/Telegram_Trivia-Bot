"""Telegram bot singleton and message-formatting helpers.

This module owns one thing: sending well-formatted messages to Telegram.
Business logic (scoring, voting decisions, DB writes) lives in trivia_bot.py.

Usage:
    from agent.services.telegram import get_bot, send_quiz, send_results
"""

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger

from agent.config import get_settings
from agent.services.trivia_db import Player, Question, RoundScore

_bot: Bot | None = None

# Topic options shown to group players during the voting phase.
# "Surprise me" is last and maps to a random LLM-generated theme.
TOPIC_OPTIONS: list[str] = [
    "History",
    "Science & Nature",
    "Pop Culture",
    "Geography",
    "Sports",
    "Food & Drink",
    "Surprise me 🎲",
]

# fal.ai image generation prompts per topic
TOPIC_IMAGE_PROMPTS: dict[str, str] = {
    "History": (
        "dramatic museum hall with ancient artifacts, statues, scrolls and maps, "
        "warm golden lighting, cinematic wide angle, no text"
    ),
    "Science & Nature": (
        "vibrant science laboratory with glowing neon experiments, colorful chemical reactions, "
        "telescope and microscope, lush nature backdrop, no text"
    ),
    "Pop Culture": (
        "electric neon concert stage with spotlights, crowd silhouettes, music and film icons, "
        "bold vivid colors, retro pop art style, no text"
    ),
    "Geography": (
        "stunning satellite view of Earth showing continents and oceans, colorful topographic map, "
        "world landmarks collage, vivid blue and green palette, no text"
    ),
    "Sports": (
        "epic stadium aerial view at night with floodlights, crowd energy, athlete in action, "
        "dynamic motion blur, bold sports poster style, no text"
    ),
    "Food & Drink": (
        "beautiful overhead flat lay of international cuisine, colorful fresh ingredients, "
        "artisan drinks, warm food photography lighting, no text"
    ),
    "Surprise me 🎲": (
        "colorful confetti explosion with question marks and stars floating, "
        "mystery box glowing, fun playful illustration style, no text"
    ),
}

CELEBRATION_IMAGE_PROMPT = (
    "winner podium with gold trophy, confetti explosion, sparkles and stars, "
    "vibrant celebratory colors, flat vector illustration style, no text"
)

FUN_FACTS_IMAGE_PROMPT = (
    "glowing lightbulb surrounded by floating facts, books, stars and exclamation marks, "
    "vibrant illustration, knowledge and curiosity theme, no text"
)

# In-memory cache: topic/key → fal.ai image URL (valid for the bot session)
_image_cache: dict[str, str] = {}


def get_bot() -> Bot:
    """Return the shared Bot instance, creating it on first call."""
    global _bot
    if _bot is None:
        token = get_settings().telegram_bot_token
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env.")
        _bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _bot


async def get_topic_image(topic_or_key: str, prompt_override: str | None = None) -> str | None:
    """Return a fal.ai generated image URL for the given topic, cached for the session."""
    import asyncio

    import fal_client

    if not get_settings().fal_key:
        return None

    cache_key = topic_or_key
    if cache_key in _image_cache:
        return _image_cache[cache_key]

    prompt = prompt_override or TOPIC_IMAGE_PROMPTS.get(
        topic_or_key, TOPIC_IMAGE_PROMPTS["Surprise me 🎲"]
    )
    try:
        result = await asyncio.to_thread(
            fal_client.run,
            "fal-ai/flux/schnell",
            arguments={
                "prompt": prompt,
                "image_size": "landscape_4_3",
                "num_inference_steps": 4,
            },
        )
        url: str = result["images"][0]["url"]
        _image_cache[cache_key] = url
        logger.debug(f"Generated image for {cache_key!r}")
        return url
    except Exception:
        logger.warning(f"Failed to generate image for {cache_key!r}")
        return None


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------


def topic_vote_keyboard(round_id: int) -> InlineKeyboardMarkup:
    """One button per topic option; callback data encodes round_id and topic."""
    buttons = [
        [InlineKeyboardButton(text=t, callback_data=f"vote:{round_id}:{t}")] for t in TOPIC_OPTIONS
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quiz_keyboard(round_id: int, questions: list[Question]) -> InlineKeyboardMarkup:
    """One row of A/B/C/D buttons per question, all in a single message.

    callback_data format: ans:{round_id}:{question_id}:{position}:{choice}
    Position is included so the answer handler can show a meaningful popup
    without an extra DB round-trip.
    """
    rows: list[list[InlineKeyboardButton]] = []
    for q in questions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Q{q.position} A",
                    callback_data=f"ans:{round_id}:{q.id}:{q.position}:A",
                ),
                InlineKeyboardButton(
                    text=f"Q{q.position} B",
                    callback_data=f"ans:{round_id}:{q.id}:{q.position}:B",
                ),
                InlineKeyboardButton(
                    text=f"Q{q.position} C",
                    callback_data=f"ans:{round_id}:{q.id}:{q.position}:C",
                ),
                InlineKeyboardButton(
                    text=f"Q{q.position} D",
                    callback_data=f"ans:{round_id}:{q.id}:{q.position}:D",
                ),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------------------------------------------------------------------
# Message formatters
# ---------------------------------------------------------------------------


def format_vote_message(closes_in_minutes: int) -> str:
    lines = [
        "🗳 <b>What are we playing today?</b>",
        "",
        "First topic past 50% of the group wins immediately.",
        f"No majority in {closes_in_minutes} min? Top vote takes it.",
        "",
        "Tap your pick 👇",
    ]
    return "\n".join(lines)


def format_quiz_message(theme: str, questions: list[Question], window_minutes: int = 30) -> str:
    lines = [f"🎯 <b>{theme}</b>", ""]
    for q in questions:
        lines.append(f"<b>Q{q.position}.</b> {q.question_text}")
        lines.append(f"  A) {q.choice_a}")
        lines.append(f"  B) {q.choice_b}")
        lines.append(f"  C) {q.choice_c}")
        lines.append(f"  D) {q.choice_d}")
        lines.append("")
    lines.append(
        f"⏱ <b>{window_minutes} minutes</b> to answer — tap the buttons below. "
        "You can change any pick before time's up!"
    )
    return "\n".join(lines)


def format_results_message(
    theme: str,
    scores: list[RoundScore],
    players: dict[int, Player],
    questions: list[Question],
    skipped: bool = False,
    mode: str = "group",
) -> str:
    lines = [f"🏁 <b>Time's up! — {theme}</b>", ""]

    if skipped:
        if mode == "group":
            lines.append(
                "Only one player this round — need at least 2 for ELO to move. Drag someone in! 😄"
            )
        else:
            lines.append(
                "ELO updates when there's someone to compete against."
                " Solo practice doesn't count. 😄"
            )
        lines.append("")
    elif not scores:
        lines.append("Nobody answered. 👀 The questions weren't that hard...")
        lines.append("")
    else:
        for s in sorted(scores, key=lambda x: x.rank or 99):
            p = players.get(s.player_id)
            name = p.display_name if p else f"Player {s.player_id}"
            sign = "+" if s.elo_delta >= 0 else ""
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(s.rank or 0, "  ")
            lines.append(
                f"{medal} <b>{name}</b>  {s.correct_count}/{s.total_questions}  "
                f"{sign}{s.elo_delta} ELO → <b>{s.elo_after}</b>"
            )
        lines.append("")

    lines.append("<b>Answers:</b>")
    for q in questions:
        lines.append(f"Q{q.position} ✅ <b>{q.correct_choice}</b> — {q.explanation or ''}")

    return "\n".join(lines)


def format_solo_feedback(question: Question, choice: str) -> str:
    """Immediate per-question feedback for solo mode."""
    correct = choice.upper() == question.correct_choice
    icon = "✅" if correct else "❌"
    correct_text = getattr(question, f"choice_{question.correct_choice.lower()}")
    if correct:
        return f"{icon} Correct! {question.explanation or ''}"
    return (
        f"{icon} Not quite — the answer was <b>{question.correct_choice}) {correct_text}</b>\n"
        f"{question.explanation or ''}"
    )


def format_leaderboard(players: list[Player], chat_id: int, viewer_id: int | None = None) -> str:
    scope = "Global Solo" if chat_id == 0 else "Season"
    lines = [f"🏆 <b>{scope} Leaderboard</b>", ""]
    for i, p in enumerate(players, 1):
        you = " ← you" if p.telegram_id == viewer_id else ""
        streak = f" 🔥{p.streak_current}" if p.streak_current >= 3 else ""
        lines.append(f"{i}. {p.display_name}  {p.elo} ELO{streak}{you}")
    return "\n".join(lines)


def format_my_stats(player: Player, rank: int, total_players: int) -> str:
    accuracy = (
        f"{player.total_correct / (player.total_rounds * 5) * 100:.0f}%"
        if player.total_rounds > 0
        else "n/a"
    )
    streak_icon = f" 🔥 {player.streak_current}-round streak" if player.streak_current >= 3 else ""
    lines = [
        f"📊 <b>Your stats</b>{streak_icon}",
        f"ELO: <b>{player.elo}</b>  |  Rank: <b>#{rank}/{total_players}</b>",
        f"Rounds played: {player.total_rounds}  |  Accuracy: {accuracy}",
        f"Best streak: {player.streak_best}",
    ]
    return "\n".join(lines)


async def send_message(chat_id: int, text: str, **kwargs) -> int:  # type: ignore[no-untyped-def]
    """Send a plain message; return the message_id."""
    bot = get_bot()
    msg = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    logger.debug(f"Sent message to {chat_id}: {text[:60]!r}")
    return msg.message_id
