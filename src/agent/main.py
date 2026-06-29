"""Entry point — starts the Telegram trivia bot.

Run it:

    uv run agent

Startup sequence:
  1. Load config + set up logging
  2. Apply DB migrations
  3. Register aiogram router
  4. Start APScheduler (scoring + vote resolution jobs)
  5. Start polling Telegram for updates
"""

import asyncio
from pathlib import Path

from aiogram import Dispatcher
from loguru import logger

from agent.agents.trivia_bot import router
from agent.logging_setup import setup_logging
from agent.scheduler import create_scheduler
from agent.services import db
from agent.services.telegram import get_bot

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


async def _run() -> None:
    setup_logging()
    logger.info("Starting TriviaBot…")

    applied = await db.apply_migrations(MIGRATIONS_DIR)
    if applied:
        logger.info(f"Applied {len(applied)} migration(s): {applied}")
    else:
        logger.info("DB schema up to date — no new migrations.")

    from aiogram.types import (
        BotCommand,
        BotCommandScopeAllGroupChats,
        BotCommandScopeAllPrivateChats,
    )

    bot = get_bot()

    # Set command menu — appears when user types "/" in the chat
    await bot.set_my_commands(
        [
            BotCommand(command="play", description="Start your daily trivia round"),
            BotCommand(command="me", description="View your ELO rank and stats"),
            BotCommand(command="funfacts", description="Get 5 fun facts on a topic"),
            BotCommand(command="leaderboard", description="See the global leaderboard"),
            BotCommand(command="help", description="How to play"),
        ],
        scope=BotCommandScopeAllPrivateChats(),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="trivia", description="Start a group trivia round"),
            BotCommand(command="score", description="See who has answered"),
            BotCommand(command="leaderboard", description="Season leaderboard"),
            BotCommand(command="funfacts", description="Get 5 fun facts on a topic"),
            BotCommand(command="help", description="How to play"),
        ],
        scope=BotCommandScopeAllGroupChats(),
    )
    logger.info("Bot commands registered.")

    # Set bot profile photo on first run (only if no photo exists)
    await _maybe_set_bot_photo(bot)

    # Pre-generate topic images in the background so they're ready before first quiz
    import asyncio as _asyncio

    _asyncio.create_task(_prewarm_topic_images())

    dp = Dispatcher()
    dp.include_router(router)

    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started (vote resolver + scorer, every 60s).")

    logger.info("Bot is live — polling for updates.")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await db.close_pool()
        await bot.session.close()
        logger.info("Bot stopped cleanly.")


async def _maybe_set_bot_photo(bot: object) -> None:
    """Generate and set a bot profile photo via fal.ai if no photo is set yet."""
    import asyncio
    import pathlib

    import fal_client
    import httpx
    from aiogram import Bot as AioBot
    from aiogram.types import BufferedInputFile, InputProfilePhotoStatic

    from agent.config import get_settings

    assert isinstance(bot, AioBot)
    settings = get_settings()
    if not settings.fal_key:
        return

    try:
        # Use a marker file to avoid regenerating on every start
        marker = pathlib.Path("/tmp/.triviabot_photo_set")
        already_set = await asyncio.to_thread(marker.exists)
        if already_set:
            return

        logger.info("Generating bot profile photo via fal.ai…")
        result = await asyncio.to_thread(
            fal_client.run,
            "fal-ai/flux/schnell",
            arguments={
                "prompt": (
                    "cute retro game character shaped like a glowing neon question mark, "
                    "holding tiny lightning bolts, surrounded by floating stars and sparkles, "
                    "vibrant gradient background in deep purple and electric blue, "
                    "flat vector illustration, bold outlines, fun and playful, "
                    "perfect circle avatar crop, no text, no letters"
                ),
                "image_size": "square",
                "num_inference_steps": 8,
            },
        )
        image_url = result["images"][0]["url"]
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(image_url)
            image_bytes = resp.content

        photo_file = BufferedInputFile(image_bytes, filename="photo.jpg")
        await bot.set_my_profile_photo(photo=InputProfilePhotoStatic(photo=photo_file))
        await asyncio.to_thread(marker.touch)
        logger.info("Bot profile photo set successfully.")
    except Exception as e:
        logger.warning(f"Could not set bot profile photo: {e}")


async def _prewarm_topic_images() -> None:
    """Generate all topic images in the background at startup."""
    from agent.services.telegram import (
        CELEBRATION_IMAGE_PROMPT,
        TOPIC_IMAGE_PROMPTS,
        get_topic_image,
    )

    keys = list(TOPIC_IMAGE_PROMPTS.keys()) + ["celebration"]
    prompts = {**TOPIC_IMAGE_PROMPTS, "celebration": CELEBRATION_IMAGE_PROMPT}
    for key in keys:
        await get_topic_image(key, prompts.get(key))
    logger.info("Topic images pre-warmed and cached.")


def main() -> None:
    """Entry point for `uv run agent`."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
