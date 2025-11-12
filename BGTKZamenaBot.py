import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import logging
import asyncio
from datetime import datetime, timedelta

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# URL расписания
SCHEDULE_URL = "https://docs.google.com/spreadsheets/u/0/d/e/2PACX-1vRgODzWJhSfml2SVezD2P4wdEyp92gZ7y3-tyjFssLI80j3CCTv7-cmJhcCsvQNKcPnzP-m2r9pswd8/pubhtml/sheet?headers=false&gid=0"

# Хранилище временных данных пользователей
user_data = {}

# Русские названия дней недели
RUSSIAN_DAYS = {
    'MONDAY': 'ПОНЕДЕЛЬНИК',
    'TUESDAY': 'ВТОРНИК', 
    'WEDNESDAY': 'СРЕДА',
    'THURSDAY': 'ЧЕТВЕРГ',
    'FRIDAY': 'ПЯТНИЦА',
    'SATURDAY': 'СУББОТА',
    'SUNDAY': 'ВОСКРЕСЕНЬЕ'
}

# Создатель бота
CREATOR_USERNAME = "@Va1kadav"

# Быстрые группы
QUICK_GROUPS = {
    '1п065': '1П065'
}

async def set_bot_commands(application: Application):
    """Установка списка команд с подсказками"""
    commands = [
        BotCommand("start", "Запустить бота"),
        BotCommand("zamena", "Поиск замен расписания - /zamena [группа] [дата/день]"),
        BotCommand("pe", "Быстрый поиск для 1П065 - /pe [дата/день]"),
        BotCommand("today", "Расписание на сегодня - /today [группа]"),
        BotCommand("tomorrow", "Расписание на завтра - /tomorrow [группа]"),
        BotCommand("info", "Информация о боте"),
        BotCommand("help", "Помощь по использованию")
    ]
    await application.bot.set_my_commands(commands)

def get_russian_day(english_day):
    """Конвертирует английское название дня в русское"""
    return RUSSIAN_DAYS.get(english_day.upper(), english_day)

def get_current_russian_day():
    """Возвращает текущий день недели на русском"""
    today = datetime.now().strftime('%A').upper()
    return RUSSIAN_DAYS.get(today, today)

def get_tomorrow_russian_day():
    """Возвращает завтрашний день недели на русском"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%A').upper()
    return RUSSIAN_DAYS.get(tomorrow, tomorrow)

def format_schedule_entry(number, row, date, day, week):
    """Форматирует запись расписания для отправки в Telegram"""
    result = f"🎓 ЗАПИСЬ #{number}\n"
    result += "=" * 40 + "\n"
    
    if week:
        result += f"📅 Неделя: {week}\n"
    if date:
        result += f"🗓️ Дата: {date}\n"
    if day:
        result += f"📋 День: {day}\n"
    
    cells = row.find_all('td')
    
    if len(cells) >= 11:
        group = cells[0].get_text(strip=True)
        result += f"📊 Группа: {group}\n"
        result += "-" * 30 + "\n"
        
        # 1 пара
        lesson1 = cells[1].get_text(separator=' | ', strip=True)
        room1 = cells[2].get_text(separator=' | ', strip=True)
        result += f"🔹 1 ПАРА:\n"
        result += f"   📚 {lesson1 if lesson1 else 'Нет урока'}\n"
        result += f"   🏫 {room1 if room1 else '-'}\n\n"
        
        # 2 пара
        lesson2 = cells[3].get_text(separator=' | ', strip=True)
        room2 = cells[4].get_text(separator=' | ', strip=True)
        result += f"🔹 2 ПАРА:\n"
        result += f"   📚 {lesson2 if lesson2 else 'Нет урока'}\n"
        result += f"   🏫 {room2 if room2 else '-'}\n\n"
        
        # 3 пара
        lesson3 = cells[5].get_text(separator=' | ', strip=True)
        room3 = cells[6].get_text(separator=' | ', strip=True)
        result += f"🔹 3 ПАРА:\n"
        result += f"   📚 {lesson3 if lesson3 else 'Нет урока'}\n"
        result += f"   🏫 {room3 if room3 else '-'}\n\n"
        
        # 4 пара
        lesson4 = cells[7].get_text(separator=' | ', strip=True)
        room4 = cells[8].get_text(separator=' | ', strip=True)
        result += f"🔹 4 ПАРА:\n"
        result += f"   📚 {lesson4 if lesson4 else 'Нет урока'}\n"
        result += f"   🏫 {room4 if room4 else '-'}\n\n"
        
        # 5 пара
        lesson5 = cells[9].get_text(separator=' | ', strip=True)
        room5 = cells[10].get_text(separator=' | ', strip=True) if len(cells) > 10 else ""
        result += f"🔹 5 ПАРА:\n"
        result += f"   📚 {lesson5 if lesson5 else 'Нет урока'}\n"
        result += f"   🏫 {room5 if room5 else '-'}\n"
    else:
        result += "❌ Недостаточно данных в строке\n"
    
    return result

async def working_schedule_search_tg(group, date=None, day=None):
    """Рабочий поиск расписания по группе для Telegram"""
    try:
        response = requests.get(SCHEDULE_URL)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.find_all('tr')
        
        found_count = 0
        current_date = None
        current_day = None
        current_week = None
        
        unique_entries = {}
        result_messages = []
        
        for row in rows:
            # Ищем информацию о неделе, дате и дне
            week_cell = row.find('td', class_='s0')
            if week_cell:
                week_text = week_cell.get_text(strip=True)
                if 'неделя' in week_text.lower():
                    current_week = week_text
            
            # Ищем дату и день недели (класс s4)
            date_cell = row.find('td', class_='s4')
            if date_cell:
                text = date_cell.get_text(strip=True)
                # Проверяем формат даты (ДД.ММ.ГГГГ)
                if '.' in text and len(text.split('.')) == 3:
                    try:
                        datetime.strptime(text, '%d.%m.%Y')
                        current_date = text
                        current_day = None
                    except ValueError:
                        # Если не дата, проверяем день недели
                        if text.upper() in RUSSIAN_DAYS.values():
                            current_day = text
                # Проверяем день недели
                elif text.upper() in RUSSIAN_DAYS.values():
                    current_day = text
            
            # Пропускаем строку если фильтры не совпадают
            if date and current_date and date != current_date:
                continue
            if day and current_day and day.upper() != current_day.upper():
                continue
            
            # Ищем ячейку с группой (класс s16)
            group_cell = row.find('td', class_='s16')
            if group_cell:
                group_text = group_cell.get_text(strip=True)
                
                if group.upper() == group_text.upper():
                    entry_key = f"{current_date}_{current_day}"
                    
                    if entry_key not in unique_entries:
                        found_count += 1
                        unique_entries[entry_key] = {
                            'row': row,
                            'date': current_date,
                            'day': current_day,
                            'week': current_week,
                            'number': found_count
                        }
        
        # Формируем сообщения
        for entry_key, entry_data in unique_entries.items():
            message = format_schedule_entry(
                entry_data['number'], 
                entry_data['row'], 
                entry_data['date'], 
                entry_data['day'],
                entry_data['week']
            )
            result_messages.append(message)
        
        if found_count == 0:
            result_messages.append("❌ Совпадений не найдено")
        else:
            result_messages.append(f"\n✅ Найдено уникальных записей: {found_count}")
            
        return result_messages
        
    except Exception as e:
        return [f"❌ Ошибка: {e}"]

async def smart_search_tg(group):
    """Умный поиск для Telegram - показывает все уникальные дни для группы"""
    try:
        response = requests.get(SCHEDULE_URL)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.find_all('tr')
        
        group_days = {}
        current_date = None
        current_day = None
        current_week = None
        
        for row in rows:
            # Обновляем информацию о дате/дне
            date_cell = row.find('td', class_='s4')
            if date_cell:
                text = date_cell.get_text(strip=True)
                # Проверяем формат даты
                if '.' in text and len(text.split('.')) == 3:
                    try:
                        datetime.strptime(text, '%d.%m.%Y')
                        current_date = text
                        current_day = None
                    except ValueError:
                        if text.upper() in RUSSIAN_DAYS.values():
                            current_day = text
                # Проверяем день недели
                elif text.upper() in RUSSIAN_DAYS.values():
                    current_day = text
            
            week_cell = row.find('td', class_='s0')
            if week_cell:
                week_text = week_cell.get_text(strip=True)
                if 'неделя' in week_text.lower():
                    current_week = week_text
            
            # Ищем группу
            group_cell = row.find('td', class_='s16')
            if group_cell:
                group_text = group_cell.get_text(strip=True)
                
                if group.upper() == group_text.upper() and (current_date or current_day):
                    key = f"{current_date}_{current_day}"
                    if key not in group_days:
                        group_days[key] = {
                            'date': current_date,
                            'day': current_day,
                            'week': current_week,
                            'row': row
                        }
        
        return group_days
        
    except Exception as e:
        logger.error(f"Ошибка в smart_search_tg: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.message.from_user
    first_name = user.first_name
    
    welcome_text = (
        f"👋 Приветствую, {first_name}!\n\n"
        f"🎓 Добро пожаловать в бот для поиска расписания!\n\n"
        f"📅 Сегодня: {get_current_russian_day()}\n"
        f"📅 Завтра: {get_tomorrow_russian_day()}\n\n"
        f"Используйте команду /zamena для поиска замен\n"
        f"Или выберите действие ниже:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск расписания", callback_data="search_schedule")],
        [InlineKeyboardButton("🚀 1П065 (Быстрый поиск)", callback_data="quick_1p065")],
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="today_schedule"),
            InlineKeyboardButton("📅 Завтра", callback_data="tomorrow_schedule")
        ],
        [
            InlineKeyboardButton("ℹ️ Информация", callback_data="info"),
            InlineKeyboardButton("❓ Помощь", callback_data="help")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def zamena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /zamena с параметрами"""
    user = update.message.from_user
    first_name = user.first_name
    args = context.args
    
    # Если есть аргументы, обрабатываем команду с параметрами
    if args:
        group = args[0].upper()
        date_or_day = None
        
        if len(args) > 1:
            # Объединяем все остальные аргументы для даты/дня
            date_or_day = ' '.join(args[1:])
            
            # Проверяем, является ли ввод датой
            try:
                datetime.strptime(date_or_day, '%d.%m.%Y')
                # Это дата
                date_filter = date_or_day
                day_filter = None
            except ValueError:
                # Это день недели
                date_filter = None
                day_filter = date_or_day.upper()
        else:
            date_filter = None
            day_filter = None
        
        await update.message.reply_text(f"🔍 Уважаемый(ая) {first_name}, ищу расписание для группы {group}...")
        
        results = await working_schedule_search_tg(group, date_filter, day_filter)
        
        for result in results:
            if len(result) > 4096:
                for i in range(0, len(result), 4096):
                    await update.message.reply_text(result[i:i+4096])
            else:
                await update.message.reply_text(result)
        
        return
    
    # Если нет аргументов, показываем меню
    keyboard = [
        [
            InlineKeyboardButton("🔍 Умный поиск", callback_data="smart_search"),
            InlineKeyboardButton("📅 Поиск с фильтрами", callback_data="filtered_search")
        ],
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="today_schedule"),
            InlineKeyboardButton("📅 Завтра", callback_data="tomorrow_schedule")
        ],
        [InlineKeyboardButton("🚀 1П065 (Быстрый)", callback_data="quick_1p065")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎯 Уважаемый(ая) {first_name}, выберите режим поиска расписания:",
        reply_markup=reply_markup
    )

async def pe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /pe для быстрого поиска группы 1П065"""
    user = update.message.from_user
    first_name = user.first_name
    args = context.args
    
    group = "1П065"
    date_filter = None
    day_filter = None
    
    if args:
        # Объединяем все аргументы для даты/дня
        date_or_day = ' '.join(args)
        
        # Проверяем, является ли ввод датой
        try:
            datetime.strptime(date_or_day, '%d.%m.%Y')
            # Это дата
            date_filter = date_or_day
            day_filter = None
        except ValueError:
            # Это день недели
            date_filter = None
            day_filter = date_or_day.upper()
    
    filter_text = ""
    if date_filter:
        filter_text = f" на {date_filter}"
    elif day_filter:
        filter_text = f" на {day_filter}"
    
    await update.message.reply_text(
        f"🚀 Уважаемый(ая) {first_name}, ищу расписание для группы {group}{filter_text}..."
    )
    
    results = await working_schedule_search_tg(group, date_filter, day_filter)
    
    for result in results:
        if len(result) > 4096:
            for i in range(0, len(result), 4096):
                await update.message.reply_text(result[i:i+4096])
        else:
            await update.message.reply_text(result)

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /today с параметрами"""
    user = update.message.from_user
    first_name = user.first_name
    args = context.args
    
    if not args:
        await update.message.reply_text(
            f"📅 Уважаемый(ая) {first_name}, используйте команду так:\n"
            f"/today [номер группы]\n"
            f"Например: /today 1п065\n"
            f"Или просто /today для группы 1П065"
        )
        return
    
    group = args[0].upper()
    today = datetime.now().strftime('%d.%m.%Y')
    current_day = get_current_russian_day()
    
    await update.message.reply_text(
        f"🔍 Уважаемый(ая) {first_name}, ищу расписание на сегодня ({today}, {current_day}) для группы {group}..."
    )
    
    results = await working_schedule_search_tg(group, today, current_day)
    
    for result in results:
        if len(result) > 4096:
            for i in range(0, len(result), 4096):
                await update.message.reply_text(result[i:i+4096])
        else:
            await update.message.reply_text(result)

async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /tomorrow с параметрами"""
    user = update.message.from_user
    first_name = user.first_name
    args = context.args
    
    if not args:
        await update.message.reply_text(
            f"📅 Уважаемый(ая) {first_name}, используйте команду так:\n"
            f"/tomorrow [номер группы]\n"
            f"Например: /tomorrow 1п065\n"
            f"Или просто /tomorrow для группы 1П065"
        )
        return
    
    group = args[0].upper()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
    tomorrow_day = get_tomorrow_russian_day()
    
    await update.message.reply_text(
        f"🔍 Уважаемый(ая) {first_name}, ищу расписание на завтра ({tomorrow}, {tomorrow_day}) для группы {group}..."
    )
    
    results = await working_schedule_search_tg(group, tomorrow, tomorrow_day)
    
    for result in results:
        if len(result) > 4096:
            for i in range(0, len(result), 4096):
                await update.message.reply_text(result[i:i+4096])
        else:
            await update.message.reply_text(result)

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /info"""
    user = update.message.from_user
    first_name = user.first_name
    
    info_text = (
        f"ℹ️ Уважаемый(ая) {first_name}, информация о боте:\n\n"
        f"🤖 Бот для поиска расписания занятий\n\n"
        f"📚 Функции:\n"
        f"• Поиск расписания по группе\n"
        f"• Фильтрация по дате и дню недели\n"
        f"• Расписание на сегодня/завтра\n"
        f"• Умный поиск всех доступных дней\n"
        f"• Быстрый поиск для группы 1П065 (/pe)\n\n"
        f"🚀 Быстрые команды для 1П065:\n"
        f"/pe - все расписание\n"
        f"/pe 20.01.2024 - на конкретную дату\n"
        f"/pe ПОНЕДЕЛЬНИК - на конкретный день\n\n"
        f"👨‍💻 Создатель: {CREATOR_USERNAME}\n"
        f"📞 По всем вопросам обращайтесь к создателю\n\n"
        f"Благодарим Вас за использование бота! 🙏"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(info_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_name = query.from_user.first_name
    data = query.data
    
    if data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("🔍 Поиск расписания", callback_data="search_schedule")],
            [InlineKeyboardButton("🚀 1П065 (Быстрый поиск)", callback_data="quick_1p065")],
            [
                InlineKeyboardButton("📅 Сегодня", callback_data="today_schedule"),
                InlineKeyboardButton("📅 Завтра", callback_data="tomorrow_schedule")
            ],
            [
                InlineKeyboardButton("ℹ️ Информация", callback_data="info"),
                InlineKeyboardButton("❓ Помощь", callback_data="help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"🎓 Уважаемый(ая) {user_name}, главное меню бота расписания",
            reply_markup=reply_markup
        )
    
    elif data == "search_schedule":
        await zamena_callback(query)
    
    elif data == "smart_search":
        user_data[user_id] = {'mode': 'smart'}
        await query.edit_message_text(
            f"🔍 Уважаемый(ая) {user_name}, умный поиск\n\n"
            "Введите номер группы:"
        )
    
    elif data == "filtered_search":
        user_data[user_id] = {'mode': 'filtered'}
        await query.edit_message_text(
            f"📅 Уважаемый(ая) {user_name}, поиск с фильтрами\n\n"
            "Введите номер группы:"
        )
    
    elif data == "today_schedule":
        user_data[user_id] = {'mode': 'today'}
        await query.edit_message_text(
            f"📅 Уважаемый(ая) {user_name}, поиск расписания на сегодня\n\n"
            "Введите номер группы:"
        )
    
    elif data == "tomorrow_schedule":
        user_data[user_id] = {'mode': 'tomorrow'}
        await query.edit_message_text(
            f"📅 Уважаемый(ая) {user_name}, поиск расписания на завтра\n\n"
            "Введите номер группы:"
        )
    
    elif data == "quick_1p065":
        # Быстрый поиск для группы 1П065
        group = "1П065"
        await query.edit_message_text(f"🚀 Уважаемый(ая) {user_name}, ищу расписание для группы {group}...")
        
        results = await working_schedule_search_tg(group)
        
        for result in results:
            if len(result) > 4096:
                for i in range(0, len(result), 4096):
                    await query.message.reply_text(result[i:i+4096])
            else:
                await query.message.reply_text(result)
        
        # Предлагаем новый поиск
        keyboard = [
            [InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")],
            [InlineKeyboardButton("🚀 1П065 снова", callback_data="quick_1p065")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить другой поиск?", reply_markup=reply_markup)
    
    elif data == "info":
        info_text = (
            f"ℹ️ Уважаемый(ая) {user_name}, информация о боте:\n\n"
            f"🤖 Бот для поиска расписания занятий\n\n"
            f"📚 Функции:\n"
            f"• Поиск расписания по группе\n"
            f"• Фильтрация по дате и дню недели\n"
            f"• Расписание на сегодня/завтра\n"
            f"• Умный поиск всех доступных дней\n"
            f"• Быстрый поиск для группы 1П065 (/pe)\n\n"
            f"🚀 Быстрые команды для 1П065:\n"
            f"/pe - все расписание\n"
            f"/pe 20.01.2024 - на конкретную дату\n"
            f"/pe ПОНЕДЕЛЬНИК - на конкретный день\n\n"
            f"👨‍💻 Создатель: {CREATOR_USERNAME}\n"
            f"📞 По всем вопросам обращайтесь к создателю\n\n"
            f"Благодарим Вас за использование бота! 🙏"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(info_text, reply_markup=reply_markup)
    
    elif data == "help":
        help_text = (
            f"❓ Уважаемый(ая) {user_name}, помощь по использованию бота:\n\n"
            "🔍 Умный поиск - показывает все доступные дни для группы и позволяет выбрать конкретный день\n\n"
            "📅 Поиск с фильтрами - поиск по конкретной дате или дню недели\n\n"
            "📅 Сегодня - поиск расписания на текущий день\n"
            "📅 Завтра - поиск расписания на завтрашний день\n"
            "🚀 1П065 - быстрый поиск для группы 1П065\n\n"
            "💻 Команды:\n"
            "/start - начать работу\n"
            "/zamena [группа] [дата/день] - поиск расписания\n"
            "/pe [дата/день] - быстрый поиск для 1П065\n"
            "/today [группа] - расписание на сегодня\n"
            "/tomorrow [группа] - расписание на завтра\n"
            "/info - информация о боте\n"
            "/help - показать эту справку\n\n"
            "📝 Примеры:\n"
            "/zamena 1п065\n"
            "/zamena 1п065 15.01.2024\n"
            "/zamena 1п065 ПОНЕДЕЛЬНИК\n"
            "/pe\n"
            "/pe 20.01.2024\n"
            "/pe ПОНЕДЕЛЬНИК\n"
            "/today 1п065\n"
            "/tomorrow 1п065"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup)

async def zamena_callback(query):
    """Обработчик для кнопки поиска расписания"""
    user_name = query.from_user.first_name
    
    keyboard = [
        [
            InlineKeyboardButton("🔍 Умный поиск", callback_data="smart_search"),
            InlineKeyboardButton("📅 Поиск с фильтрами", callback_data="filtered_search")
        ],
        [
            InlineKeyboardButton("📅 Сегодня", callback_data="today_schedule"),
            InlineKeyboardButton("📅 Завтра", callback_data="tomorrow_schedule")
        ],
        [InlineKeyboardButton("🚀 1П065 (Быстрый)", callback_data="quick_1p065")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🎯 Уважаемый(ая) {user_name}, выберите режим поиска расписания:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.first_name
    text = update.message.text.strip()
    
    if user_id not in user_data:
        await update.message.reply_text(f"Уважаемый(ая) {user_name}, пожалуйста, выберите действие через меню /start")
        return
    
    user_state = user_data[user_id]
    
    if 'mode' in user_state and 'group' not in user_state:
        # Получили номер группы
        user_state['group'] = text
        
        if user_state['mode'] == 'smart':
            await process_smart_search(update, text, user_name)
        elif user_state['mode'] == 'filtered':
            keyboard = [
                [InlineKeyboardButton("Пропустить дату", callback_data="skip_date")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="search_schedule")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"📅 Уважаемый(ая) {user_name}, введите дату в формате ДД.ММ.ГГГГ (например, 15.01.2024) или нажмите 'Пропустить дату':",
                reply_markup=reply_markup
            )
        elif user_state['mode'] == 'today':
            # Поиск на сегодня
            today = datetime.now().strftime('%d.%m.%Y')
            current_day = get_current_russian_day()
            
            await update.message.reply_text(f"🔍 Уважаемый(ая) {user_name}, ищу расписание на сегодня ({today}, {current_day})...")
            
            results = await working_schedule_search_tg(text, today, current_day)
            
            for result in results:
                if len(result) > 4096:
                    for i in range(0, len(result), 4096):
                        await update.message.reply_text(result[i:i+4096])
                else:
                    await update.message.reply_text(result)
            
            # Очищаем данные пользователя
            del user_data[user_id]
            
            # Предлагаем новый поиск
            keyboard = [[InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить новый поиск?", reply_markup=reply_markup)
        
        elif user_state['mode'] == 'tomorrow':
            # Поиск на завтра
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
            tomorrow_day = get_tomorrow_russian_day()
            
            await update.message.reply_text(f"🔍 Уважаемый(ая) {user_name}, ищу расписание на завтра ({tomorrow}, {tomorrow_day})...")
            
            results = await working_schedule_search_tg(text, tomorrow, tomorrow_day)
            
            for result in results:
                if len(result) > 4096:
                    for i in range(0, len(result), 4096):
                        await update.message.reply_text(result[i:i+4096])
                else:
                    await update.message.reply_text(result)
            
            # Очищаем данные пользователя
            del user_data[user_id]
            
            # Предлагаем новый поиск
            keyboard = [[InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить новый поиск?", reply_markup=reply_markup)
    
    elif 'mode' in user_state and 'group' in user_state and 'date' not in user_state and user_state['mode'] == 'filtered':
        # Получили дату для фильтрованного поиска
        if text.lower() != 'пропустить':
            user_state['date'] = text
        
        keyboard = [
            [InlineKeyboardButton("Пропустить день", callback_data="skip_day")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="search_schedule")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"📋 Уважаемый(ая) {user_name}, введите день недели ({', '.join(RUSSIAN_DAYS.values())}) или нажмите 'Пропустить день':",
            reply_markup=reply_markup
        )
    
    elif 'mode' in user_state and 'group' in user_state and 'date' in user_state and 'day' not in user_state and user_state['mode'] == 'filtered':
        # Получили день недели
        if text.lower() != 'пропустить':
            user_state['day'] = text
        
        # Выполняем поиск
        group = user_state['group']
        date = user_state.get('date')
        day = user_state.get('day')
        
        await update.message.reply_text(f"🔍 Уважаемый(ая) {user_name}, ищу расписание...")
        
        results = await working_schedule_search_tg(group, date, day)
        
        for result in results:
            # Разбиваем длинные сообщения если нужно
            if len(result) > 4096:
                for i in range(0, len(result), 4096):
                    await update.message.reply_text(result[i:i+4096])
            else:
                await update.message.reply_text(result)
        
        # Очищаем данные пользователя
        del user_data[user_id]
        
        # Предлагаем новый поиск
        keyboard = [[InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить новый поиск?", reply_markup=reply_markup)

async def process_smart_search(update, group, user_name):
    """Обработка умного поиска"""
    await update.message.reply_text(f"🔍 Уважаемый(ая) {user_name}, ищу все доступные дни для группы...")
    
    group_days = await smart_search_tg(group)
    
    if not group_days:
        await update.message.reply_text(f"❌ Уважаемый(ая) {user_name}, группа не найдена или произошла ошибка")
        del user_data[update.message.from_user.id]
        return
    
    # Создаем клавиатуру с днями
    keyboard = []
    days_list = list(group_days.items())
    
    for i, (key, data) in enumerate(days_list, 1):
        day_display = data['day'] if data['day'] else "Не указан"
        date_display = data['date'] if data['date'] else "Не указана"
        button_text = f"{i}. {date_display} - {day_display}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"day_{i}")])
    
    keyboard.append([InlineKeyboardButton("📋 Показать все", callback_data="show_all")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="search_schedule")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Сохраняем данные для callback
    user_id = update.message.from_user.id
    user_data[user_id]['group_days'] = days_list
    user_data[user_id]['current_group'] = group
    
    await update.message.reply_text(
        f"📅 Уважаемый(ая) {user_name}, найдены следующие дни для группы {group}:\n"
        f"Выберите день для просмотра:",
        reply_markup=reply_markup
    )

async def day_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора дня в умном поиске"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_name = query.from_user.first_name
    data = query.data
    
    if user_id not in user_data or 'group_days' not in user_data[user_id]:
        await query.edit_message_text("❌ Сессия устарела, начните заново")
        return
    
    days_list = user_data[user_id]['group_days']
    group = user_data[user_id]['current_group']
    
    if data == "show_all":
        # Показываем все дни
        await query.edit_message_text(f"📋 Уважаемый(ая) {user_name}, загружаю все дни...")
        
        for i, (key, day_data) in enumerate(days_list, 1):
            message = format_schedule_entry(
                i, day_data['row'], day_data['date'], day_data['day'], day_data['week']
            )
            # Разбиваем длинные сообщения
            if len(message) > 4096:
                for j in range(0, len(message), 4096):
                    await query.message.reply_text(message[j:j+4096])
            else:
                await query.message.reply_text(message)
        
        # Очищаем данные
        del user_data[user_id]
        
        # Предлагаем новый поиск
        keyboard = [[InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить новый поиск?", reply_markup=reply_markup)
    
    elif data.startswith("day_"):
        # Показываем выбранный день
        day_index = int(data.split("_")[1]) - 1
        selected_day = days_list[day_index][1]
        
        message = format_schedule_entry(
            1, selected_day['row'], selected_day['date'], selected_day['day'], selected_day['week']
        )
        
        # Разбиваем длинные сообщения
        if len(message) > 4096:
            await query.edit_message_text(f"📋 Уважаемый(ая) {user_name}, расписание слишком длинное, отправляю частями...")
            for i in range(0, len(message), 4096):
                await query.message.reply_text(message[i:i+4096])
        else:
            await query.edit_message_text(message)
        
        # Очищаем данные
        del user_data[user_id]
        
        # Предлагаем новый поиск
        keyboard = [[InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить новый поиск?", reply_markup=reply_markup)

async def skip_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок пропуска"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_name = query.from_user.first_name
    data = query.data
    
    if user_id not in user_data:
        await query.edit_message_text("❌ Сессия устарела")
        return
    
    if data == "skip_date":
        await query.edit_message_text(f"✅ Уважаемый(ая) {user_name}, пропущено ввод даты")
        # Переходим к вводу дня недели
        keyboard = [
            [InlineKeyboardButton("Пропустить день", callback_data="skip_day")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="search_schedule")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            f"📋 Уважаемый(ая) {user_name}, введите день недели ({', '.join(RUSSIAN_DAYS.values())}) или нажмите 'Пропустить день':",
            reply_markup=reply_markup
        )
    
    elif data == "skip_day":
        await query.edit_message_text(f"✅ Уважаемый(ая) {user_name}, пропущено ввод дня")
        # Выполняем поиск только по группе
        user_state = user_data[user_id]
        group = user_state['group']
        
        await query.message.reply_text(f"🔍 Уважаемый(ая) {user_name}, ищу расписание...")
        
        results = await working_schedule_search_tg(group)
        
        for result in results:
            if len(result) > 4096:
                for i in range(0, len(result), 4096):
                    await query.message.reply_text(result[i:i+4096])
            else:
                await query.message.reply_text(result)
        
        # Очищаем данные
        del user_data[user_id]
        
        # Предлагаем новый поиск
        keyboard = [[InlineKeyboardButton("🔍 Новый поиск", callback_data="search_schedule")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"Уважаемый(ая) {user_name}, хотите выполнить новый поиск?", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user_name = update.message.from_user.first_name
    help_text = (
        f"❓ Уважаемый(ая) {user_name}, помощь по использованию бота:\n\n"
        "🔍 Умный поиск - показывает все доступные дни для группы и позволяет выбрать конкретный день\n\n"
        "📅 Поиск с фильтрами - поиск по конкретной дате или дню недели\n\n"
        "📅 Сегодня - поиск расписания на текущий день\n"
        "📅 Завтра - поиск расписания на завтрашний день\n"
        "🚀 1П065 - быстрый поиск для группы 1П065\n\n"
        "💻 Команды:\n"
        "/start - начать работу\n"
        "/zamena [группа] [дата/день] - поиск расписания\n"
        "/pe [дата/день] - быстрый поиск для 1П065\n"
        "/today [группа] - расписание на сегодня\n"
        "/tomorrow [группа] - расписание на завтра\n"
        "/info - информация о боте\n"
        "/help - показать эту справку\n\n"
        "📝 Примеры:\n"
        "/zamena 1п065\n"
        "/zamena 1п065 15.01.2024\n"
        "/zamena 1п065 ПОНЕДЕЛЬНИК\n"
        "/pe\n"
        "/pe 20.01.2024\n"
        "/pe ПОНЕДЕЛЬНИК\n"
        "/today 1п065\n"
        "/tomorrow 1п065"
    )
    await update.message.reply_text(help_text)

async def post_init(application: Application):
    """Функция инициализации после запуска бота"""
    await set_bot_commands(application)

def main():
    """Основная функция"""
    # ЗАМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ ТОКЕН!
    BOT_TOKEN = "8458169643:AAG1eT_VuHllWykR-Bvvm8yRhX0ueY80-U4"
    
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("zamena", zamena))
    application.add_handler(CommandHandler("pe", pe_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("tomorrow", tomorrow_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(main_menu|search_schedule|smart_search|filtered_search|today_schedule|tomorrow_schedule|quick_1p065|info|help)$"))
    application.add_handler(CallbackQueryHandler(skip_handler, pattern="^(skip_date|skip_day)$"))
    application.add_handler(CallbackQueryHandler(day_selection_handler, pattern="^(day_|show_all)"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()