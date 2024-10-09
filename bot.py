import json
import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command
import aiohttp
import logging
from datetime import datetime, timedelta

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load and save user data
DATA_FILE = 'user_data.json'

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        user_data = json.load(f)
else:
    user_data = {}

def save_user_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(user_data, f)

# Bot initialization
bot = Bot(token="YOUR_TOKEN")
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class Form(StatesGroup):
    language_choice = State()
    set_wallets = State()
    monitor_threshold = State()
    monitor_interval = State()

# Translations
translations = {
    'en': {
        'start': "Hello! I'm a bot for monitoring Curve Lend positions.\nHere's what I can do:",
        'set_command': "Set wallets",
        'pos_command': "Current positions",
        'monitor_command': "Monitor positions",
        'language_prompt': "Please select your preferred language:",
        'wallets_prompt': "Send a wallet or list of wallets separated by commas for tracking.",
        'wallets_saved': "Wallets saved.",
        'no_wallets': "No wallets set. Use the /set command to set up wallets.",
        'threshold_prompt': "Enter the health threshold for notifications (e.g., 5.0).",
        'invalid_threshold': "Invalid format. Please enter a number.",
        'interval_prompt': "Threshold saved. Enter the interval for repeated notifications in hours (0 - do not repeat).",
        'invalid_interval': "Invalid format. Please enter an integer.",
        'monitoring_started': "Monitoring settings completed. Monitoring started.",
        'network': "Network",
        'position': "Position",
        'health': "Health",
        'debt': "Debt",
        'oracle_price': "Oracle Price",
        'soft_liquidation': "Soft Liquidation",
        'no_positions': "No active positions found.",
        'health_alert': "Health of the position {market_name} has fallen below {threshold}.",
    },
    'ru': {
        'start': "Привет! Я бот для мониторинга позиций Curve Lend.\nВот что я могу делать:",
        'set_command': "Настройка кошельков",
        'pos_command': "Текущие позиции",
        'monitor_command': "Мониторинг позиций",
        'language_prompt': "Пожалуйста, выберите предпочитаемый язык:",
        'wallets_prompt': "Отправьте кошелек или список кошельков через запятую для отслеживания.",
        'wallets_saved': "Кошельки сохранены.",
        'no_wallets': "Кошельки не настроены. Используйте команду /set для настройки.",
        'threshold_prompt': "Введите порог health для уведомлений (например, 5.0).",
        'invalid_threshold': "Неверный формат. Введите число.",
        'interval_prompt': "Порог сохранен. Введите интервал повторных уведомлений в часах (0 — не повторять).",
        'invalid_interval': "Неверный формат. Введите целое число.",
        'monitoring_started': "Настройки мониторинга завершены. Мониторинг запущен.",
        'network': "Сеть",
        'position': "Позиция",
        'health': "Здоровье",
        'debt': "Долг",
        'oracle_price': "Oracle Price",
        'soft_liquidation': "Soft Liquidation",
        'no_positions': "Активные позиции не найдены.",
        'health_alert': "Health позиции {market_name} упал ниже {threshold}.",
    }
}

async def set_bot_commands(lang):
    commands = [
        BotCommand(command="/set", description=translations[lang]['set_command']),
        BotCommand(command="/pos", description=translations[lang]['pos_command']),
        BotCommand(command="/monitor", description=translations[lang]['monitor_command'])
    ]
    await bot.set_my_commands(commands)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="English", callback_data="lang_en"),
         InlineKeyboardButton(text="Русский", callback_data="lang_ru")]
    ])
    await message.answer("Please select your language / Пожалуйста, выберите ваш язык:", reply_markup=markup)

@dp.callback_query(lambda c: c.data.startswith('lang_'))
async def process_callback_language(callback_query: types.CallbackQuery):
    lang = callback_query.data.split('_')[1]
    user_id = str(callback_query.from_user.id)
    
    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]['language'] = lang
    save_user_data()

    await set_bot_commands(lang)
    await callback_query.message.answer(translations[lang]['start'] + f"\n/set — {translations[lang]['set_command']}\n/pos — {translations[lang]['pos_command']}\n/monitor — {translations[lang]['monitor_command']}")
    await callback_query.answer()

# Settings /set
@dp.message(Command("set"))
async def cmd_set(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    lang = user_data.get(user_id, {}).get('language', 'en')
    await message.answer(translations[lang]['wallets_prompt'])
    await state.set_state(Form.set_wallets)

@dp.message(Form.set_wallets)
async def process_wallets(message: types.Message, state: FSMContext):
    wallets = message.text.split(',')
    user_id = str(message.from_user.id)
    lang = user_data.get(user_id, {}).get('language', 'en')

    if user_id not in user_data:
        user_data[user_id] = {}
    
    user_data[user_id]['wallets'] = wallets
    save_user_data()

    await message.answer(translations[lang]['wallets_saved'])
    await state.clear()

# Function to get positions
async def get_positions(chain, wallet):
    url = f"https://prices.curve.fi/v1/lending/users/{chain}/{wallet}"
    logger.info(f"Sending request to {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                logger.info(f"Response from API: status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Received data: {data}")
                    return data
                else:
                    logger.error(f"Error getting data: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error when requesting API: {e}")
        return None

# Function to get position statistics
async def get_position_stats(chain, wallet, controller):
    url = f"https://prices.curve.fi/v1/lending/users/{chain}/{wallet}/{controller}/stats"
    logger.info(f"Sending request to {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                logger.info(f"Response from API: status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Received data: {data}")
                    return data
                else:
                    logger.error(f"Error getting data: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error when requesting API: {e}")
        return None
        
# Color the output        
def get_health_indicator(health):
    if health > 10:
        return "\U0001F7E2"  # Green circle
    elif 5 <= health <= 10:
        return "\U0001F7E1"  # Yellow circle
    elif 2 <= health < 5:
        return "\U0001F7E0"  # Orange circle
    else:
        return "\U0001F534"  # Red circle

def get_soft_liquidation_indicator(soft_liquidation):
    return "\U0001F7E0" if soft_liquidation else "\U0001F7E2"  # Orange circle if True, otherwise green

# Request positions /pos
@dp.message(Command("pos"))
async def cmd_pos(message: types.Message):
    user_id = str(message.from_user.id)
    lang = user_data.get(user_id, {}).get('language', 'en')
    if user_id not in user_data or not user_data[user_id].get('wallets'):
        await message.answer(translations[lang]['no_wallets'])
        return

    msg = await message.answer("Request sent, please wait...")

    wallets = user_data[user_id]['wallets']
    response = ""

    for wallet in wallets:
        for chain in ['ethereum', 'arbitrum']:
            positions = await get_positions(chain, wallet)
            if positions and positions.get("markets"):
                for market in positions["markets"]:
                    controller = market["controller"]
                    stats = await get_position_stats(chain, wallet, controller)
                    if stats and stats["health"] > 0 and stats["debt"] > 0:
                        health_indicator = get_health_indicator(stats['health'])
                        soft_liquidation_indicator = get_soft_liquidation_indicator(stats.get('soft_liquidation', False))
                        response += (
                            f"{translations[lang]['network']}: {chain}\n"
                            f"{translations[lang]['position']}: {market['market_name']}\n"
                            f"{translations[lang]['health']}: {health_indicator} {round(stats['health'], 2)}\n"
                            f"{translations[lang]['debt']}: {round(stats['debt'], 2)} crvUSD\n"
                            f"{translations[lang]['oracle_price']}: {round(stats['oracle_price'], 2)}\n"
                            f"{translations[lang]['soft_liquidation']}: {soft_liquidation_indicator} {stats.get('soft_liquidation', False)}\n\n"
                        )
    
    if response == "":
        response = translations[lang]['no_positions']
    
    await msg.edit_text(response)

# Monitoring /monitor
@dp.message(Command("monitor"))
async def cmd_monitor(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    lang = user_data.get(user_id, {}).get('language', 'en')
    logger.info(f"User {user_id} started monitoring setup")
    
    if user_id not in user_data or not user_data[user_id].get('wallets'):
        await message.answer(translations[lang]['no_wallets'])
        return
    
    await message.answer(translations[lang]['threshold_prompt'])
    await state.set_state(Form.monitor_threshold)

@dp.message(Form.monitor_threshold)
async def process_monitor_threshold(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    lang = user_data.get(user_id, {}).get('language', 'en')
    try:
        threshold = float(message.text)
        logger.info(f"User {user_id} set health threshold: {threshold}")
    except ValueError:
        await message.answer(translations[lang]['invalid_threshold'])
        return

    user_data[user_id]['monitor_threshold'] = threshold
    save_user_data()

    await message.answer(translations[lang]['interval_prompt'])
    await state.set_state(Form.monitor_interval)

@dp.message(Form.monitor_interval)
async def process_monitor_interval(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    lang = user_data.get(user_id, {}).get('language', 'en')
    try:
        interval = int(message.text)
        logger.info(f"User {user_id} set notification interval: {interval} hours")
    except ValueError:
        await message.answer(translations[lang]['invalid_interval'])
        return

    user_data[user_id]['notification_interval'] = interval
    user_data[user_id]['monitoring_active'] = True
    save_user_data()

    await message.answer(translations[lang]['monitoring_started'])
    await state.clear()

    # Start monitoring in background
    asyncio.create_task(monitor_positions(user_id))
    logger.info(f"Monitoring started for user {user_id}")

# Background monitoring
async def monitor_positions(user_id):
    logger.info(f"Monitoring function started for user {user_id}.")
    last_notification = {}
    while True:
        if user_id in user_data and user_data[user_id].get('monitoring_active', False):
            lang = user_data.get(user_id, {}).get('language', 'en')
            wallets = user_data[user_id].get('wallets', [])
            threshold = user_data[user_id].get('monitor_threshold', float('inf'))
            notification_interval = user_data[user_id].get('notification_interval', 0)  # Interval in hours
            logger.info(f"Checking positions for user {user_id} with threshold {threshold}.")
            
            for wallet in wallets:
                for chain in ['ethereum', 'arbitrum']:
                    positions = await get_positions(chain, wallet)
                    logger.info(f"Received positions for {wallet} in network {chain}: {positions}")
                    
                    if positions and positions.get("markets"):
                        for market in positions["markets"]:
                            controller = market["controller"]
                            stats = await get_position_stats(chain, wallet, controller)
                            logger.info(f"Statistics for position {market['market_name']}")

                            if stats and stats["health"] < threshold and stats["debt"] > 0:
                                position_key = f"{chain}_{wallet}_{controller}"
                                current_time = datetime.now()
                                if (position_key not in last_notification or 
                                    (notification_interval > 0 and 
                                     current_time - last_notification[position_key] >= timedelta(hours=notification_interval))):
                                    health_indicator = get_health_indicator(stats['health'])
                                    soft_liquidation_indicator = get_soft_liquidation_indicator(stats.get('soft_liquidation', False))
                                    message = (
                                        f"\u26A0\uFE0F {translations[lang]['health_alert'].format(market_name=market['market_name'], threshold=threshold)}\n\n"
                                        f"{translations[lang]['health']}: {health_indicator} {round(stats['health'], 2)}\n"
                                        f"{translations[lang]['debt']}: {round(stats['debt'], 2)} crvUSD\n"
                                        f"{translations[lang]['oracle_price']}: {round(stats['oracle_price'], 2)}\n"
                                        f"{translations[lang]['soft_liquidation']}: {soft_liquidation_indicator} {stats.get('soft_liquidation', False)}\n"
                                    )
                                    await bot.send_message(user_id, message)
                                    last_notification[position_key] = current_time
                                    logger.info(f"Notification sent to user {user_id}")
            
            logger.info(f"Next position check for user {user_id} will be in 5 minutes")
        else:
            logger.info(f"Monitoring for user {user_id} is not active or user not found.")
        
        await asyncio.sleep(300)  # Check every 5 minutes

# Function to start monitoring for all users when the bot starts
async def start_monitoring_for_all_users():
    logger.info("Starting monitoring for all users at bot startup.")
    for user_id, data in user_data.items():
        if data.get('monitoring_active', False):
            asyncio.create_task(monitor_positions(user_id))
            logger.info(f"Monitoring started for user {user_id}")

# Bot launch
async def main():
    await set_bot_commands('en')  # Set bot commands (default to English)
    await start_monitoring_for_all_users()  # Start monitoring for all users
    logger.info("Bot is launched and ready to work.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
