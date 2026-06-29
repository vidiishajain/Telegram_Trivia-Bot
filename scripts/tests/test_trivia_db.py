"""Integration tests: trivia_db service against a live Neon database.

Applies migrations, runs a full round lifecycle for both group and solo modes,
tests topic voting, and verifies ELO/streak/rivalry logic.

    uv run pytest -m integration scripts/tests/test_trivia_db.py

Skips automatically if DATABASE_URL isn't set in .env.
"""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from agent.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"

# Test telegram IDs — large numbers unlikely to clash with real users
_T1 = 990_000_001
_T2 = 990_000_002
_T3 = 990_000_003
_GROUP_CHAT = -990_000_100  # group chats have negative IDs in Telegram


def _db_ready() -> bool:
    try:
        return bool(get_settings().database_url)
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _db_ready(), reason="DATABASE_URL not set in .env"),
]


@pytest.fixture(scope="session", autouse=True)
async def _db_session():  # type: ignore[return]
    """Apply migrations once for the whole test session. Close pool at end."""
    from agent.services import db

    await db.apply_migrations(MIGRATIONS_DIR)
    yield
    await db.close_pool()


@pytest.fixture(scope="session")
async def group_season():
    """A group-scoped season for the test group chat."""
    from agent.services import trivia_db

    return await trivia_db.create_season(
        name="Test Group Season",
        started_at=date.today(),
        chat_id=_GROUP_CHAT,
    )


@pytest.fixture(scope="session")
async def solo_season():
    """The global solo season (chat_id=0)."""
    from agent.services import trivia_db

    return await trivia_db.create_season(
        name="Test Solo Season",
        started_at=date.today(),
        chat_id=0,
    )


# ---------------------------------------------------------------------------
# Migration idempotency
# ---------------------------------------------------------------------------


async def test_migrations_apply() -> None:
    """apply_migrations() is idempotent — second call applies nothing new."""
    from agent.services import db

    applied_again = await db.apply_migrations(MIGRATIONS_DIR)
    assert applied_again == [], f"Expected no new migrations, got {applied_again}"


# ---------------------------------------------------------------------------
# Season
# ---------------------------------------------------------------------------


async def test_season_create_and_get(group_season, solo_season) -> None:
    from agent.services import trivia_db

    assert group_season.id > 0
    assert group_season.chat_id == _GROUP_CHAT

    active_group = await trivia_db.get_active_season(chat_id=_GROUP_CHAT)
    assert active_group is not None
    assert active_group.chat_id == _GROUP_CHAT  # correct chat scope

    active_solo = await trivia_db.get_active_season(chat_id=0)
    assert active_solo is not None
    assert active_solo.chat_id == 0


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


async def test_player_upsert_and_get(group_season) -> None:
    from agent.services import trivia_db

    # Create a group player
    p = await trivia_db.upsert_player(
        telegram_id=_T1,
        display_name="Alice",
        username="alice",
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
    )
    assert p.telegram_id == _T1
    assert p.chat_id == _GROUP_CHAT
    assert p.elo == 1200
    assert p.streak_current == 0

    # get_player by telegram_id + chat_id
    fetched = await trivia_db.get_player(_T1, chat_id=_GROUP_CHAT)
    assert fetched is not None
    assert fetched.id == p.id
    assert fetched.display_name == "Alice"


async def test_player_upsert_idempotent(group_season) -> None:
    """upsert_player is safe to call twice — updates display_name, same row."""
    from agent.services import trivia_db

    p1 = await trivia_db.upsert_player(_T2, "Bob", "bob", _GROUP_CHAT, group_season.id)
    p2 = await trivia_db.upsert_player(_T2, "Bob Updated", "bob2", _GROUP_CHAT, group_season.id)
    assert p1.id == p2.id
    assert p2.display_name == "Bob Updated"


async def test_same_user_solo_and_group(group_season, solo_season) -> None:
    """Same telegram user gets separate rows for solo (chat_id=0) and group."""
    from agent.services import trivia_db

    group_p = await trivia_db.upsert_player(_T3, "Carol", "carol", _GROUP_CHAT, group_season.id)
    solo_p = await trivia_db.upsert_player(_T3, "Carol", "carol", 0, solo_season.id)

    assert group_p.id != solo_p.id, "Separate rows for group vs solo"
    assert group_p.telegram_id == solo_p.telegram_id == _T3
    assert group_p.chat_id == _GROUP_CHAT
    assert solo_p.chat_id == 0


# ---------------------------------------------------------------------------
# Topic voting (group mode only)
# ---------------------------------------------------------------------------


async def test_topic_voting_majority(group_season) -> None:
    from agent.services import trivia_db

    now = datetime.now(tz=UTC)
    round_ = await trivia_db.create_round(
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
        mode="group",
        scheduled_for=now,
        closes_at=now + timedelta(hours=2),
        topic_vote_ends_at=now + timedelta(minutes=5),
    )
    assert round_.status == "voting"
    assert round_.theme == ""

    # Register two test players for this chat
    p1 = await trivia_db.upsert_player(990_001, "V1", None, _GROUP_CHAT, group_season.id)
    p2 = await trivia_db.upsert_player(990_002, "V2", None, _GROUP_CHAT, group_season.id)
    p3 = await trivia_db.upsert_player(990_003, "V3", None, _GROUP_CHAT, group_season.id)

    # Two out of three vote for "Science" — that's >50% of 3 registered players
    await trivia_db.record_topic_vote(round_.id, p1.id, "Science")
    await trivia_db.record_topic_vote(round_.id, p2.id, "Science")
    await trivia_db.record_topic_vote(round_.id, p3.id, "History")

    counts = await trivia_db.get_vote_counts(round_.id)
    assert counts["Science"] == 2
    assert counts["History"] == 1

    winner = trivia_db.check_majority_topic(counts, total_players=3)
    assert winner == "Science"


async def test_topic_vote_change(group_season) -> None:
    """Player can change their vote — only last vote counts."""
    from agent.services import trivia_db

    now = datetime.now(tz=UTC)
    round_ = await trivia_db.create_round(
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
        mode="group",
        scheduled_for=now,
        closes_at=now + timedelta(hours=2),
        topic_vote_ends_at=now + timedelta(minutes=5),
    )
    p = await trivia_db.upsert_player(990_004, "Flipper", None, _GROUP_CHAT, group_season.id)

    await trivia_db.record_topic_vote(round_.id, p.id, "Sports")
    await trivia_db.record_topic_vote(round_.id, p.id, "Music")  # changed mind

    counts = await trivia_db.get_vote_counts(round_.id)
    assert counts.get("Music") == 1
    assert counts.get("Sports") is None  # old vote gone


async def test_no_majority_returns_none() -> None:
    """check_majority_topic returns None when no topic has >50%."""
    from agent.services import trivia_db

    counts = {"Science": 2, "History": 2}
    assert trivia_db.check_majority_topic(counts, total_players=4) is None

    counts2 = {"Science": 1, "History": 1, "Sports": 1}
    assert trivia_db.check_majority_topic(counts2, total_players=3) is None


# ---------------------------------------------------------------------------
# Full round lifecycle (group mode)
# ---------------------------------------------------------------------------


async def test_full_round_lifecycle(group_season) -> None:
    """season → round → questions → answers → scoring → rivalry — full cycle."""
    from agent.services import trivia_db
    from agent.services.scoring import PlayerScore, compute_round_elos

    p1 = await trivia_db.upsert_player(990_010, "P1", None, _GROUP_CHAT, group_season.id)
    p2 = await trivia_db.upsert_player(990_011, "P2", None, _GROUP_CHAT, group_season.id)
    streak_before = p1.streak_current
    rounds_before = p1.total_rounds
    correct_before = p1.total_correct

    # Create an already-expired open round (skip voting for test simplicity)
    now = datetime.now(tz=UTC)
    round_ = await trivia_db.create_round(
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
        mode="group",
        scheduled_for=now - timedelta(hours=3),
        closes_at=now - timedelta(hours=1),
    )
    # Move past voting straight to open
    await trivia_db.set_round_theme(round_.id, "Ancient Rome")
    await trivia_db.set_round_status(round_.id, "open")

    qs = await trivia_db.save_questions(
        round_.id,
        [
            {
                "question_text": "Who founded Rome?",
                "choice_a": "Romulus",
                "choice_b": "Remus",
                "choice_c": "Caesar",
                "choice_d": "Augustus",
                "correct_choice": "A",
                "explanation": "Romulus is the legendary founder of Rome in 753 BC.",
            },
            {
                "question_text": "What language did Romans speak?",
                "choice_a": "Greek",
                "choice_b": "Latin",
                "choice_c": "Etruscan",
                "choice_d": "Oscan",
                "correct_choice": "B",
                "explanation": "Latin was the official language of the Roman Republic and Empire.",
            },
            {
                "question_text": "What is the Colosseum?",
                "choice_a": "Temple",
                "choice_b": "Palace",
                "choice_c": "Amphitheatre",
                "choice_d": "Forum",
                "correct_choice": "C",
                "explanation": "The Colosseum is an elliptical amphitheatre completed in 80 AD.",
            },
        ],
    )
    assert len(qs) == 3
    assert qs[0].position == 1

    # p1 answers all correctly; p2 gets 1/3
    await trivia_db.record_answer(round_.id, qs[0].id, p1.id, "A")
    await trivia_db.record_answer(round_.id, qs[1].id, p1.id, "B")
    await trivia_db.record_answer(round_.id, qs[2].id, p1.id, "C")
    await trivia_db.record_answer(round_.id, qs[0].id, p2.id, "B")  # wrong
    await trivia_db.record_answer(round_.id, qs[1].id, p2.id, "B")  # correct
    await trivia_db.record_answer(round_.id, qs[2].id, p2.id, "D")  # wrong

    # p1 changes Q1 answer (still correct — upsert)
    await trivia_db.record_answer(round_.id, qs[0].id, p1.id, "A")

    respondents = await trivia_db.get_round_respondents(round_.id)
    assert set(respondents) == {p1.id, p2.id}

    # Compute ELO and save
    player_scores = [
        PlayerScore(player_id=p1.id, elo=p1.elo, correct=3, total=3),
        PlayerScore(player_id=p2.id, elo=p2.elo, correct=1, total=3),
    ]
    elo_updates = compute_round_elos(player_scores)
    by_pid = {u.player_id: u for u in elo_updates}

    round_scores = [
        trivia_db.RoundScore(
            round_id=round_.id,
            player_id=pid,
            correct_count=next(s.correct for s in player_scores if s.player_id == pid),
            total_questions=3,
            rank=rank,
            elo_before=by_pid[pid].elo_before,
            elo_after=by_pid[pid].elo_after,
            elo_delta=by_pid[pid].delta,
        )
        for rank, pid in enumerate(sorted(by_pid, key=lambda x: -by_pid[x].delta), start=1)
    ]

    await trivia_db.save_round_results(
        round_id=round_.id,
        scores=round_scores,
        absent_player_ids=[],
    )

    updated_round = await trivia_db.get_round(round_.id)
    assert updated_round is not None
    assert updated_round.status == "scored"

    updated_p1 = await trivia_db.get_player_by_id(p1.id)
    updated_p2 = await trivia_db.get_player_by_id(p2.id)
    assert updated_p1 is not None and updated_p2 is not None
    assert updated_p1.elo > 1200, "Winner should gain ELO"
    assert updated_p2.elo < 1200, "Loser should lose ELO"
    assert updated_p1.streak_current == streak_before + 1
    assert updated_p1.total_rounds == rounds_before + 1
    assert updated_p1.total_correct == correct_before + 3

    # Rivalry upsert
    rivalry_before = await trivia_db.get_rivalry(p1.id, p2.id)
    total_before = (
        (rivalry_before.a_wins + rivalry_before.b_wins + rivalry_before.ties)
        if rivalry_before
        else 0
    )
    low = min(p1.id, p2.id)
    a_wins = 1 if low == p1.id else 0
    b_wins = 0 if low == p1.id else 1
    await trivia_db.upsert_rivalry(p1.id, p2.id, a_wins, b_wins, 0)

    rivalry = await trivia_db.get_rivalry(p1.id, p2.id)
    assert rivalry is not None
    assert rivalry.a_wins + rivalry.b_wins + rivalry.ties == total_before + 1


# ---------------------------------------------------------------------------
# Streak reset for absent players
# ---------------------------------------------------------------------------


async def test_absent_player_streak_reset(group_season) -> None:
    from agent.services import db, trivia_db

    p = await trivia_db.upsert_player(990_020, "Streaky", None, _GROUP_CHAT, group_season.id)
    await db.execute(
        "UPDATE trivia_players SET streak_current = 5, streak_best = 5 WHERE id = $1",
        p.id,
    )

    now = datetime.now(tz=UTC)
    round_ = await trivia_db.create_round(
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
        mode="group",
        scheduled_for=now - timedelta(hours=2),
        closes_at=now - timedelta(hours=1),
    )
    await trivia_db.set_round_theme(round_.id, "Streak test")
    await trivia_db.set_round_status(round_.id, "open")

    await trivia_db.save_round_results(
        round_id=round_.id,
        scores=[],
        absent_player_ids=[p.id],
    )

    updated = await trivia_db.get_player_by_id(p.id)
    assert updated is not None
    assert updated.streak_current == 0, "Absence should reset streak"
    assert updated.streak_best == 5, "Best streak should be preserved"


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


async def test_leaderboard_ordering(group_season) -> None:
    from agent.services import db, trivia_db

    hi = await trivia_db.upsert_player(990_030, "HighELO", None, _GROUP_CHAT, group_season.id)
    lo = await trivia_db.upsert_player(990_031, "LowELO", None, _GROUP_CHAT, group_season.id)
    await db.execute("UPDATE trivia_players SET elo = 1400 WHERE id = $1", hi.id)
    await db.execute("UPDATE trivia_players SET elo = 900  WHERE id = $1", lo.id)

    board = await trivia_db.get_leaderboard(chat_id=_GROUP_CHAT, limit=100)
    ids = [p.id for p in board]
    assert hi.id in ids and lo.id in ids
    assert ids.index(hi.id) < ids.index(lo.id), "Higher ELO should rank first"


# ---------------------------------------------------------------------------
# Expired round queries
# ---------------------------------------------------------------------------


async def test_expired_rounds_query(group_season) -> None:
    from agent.services import trivia_db

    now = datetime.now(tz=UTC)
    round_ = await trivia_db.create_round(
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
        mode="group",
        scheduled_for=now - timedelta(hours=3),
        closes_at=now - timedelta(hours=1),
    )
    await trivia_db.set_round_theme(round_.id, "Expired round test")
    await trivia_db.set_round_status(round_.id, "open")

    found = await trivia_db.get_open_expired_rounds()
    ids = [r.id for r in found]
    assert round_.id in ids


async def test_expired_voting_query(group_season) -> None:
    from agent.services import trivia_db

    now = datetime.now(tz=UTC)
    round_ = await trivia_db.create_round(
        chat_id=_GROUP_CHAT,
        season_id=group_season.id,
        mode="group",
        scheduled_for=now - timedelta(minutes=10),
        closes_at=now + timedelta(hours=2),
        topic_vote_ends_at=now - timedelta(minutes=1),  # voting already expired
    )
    assert round_.status == "voting"

    found = await trivia_db.get_voting_expired_rounds()
    ids = [r.id for r in found]
    assert round_.id in ids
