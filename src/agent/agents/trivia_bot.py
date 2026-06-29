"""aiogram router — all Telegram command and callback handlers.

Routing rule:
  - Private chat (message.chat.type == "private") → solo mode (chat_id=0 in DB)
  - Group/supergroup                               → group mode (chat_id=telegram group id)

Handler responsibilities:
  - Parse the incoming event
  - Write to DB via trivia_db
  - Send a reply via telegram service
  - No business logic beyond routing — ELO math lives in scoring.py,
    question generation in question_generator.py.
"""

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from loguru import logger

from agent.config import get_settings
from agent.services import trivia_db
from agent.services.question_generator import generate_fun_facts, generate_questions, generate_theme
from agent.services.telegram import (
    CELEBRATION_IMAGE_PROMPT,
    FUN_FACTS_IMAGE_PROMPT,
    TOPIC_IMAGE_PROMPTS,
    TOPIC_OPTIONS,
    format_leaderboard,
    format_my_stats,
    format_quiz_message,
    format_solo_feedback,
    format_vote_message,
    get_bot,
    get_topic_image,
    quiz_keyboard,
    topic_vote_keyboard,
)

router = Router()

_SOLO_CHAT_ID = 0  # sentinel for global solo pool in the DB
_question_timers: dict[int, asyncio.Task[None]] = {}  # question_id → active countdown task


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_private(message: Message) -> bool:
    return message.chat.type == "private"


def _group_chat_id(message: Message) -> int:
    return message.chat.id


async def _get_or_create_season(chat_id: int) -> trivia_db.Season:
    """Return the active season for a chat, creating one if needed."""
    season = await trivia_db.get_active_season(chat_id=chat_id)
    if season is None:
        from datetime import date

        season = await trivia_db.create_season(
            name="Season 1",
            started_at=date.today(),
            chat_id=chat_id,
        )
    return season


async def _get_or_register_player(
    telegram_id: int,
    display_name: str,
    username: str | None,
    chat_id: int,
) -> trivia_db.Player:
    """Upsert player row for the correct context (solo or group)."""
    season = await _get_or_create_season(chat_id)
    return await trivia_db.upsert_player(
        telegram_id=telegram_id,
        display_name=display_name,
        username=username,
        chat_id=chat_id,
        season_id=season.id,
    )


# ---------------------------------------------------------------------------
# /start — solo onboarding (private DM only)
# ---------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not _is_private(message):
        await message.reply(
            "👋 I'm TriviaBot! Add me to any group and type /trivia to start a game.\n"
            "DM me directly to play solo and compete on the global leaderboard."
        )
        return

    user = message.from_user
    if user is None:
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=_SOLO_CHAT_ID,
    )

    first_name = user.first_name or "friend"
    returning = player.total_rounds > 0
    if returning:
        await message.answer(
            f"Hey {first_name}, welcome back! 👋\n\n"
            f"Your ELO is sitting at <b>{player.elo}</b>. "
            f"{'On a ' + str(player.streak_current) + '-round streak 🔥 ' if player.streak_current >= 2 else ''}"  # noqa: E501
            f"Ready to push it higher?\n\n"
            f"Type /play to pick a topic and get your next quiz."
        )
    else:
        await message.answer(
            f"Hey {first_name}! 🎉 You found the trivia bot.\n\n"
            "Here's the deal: you pick a topic, get 5 questions, "
            "and your score goes up against everyone else playing solo worldwide. "
            "Win more than expected and your ELO climbs. "
            "Lose to someone ranked lower — it stings.\n\n"
            "No pressure. Okay, a little pressure.\n\n"
            "Type /play whenever you're ready. Good luck 🍀"
        )


# ---------------------------------------------------------------------------
# /play — solo round (private DM only)
# ---------------------------------------------------------------------------


@router.message(Command("play"))
async def cmd_play(message: Message) -> None:
    if not _is_private(message):
        await message.reply("Use /trivia to start a game in a group chat.")
        return

    user = message.from_user
    if user is None:
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=_SOLO_CHAT_ID,
    )

    # Block if today's window is almost over
    settings = get_settings()
    now = datetime.now(tz=UTC)
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=0)
    minutes_left = int((midnight - now).total_seconds() / 60)
    if minutes_left < settings.trivia_min_solo_window_minutes:
        await message.answer(
            f"⏰ Today's quiz window closes in {minutes_left} minutes — not enough time to start.\n"
            "Come back tomorrow for a fresh quiz!"
        )
        return

    # Block if player already played (or is mid-quiz) today
    existing = await trivia_db.get_todays_round(chat_id=user.id)
    if existing:
        if existing.status == "scored":
            await message.answer("You've already played and been scored today. Come back tomorrow!")
            return
        # Round is still open — check if all questions were answered
        round_questions = await trivia_db.get_round_questions(existing.id)
        all_answers = await trivia_db.get_round_answers(existing.id)
        my_answers = [a for a in all_answers if a.player_id == player.id]
        if len(my_answers) >= len(round_questions):
            await message.answer(
                "You've already played today! 🎉 ELO updates at midnight UTC. See you tomorrow."
            )
        else:
            await message.answer(
                "You've already got a quiz going! Scroll up and finish your answers first."
            )
        return

    # Close any active practice round before starting the real quiz
    active = await trivia_db.get_active_round(chat_id=user.id)
    if active and active.mode == "practice":
        await trivia_db.set_round_status(active.id, "closed")
        await message.answer("Closing your practice round — let's start the real thing! 🎯")

    # Returning players: show current rank + ELO delta from last round
    if player.total_rounds > 0:
        rank, total_players = await trivia_db.get_player_rank(player.id, chat_id=_SOLO_CHAT_ID)
        last_score = await trivia_db.get_last_round_score(player.id)
        elo_note = ""
        if last_score and last_score.elo_delta != 0:
            sign = "+" if last_score.elo_delta > 0 else ""
            elo_note = f" ({sign}{last_score.elo_delta} from last round)"
        await message.answer(
            f"📊 Current rank: <b>#{rank} of {total_players}</b>\n"
            f"ELO: <b>{player.elo}</b>{elo_note}\n\n"
            "Ready to play? Pick a topic:"
        )

    # Show topic picker — quiz starts once they tap a topic
    topic_buttons = [
        [InlineKeyboardButton(text=t, callback_data=f"solo_topic:{t}")] for t in TOPIC_OPTIONS
    ]
    prompt = (
        "Pick a topic:" if player.total_rounds > 0 else "What do you want to be quizzed on today?"
    )
    await message.answer(
        prompt,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=topic_buttons),
    )


# ---------------------------------------------------------------------------
# Solo topic selection callback
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("solo_topic:"))
async def cb_solo_topic(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    topic = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    user = callback.from_user
    now = datetime.now(tz=UTC)

    # Guard: block if a round is already open or already played today
    existing = await trivia_db.get_todays_round(chat_id=user.id)
    if existing:
        if existing.status == "open":
            await callback.answer(
                "You already have a quiz in progress — scroll up to finish it!",
                show_alert=True,
            )
        else:
            await callback.answer(
                "You've already played today! Come back tomorrow for a new quiz.",
                show_alert=True,
            )
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=_SOLO_CHAT_ID,
    )

    # Dismiss the topic picker buttons so they can't be tapped again
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]

    await callback.message.answer("⏳ Generating your quiz…")  # type: ignore[union-attr]

    # Resolve "Surprise me" to a real theme
    if topic == "Surprise me 🎲":
        theme = await generate_theme(
            recent_themes=await trivia_db.get_recent_themes(chat_id=_SOLO_CHAT_ID)
        )
    else:
        theme = topic

    season = await _get_or_create_season(chat_id=_SOLO_CHAT_ID)
    closes_at = now.replace(hour=23, minute=59, second=59, microsecond=0)
    round_ = await trivia_db.create_round(
        chat_id=user.id,
        season_id=season.id,
        mode="solo",
        scheduled_for=now,
        closes_at=closes_at,
    )
    await trivia_db.set_round_theme(round_.id, theme)

    try:
        questions = await generate_questions(theme)
    except Exception:
        logger.exception(f"Failed to generate questions for theme {theme!r}")
        await trivia_db.set_round_status(round_.id, "closed")
        await callback.message.answer(  # type: ignore[union-attr]
            "😬 Something went wrong generating your quiz — please try /play again!"
        )
        return

    await trivia_db.save_questions(round_.id, [q.model_dump() for q in questions])
    db_questions = await trivia_db.get_round_questions(round_.id)

    # Send topic header image
    bot = get_bot()
    image_prompt = TOPIC_IMAGE_PROMPTS.get(topic, TOPIC_IMAGE_PROMPTS["Surprise me 🎲"])
    image_url = await get_topic_image(topic, image_prompt)
    caption = f"🎯 <b>{theme}</b> — let's go! Question 1 of {len(db_questions)}:"
    sent = False
    if image_url:
        try:
            await bot.send_photo(
                chat_id=callback.message.chat.id,  # type: ignore[union-attr]
                photo=image_url,
                caption=caption,
            )
            sent = True
        except Exception:
            pass
    if not sent:
        await callback.message.answer(caption)  # type: ignore[union-attr]

    # Dice animation + hype audio clip
    chat_id_for_media = callback.message.chat.id  # type: ignore[union-attr]
    try:
        await bot.send_dice(chat_id=chat_id_for_media, emoji="🎯")
    except Exception as e:
        logger.warning(f"Dice send failed: {e}")
    await _send_solo_question(callback.message.chat.id, round_.id, db_questions, 0, player.id)


def _solo_question_text(q: trivia_db.Question, timer_line: str) -> str:
    return (
        f"<b>Q{q.position}.</b> {q.question_text}\n\n"
        f"A) {q.choice_a}\n"
        f"B) {q.choice_b}\n"
        f"C) {q.choice_c}\n"
        f"D) {q.choice_d}\n\n"
        f"{timer_line}"
    )


async def _run_question_timer(
    chat_id: int,
    message_id: int,
    round_id: int,
    q: trivia_db.Question,
    keyboard: InlineKeyboardMarkup,
    questions: list[trivia_db.Question],
    index: int,
    player_id: int,
    is_practice: bool,
) -> None:
    bot = get_bot()
    try:
        await asyncio.sleep(15)
        with contextlib.suppress(Exception):
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=_solo_question_text(q, "⏱ <b>30 seconds left</b>"),
                reply_markup=keyboard,
            )
        await asyncio.sleep(15)
        with contextlib.suppress(Exception):
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=_solo_question_text(q, "⚠️ <b>15 seconds left!</b>"),
                reply_markup=keyboard,
            )
        await asyncio.sleep(10)
        with contextlib.suppress(Exception):
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=_solo_question_text(q, "🔴 <b>5 seconds!</b>"),
                reply_markup=keyboard,
            )
        await asyncio.sleep(5)
    except asyncio.CancelledError:
        return  # Player answered in time — cancelled cleanly

    # Time's up
    _question_timers.pop(q.id, None)

    correct_text = getattr(q, f"choice_{q.correct_choice.lower()}")
    timeout_msg_text = (
        f"<b>Q{q.position}.</b> {q.question_text}\n\n"
        f"A) {q.choice_a}\n"
        f"B) {q.choice_b}\n"
        f"C) {q.choice_c}\n"
        f"D) {q.choice_d}\n\n"
        f"⏰ <b>Time's up!</b> Answer: <b>{q.correct_choice}) {correct_text}</b>"
    )
    with contextlib.suppress(Exception):
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=timeout_msg_text,
            reply_markup=None,
        )

    # Compute running score (this question not answered)
    answers = await trivia_db.get_round_answers(round_id)
    player_answers = [a for a in answers if a.player_id == player_id]
    correct_count = sum(
        1
        for a in player_answers
        for q2 in questions
        if q2.id == a.question_id and q2.correct_choice.upper() == a.choice.upper()
    )

    feedback = (
        f"⏰ <b>Time's up!</b> The answer was <b>{q.correct_choice}) {correct_text}</b>\n"
        f"{q.explanation or ''}"
        f"\n\n📊 <b>{correct_count}/{len(player_answers)}</b> correct so far"
    )
    with contextlib.suppress(Exception):
        await bot.send_message(chat_id=chat_id, text=feedback)

    next_index = index + 1
    if next_index < len(questions):
        if is_practice:
            await _send_practice_question(chat_id, round_id, questions, next_index, player_id)
        else:
            await _send_solo_question(chat_id, round_id, questions, next_index, player_id)
    else:
        # Quiz complete — show final result
        rank, total_players = await trivia_db.get_player_rank(player_id, chat_id=_SOLO_CHAT_ID)
        play_again_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎲 Play another round (just for fun)",
                        callback_data="practice_start",
                    )
                ]
            ]
        )
        if is_practice:
            caption = (
                f"🎉 Practice done! You got <b>{correct_count}/{len(questions)}</b> right.\n"
                "No ELO change — but good reps! 💪"
            )
        else:
            caption = (
                f"🎉 <b>Quiz complete!</b> You got"
                f" <b>{correct_count}/{len(questions)}</b> right.\n\n"
                f"Current rank: <b>#{rank} of {total_players}</b>\n"
                "ELO updates at midnight UTC. See you tomorrow!"
            )
        image_url = await get_topic_image("celebration", CELEBRATION_IMAGE_PROMPT)
        sent = False
        if image_url:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=caption,
                    reply_markup=play_again_keyboard,
                )
                sent = True
            except Exception:
                pass
        if not sent:
            await bot.send_message(chat_id=chat_id, text=caption, reply_markup=play_again_keyboard)


async def _send_solo_question(
    chat_id: int,
    round_id: int,
    questions: list[trivia_db.Question],
    index: int,
    player_id: int,
) -> None:
    """Send one solo question with A/B/C/D buttons."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    if index >= len(questions):
        return

    q = questions[index]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="A", callback_data=f"solo:{round_id}:{q.id}:A:{index}"),
                InlineKeyboardButton(text="B", callback_data=f"solo:{round_id}:{q.id}:B:{index}"),
                InlineKeyboardButton(text="C", callback_data=f"solo:{round_id}:{q.id}:C:{index}"),
                InlineKeyboardButton(text="D", callback_data=f"solo:{round_id}:{q.id}:D:{index}"),
            ]
        ]
    )
    bot = get_bot()
    msg = await bot.send_message(
        chat_id=chat_id,
        text=_solo_question_text(q, "⏱ <b>45 seconds</b>"),
        reply_markup=keyboard,
    )

    old = _question_timers.pop(q.id, None)
    if old:
        old.cancel()
    _question_timers[q.id] = asyncio.create_task(
        _run_question_timer(
            chat_id=chat_id,
            message_id=msg.message_id,
            round_id=round_id,
            q=q,
            keyboard=keyboard,
            questions=questions,
            index=index,
            player_id=player_id,
            is_practice=False,
        )
    )


# ---------------------------------------------------------------------------
# Solo answer callback — tap A/B/C/D on a solo question
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("solo:"))
async def cb_solo_answer(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    # callback_data format: solo:{round_id}:{question_id}:{choice}:{index}
    _, round_id_s, question_id_s, choice, index_s = callback.data.split(":")  # type: ignore[union-attr]
    round_id = int(round_id_s)
    question_id = int(question_id_s)
    index = int(index_s)
    user = callback.from_user

    round_ = await trivia_db.get_round(round_id)
    if round_ is None or round_.status != "open":
        await callback.answer("This round is already closed.", show_alert=True)
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=_SOLO_CHAT_ID,
    )

    await trivia_db.record_answer(round_id, question_id, player.id, choice)

    # Cancel the countdown timer for this question
    timer_task = _question_timers.pop(question_id, None)
    if timer_task:
        timer_task.cancel()

    # Remove buttons from this question immediately — can't tap again
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]

    # Find the question to give feedback
    questions = await trivia_db.get_round_questions(round_id)
    q = next((q for q in questions if q.id == question_id), None)
    if q is None:
        await callback.answer("Something went wrong.", show_alert=True)
        return

    # Compute running score by comparing all player answers to correct choices
    answers = await trivia_db.get_round_answers(round_id)
    player_answers = [a for a in answers if a.player_id == player.id]
    correct_count = sum(
        1
        for a in player_answers
        for q2 in questions
        if q2.id == a.question_id and q2.correct_choice.upper() == a.choice.upper()
    )
    questions_answered = len(player_answers)

    rank, total_players = await trivia_db.get_player_rank(player.id, chat_id=_SOLO_CHAT_ID)

    feedback = format_solo_feedback(q, choice)
    score_line = (
        f"\n\n📊 <b>{correct_count}/{questions_answered}</b> correct so far · "
        f"Rank #{rank} of {total_players}"
    )
    await callback.answer()
    await callback.message.answer(feedback + score_line)  # type: ignore[union-attr]

    next_index = index + 1
    if next_index < len(questions):
        await _send_solo_question(
            callback.message.chat.id, round_id, questions, next_index, player.id
        )
    else:
        bot = get_bot()
        caption = (
            f"🎉 <b>Quiz complete!</b> You got <b>{correct_count}/{len(questions)}</b> right.\n\n"
            f"Current rank: <b>#{rank} of {total_players}</b>\n"
            "ELO updates at midnight UTC when all solo scores are tallied. See you tomorrow!"
        )
        play_again_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎲 Play another round (just for fun)",
                        callback_data="practice_start",
                    )
                ]
            ]
        )
        image_url = await get_topic_image("celebration", CELEBRATION_IMAGE_PROMPT)
        sent = False
        if image_url:
            try:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,  # type: ignore[union-attr]
                    photo=image_url,
                    caption=caption,
                    reply_markup=play_again_keyboard,
                )
                sent = True
            except Exception:
                pass
        if not sent:
            await callback.message.answer(caption, reply_markup=play_again_keyboard)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# /trivia — group voting (group chats only)
# ---------------------------------------------------------------------------


@router.message(Command("trivia"))
async def cmd_trivia(message: Message) -> None:
    if _is_private(message):
        await message.reply("Use /play to start a solo quiz in a private chat.")
        return

    chat_id = _group_chat_id(message)
    user = message.from_user
    if user is None:
        return

    # Block if a round is already in progress
    existing = await trivia_db.get_active_round(chat_id=chat_id)
    if existing:
        status_text = "voting on a topic" if existing.status == "voting" else "in progress"
        await message.reply(
            f"A round is already {status_text}! Use /score to see who has answered."
        )
        return

    season = await _get_or_create_season(chat_id=chat_id)
    settings = get_settings()
    now = datetime.now(tz=UTC)

    round_ = await trivia_db.create_round(
        chat_id=chat_id,
        season_id=season.id,
        mode="group",
        scheduled_for=now,
        closes_at=now + timedelta(minutes=settings.trivia_answer_window_minutes),
        topic_vote_ends_at=now + timedelta(minutes=settings.trivia_vote_window_minutes),
    )

    vote_text = format_vote_message(settings.trivia_vote_window_minutes)
    bot = get_bot()
    await bot.send_message(
        chat_id=chat_id,
        text=vote_text,
        reply_markup=topic_vote_keyboard(round_.id),
    )
    logger.info(f"Started topic vote for round {round_.id} in chat {chat_id}")


# ---------------------------------------------------------------------------
# Topic vote callback
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("vote:"))
async def cb_topic_vote(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    # callback_data format: vote:{round_id}:{topic}
    parts = callback.data.split(":", 2)  # type: ignore[union-attr]
    round_id = int(parts[1])
    topic = parts[2]

    user = callback.from_user
    chat_id = callback.message.chat.id

    round_ = await trivia_db.get_round(round_id)
    if round_ is None or round_.status != "voting":
        await callback.answer("Voting is closed.", show_alert=True)
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=chat_id,
    )

    await trivia_db.record_topic_vote(round_id, player.id, topic)
    await callback.answer(f"Voted for {topic}!")

    # Check if a topic now has majority
    chat_players = await trivia_db.get_chat_players(chat_id)
    total_players = len(chat_players)
    vote_counts = await trivia_db.get_vote_counts(round_id)
    winner = trivia_db.check_majority_topic(vote_counts, total_players)

    if winner and isinstance(callback.message, Message):
        await _start_round_with_topic(callback.message, round_, winner, chat_id)


def _build_answered_by(answers: list[trivia_db.Answer]) -> dict[int, set[int]]:
    """Map player_id → set of question_ids they have answered."""
    result: dict[int, set[int]] = {}
    for a in answers:
        result.setdefault(a.player_id, set()).add(a.question_id)
    return result


async def _all_players_answered(
    round_id: int,
    answered_by: dict[int, set[int]],
    question_ids: set[int],
) -> bool:
    """Return True when every committed player has finished all questions.

    "Committed" means they cast a topic vote for this round — that tap is the
    clearest "I want to play" signal before questions exist.  Players who answer
    without voting (joined mid-round) are a bonus but don't block the close.

    If no one voted (scheduler forced a random topic), falls back to requiring
    all current respondents finished, with a minimum of 2.
    """
    voter_ids = set(await trivia_db.get_topic_voter_ids(round_id))

    if voter_ids:
        # All topic voters must have answered every question
        return all(answered_by.get(pid, set()) >= question_ids for pid in voter_ids)
    else:
        # No topic vote happened — wait for every respondent to finish, min 2
        respondent_ids = set(answered_by.keys())
        if len(respondent_ids) < 2:
            return False
        return all(answered_by.get(pid, set()) >= question_ids for pid in respondent_ids)


async def _start_round_with_topic(
    message: Message,
    round_: trivia_db.Round,
    topic: str,
    chat_id: int,
) -> None:
    """Lock in the winning topic, generate questions, post the quiz."""
    if topic == "Surprise me 🎲":
        theme = await generate_theme(
            recent_themes=await trivia_db.get_recent_themes(chat_id=chat_id)
        )
    else:
        theme = topic

    await trivia_db.set_round_theme(round_.id, theme)
    await trivia_db.set_round_status(round_.id, "open")

    await message.answer("⏳ Generating questions…")

    try:
        questions = await generate_questions(theme)
    except Exception:
        logger.exception(f"Failed to generate questions for theme {theme!r} in chat {chat_id}")
        await trivia_db.set_round_status(round_.id, "closed")
        await message.answer(
            "😬 Something went wrong generating the quiz — please try /trivia again!"
        )
        return

    await trivia_db.save_questions(round_.id, [q.model_dump() for q in questions])
    db_questions = await trivia_db.get_round_questions(round_.id)

    settings = get_settings()
    bot = get_bot()

    # Topic header image
    image_prompt = TOPIC_IMAGE_PROMPTS.get(topic, TOPIC_IMAGE_PROMPTS["Surprise me 🎲"])
    image_url = await get_topic_image(topic, image_prompt)
    gif_caption = (
        f"🎲 <b>{theme}</b> wins the vote! "
        f"Quiz is live — {settings.trivia_answer_window_minutes} min on the clock. Go! 🏁"
    )
    sent = False
    if image_url:
        try:
            await bot.send_photo(chat_id=chat_id, photo=image_url, caption=gif_caption)
            sent = True
        except Exception:
            pass
    if not sent:
        await message.answer(gif_caption)

    # Dice animation
    try:
        await bot.send_dice(chat_id=chat_id, emoji="🎯")
    except Exception as e:
        logger.warning(f"Dice send failed: {e}")

    # Rivalry tease — fires only if this group has head-to-head history
    voter_ids = await trivia_db.get_topic_voter_ids(round_.id)
    tease = await trivia_db.get_rivalry_tease_line(voter_ids)
    if tease:
        await bot.send_message(chat_id=chat_id, text=tease)

    quiz_text = format_quiz_message(theme, db_questions, settings.trivia_answer_window_minutes)
    msg = await bot.send_message(
        chat_id=chat_id,
        text=quiz_text,
        reply_markup=quiz_keyboard(round_.id, db_questions),
    )
    await trivia_db.set_round_message_id(round_.id, msg.message_id)

    # Pin so the quiz stays visible — silently fails if the bot isn't an admin
    with contextlib.suppress(Exception):
        await bot.pin_chat_message(
            chat_id=chat_id, message_id=msg.message_id, disable_notification=True
        )

    logger.info(f"Quiz started for round {round_.id} in chat {chat_id} — theme: {theme!r}")


# ---------------------------------------------------------------------------
# Group answer callback — tap Q1-A, Q2-B, etc.
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith("ans:"))
async def cb_group_answer(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    # callback_data format: ans:{round_id}:{question_id}:{position}:{choice}
    _, round_id_s, question_id_s, position_s, choice = callback.data.split(":")  # type: ignore[union-attr]
    round_id = int(round_id_s)
    question_id = int(question_id_s)
    position = int(position_s)
    user = callback.from_user
    chat_id = callback.message.chat.id

    round_ = await trivia_db.get_round(round_id)
    if round_ is None or round_.status != "open":
        await callback.answer("This round is already closed.", show_alert=True)
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=chat_id,
    )

    await trivia_db.record_answer(round_id, question_id, player.id, choice)
    await callback.answer(
        f"Q{position} → {choice} locked in ✅\nYou can change any answer before time's up!",
        show_alert=True,
    )
    logger.debug(f"Player {user.id} answered Q{position} → {choice} in round {round_id}")

    # Fetch questions + all answers once — reused for both progress and early-close checks
    questions = await trivia_db.get_round_questions(round_id)
    all_answers = await trivia_db.get_round_answers(round_id)
    question_ids = {q.id for q in questions}
    answered_by = _build_answered_by(all_answers)

    player_just_finished = answered_by.get(player.id, set()) >= question_ids

    if await _all_players_answered(round_id, answered_by, question_ids):
        # Everyone is done — score immediately
        fresh_round = await trivia_db.get_round(round_id)
        if fresh_round and fresh_round.status == "open":
            bot = get_bot()
            await bot.send_message(
                chat_id=chat_id, text="Everyone's answered! 🎯 Tallying results now..."
            )
            from agent.scheduler import _score_round

            await _score_round(fresh_round)
    elif player_just_finished:
        # This player finished but others are still going — show group progress
        finished_count = sum(1 for qids in answered_by.values() if qids >= question_ids)
        voter_ids = set(await trivia_db.get_topic_voter_ids(round_id))
        total_expected = len(voter_ids) if voter_ids else len(answered_by)
        first_name = user.first_name or user.full_name.split()[0]
        bot = get_bot()
        await bot.send_message(
            chat_id=chat_id,
            text=f"✅ <b>{first_name}</b> is done — {finished_count}/{total_expected} wrapped up",
        )


# ---------------------------------------------------------------------------
# Practice mode — "Play again for fun" (no ELO, unlimited replays)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == "practice_start")
async def cb_practice_start(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    user = callback.from_user
    if callback.message.chat.type != "private":
        await callback.answer("Practice mode is only available in DMs!", show_alert=True)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.message.answer("⏳ Picking a surprise topic and generating questions…")  # type: ignore[union-attr]

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=_SOLO_CHAT_ID,
    )

    # Close any lingering practice round — one at a time is enough
    old_practice = await trivia_db.get_active_round(chat_id=user.id)
    if old_practice and old_practice.mode == "practice":
        await trivia_db.set_round_status(old_practice.id, "closed")

    theme = await generate_theme(
        recent_themes=await trivia_db.get_recent_themes(chat_id=_SOLO_CHAT_ID)
    )

    from datetime import UTC, datetime, timedelta

    now = datetime.now(tz=UTC)
    season = await _get_or_create_season(chat_id=_SOLO_CHAT_ID)
    round_ = await trivia_db.create_round(
        chat_id=user.id,
        season_id=season.id,
        mode="practice",
        scheduled_for=now,
        closes_at=now + timedelta(hours=1),
    )
    await trivia_db.set_round_theme(round_.id, theme)

    try:
        questions = await generate_questions(theme)
    except Exception:
        logger.exception(f"Failed to generate questions for theme {theme!r}")
        await trivia_db.set_round_status(round_.id, "closed")
        await callback.message.answer(  # type: ignore[union-attr]
            "😬 Something went wrong generating your quiz — please try /play again!"
        )
        return

    await trivia_db.save_questions(round_.id, [q.model_dump() for q in questions])
    db_questions = await trivia_db.get_round_questions(round_.id)

    bot = get_bot()
    image_url = await get_topic_image("Surprise me 🎲")
    caption = (
        f"🎲 <b>{theme}</b> — practice round! No ELO on the line. "
        f"Question 1 of {len(db_questions)}:"
    )
    sent = False
    if image_url:
        try:
            await bot.send_photo(
                chat_id=callback.message.chat.id,  # type: ignore[union-attr]
                photo=image_url,
                caption=caption,
            )
            sent = True
        except Exception:
            pass
    if not sent:
        await callback.message.answer(caption)  # type: ignore[union-attr]

    # Dice animation for practice — casual vibe
    try:
        await bot.send_dice(
            chat_id=callback.message.chat.id,  # type: ignore[union-attr]
            emoji="🎲",
        )
    except Exception as e:
        logger.warning(f"Dice send failed: {e}")

    await _send_practice_question(callback.message.chat.id, round_.id, db_questions, 0, player.id)


async def _send_practice_question(
    chat_id: int,
    round_id: int,
    questions: list[trivia_db.Question],
    index: int,
    player_id: int,
) -> None:
    """Send one practice question with A/B/C/D buttons."""
    if index >= len(questions):
        return
    q = questions[index]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="A", callback_data=f"prac:{round_id}:{q.id}:A:{index}"),
                InlineKeyboardButton(text="B", callback_data=f"prac:{round_id}:{q.id}:B:{index}"),
                InlineKeyboardButton(text="C", callback_data=f"prac:{round_id}:{q.id}:C:{index}"),
                InlineKeyboardButton(text="D", callback_data=f"prac:{round_id}:{q.id}:D:{index}"),
            ]
        ]
    )
    bot = get_bot()
    msg = await bot.send_message(
        chat_id=chat_id,
        text=_solo_question_text(q, "⏱ <b>45 seconds</b>"),
        reply_markup=keyboard,
    )

    old = _question_timers.pop(q.id, None)
    if old:
        old.cancel()
    _question_timers[q.id] = asyncio.create_task(
        _run_question_timer(
            chat_id=chat_id,
            message_id=msg.message_id,
            round_id=round_id,
            q=q,
            keyboard=keyboard,
            questions=questions,
            index=index,
            player_id=player_id,
            is_practice=True,
        )
    )


@router.callback_query(F.data.startswith("prac:"))
async def cb_practice_answer(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    _, round_id_s, question_id_s, choice, index_s = callback.data.split(":")  # type: ignore[union-attr]
    round_id = int(round_id_s)
    question_id = int(question_id_s)
    index = int(index_s)
    user = callback.from_user

    round_ = await trivia_db.get_round(round_id)
    if round_ is None or round_.status != "open":
        await callback.answer("This practice round has ended.", show_alert=True)
        return

    player = await _get_or_register_player(
        telegram_id=user.id,
        display_name=user.full_name,
        username=user.username,
        chat_id=_SOLO_CHAT_ID,
    )

    await trivia_db.record_answer(round_id, question_id, player.id, choice)

    # Cancel the countdown timer for this question
    timer_task = _question_timers.pop(question_id, None)
    if timer_task:
        timer_task.cancel()

    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]

    questions = await trivia_db.get_round_questions(round_id)
    q = next((q for q in questions if q.id == question_id), None)
    if q is None:
        await callback.answer("Something went wrong.", show_alert=True)
        return

    answers = await trivia_db.get_round_answers(round_id)
    player_answers = [a for a in answers if a.player_id == player.id]
    correct_count = sum(
        1
        for a in player_answers
        for q2 in questions
        if q2.id == a.question_id and q2.correct_choice.upper() == a.choice.upper()
    )
    questions_answered = len(player_answers)

    feedback = format_solo_feedback(q, choice)
    score_line = f"\n\n📊 <b>{correct_count}/{questions_answered}</b> correct so far"
    await callback.answer()
    await callback.message.answer(feedback + score_line)  # type: ignore[union-attr]

    next_index = index + 1
    if next_index < len(questions):
        await _send_practice_question(
            callback.message.chat.id, round_id, questions, next_index, player.id
        )
    else:
        await trivia_db.set_round_status(round_id, "closed")
        bot = get_bot()
        caption = (
            f"🎉 Practice done! You got <b>{correct_count}/{len(questions)}</b> right.\n"
            "No ELO change — but good reps! 💪"
        )
        play_again_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🎲 Play another round", callback_data="practice_start")]
            ]
        )
        image_url = await get_topic_image("celebration", CELEBRATION_IMAGE_PROMPT)
        sent = False
        if image_url:
            try:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,  # type: ignore[union-attr]
                    photo=image_url,
                    caption=caption,
                    reply_markup=play_again_keyboard,
                )
                sent = True
            except Exception:
                pass
        if not sent:
            await callback.message.answer(caption, reply_markup=play_again_keyboard)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# /funfacts — fun trivia facts on a chosen topic
# ---------------------------------------------------------------------------


@router.message(Command("funfacts"))
async def cmd_funfacts(message: Message) -> None:
    buttons = [[InlineKeyboardButton(text=t, callback_data=f"ff:{t}")] for t in TOPIC_OPTIONS]
    await message.answer(
        "🧠 <b>Fun Facts!</b>\n\nPick a topic and I'll hit you with 5 facts worth knowing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("ff:"))
async def cb_funfacts_topic(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    topic = callback.data.split(":", 1)[1]  # type: ignore[union-attr]
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    await callback.message.answer("⏳ Digging up the good stuff…")  # type: ignore[union-attr]

    if topic == "Surprise me 🎲":
        theme = await generate_theme(
            recent_themes=await trivia_db.get_recent_themes(chat_id=_SOLO_CHAT_ID)
        )
    else:
        theme = topic

    facts = await generate_fun_facts(theme)

    lines = [f"🧠 <b>{theme} — 5 Facts Worth Knowing</b>", ""]
    for i, fact in enumerate(facts, 1):
        lines.append(f"<b>{i}.</b> {fact}")

    bot = get_bot()
    image_prompt = TOPIC_IMAGE_PROMPTS.get(topic, FUN_FACTS_IMAGE_PROMPT)
    image_url = await get_topic_image(topic, image_prompt)
    text = "\n".join(lines)
    _CAPTION_LIMIT = 950  # safe margin under Telegram's 1024

    sent = False
    if image_url:
        try:
            if len(text) <= _CAPTION_LIMIT:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,  # type: ignore[union-attr]
                    photo=image_url,
                    caption=text,
                )
            else:
                await bot.send_photo(
                    chat_id=callback.message.chat.id,  # type: ignore[union-attr]
                    photo=image_url,
                    caption=f"🧠 <b>{theme} — 5 Facts Worth Knowing</b>",
                )
                await callback.message.answer(text)  # type: ignore[union-attr]
            sent = True
        except Exception:
            pass
    if not sent:
        await callback.message.answer(text)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# /score — who has answered so far?
# ---------------------------------------------------------------------------


@router.message(Command("score"))
async def cmd_score(message: Message) -> None:
    # Solo /score: just show the active round status briefly
    if _is_private(message):
        user = message.from_user
        if user is None:
            return
        round_ = await trivia_db.get_active_round(chat_id=user.id)
        if round_ is None or round_.status != "open":
            await message.reply("No active quiz right now. Type /play to start one!")
            return
        questions = await trivia_db.get_round_questions(round_.id)
        all_answers = await trivia_db.get_round_answers(round_.id)
        player = await trivia_db.get_player(user.id, chat_id=_SOLO_CHAT_ID)
        if player is None:
            await message.reply("No active quiz right now. Type /play to start one!")
            return
        my_answers = [a for a in all_answers if a.player_id == player.id]
        closes_at = round_.closes_at
        now = datetime.now(tz=UTC)
        minutes_left = max(0, int((closes_at - now).total_seconds() / 60))
        await message.reply(
            f"You've answered <b>{len(my_answers)}/{len(questions)}</b> questions. "
            f"⏱ {minutes_left} minutes left."
        )
        return

    # Group /score
    chat_id = _group_chat_id(message)
    round_ = await trivia_db.get_active_round(chat_id=chat_id)
    if round_ is None or round_.status not in ("open", "voting"):
        await message.reply("No active round right now. Use /trivia to start one!")
        return

    if round_.status == "voting":
        vote_counts = await trivia_db.get_vote_counts(round_.id)
        if not vote_counts:
            await message.reply("Voting is open — no votes yet. Tap a topic!")
            return
        lines = ["🗳 <b>Current votes:</b>"]
        for topic, count in sorted(vote_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {topic}: {count}")
        await message.reply("\n".join(lines))
        return

    # Open round — show detailed progress
    questions = await trivia_db.get_round_questions(round_.id)
    all_answers = await trivia_db.get_round_answers(round_.id)
    answered_by = _build_answered_by(all_answers)
    question_ids = {q.id for q in questions}

    voter_ids = set(await trivia_db.get_topic_voter_ids(round_.id))
    respondent_ids = set(answered_by.keys())
    done_ids = {pid for pid in respondent_ids if answered_by.get(pid, set()) >= question_ids}
    in_progress_ids = respondent_ids - done_ids
    waiting_ids = voter_ids - respondent_ids  # voted but haven't tapped a single answer

    closes_at = round_.closes_at
    now = datetime.now(tz=UTC)
    minutes_left = max(0, int((closes_at - now).total_seconds() / 60))

    lines: list[str] = []

    if done_ids:
        names = []
        for pid in done_ids:
            p = await trivia_db.get_player_by_id(pid)
            if p:
                names.append(p.display_name)
        lines.append(f"✅ Done: {', '.join(names)}")

    if in_progress_ids:
        parts = []
        for pid in in_progress_ids:
            p = await trivia_db.get_player_by_id(pid)
            if p:
                n = len(answered_by.get(pid, set()))
                parts.append(f"{p.display_name} ({n}/{len(questions)})")
        lines.append(f"⏳ In progress: {', '.join(parts)}")

    if waiting_ids:
        mentions = []
        for pid in waiting_ids:
            p = await trivia_db.get_player_by_id(pid)
            if p:
                mentions.append(f'<a href="tg://user?id={p.telegram_id}">{p.display_name}</a>')
        lines.append(f"😴 Still waiting on: {', '.join(mentions)}")

    if not lines:
        lines.append("Nobody has answered yet — scroll up and tap! 👆")

    lines.append(f"\n⏱ {minutes_left} minutes left")
    await message.reply("\n".join(lines))


# ---------------------------------------------------------------------------
# /leaderboard
# ---------------------------------------------------------------------------


@router.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message) -> None:
    chat_id = _SOLO_CHAT_ID if _is_private(message) else _group_chat_id(message)
    viewer_id = message.from_user.id if message.from_user else None
    players = await trivia_db.get_leaderboard(chat_id=chat_id, limit=10)
    if not players:
        await message.reply("No players yet. Be the first!")
        return
    await message.reply(format_leaderboard(players, chat_id, viewer_id))


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@router.message(Command("me"))
async def cmd_me(message: Message) -> None:
    if message.from_user is None:
        return

    chat_id = _SOLO_CHAT_ID if _is_private(message) else _group_chat_id(message)
    player = await trivia_db.get_player(message.from_user.id, chat_id=chat_id)
    if player is None:
        hint = "Type /play to start!" if _is_private(message) else "Tap an answer to join!"
        await message.reply(f"You're not registered yet. {hint}")
        return

    all_players = await trivia_db.get_leaderboard(chat_id=chat_id, limit=1000)
    rank = next((i + 1 for i, p in enumerate(all_players) if p.id == player.id), 0)
    await message.reply(format_my_stats(player, rank, len(all_players)))


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if _is_private(message):
        text = (
            "<b>Solo TriviaBot commands</b>\n\n"
            "/play — start today's quiz (5 questions, instant feedback)\n"
            "/me — view your ELO rank and stats\n"
            "/funfacts — get 5 fun facts on a topic\n"
            "/leaderboard — global solo rankings\n"
            "/score — check your progress on the current round\n\n"
            "Answer questions by tapping the A/B/C/D buttons. "
            "ELO updates daily when the quiz window closes at midnight UTC."
        )
    else:
        text = (
            "<b>Group TriviaBot commands</b>\n\n"
            "/trivia — start a new round (vote for a topic first)\n"
            "/score — see who's answered and time remaining\n"
            "/leaderboard — this group's season standings\n"
            "/me — your personal stats in this group\n"
            "/funfacts — get 5 fun facts on a topic\n\n"
            "Tap A/B/C/D buttons to answer. "
            "You can change answers any time before the window closes.\n"
            "ELO is based on how you score vs every other player in the group."
        )
    await message.reply(text)
