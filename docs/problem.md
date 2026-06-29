# Problem

**Stage 1 — Identify the limits of your current agency.**

## The problem, in your words

Running a fun, competitive trivia game in a group chat is something you *could* do manually — post a quiz, collect answers, tally scores — but it collapses almost immediately. The host has to write questions, wait for replies, count correct answers, maintain a spreadsheet for standings, and remember who has a rivalry with whom. In practice, it happens once or twice and then stops. The social energy is there; the administrative overhead kills it.

There's also no memory. You play, scores get posted, and then it's gone. Nobody knows if they've beaten Dana four times in a row or what their ELO would be if the game had kept running for six months. The lack of history means there's no narrative — no grudge matches, no streaks, no seasonal drama.

The specific pain:
- **Question writing** is tedious and inconsistent. Hard to maintain daily themed variety.
- **Scoring** has to be done by hand or with clunky poll tools that don't track history.
- **Standings** live in someone's head or a rarely-updated spreadsheet.
- **Rivalries** are completely invisible — you can feel them, but nobody tracks them.
- **Seasons and playoffs** are just a fantasy unless someone runs the whole thing manually.

## How it's done today

Either: manual quiz posts (poll bot) with no scoring or standings. Or: a hosted trivia platform that isn't connected to your specific friend group, doesn't persist your history, and has no rivalry layer.

## Why an agent (not just a script or a human)

Three things the "intelligence" buys here:

1. **Daily question generation.** A script can't write fresh, themed, well-formed multiple-choice trivia questions every morning. An LLM can — and it can vary themes, calibrate difficulty, and write good distractors.

2. **Rivalry detection and callout writing.** Surfacing *interesting* rivalries from raw win/loss data ("you've lost to Dana 3 times, but you're 4-1 against Alex") and writing callout text that's fun rather than robotic is a natural language task.

3. **Handling the unexpected.** A pure script breaks on edge cases: only one person answers, there's a tie, a player joins mid-season. An agent-backed system can respond gracefully.

The rest — scheduling, scoring, ELO math, DB updates — is deterministic code that a script could do. But you need the LLM for questions and callouts, and you need the database to give those LLM outputs memory.

## Why now

LLMs are good enough to write reliable multiple-choice trivia questions with explanations. Neon + asyncpg makes it practical to maintain 9 tables of relational state without running a dedicated server. aiogram + Railway makes deploying a persistent Telegram bot straightforward. Three years ago this was a significant infrastructure project; today it's an afternoon of architecture and a few evenings of code.
