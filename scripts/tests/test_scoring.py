"""Unit tests for the ELO scoring engine — offline, no DB or LLM needed.

uv run pytest scripts/tests/test_scoring.py
"""

from agent.services.scoring import (
    PlayerScore,
    apply_season_reset,
    compute_round_elos,
    get_k_factor,
)

# ---------------------------------------------------------------------------
# K-factor
# ---------------------------------------------------------------------------


def test_k_factor_new_player() -> None:
    assert get_k_factor(0) == 40
    assert get_k_factor(9) == 40


def test_k_factor_mid_player() -> None:
    assert get_k_factor(10) == 24
    assert get_k_factor(49) == 24


def test_k_factor_established() -> None:
    assert get_k_factor(50) == 16
    assert get_k_factor(999) == 16


# ---------------------------------------------------------------------------
# Solo and empty rounds
# ---------------------------------------------------------------------------


def test_solo_player_no_elo_change() -> None:
    """One player: no pairwise matches, zero ELO change."""
    players = [PlayerScore(player_id=1, elo=1200, correct=5, total=5)]
    updates = compute_round_elos(players)
    assert len(updates) == 1
    assert updates[0].delta == 0
    assert updates[0].elo_after == 1200


def test_empty_round_returns_empty() -> None:
    assert compute_round_elos([]) == []


# ---------------------------------------------------------------------------
# Two-player rounds
# ---------------------------------------------------------------------------


def test_equal_rating_winner_gains() -> None:
    """Two equal-rated players: winner gains, loser loses by a symmetric amount."""
    players = [
        PlayerScore(player_id=1, elo=1200, correct=5, total=5),
        PlayerScore(player_id=2, elo=1200, correct=2, total=5),
    ]
    updates = compute_round_elos(players)
    by_id = {u.player_id: u for u in updates}

    assert by_id[1].delta > 0, "Winner should gain ELO"
    assert by_id[2].delta < 0, "Loser should lose ELO"
    # At equal ratings the ELO exchange is symmetric
    assert abs(by_id[1].delta) == abs(by_id[2].delta)


def test_upset_lower_rated_wins_more() -> None:
    """Underdog winning earns more ELO than a top-seeded player winning."""
    # Favourite wins (expected)
    favoured = [
        PlayerScore(player_id=1, elo=1400, correct=5, total=5),
        PlayerScore(player_id=2, elo=1000, correct=2, total=5),
    ]
    upset = [
        PlayerScore(player_id=1, elo=1000, correct=5, total=5),  # underdog wins
        PlayerScore(player_id=2, elo=1400, correct=2, total=5),
    ]
    fav_updates = {u.player_id: u for u in compute_round_elos(favoured)}
    upset_updates = {u.player_id: u for u in compute_round_elos(upset)}

    # Underdog gains more from an upset win than favourite from expected win
    assert upset_updates[1].delta > fav_updates[1].delta


def test_tie_at_equal_rating_is_neutral() -> None:
    """Draw between equal-rated players: both gain 0 (expected outcome)."""
    players = [
        PlayerScore(player_id=1, elo=1200, correct=3, total=5),
        PlayerScore(player_id=2, elo=1200, correct=3, total=5),
    ]
    updates = compute_round_elos(players)
    for u in updates:
        assert u.delta == 0, "Draw at equal rating should be neutral"


def test_tie_underdog_gains() -> None:
    """Draw between unequal players: lower-rated player gains, higher loses."""
    players = [
        PlayerScore(player_id=1, elo=1400, correct=3, total=5),
        PlayerScore(player_id=2, elo=1000, correct=3, total=5),
    ]
    updates = {u.player_id: u for u in compute_round_elos(players)}
    assert updates[2].delta > 0, "Underdog gains from a draw"
    assert updates[1].delta < 0, "Favourite loses ELO from a draw"


# ---------------------------------------------------------------------------
# Multi-player rounds
# ---------------------------------------------------------------------------


def test_three_players_sum_is_zero() -> None:
    """Total ELO in the system is conserved across a round."""
    players = [
        PlayerScore(player_id=1, elo=1200, correct=5, total=5),
        PlayerScore(player_id=2, elo=1200, correct=3, total=5),
        PlayerScore(player_id=3, elo=1200, correct=1, total=5),
    ]
    updates = compute_round_elos(players)
    total_delta = sum(u.delta for u in updates)
    # Due to integer rounding this may not be exactly 0 but should be very close
    assert abs(total_delta) <= 2, f"ELO should be roughly conserved; got delta sum {total_delta}"


def test_ranking_order_preserved() -> None:
    """Player who scores highest always ends up with highest ELO after the round."""
    players = [
        PlayerScore(player_id=1, elo=1200, correct=5, total=5),
        PlayerScore(player_id=2, elo=1200, correct=3, total=5),
        PlayerScore(player_id=3, elo=1200, correct=0, total=5),
    ]
    updates = {u.player_id: u for u in compute_round_elos(players)}
    assert updates[1].elo_after > updates[2].elo_after > updates[3].elo_after


def test_elo_floor_at_100() -> None:
    """Ratings can't drop below 100, even with catastrophic losses."""
    players = [
        PlayerScore(player_id=1, elo=105, correct=0, total=5),
        PlayerScore(player_id=2, elo=2000, correct=5, total=5),
    ]
    updates = {u.player_id: u for u in compute_round_elos(players)}
    assert updates[1].elo_after >= 100


# ---------------------------------------------------------------------------
# Season reset
# ---------------------------------------------------------------------------


def test_season_reset_pulls_toward_baseline() -> None:
    players = [
        PlayerScore(player_id=1, elo=1600, correct=0, total=0),
        PlayerScore(player_id=2, elo=800, correct=0, total=0),
        PlayerScore(player_id=3, elo=1200, correct=0, total=0),
    ]
    updates = {u.player_id: u for u in apply_season_reset(players)}

    assert updates[1].elo_after == 1400, "1600 → 1400 (50% toward 1200)"
    assert updates[2].elo_after == 1000, "800 → 1000 (50% toward 1200)"
    assert updates[3].elo_after == 1200, "1200 stays at 1200"


def test_season_reset_preserves_relative_order() -> None:
    players = [
        PlayerScore(player_id=1, elo=1500, correct=0, total=0),
        PlayerScore(player_id=2, elo=1300, correct=0, total=0),
        PlayerScore(player_id=3, elo=1100, correct=0, total=0),
    ]
    updates = sorted(apply_season_reset(players), key=lambda u: -u.elo_after)
    assert [u.player_id for u in updates] == [1, 2, 3]
