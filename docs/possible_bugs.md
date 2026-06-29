# Possible Bugs

Simple language. Each bug explains what breaks, why, and how bad it is.

---

## 🔴 Fix These First (Will Definitely Happen)

### 1. The quiz generator crashes silently
**What happens:** When someone picks a topic, the bot asks an AI to make 5 questions. Sometimes the AI is slow or sends back gibberish. When that happens, the bot just... stops. No message. The player sits there waiting forever.

**Why:** Errors during question generation aren't caught and reported back to the user.

**How bad:** Very bad. Common enough that real users will hit it.

---

### 2. GIF fails and the bot goes quiet
**What happens:** The bot tries to send a GIF. Giphy is down, or the URL is broken. The bot suppresses the error and tries to send a plain text fallback — but the fallback sometimes also fails silently (especially for `/funfacts` where the text is too long for a GIF caption). Nothing arrives.

**Why:** The fallback after a GIF failure isn't always safe either.

**How bad:** Bad for UX. Player sees nothing after picking a topic or requesting fun facts.

---

### 3. Player starts a quiz 2 minutes before midnight
**What happens:** Someone starts their daily solo quiz at 11:58pm. At midnight, the bot's automatic scoring job fires and tries to score their round — but they've only answered 2 out of 5 questions. They get a midnight DM saying they scored 2/5, even though they weren't done.

**Why:** The scorer doesn't check if the player actually finished. It just scores whatever answers exist when time's up.

**How bad:** Annoying and confusing. Will definitely happen to night-owl players.

---

### 4. `/funfacts` goes completely silent in groups
**What happens:** Someone types `/funfacts` in a group, picks a topic. The bot generates 5 facts and tries to attach them as a GIF caption. Telegram only allows 1024 characters in a caption — 5 fun facts easily exceeds that. The GIF send fails silently, then the plain text fallback also tries to send the same long text... and also fails silently. Nothing appears.

**Why:** No length check before sending, and the fallback has the same problem.

**How bad:** `/funfacts` is completely broken in groups for long responses.

---

## 🟡 Fix These Soon (Will Happen Occasionally)

### 5. Vote resolution can run twice if the bot restarts at the wrong moment
**What happens:** The bot is in the middle of resolving a topic vote and generating questions. Someone restarts the bot. When it comes back, the scheduler fires again and tries to resolve the same vote — creating duplicate questions for the round.

**Why:** `_score_round` is protected against this (it marks the round closed immediately). But `_resolve_vote` has no such guard.

**How bad:** Medium. Players get duplicate quiz messages. Confusing but not data-corrupting.

---

### 6. `/score` gets slow with large groups
**What happens:** In a group with lots of players, `/score` fetches each player's info one at a time from the database. With 50 players that's 50 separate database calls in a row.

**Why:** The code loops and awaits each player individually instead of fetching them all at once.

**How bad:** Low now (small groups), but will feel sluggish as groups grow.

---

### 7. Practice rounds pile up in the database
**What happens:** A solo player keeps tapping "Play again for fun" 30 times. Each tap creates a new round with 5 questions in the database. No limit is enforced.

**Why:** Practice rounds aren't capped per player per day.

**How bad:** Low risk of real harm, but wastes database space and could slow things down over time.

---

## 🟢 Weird Edge Cases (Annoying But Not Broken)

### 8. One person plays alone in a group round
**What happens:** Someone starts a group trivia round and nobody else joins. They answer all 5 questions alone. The results message says "Solo effort doesn't move the ELO needle — drag someone in next time!" — which makes sense, but it sounds odd when it appears in a group chat.

**Why:** The message was written for solo mode but appears in group context too.

**How bad:** Just a confusing message. Easy fix.

---

### 9. Streak warning DM arrives at 3am for some players
**What happens:** The bot sends streak warning messages at 15:00 UTC every day. For players in timezones like India (UTC+5:30) or Australia (UTC+10), that's late at night or the middle of the night. Nobody wants a push notification at 3am reminding them to play trivia.

**Why:** The warning time is hardcoded to 15:00 UTC with no timezone awareness.

**How bad:** Mildly annoying. Could make players turn off notifications.

---

### 10. Mid-practice `/play` causes confusion
**What happens:** A player is in the middle of a "play for fun" practice round. They type `/play` anyway. The bot lets them start a real daily round because `/play` only checks for `mode='solo'` rounds, not `mode='practice'` ones. Now they have two active quizzes.

**Why:** The "already playing today?" check doesn't look at practice rounds.

**How bad:** Confusing UX. They might think the practice round is their real one.

---

## Priority Order for Fixing

1. ✅ Silent crash when questions fail to generate (#1)
2. ✅ `/funfacts` goes silent in groups (#4)
3. ✅ GIF fallback goes silent (#2)
4. ✅ Midnight scorer catches unfinished players (#3)
5. ✅ Vote resolution double-fire on restart (#5)
6. ✅ Mid-practice `/play` confusion (#10)
7. ✅ Practice rounds pile up (#7)
8. ✅ Weird solo-in-group message (#8)
9. `/score` slow with large groups (#6) — low risk until group grows past ~20 players
10. Streak warning timezone (#9) — annoying for non-UTC users, fix when internationalising
