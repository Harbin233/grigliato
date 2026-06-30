import asyncio

from aiogram import Bot, Dispatcher
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import logger
from app.core.startup import initialize_reference_data
from app.db.session import engine
from app.handlers import routers


async def check_database() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def main() -> None:
    logger.info("========================================")
    logger.info("Production Bot")
    logger.info("Запуск системы...")

    try:
        await check_database()
        logger.success("PostgreSQL ........ OK")

        await initialize_reference_data()
        logger.success("Справочники ...... OK")
    except Exception as error:
        logger.exception(f"Ошибка PostgreSQL: {error}")
        return

    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    for router in routers:
        dp.include_router(router)

    logger.success("Бот успешно запущен")
    logger.info("========================================")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
