import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.shift_machine_assignment import ShiftMachineAssignment
from app.models.shift_mechanic import ShiftMechanic
from app.models.user import User, UserRole
from app.services.shift_service import shift_service

REMINDER_TIMES = {
    time(7, 30),
    time(19, 30),
}


async def reminder_recipients(shift_id: int) -> set[int]:
    recipients = set(settings.admin_ids)

    async with SessionLocal() as session:
        admin_result = await session.execute(
            select(User.telegram_id).where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
                User.telegram_id > 0,
            )
        )
        recipients.update(admin_result.scalars().all())

        mechanic_result = await session.execute(
            select(User.telegram_id)
            .join(ShiftMechanic, ShiftMechanic.user_id == User.id)
            .where(
                ShiftMechanic.shift_id == shift_id,
                User.is_active.is_(True),
                User.telegram_id > 0,
            )
        )
        recipients.update(mechanic_result.scalars().all())

        assignment_result = await session.execute(
            select(User.telegram_id)
            .join(ShiftMachineAssignment, ShiftMachineAssignment.user_id == User.id)
            .where(
                ShiftMachineAssignment.shift_id == shift_id,
                User.is_active.is_(True),
                User.telegram_id > 0,
            )
        )
        recipients.update(assignment_result.scalars().all())

    return recipients


async def notify_shift_close_reminder(bot: Bot) -> None:
    active = await shift_service.get_active_shift()

    if active is None:
        return

    recipients = await reminder_recipients(active.id)

    if not recipients:
        return

    text = (
        "Напоминание: через 30 минут следующая смена.\n\n"
        f"Открыта смена №{active.shift_number}. "
        "Проверьте отчёт и закройте смену, чтобы новая не стартовала поверх старой."
    )

    for telegram_id in recipients:
        try:
            await bot.send_message(telegram_id, text)
        except Exception:
            pass


async def shift_close_reminder_loop(bot: Bot) -> None:
    timezone = ZoneInfo(settings.TIMEZONE)
    sent_keys: set[tuple[int, str, str]] = set()

    while True:
        now = datetime.now(timezone)
        current_time = now.time().replace(second=0, microsecond=0)

        if current_time in REMINDER_TIMES:
            active = await shift_service.get_active_shift()

            if active is not None:
                key = (active.id, now.date().isoformat(), current_time.isoformat())

                if key not in sent_keys:
                    await notify_shift_close_reminder(bot)
                    sent_keys.add(key)

        await asyncio.sleep(60)
