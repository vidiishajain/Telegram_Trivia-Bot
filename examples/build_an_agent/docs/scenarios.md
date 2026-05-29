# Scenarios

> **Worked example** for the terminal idea generator. (Stage 3: concrete walkthroughs.)

## Happy path

1. User runs `uv run python examples/build_an_agent/main.py`.
2. Prompt: *"What kind of agent would you like to build?"* → user types
   `a playful agent that helps me cook dinner from what's in my fridge`.
3. App shows "🔬 Researching… → 🧠 Designing…", then prints a titled idea
   (e.g. *"FridgeLine Chef"*) with a one-liner, why it's fun, what it does, the services
   it'd use, and a first step.
4. The idea is saved to `ideas/fridgeline-chef.md`.

**Expected:** a concrete, buildable, fun idea on screen and on disk, in well under a minute.

## Edge cases

- **Empty / gibberish input** (`asdfgh`) → expected: still returns a playful, generic-but-
  concrete idea; never crashes.
- **A very broad topic** (`health`) → expected: narrows to one specific, doable angle, not a
  vague platform.
