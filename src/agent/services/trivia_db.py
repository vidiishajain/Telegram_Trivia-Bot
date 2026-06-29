"""Trivia-domain database queries.

All functions talk to Postgres via the shared db.py service.
Each function does one focused thing — callers compose them.

Table prefix: `trivia_` (shared DB convention from CLAUDE.md).

Key design decisions encoded here:
- chat_id=0 means "solo/global" (not NULL — NULL breaks UNIQUE constraints).
- trivia_players.id is a serial PK; telegram_id+chat_id is the user-facing identity.
- Rivalries are naturally per-chat because player rows are per-chat.
"""

from datetime import datetime
from typing import Any

import asyncpg
from pydantic import BaseModel

from agent.services import db

# ---------------------------------------------------------------------------
# Pydantic models (typed wrappers around DB rows)
# ---------------------------------------------------------------------------


class Season(BaseModel):
    id: int
    chat_id: int
    name: str
    started_at: Any  # date
    ended_at: Any | None  # date | None
    playoff_done: bool
    created_at: datetime


class Player(BaseModel):
    id: int
    telegram_id: int
    chat_id: int
    username: str | None
    display_name: str
    elo: int
    streak_current: int
    streak_best: int
    total_rounds: int
    total_correct: int
    season_id: int | None
    joined_at: datetime
    last_active_at: datetime
    is_active: bool


class Round(BaseModel):
    id: int
    chat_id: int
    season_id: int
    mode: str
    theme: str
    status: str
    scheduled_for: datetime
    closes_at: datetime
    topic_vote_ends_at: datetime | None
    message_id: int | None
    scored_at: datetime | None
    created_at: datetime


class Question(BaseModel):
    id: int
    round_id: int
    position: int
    question_text: str
    choice_a: str
    choice_b: str
    choice_c: str
    choice_d: str
    correct_choice: str
    explanation: str | None
    difficulty: int


class Answer(BaseModel):
    id: int
    round_id: int
    question_id: int
    player_id: int
    choice: str
    is_correct: bool | None
    answered_at: datetime
    response_time_s: int | None


class RoundScore(BaseModel):
    round_id: int
    player_id: int
    correct_count: int
    total_questions: int
    rank: int | None
    elo_before: int
    elo_after: int
    elo_delta: int


class Rivalry(BaseModel):
    id: int
    player_a_id: int
    player_b_id: int
    a_wins: int
    b_wins: int
    ties: int
    last_played_at: datetime | None


class TopicVote(BaseModel):
    id: int
    round_id: int
    player_id: int
    topic: str
    voted_at: datetime


def _row(record: asyncpg.Record, model: type) -> Any:
    return model(**dict(record))


def _rows(records: list[asyncpg.Record], model: type) -> list[Any]:
    return [_row(r, model) for r in records]


# ---------------------------------------------------------------------------
# Season queries
# ---------------------------------------------------------------------------


async def create_season(name: str, started_at: Any, chat_id: int = 0) -> Season:
    row = await db.fetchrow(
        """
        INSERT INTO trivia_seasons (chat_id, name, started_at)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        chat_id,
        name,
        started_at,
    )
    assert row is not None
    return _row(row, Season)


async def get_active_season(chat_id: int = 0) -> Season | None:
    """Return the running season for a chat (or the global solo season if chat_id=0)."""
    row = await db.fetchrow(
        """
        SELECT * FROM trivia_seasons
        WHERE chat_id = $1 AND ended_at IS NULL
        ORDER BY started_at DESC LIMIT 1
        """,
        chat_id,
    )
    return _row(row, Season) if row else None


async def end_season(season_id: int) -> None:
    await db.execute(
        "UPDATE trivia_seasons SET ended_at = CURRENT_DATE WHERE id = $1",
        season_id,
    )


# ---------------------------------------------------------------------------
# Player queries
# ---------------------------------------------------------------------------


async def upsert_player(
    telegram_id: int,
    display_name: str,
    username: str | None,
    chat_id: int = 0,
    season_id: int | None = None,
) -> Player:
    """Create or update a player for a given (telegram_id, chat_id) context.

    Called on /start (solo, chat_id=0) or first answer tap in a group.
    """
    row = await db.fetchrow(
        """
        INSERT INTO trivia_players (telegram_id, chat_id, display_name, username, season_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (telegram_id, chat_id) DO UPDATE
            SET display_name   = EXCLUDED.display_name,
                username       = EXCLUDED.username,
                last_active_at = NOW()
        RETURNING *
        """,
        telegram_id,
        chat_id,
        display_name,
        username,
        season_id,
    )
    assert row is not None
    return _row(row, Player)


async def get_player(telegram_id: int, chat_id: int = 0) -> Player | None:
    row = await db.fetchrow(
        "SELECT * FROM trivia_players WHERE telegram_id = $1 AND chat_id = $2",
        telegram_id,
        chat_id,
    )
    return _row(row, Player) if row else None


async def get_player_by_id(player_id: int) -> Player | None:
    row = await db.fetchrow("SELECT * FROM trivia_players WHERE id = $1", player_id)
    return _row(row, Player) if row else None


async def get_chat_players(chat_id: int) -> list[Player]:
    """All active players registered in a group chat."""
    rows = await db.fetch(
        "SELECT * FROM trivia_players WHERE chat_id = $1 AND is_active = TRUE",
        chat_id,
    )
    return _rows(rows, Player)


async def get_leaderboard(chat_id: int = 0, limit: int = 10) -> list[Player]:
    """Top players by ELO for a chat (or global solo leaderboard if chat_id=0)."""
    rows = await db.fetch(
        """
        SELECT * FROM trivia_players
        WHERE chat_id = $1 AND is_active = TRUE
        ORDER BY elo DESC
        LIMIT $2
        """,
        chat_id,
        limit,
    )
    return _rows(rows, Player)


# ---------------------------------------------------------------------------
# Round queries
# ---------------------------------------------------------------------------


async def create_round(
    chat_id: int,
    season_id: int,
    mode: str,
    scheduled_for: datetime,
    closes_at: datetime,
    topic_vote_ends_at: datetime | None = None,
) -> Round:
    """Create a new round.

    Group rounds start with status='voting' and an empty theme.
    Solo rounds start with status='open' and theme is set immediately after.
    """
    initial_status = "voting" if mode == "group" else "open"
    row = await db.fetchrow(
        """
        INSERT INTO trivia_rounds
            (chat_id, season_id, mode, theme, status, scheduled_for, closes_at, topic_vote_ends_at)
        VALUES ($1, $2, $3, '', $4, $5, $6, $7)
        RETURNING *
        """,
        chat_id,
        season_id,
        mode,
        initial_status,
        scheduled_for,
        closes_at,
        topic_vote_ends_at,
    )
    assert row is not None
    return _row(row, Round)


async def get_round(round_id: int) -> Round | None:
    row = await db.fetchrow("SELECT * FROM trivia_rounds WHERE id = $1", round_id)
    return _row(row, Round) if row else None


async def get_active_round(chat_id: int) -> Round | None:
    """Return the in-progress round (voting or open) for a chat, if any."""
    row = await db.fetchrow(
        """
        SELECT * FROM trivia_rounds
        WHERE chat_id = $1 AND status IN ('voting', 'open')
        ORDER BY created_at DESC LIMIT 1
        """,
        chat_id,
    )
    return _row(row, Round) if row else None


async def get_open_expired_rounds() -> list[Round]:
    """Rounds that are open but whose answer window has passed — ready to score."""
    rows = await db.fetch(
        "SELECT * FROM trivia_rounds WHERE status = 'open' AND closes_at <= NOW()"
    )
    return _rows(rows, Round)


async def get_voting_expired_rounds() -> list[Round]:
    """Rounds still in voting whose topic_vote_ends_at has passed — force-pick a topic."""
    rows = await db.fetch(
        """
        SELECT * FROM trivia_rounds
        WHERE status = 'voting' AND topic_vote_ends_at <= NOW()
        """
    )
    return _rows(rows, Round)


async def set_round_status(round_id: int, status: str) -> None:
    await db.execute(
        "UPDATE trivia_rounds SET status = $1 WHERE id = $2",
        status,
        round_id,
    )


async def set_round_theme(round_id: int, theme: str) -> None:
    await db.execute(
        "UPDATE trivia_rounds SET theme = $1 WHERE id = $2",
        theme,
        round_id,
    )


async def set_round_message_id(round_id: int, message_id: int) -> None:
    await db.execute(
        "UPDATE trivia_rounds SET message_id = $1 WHERE id = $2",
        message_id,
        round_id,
    )


async def get_todays_round(chat_id: int) -> "Round | None":
    """Return any round created today for this chat (open or already scored)."""
    row = await db.fetchrow(
        """
        SELECT * FROM trivia_rounds
        WHERE chat_id = $1
          AND mode = 'solo'
          AND scheduled_for >= CURRENT_DATE
          AND status IN ('open', 'scored')
        ORDER BY created_at DESC LIMIT 1
        """,
        chat_id,
    )
    return _row(row, Round) if row else None


async def get_recent_themes(chat_id: int = 0, limit: int = 14) -> list[str]:
    """Recent round themes to help the LLM avoid repeats within a context."""
    rows = await db.fetch(
        """
        SELECT theme FROM trivia_rounds
        WHERE chat_id = $1 AND theme != ''
        ORDER BY scheduled_for DESC LIMIT $2
        """,
        chat_id,
        limit,
    )
    return [r["theme"] for r in rows]


# ---------------------------------------------------------------------------
# Topic voting queries (group mode only)
# ---------------------------------------------------------------------------


async def record_topic_vote(round_id: int, player_id: int, topic: str) -> TopicVote:
    """Upsert a player's topic vote — they can change their vote before voting closes."""
    row = await db.fetchrow(
        """
        INSERT INTO trivia_topic_votes (round_id, player_id, topic)
        VALUES ($1, $2, $3)
        ON CONFLICT (round_id, player_id) DO UPDATE
            SET topic    = EXCLUDED.topic,
                voted_at = NOW()
        RETURNING *
        """,
        round_id,
        player_id,
        topic,
    )
    assert row is not None
    return _row(row, TopicVote)


async def get_vote_counts(round_id: int) -> dict[str, int]:
    """Return {topic: vote_count} for all votes cast in a round."""
    rows = await db.fetch(
        """
        SELECT topic, COUNT(*) AS votes
        FROM trivia_topic_votes
        WHERE round_id = $1
        GROUP BY topic
        ORDER BY votes DESC
        """,
        round_id,
    )
    return {r["topic"]: r["votes"] for r in rows}


async def get_total_votes(round_id: int) -> int:
    row = await db.fetchrow(
        "SELECT COUNT(*) AS n FROM trivia_topic_votes WHERE round_id = $1",
        round_id,
    )
    return int(row["n"]) if row else 0


async def get_topic_voter_ids(round_id: int) -> list[int]:
    """Player IDs who cast a topic vote for this round — the committed players."""
    rows = await db.fetch(
        "SELECT DISTINCT player_id FROM trivia_topic_votes WHERE round_id = $1",
        round_id,
    )
    return [r["player_id"] for r in rows]


def check_majority_topic(vote_counts: dict[str, int], total_players: int) -> str | None:
    """Return the winning topic if any has strictly more than 50% of the engaged group.

    Uses max(registered_players, total_votes_cast) as the denominator so that a
    single voter in a brand-new group can never instantly win by representing 100%
    of "registered" players.  Requires at least 2 votes before any majority fires.
    """
    total_votes = sum(vote_counts.values())
    effective_total = max(total_players, total_votes)
    if effective_total < 2:
        return None
    threshold = effective_total / 2
    for topic, count in vote_counts.items():
        if count > threshold:
            return topic
    return None


# ---------------------------------------------------------------------------
# Question queries
# ---------------------------------------------------------------------------


async def save_questions(round_id: int, questions: list[dict[str, Any]]) -> list[Question]:
    """Save a list of question dicts.

    Expected keys: question_text, choice_a/b/c/d, correct_choice,
    explanation (optional), difficulty (optional, default 2).
    """
    rows = []
    for i, q in enumerate(questions, start=1):
        row = await db.fetchrow(
            """
            INSERT INTO trivia_questions
                (round_id, position, question_text, choice_a, choice_b, choice_c, choice_d,
                 correct_choice, explanation, difficulty)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING *
            """,
            round_id,
            i,
            q["question_text"],
            q["choice_a"],
            q["choice_b"],
            q["choice_c"],
            q["choice_d"],
            q["correct_choice"],
            q.get("explanation"),
            q.get("difficulty", 2),
        )
        assert row is not None
        rows.append(row)
    return _rows(rows, Question)


async def get_round_questions(round_id: int) -> list[Question]:
    rows = await db.fetch(
        "SELECT * FROM trivia_questions WHERE round_id = $1 ORDER BY position",
        round_id,
    )
    return _rows(rows, Question)


# ---------------------------------------------------------------------------
# Answer queries
# ---------------------------------------------------------------------------


async def record_answer(
    round_id: int,
    question_id: int,
    player_id: int,
    choice: str,
    response_time_s: int | None = None,
) -> Answer:
    """Upsert an answer — players can change their choice before the window closes."""
    row = await db.fetchrow(
        """
        INSERT INTO trivia_answers (round_id, question_id, player_id, choice, response_time_s)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (question_id, player_id) DO UPDATE
            SET choice          = EXCLUDED.choice,
                answered_at     = NOW(),
                response_time_s = EXCLUDED.response_time_s
        RETURNING *
        """,
        round_id,
        question_id,
        player_id,
        choice,
        response_time_s,
    )
    assert row is not None
    return _row(row, Answer)


async def get_round_answers(round_id: int) -> list[Answer]:
    rows = await db.fetch(
        "SELECT * FROM trivia_answers WHERE round_id = $1",
        round_id,
    )
    return _rows(rows, Answer)


async def get_round_respondents(round_id: int) -> list[int]:
    """Player IDs who submitted at least one answer for this round."""
    rows = await db.fetch(
        "SELECT DISTINCT player_id FROM trivia_answers WHERE round_id = $1",
        round_id,
    )
    return [r["player_id"] for r in rows]


# ---------------------------------------------------------------------------
# Scoring — single atomic transaction
# ---------------------------------------------------------------------------


async def save_round_results(
    round_id: int,
    scores: list[RoundScore],
    absent_player_ids: list[int],
) -> None:
    """Atomically persist all scoring outputs for a round.

    Saves round_scores, updates player ELO + stats, writes elo_history,
    updates streaks for participants and resets streaks for absent players.
    """
    pool = await db.get_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "UPDATE trivia_rounds SET status = 'scored', scored_at = NOW() WHERE id = $1",
            round_id,
        )

        for s in scores:
            await conn.execute(
                """
                INSERT INTO trivia_round_scores
                    (round_id, player_id, correct_count, total_questions, rank,
                     elo_before, elo_after, elo_delta)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                s.round_id,
                s.player_id,
                s.correct_count,
                s.total_questions,
                s.rank,
                s.elo_before,
                s.elo_after,
                s.elo_delta,
            )

            await conn.execute(
                """
                UPDATE trivia_answers ta
                SET is_correct = (ta.choice = tq.correct_choice)
                FROM trivia_questions tq
                WHERE ta.question_id = tq.id
                  AND ta.round_id = $1
                  AND ta.player_id = $2
                """,
                round_id,
                s.player_id,
            )

            await conn.execute(
                """
                UPDATE trivia_players
                SET elo            = $1,
                    total_rounds   = total_rounds + 1,
                    total_correct  = total_correct + $2,
                    streak_current = streak_current + 1,
                    streak_best    = GREATEST(streak_best, streak_current + 1),
                    last_active_at = NOW()
                WHERE id = $3
                """,
                s.elo_after,
                s.correct_count,
                s.player_id,
            )

            if s.elo_delta != 0:
                await conn.execute(
                    """
                    INSERT INTO trivia_elo_history
                        (player_id, round_id, elo_before, elo_after, delta, reason)
                    VALUES ($1, $2, $3, $4, $5, 'round_score')
                    """,
                    s.player_id,
                    round_id,
                    s.elo_before,
                    s.elo_after,
                    s.elo_delta,
                )

        for pid in absent_player_ids:
            await conn.execute(
                "UPDATE trivia_players SET streak_current = 0 WHERE id = $1",
                pid,
            )


# ---------------------------------------------------------------------------
# Rivalry queries
# ---------------------------------------------------------------------------


def _canonical_pair(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


async def upsert_rivalry(
    player_a_id: int,
    player_b_id: int,
    a_wins_delta: int,
    b_wins_delta: int,
    ties_delta: int,
) -> None:
    low, high = _canonical_pair(player_a_id, player_b_id)
    if player_a_id > player_b_id:
        a_wins_delta, b_wins_delta = b_wins_delta, a_wins_delta

    await db.execute(
        """
        INSERT INTO trivia_rivalries
            (player_a_id, player_b_id, a_wins, b_wins, ties, last_played_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (player_a_id, player_b_id) DO UPDATE
            SET a_wins         = trivia_rivalries.a_wins + EXCLUDED.a_wins,
                b_wins         = trivia_rivalries.b_wins + EXCLUDED.b_wins,
                ties           = trivia_rivalries.ties + EXCLUDED.ties,
                last_played_at = NOW()
        """,
        low,
        high,
        a_wins_delta,
        b_wins_delta,
        ties_delta,
    )


async def get_rivalry(player_a_id: int, player_b_id: int) -> Rivalry | None:
    low, high = _canonical_pair(player_a_id, player_b_id)
    row = await db.fetchrow(
        "SELECT * FROM trivia_rivalries WHERE player_a_id = $1 AND player_b_id = $2",
        low,
        high,
    )
    return _row(row, Rivalry) if row else None


async def get_player_rivalries(player_id: int) -> list[Rivalry]:
    rows = await db.fetch(
        """
        SELECT * FROM trivia_rivalries
        WHERE player_a_id = $1 OR player_b_id = $1
        ORDER BY last_played_at DESC
        """,
        player_id,
    )
    return _rows(rows, Rivalry)


async def get_rivalry_tease_line(voter_ids: list[int]) -> str | None:
    """Best one-line rivalry tease for a group, or None if no history yet.

    Picks the pair with the most rounds played and formats a punchy line.
    Requires at least 2 rounds of history before saying anything.
    """
    from itertools import combinations

    if len(voter_ids) < 2:
        return None

    voter_players: dict[int, Player] = {}
    for pid in voter_ids:
        p = await get_player_by_id(pid)
        if p:
            voter_players[pid] = p

    best_line: str | None = None
    best_total = 0

    for pid_a, pid_b in combinations(list(voter_players.keys()), 2):
        rivalry = await get_rivalry(pid_a, pid_b)
        if rivalry is None:
            continue
        total = rivalry.a_wins + rivalry.b_wins + rivalry.ties
        if total < 2 or total <= best_total:
            continue

        pa = voter_players.get(pid_a)
        pb = voter_players.get(pid_b)
        if not pa or not pb:
            continue

        a_wins = rivalry.a_wins if rivalry.player_a_id == pid_a else rivalry.b_wins
        b_wins = rivalry.b_wins if rivalry.player_a_id == pid_a else rivalry.a_wins
        na, nb = pa.display_name, pb.display_name

        if a_wins == b_wins:
            best_line = (
                f"👀 <b>{na}</b> and <b>{nb}</b> are {a_wins}-{a_wins} all time. "
                "Could be the decider tonight."
            )
        elif a_wins > b_wins:
            best_line = (
                f"👀 <b>{na}</b> leads <b>{nb}</b> {a_wins}-{b_wins} all time. Time for revenge?"
            )
        else:
            best_line = (
                f"👀 <b>{nb}</b> leads <b>{na}</b> {b_wins}-{a_wins} all time. Time for revenge?"
            )
        best_total = total

    return best_line


async def get_at_risk_solo_players(min_streak: int = 3) -> list[Player]:
    """Solo players with a streak >= min_streak who haven't played today.

    Used by the daily streak-warning scheduler job.
    """
    rows = await db.fetch(
        """
        SELECT p.* FROM trivia_players p
        WHERE p.chat_id = 0
          AND p.is_active = TRUE
          AND p.streak_current >= $1
          AND NOT EXISTS (
            SELECT 1 FROM trivia_rounds r
            WHERE r.chat_id = p.telegram_id
              AND r.mode = 'solo'
              AND r.scheduled_for >= CURRENT_DATE
          )
        """,
        min_streak,
    )
    return _rows(rows, Player)


# ---------------------------------------------------------------------------
# Rank + history helpers
# ---------------------------------------------------------------------------


async def get_player_rank(player_id: int, chat_id: int = 0) -> tuple[int, int]:
    """Return (rank, total_players) for a player by ELO within a chat context.

    Rank 1 = highest ELO. Players with equal ELO share the same rank.
    """
    row = await db.fetchrow(
        """
        SELECT
            (SELECT COUNT(*) + 1 FROM trivia_players
             WHERE chat_id = $2 AND is_active = TRUE
               AND elo > (SELECT elo FROM trivia_players WHERE id = $1)) AS rank,
            COUNT(*) AS total
        FROM trivia_players
        WHERE chat_id = $2 AND is_active = TRUE
        """,
        player_id,
        chat_id,
    )
    if row is None:
        return (1, 1)
    return (int(row["rank"]), int(row["total"]))


async def get_last_round_score(player_id: int) -> RoundScore | None:
    """Most recent scored round for this player (used to show ELO delta before next quiz)."""
    row = await db.fetchrow(
        """
        SELECT rs.* FROM trivia_round_scores rs
        JOIN trivia_rounds r ON r.id = rs.round_id
        WHERE rs.player_id = $1
        ORDER BY r.scored_at DESC NULLS LAST LIMIT 1
        """,
        player_id,
    )
    return _row(row, RoundScore) if row else None
