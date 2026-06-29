# User Stories

**Stage 3 — Operationalize success as UX.**

Three types of users: **Player** (anyone in the group game), **New member** (just joined the group), **Admin** (the person who deployed the bot, probably you).

## Stories

### As a player
1. As a player, I want to receive a daily themed quiz at 9am so that I have a fun morning ritual to look forward to.
2. As a player, I want to answer by tapping A/B/C/D inline buttons so that participation is frictionless on mobile.
3. As a player, I want the results posted automatically when the window closes so that I get instant gratification without waiting for a human to tally scores.
4. As a player, I want to see my ELO change explained in the results ("▲ +18 ELO — you beat 3 of 5 opponents") so that the rating system feels fair and legible.
5. As a player, I want rivalry callouts in the results message so that the competition feels personal ("You've lost to Dana 3 rounds in a row — redemption pending").
6. As a player, I want to type `/me` and see my personal stats (ELO, rank, streak, accuracy, head-to-head record) so that I can track my own progress.
7. As a player, I want to type `/leaderboard` and see the season standings so that I always know where I sit in the rankings.
8. As a player, I want to type `/rivalry` and see my head-to-head records with each opponent so that I can strategize and trash-talk with data.
9. As a player, I want my streak shown prominently in results ("🔥 5-day streak!") so that consistency feels rewarded and breaks feel meaningful.
10. As a player, I want to type `/score` mid-round and see who has answered (without seeing their answers) so that I can feel the competitive pressure.

### As a new member
11. As a new group member, I want to type `/join` and immediately be registered so that I can start playing the next round without admin help.
12. As a new member, I want the bot to welcome me and explain how the game works so that I understand what I'm joining.

### As an admin
13. As the admin, I want seasons to end automatically and playoffs to run so that I don't have to manually manage the competition calendar.
14. As the admin, I want `/forcescore` to manually close a round early so that I can recover from scheduling issues without redeploying.
15. As the admin, I want the bot to log errors clearly (not silently fail) so that I can diagnose problems when something goes wrong.

## What "good" feels like

You wake up, the bot has already posted the quiz in the group. You tap your answers in 30 seconds. You go about your day. At 11am your phone buzzes: the results drop. You've moved up one spot in the season standings. The rivalry callout makes you laugh. You mention it to a friend in real life. That's the loop working.

## Out of scope (for now)

- Multiple Telegram groups (one group, one bot instance for now)
- Web leaderboard UI (Telegram messages only)
- Custom question submission by players (LLM-only generation for now)
- Voice/media questions (text only)
- Real-money stakes or prizes
- Difficulty tiers per player (flat difficulty for now)
