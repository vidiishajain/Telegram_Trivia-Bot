"""Pure ELO math for the trivia tournament — no I/O, fully unit-testable.

Algorithm: pairwise decomposition.
  For N players in a round, generate all C(N,2) virtual 1v1 matches.
  Each match outcome is based on normalized score fraction (correct / total).
  Apply standard ELO formula to each virtual match, then sum deltas per player.

References: https://en.wikipedia.org/wiki/Elo_rating_system
"""

from dataclasses import dataclass
from itertools import combinations


@dataclass
class PlayerScore:
    player_id: int
    elo: int
    correct: int
    total: int

    @property
    def fraction(self) -> float:
        return self.correct / self.total if self.total > 0 else 0.0


@dataclass
class ELOUpdate:
    player_id: int
    elo_before: int
    elo_after: int
    delta: int


def get_k_factor(total_rounds_played: int) -> int:
    """Dynamic K-factor that shrinks as a player's rating stabilises."""
    if total_rounds_played < 10:
        return 40
    if total_rounds_played < 50:
        return 24
    return 16


def _expected_score(rating_a: int, rating_b: int) -> float:
    """Probability that player A wins against player B (standard ELO formula)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def _match_outcome(score_a: float, score_b: float) -> tuple[float, float]:
    """Convert two score fractions into a win/draw/loss result (1/0.5/0)."""
    if score_a > score_b:
        return 1.0, 0.0
    if score_b > score_a:
        return 0.0, 1.0
    return 0.5, 0.5


def compute_round_elos(
    players: list[PlayerScore],
    rounds_played: int = 0,
) -> list[ELOUpdate]:
    """Compute ELO changes for all players in one round via pairwise decomposition.

    For N players this generates C(N,2) virtual 1v1 matches, one per pair.
    Each player's total delta is the sum across all their pairwise results,
    divided by (N-1) so total movement stays reasonable as the group grows.

    Absences are handled by the caller — only pass players who actually answered.
    """
    if len(players) < 2:
        # Solo round or empty: no pairwise matches, no ELO change
        return [
            ELOUpdate(
                player_id=p.player_id,
                elo_before=p.elo,
                elo_after=p.elo,
                delta=0,
            )
            for p in players
        ]

    n = len(players)
    k = get_k_factor(rounds_played)
    # Divide K by (N-1) so the maximum swing per round stays ~K regardless of group size
    effective_k = k / (n - 1)

    raw_deltas: dict[int, float] = {p.player_id: 0.0 for p in players}
    by_id = {p.player_id: p for p in players}

    for pa, pb in combinations(players, 2):
        s_a, s_b = _match_outcome(pa.fraction, pb.fraction)
        e_a = _expected_score(pa.elo, pb.elo)
        e_b = 1.0 - e_a

        raw_deltas[pa.player_id] += effective_k * (s_a - e_a)
        raw_deltas[pb.player_id] += effective_k * (s_b - e_b)

    updates = []
    for pid, raw_delta in raw_deltas.items():
        delta = round(raw_delta)
        elo_before = by_id[pid].elo
        elo_after = max(100, elo_before + delta)  # floor at 100 — ratings can't go negative
        updates.append(
            ELOUpdate(
                player_id=pid,
                elo_before=elo_before,
                elo_after=elo_after,
                delta=elo_after - elo_before,
            )
        )
    return updates


def apply_season_reset(players: list[PlayerScore]) -> list[ELOUpdate]:
    """Soft reset at season end: pull all ratings 50% toward the baseline (1200).

    A 1600-rated player becomes 1400; a 900-rated player becomes 1050.
    Relative rankings are preserved; no one resets all the way to 1200.
    """
    baseline = 1200
    updates = []
    for p in players:
        elo_after = round(baseline + (p.elo - baseline) * 0.5)
        updates.append(
            ELOUpdate(
                player_id=p.player_id,
                elo_before=p.elo,
                elo_after=elo_after,
                delta=elo_after - p.elo,
            )
        )
    return updates
