"""APScheduler background jobs for the trivia bot.

Two jobs run on the same asyncio event loop as the bot:

  job_resolve_expired_votes (every 60s)
    — finds group rounds still in 'voting' whose topic_vote_ends_at has passed
    — picks the highest-voted topic (or a random theme if no votes at all)
    — transitions the round to 'open' and posts the quiz

  job_score_expired_rounds (every 60s)
    — finds rounds in 'open' whose closes_at has passed
    — scores them, posts results, updates ELO
"""

import contextlib
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

from agent.services import trivia_db
from agent.services.question_generator import generate_questions, generate_theme
from agent.services.scoring import ELOUpdate, PlayerScore, compute_round_elos
from agent.services.telegram import (
    TOPIC_IMAGE_PROMPTS,
    format_results_message,
    get_bot,
    get_topic_image,
    quiz_keyboard,
)


@dataclass
class _ZeroELO:
    """Placeholder ELO update used when ELO changes are skipped (< 2 players)."""

    player_id: int
    elo_before: int
    elo_after: int
    delta: int = 0


async def job_resolve_expired_votes() -> None:
    """Force-resolve any group voting rounds whose time window has passed."""
    expired = await trivia_db.get_voting_expired_rounds()
    if not expired:
        return

    for round_ in expired:
        try:
            await _resolve_vote(round_)
        except Exception:
            logger.exception(f"Failed to resolve vote for round {round_.id}")


async def _resolve_vote(round_: trivia_db.Round) -> None:
    # Guard against double-fire: if questions already exist, this was already resolved
    existing_questions = await trivia_db.get_round_questions(round_.id)
    if existing_questions:
        logger.warning(f"Round {round_.id} already has questions — skipping duplicate resolve")
        return

    vote_counts = await trivia_db.get_vote_counts(round_.id)

    # Pick highest-voted topic; ties broken alphabetically for determinism.
    # None means no votes at all — LLM will pick a random theme.
    topic = max(vote_counts, key=lambda t: (vote_counts[t], t)) if vote_counts else None

    if topic == "Surprise me 🎲" or topic is None:
        theme = await generate_theme(
            recent_themes=await trivia_db.get_recent_themes(chat_id=round_.chat_id)
        )
    else:
        theme = topic

    await trivia_db.set_round_theme(round_.id, theme)
    await trivia_db.set_round_status(round_.id, "open")

    bot = get_bot()

    try:
        questions = await generate_questions(theme)
    except Exception:
        logger.exception(f"Failed to generate questions for round {round_.id}")
        await trivia_db.set_round_status(round_.id, "closed")
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id=round_.chat_id,
                text="😬 Something went wrong generating today's quiz — type /trivia to try again!",
            )
        return

    await trivia_db.save_questions(round_.id, [q.model_dump() for q in questions])
    db_questions = await trivia_db.get_round_questions(round_.id)

    from agent.config import get_settings
    from agent.services.telegram import format_quiz_message

    settings = get_settings()

    fallback_topic = topic or "Surprise me 🎲"
    image_prompt = TOPIC_IMAGE_PROMPTS.get(fallback_topic, TOPIC_IMAGE_PROMPTS["Surprise me 🎲"])
    image_url = await get_topic_image(fallback_topic, image_prompt)
    gif_caption = (
        f"⏰ Voting closed! <b>{theme}</b> takes it. "
        f"You've got {settings.trivia_answer_window_minutes} minutes — go! 🏁"
    )
    sent = False
    if image_url:
        try:
            await bot.send_photo(chat_id=round_.chat_id, photo=image_url, caption=gif_caption)
            sent = True
        except Exception:
            pass
    if not sent:
        with contextlib.suppress(Exception):
            await bot.send_message(chat_id=round_.chat_id, text=gif_caption)

    # Dice animation
    try:
        await bot.send_dice(chat_id=round_.chat_id, emoji="🎯")
    except Exception as e:
        logger.warning(f"Dice send failed in scheduler: {e}")

    # Rivalry tease between topic voters
    voter_ids = await trivia_db.get_topic_voter_ids(round_.id)
    tease = await trivia_db.get_rivalry_tease_line(voter_ids)
    if tease:
        await bot.send_message(chat_id=round_.chat_id, text=tease)

    msg = await bot.send_message(
        chat_id=round_.chat_id,
        text=format_quiz_message(theme, db_questions, settings.trivia_answer_window_minutes),
        reply_markup=quiz_keyboard(round_.id, db_questions),
    )
    await trivia_db.set_round_message_id(round_.id, msg.message_id)

    with contextlib.suppress(Exception):
        await bot.pin_chat_message(
            chat_id=round_.chat_id, message_id=msg.message_id, disable_notification=True
        )

    logger.info(f"Vote expired for round {round_.id} — started with topic {theme!r}")


async def job_score_expired_rounds() -> None:
    """Score any open rounds whose answer window has closed."""
    expired = await trivia_db.get_open_expired_rounds()
    if not expired:
        return

    for round_ in expired:
        try:
            await _score_round(round_)
        except Exception:
            logger.exception(f"Failed to score round {round_.id}")


async def _score_round(round_: trivia_db.Round) -> None:
    # Mark closed immediately to prevent double-scoring if the job fires twice
    await trivia_db.set_round_status(round_.id, "closed")

    questions = await trivia_db.get_round_questions(round_.id)
    answers = await trivia_db.get_round_answers(round_.id)
    respondent_ids = await trivia_db.get_round_respondents(round_.id)

    # Build per-player correct counts
    correct_by_player: dict[int, int] = {pid: 0 for pid in respondent_ids}
    correct_set = {q.id: q.correct_choice for q in questions}
    for a in answers:
        if a.player_id in correct_by_player and correct_set.get(a.question_id) == a.choice:
            correct_by_player[a.player_id] += 1

    # Fetch current ELO for each respondent
    player_map: dict[int, trivia_db.Player] = {}
    for pid in respondent_ids:
        p = await trivia_db.get_player_by_id(pid)
        if p:
            player_map[pid] = p

    # Compute ELO — skip if fewer than 2 players (no pairwise matches possible)
    skip_elo = len(respondent_ids) < 2
    if round_.mode == "practice":
        skip_elo = True

    player_scores = [
        PlayerScore(
            player_id=pid,
            elo=player_map[pid].elo if pid in player_map else 1200,
            correct=correct_by_player[pid],
            total=len(questions),
        )
        for pid in respondent_ids
        if pid in player_map
    ]

    elo_map: dict[int, ELOUpdate | _ZeroELO]
    if skip_elo:
        elo_map = {p.player_id: _ZeroELO(p.player_id, p.elo, p.elo) for p in player_scores}
    else:
        elo_map = {u.player_id: u for u in compute_round_elos(player_scores)}

    # Build RoundScore objects, ranked by correct count descending
    sorted_players = sorted(
        respondent_ids,
        key=lambda pid: correct_by_player.get(pid, 0),
        reverse=True,
    )
    round_scores = [
        trivia_db.RoundScore(
            round_id=round_.id,
            player_id=pid,
            correct_count=correct_by_player.get(pid, 0),
            total_questions=len(questions),
            rank=rank,
            elo_before=elo_map[pid].elo_before,
            elo_after=elo_map[pid].elo_after,
            elo_delta=elo_map[pid].delta,
        )
        for rank, pid in enumerate(sorted_players, start=1)
        if pid in elo_map
    ]

    # Absent players — all registered chat players who didn't respond
    if round_.mode == "group":
        all_chat_players = await trivia_db.get_chat_players(round_.chat_id)
        absent_ids = [p.id for p in all_chat_players if p.id not in respondent_ids]
    else:
        absent_ids = []

    await trivia_db.save_round_results(round_.id, round_scores, absent_ids)

    # Upsert rivalries for all pairs (group mode only)
    if round_.mode == "group" and not skip_elo and len(sorted_players) >= 2:
        from itertools import combinations

        for pid_a, pid_b in combinations(sorted_players, 2):
            score_a = correct_by_player.get(pid_a, 0)
            score_b = correct_by_player.get(pid_b, 0)
            a_wins = 1 if score_a > score_b else 0
            b_wins = 1 if score_b > score_a else 0
            ties = 1 if score_a == score_b else 0
            await trivia_db.upsert_rivalry(pid_a, pid_b, a_wins, b_wins, ties)

    # Remove inline buttons and unpin the quiz message — round is over
    bot = get_bot()
    if round_.message_id:
        with contextlib.suppress(Exception):
            await bot.edit_message_reply_markup(
                chat_id=round_.chat_id,
                message_id=round_.message_id,
                reply_markup=None,
            )
        with contextlib.suppress(Exception):
            await bot.unpin_chat_message(
                chat_id=round_.chat_id,
                message_id=round_.message_id,
            )

    # Post results to the chat
    results_text = format_results_message(
        theme=round_.theme,
        scores=round_scores,
        players=player_map,
        questions=questions,
        skipped=skip_elo,
        mode=round_.mode,
    )
    await bot.send_message(chat_id=round_.chat_id, text=results_text)

    # Group: rivalry callouts after results
    if round_.mode == "group" and not skip_elo and len(sorted_players) >= 2:
        callout = await _build_rivalry_callout(sorted_players, player_map)
        if callout:
            await bot.send_message(chat_id=round_.chat_id, text=callout)

    # Solo: personal DM recap with ELO delta + new rank
    if round_.mode == "solo" and round_scores:
        score = round_scores[0]
        player = player_map.get(score.player_id)
        if player:
            player_answers = [a for a in answers if a.player_id == score.player_id]
            did_finish = len(player_answers) >= len(questions)
            updated = await trivia_db.get_player_by_id(player.id)
            rank, total = await trivia_db.get_player_rank(player.id, chat_id=0)
            await _send_solo_recap(bot, player.telegram_id, score, rank, total, updated, did_finish)

    logger.info(
        f"Scored round {round_.id} in chat {round_.chat_id} — "
        f"{len(round_scores)} players, skip_elo={skip_elo}"
    )


async def _send_solo_recap(
    bot: object,
    telegram_id: int,
    score: trivia_db.RoundScore,
    rank: int,
    total_players: int,
    updated_player: trivia_db.Player | None,
    did_finish: bool = True,
) -> None:
    """DM a solo player their personalised end-of-day results."""
    from aiogram import Bot as AioBot

    assert isinstance(bot, AioBot)

    sign = "+" if score.elo_delta >= 0 else ""
    elo_emoji = "📈" if score.elo_delta > 0 else ("📉" if score.elo_delta < 0 else "➡️")

    lines = [
        "🌙 <b>Today's results are in!</b>",
        "",
    ]

    if did_finish:
        lines.append(f"Score: <b>{score.correct_count}/{score.total_questions}</b>")
    else:
        lines.append(
            f"Score: <b>{score.correct_count}/{score.total_questions}</b> "
            f"(⏰ time ran out before you finished)"
        )

    lines += [
        f"ELO: {score.elo_before} → <b>{score.elo_after}</b> ({sign}{score.elo_delta}) {elo_emoji}",
        f"Rank: <b>#{rank} of {total_players}</b>",
    ]

    if updated_player and updated_player.streak_current >= 3:
        lines.append(f"\n🔥 {updated_player.streak_current}-day streak — you're on fire!")

    if not did_finish:
        lines.append("\nRan out of time — tomorrow's a fresh start. 🎯")
    elif score.correct_count == score.total_questions:
        lines.append("\nPerfect score! 🎯 Come back tomorrow to defend it.")
    elif score.elo_delta > 0:
        lines.append("\nGood round! 💪 See you tomorrow.")
    else:
        lines.append("\nTough one — tomorrow's a fresh start. 🎯")

    with contextlib.suppress(Exception):
        await bot.send_message(chat_id=telegram_id, text="\n".join(lines))

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
    with contextlib.suppress(Exception):
        await bot.send_message(
            chat_id=telegram_id,
            text="Want to keep playing? No ELO on the line — just for fun 🎮",
            reply_markup=play_again_keyboard,
        )


async def _build_rivalry_callout(
    sorted_players: list[int],
    player_map: dict[int, trivia_db.Player],
) -> str | None:
    """Return a rivalry callout message for the group, or None if nothing interesting."""
    from itertools import combinations

    lines: list[str] = []

    # Collect all rivalry records for pairs who played this round
    pairs: list[tuple[str, int]] = []  # (formatted line, closeness score)
    for pid_a, pid_b in combinations(sorted_players, 2):
        rivalry = await trivia_db.get_rivalry(pid_a, pid_b)
        if rivalry is None:
            continue
        total = rivalry.a_wins + rivalry.b_wins + rivalry.ties
        if total < 2:
            continue  # need at least 2 rounds of history to be meaningful

        pa = player_map.get(pid_a)
        pb = player_map.get(pid_b)
        if not pa or not pb:
            continue

        # Orient wins from pid_a's perspective
        a_wins = rivalry.a_wins if rivalry.player_a_id == pid_a else rivalry.b_wins
        b_wins = rivalry.b_wins if rivalry.player_a_id == pid_a else rivalry.a_wins
        na, nb = pa.display_name, pb.display_name

        diff = abs(a_wins - b_wins)
        if a_wins == b_wins:
            line = f"⚔️ <b>{na}</b> and <b>{nb}</b> — dead level at {a_wins} each. Someone break it."
        elif diff == 1:
            leader, trailer = (na, nb) if a_wins > b_wins else (nb, na)
            lw, tw = max(a_wins, b_wins), min(a_wins, b_wins)
            line = f"👀 <b>{leader}</b> edges <b>{trailer}</b> {lw}-{tw} — very close series"
        else:
            leader, trailer = (na, nb) if a_wins > b_wins else (nb, na)
            lw, tw = max(a_wins, b_wins), min(a_wins, b_wins)
            line = f"🔥 <b>{leader}</b> leads <b>{trailer}</b> {lw}-{tw}"

        pairs.append((line, diff))  # lower diff = more interesting

    if not pairs:
        return None

    # Sort by closeness (ties first, then 1-gap, etc.) and take top 3
    pairs.sort(key=lambda x: x[1])
    lines = [p[0] for p in pairs[:3]]

    return "<b>Head to head:</b>\n" + "\n".join(lines)


async def job_streak_warning() -> None:
    """Send a daily nudge DM to solo players whose streak will die at midnight."""
    at_risk = await trivia_db.get_at_risk_solo_players(min_streak=3)
    if not at_risk:
        return

    bot = get_bot()
    for player in at_risk:
        with contextlib.suppress(Exception):
            await bot.send_message(
                chat_id=player.telegram_id,
                text=(
                    f"⚠️ Your <b>{player.streak_current}-round streak</b> ends "
                    "at midnight if you don't play today!\n\n"
                    "Type /play to keep it alive. 🔥"
                ),
            )
    logger.info(f"Sent streak warnings to {len(at_risk)} players")


def create_scheduler() -> AsyncIOScheduler:
    """Create and return the scheduler. Caller must call .start()."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(job_resolve_expired_votes, "interval", seconds=60)
    scheduler.add_job(job_score_expired_rounds, "interval", seconds=60)
    scheduler.add_job(job_streak_warning, "cron", hour=15, minute=0)
    return scheduler
