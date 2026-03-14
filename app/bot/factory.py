from aiogram import Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from app.models import BotTenant


def build_dispatcher(bot_config: BotTenant) -> Dispatcher:
    router = Router(name=f"tenant_{bot_config.id}")
    menu_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=bot_config.menu_button_label)],
            [KeyboardButton(text="Admin bilan bog'lanish")],
        ],
        resize_keyboard=True,
    )

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        await message.answer(bot_config.welcome_text, reply_markup=menu_keyboard)

    @router.message(Command("menu"))
    async def handle_menu(message: Message) -> None:
        await message.answer("Asosiy menyu:", reply_markup=menu_keyboard)

    @router.message(F.text == bot_config.menu_button_label)
    async def handle_main_action(message: Message) -> None:
        text = bot_config.description or "Bot oqimi keyingi iteratsiyada chuqurlashtiriladi."
        await message.answer(text)

    @router.message(F.text == "Admin bilan bog'lanish")
    async def handle_support(message: Message) -> None:
        await message.answer(bot_config.support_text)

    @router.message()
    async def fallback(message: Message) -> None:
        await message.answer("Buyruq qabul qilindi. Davomiy logika keyingi bosqichda qo'shiladi.")

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
