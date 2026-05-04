from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from bot import texts

EMPLOYEE_COMMANDS = [
    BotCommand(command="start", description=texts.CMD_START),
    BotCommand(command="grafic", description=texts.CMD_GRAPH),
    BotCommand(command="report", description=texts.CMD_QUICK_REPORT),
    BotCommand(command="profile", description=texts.CMD_PROFILE),
    BotCommand(command="last_reports", description=texts.CMD_LAST_REPORTS)
]

MANAGER_COMMANDS = [
    BotCommand(command="start", description=texts.CMD_START),
    BotCommand(command="report", description=texts.CMD_QUICK_REPORT),
    BotCommand(command="profile", description=texts.CMD_PROFILE),
    BotCommand(command="last_reports", description=texts.CMD_LAST_REPORTS)
]

ADMIN_COMMANDS = [
    BotCommand(command="start", description=texts.CMD_START),
    BotCommand(command="profile", description=texts.CMD_PROFILE),
    BotCommand(command="last_reports", description=texts.CMD_LAST_REPORTS),
    BotCommand(command="active_workers", description=texts.CMD_ACTIVE_WORKERS),
    BotCommand(command="employees", description=texts.CMD_EMPLOYEES),
    BotCommand(command="settings", description=texts.CMD_SETTINGS)
]


async def setup_default_commands(bot: Bot) -> None:
    await bot.set_my_commands(EMPLOYEE_COMMANDS, scope=BotCommandScopeAllPrivateChats())


async def apply_commands_for_chat(bot: Bot, chat_id: int, is_admin: bool, role: str | None = None) -> None:
    if is_admin or role == "admin":
        commands = ADMIN_COMMANDS
    elif role == "manager":
        commands = MANAGER_COMMANDS
    else:
        commands = EMPLOYEE_COMMANDS
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=chat_id))
    except TelegramBadRequest:
        pass
