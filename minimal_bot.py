# minimal_bot.py - БЕЗОПАСНАЯ ВЕРСИЯ ТЕЛЕГРАМ БОТА ДЛЯ TRAVEL COMPANION
import logging
import os
from dotenv import load_dotenv
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import sys

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем нашу базу данных
import database
from sqlalchemy.orm import Session

load_dotenv()

# =============== НАСТРОЙКИ ===============
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://zhyvvu.github.io/travel-companion-app/")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Проверка обязательных переменных
if not BOT_TOKEN:
    logging.critical("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
    exit(1)

if not DATABASE_URL:
    logging.warning("⚠️  DATABASE_URL не установлен. Бот будет использовать локальную SQLite")

# =============== ЛОГИРОВАНИЕ ===============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# =============== УТИЛИТЫ ===============
def get_db_session():
    """Получить сессию базы данных"""
    return Session(database.engine)

# =============== ФУНКЦИИ БОТА ===============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветствие и кнопка Mini App"""
    user = update.effective_user
    
    # Получаем сессию базы данных
    db = get_db_session()
    
    try:
        logger.info(f"Пользователь {user.id} ({user.username}) запустил бота")
        
        # Проверяем, есть ли пользователь в базе
        existing_user = db.query(database.User).filter(
            database.User.telegram_id == user.id
        ).first()
        
        if not existing_user:
            # Создаем нового пользователя
            new_user = database.User(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name or "",
                last_name=user.last_name,
                language_code=user.language_code,
                is_bot=user.is_bot,
                registration_date=datetime.utcnow(),
                last_active=datetime.utcnow(),
                role=database.UserRole.PASSENGER
            )
            db.add(new_user)
            db.commit()
            welcome_msg = "🎉 Добро пожаловать! Вы зарегистрированы в системе!"
        else:
            # Обновляем время последней активности
            existing_user.last_active = datetime.utcnow()
            db.commit()
            welcome_msg = "👋 С возвращением!"
        
        welcome_text = f"""
👋 Привет, {user.first_name}! {welcome_msg}

🚗 *Travel Companion* — сервис поиска попутчиков для путешествий!

✨ *Что умеет бот:*
• 🔍 Найти поездку с попутчиками
• 🚗 Создать свою поездку
• 👥 Найти пассажиров для своей машины
• 💬 Общаться с попутчиками
• ⭐ Оставлять отзывы и рейтинги

🎯 *Как начать:*
1. Нажмите кнопку *"Открыть приложение"* ниже
2. В приложении авторизуйтесь через Telegram
3. Начните искать поездки или создавайте свои!

📱 *Быстрые команды:*
/start - Показать это сообщение
/help - Получить справку
/about - О проекте
/app - Открыть приложение
/profile - Ваш профиль
/stats - Статистика системы
/my_trips - Мои поездки
"""
        
        # Создаем клавиатуру с кнопкой Mini App
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Открыть Travel Companion",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("😕 Произошла ошибка. Попробуйте позже.")
    finally:
        db.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил помощь")
    
    help_text = """
🆘 *Помощь по Travel Companion*

*Основные возможности:*
• *Поиск поездок* — найдите попутчиков по нужному маршруту
• *Создание поездок* — предложите свою поездку и найдите пассажиров
• *Бронирование* — забронируйте место в поездке
• *Рейтинги* — оставляйте отзывы после поездок

*Как использовать:*
1. Нажмите кнопку *"Открыть Travel Companion"*
2. Разрешите доступ к вашим данным Telegram
3. Заполните профиль (особенно если вы водитель)
4. Начните искать или создавать поездки!

*Команды бота:*
/start - Главное меню
/help - Эта справка
/about - О проекте
/app - Быстрый доступ к приложению
/profile - Ваш профиль
/stats - Статистика системы
/my_trips - Мои поездки
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил информацию о проекте")
    
    about_text = """
📱 *Travel Companion*

*Версия:* 3.0
*Разработчик:* Команда Travel Companion

*О проекте:*
Travel Companion — это сервис для поиска попутчиков в путешествиях. 
Мы помогаем людям находить попутчиков для совместных поездок, 
экономить на путешествиях и находить новых друзей.

*Основные функции:*
• Умный поиск поездок по маршруту и дате
• Создание собственных поездок
• Система бронирования и подтверждения
• Система рейтингов и отзывов
• Поддержка Telegram Web App

*Технологии:*
• Backend: Python, FastAPI, SQLAlchemy
• Frontend: HTML/CSS/JavaScript, Telegram Web App
• База данных: PostgreSQL
• Хостинг: GitHub Pages + Render.com
"""
    
    await update.message.reply_text(about_text, parse_mode='Markdown')

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /app - быстрый доступ к приложению"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил прямое открытие приложения")
    
    keyboard = [[
        InlineKeyboardButton(
            "🚗 Открыть Travel Companion",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Нажмите кнопку ниже, чтобы открыть приложение:",
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats - статистика"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил статистику")
    
    db = get_db_session()
    
    try:
        # Получаем статистику из базы
        stats = {
            "users": db.query(database.User).count(),
            "drivers": db.query(database.User).filter(database.User.has_car == True).count(),
            "passengers": db.query(database.User).filter(database.User.has_car == False).count(),
            "trips": db.query(database.DriverTrip).count(),
            "active_trips": db.query(database.DriverTrip).filter(
                database.DriverTrip.status == database.TripStatus.ACTIVE
            ).count(),
            "bookings": db.query(database.Booking).count(),
            "active_bookings": db.query(database.Booking).filter(
                database.Booking.status == database.TripStatus.ACTIVE
            ).count()
        }
        
        # Получаем последние 5 пользователей
        recent_users = db.query(database.User).order_by(
            database.User.registration_date.desc()
        ).limit(5).all()
        
        recent_users_text = ""
        for u in recent_users:
            recent_users_text += f"• {u.first_name} ({u.registration_date.strftime('%d.%m.%Y')})\n"
        
        stats_text = f"""
📊 *Статистика системы Travel Companion*

👥 *Пользователи:*
• Всего: {stats['users']}
• Водителей: {stats['drivers']}
• Пассажиров: {stats['passengers']}

📍 *Поездки:*
• Всего: {stats['trips']}
• Активных: {stats['active_trips']}

🎫 *Бронирования:*
• Всего: {stats['bookings']}
• Активных: {stats['active_bookings']}

🆕 *Последние пользователи:*
{recent_users_text if recent_users_text else "• Нет новых пользователей"}

🕐 *Время сервера:* {datetime.now().strftime('%H:%M %d.%m.%Y')}
💾 *База данных:* PostgreSQL
"""
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("😕 Произошла ошибка при получении статистики.")
    finally:
        db.close()

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile - профиль пользователя"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил профиль")
    
    db = get_db_session()
    
    try:
        # Ищем пользователя в базе
        db_user = db.query(database.User).filter(
            database.User.telegram_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы в системе.\n"
                "Используйте /start для регистрации."
            )
            return
        
        # Формируем текст профиля
        profile_text = f"""
👤 *Ваш профиль*

*Основное:*
• Имя: {db_user.first_name} {db_user.last_name or ''}
• Username: @{db_user.username or 'не указан'}
• Телефон: {db_user.phone or 'не указан'}
• Роль: {db_user.role.value if db_user.role else 'пассажир'}

*Автомобиль:*
• Есть автомобиль: {'✅ Да' if db_user.has_car else '❌ Нет'}
"""
        
        if db_user.has_car:
            profile_text += f"""
• Модель: {db_user.car_model or 'не указана'}
• Цвет: {db_user.car_color or 'не указан'}
• Номер: {db_user.car_plate or 'не указан'}
• Тип: {db_user.car_type.value if db_user.car_type else 'не указан'}
• Мест: {db_user.car_seats or 'не указано'}
"""
        
        profile_text += f"""
📊 *Статистика:*
• Поездок как водитель: {db_user.total_driver_trips}
• Поездок как пассажир: {db_user.total_passenger_trips}
• Рейтинг водителя: {db_user.driver_rating:.1f}/5
• Рейтинг пассажира: {db_user.passenger_rating:.1f}/5

📅 *Дата регистрации:* {db_user.registration_date.strftime('%d.%m.%Y')}
🕐 *Последняя активность:* {db_user.last_active.strftime('%d.%m.%Y %H:%M') if db_user.last_active else 'неизвестно'}

ℹ️ *Для редактирования профиля откройте приложение:*
"""
        
        keyboard = [[
            InlineKeyboardButton(
                "✏️ Редактировать профиль",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            profile_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in profile command: {e}")
        await update.message.reply_text("😕 Произошла ошибка при получении профиля.")
    finally:
        db.close()

async def my_trips_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /my_trips - мои поездки"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил свои поездки")
    
    db = get_db_session()
    
    try:
        # Ищем пользователя в базе
        db_user = db.query(database.User).filter(
            database.User.telegram_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы в системе.\n"
                "Используйте /start для регистрации."
            )
            return
        
        # Поездки как водитель
        driver_trips = db.query(database.DriverTrip).filter(
            database.DriverTrip.driver_id == db_user.id
        ).order_by(database.DriverTrip.departure_date.desc()).limit(5).all()
        
        # Бронирования как пассажир
        passenger_bookings = db.query(database.Booking).filter(
            database.Booking.passenger_id == db_user.id
        ).order_by(database.Booking.booked_at.desc()).limit(5).all()
        
        if not driver_trips and not passenger_bookings:
            keyboard = [[
                InlineKeyboardButton(
                    "🚗 Создать первую поездку",
                    web_app=WebAppInfo(url=MINI_APP_URL)
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 У вас еще нет поездок.\n\n"
                "Создайте свою первую поездку или найдите попутчиков!",
                reply_markup=reply_markup
            )
            return
        
        trips_text = "📍 *Ваши поездки*\n\n"
        
        if driver_trips:
            trips_text += "🚗 *Как водитель:*\n"
            for trip in driver_trips:
                trips_text += f"""
• *Маршрут:* {trip.start_address[:20]}... → {trip.finish_address[:20]}...
• *Дата:* {trip.departure_date.strftime('%d.%m.%Y %H:%M')}
• *Мест:* {trip.available_seats} | *Цена:* {trip.price_per_seat}₽
• *Статус:* {trip.status.value}
• *Пассажиров:* {len(trip.bookings)}
"""
        
        if passenger_bookings:
            trips_text += "\n👤 *Как пассажир:*\n"
            for booking in passenger_bookings:
                trip = booking.driver_trip
                if trip:
                    trips_text += f"""
• *Маршрут:* {trip.start_address[:20]}... → {trip.finish_address[:20]}...
• *Водитель:* {trip.driver.first_name}
• *Дата:* {trip.departure_date.strftime('%d.%m.%Y %H:%M')}
• *Мест:* {booking.booked_seats} | *Цена:* {booking.price_agreed or trip.price_per_seat}₽
• *Статус:* {booking.status.value}
"""
        
        trips_text += "\n🌐 *Для управления поездками откройте приложение:*"
        
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Управлять поездками",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            trips_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error in my_trips command: {e}")
        await update.message.reply_text("😕 Произошла ошибка при получении поездок.")
    finally:
        db.close()

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных из Web App"""
    user = update.effective_user
    data = update.effective_message.web_app_data.data
    
    logger.info(f"Получены данные из Web App от пользователя {user.id}: {data[:50]}...")
    
    try:
        await update.message.reply_text(
            "✅ Данные из приложения получены. Спасибо за использование Travel Companion!",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка обработки данных Web App: {e}")
        await update.message.reply_text(
            "⚠️ Произошла ошибка при обработке данных. Попробуйте еще раз."
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user = update.effective_user
    text = update.message.text.lower()
    
    logger.info(f"Текстовое сообщение от {user.id}: {text[:50]}...")
    
    if any(word in text for word in ['привет', 'hello', 'хай', 'hi']):
        await update.message.reply_text(
            f"Привет, {user.first_name}! Напишите /start чтобы открыть меню приложения 🚗"
        )
    elif any(word in text for word in ['поездк', 'попутчик', 'машин', 'водител']):
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Найти поездку",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Чтобы найти или создать поездку, откройте приложение:",
            reply_markup=reply_markup
        )
    elif any(word in text for word in ['помощь', 'help', 'поддержк', 'problem']):
        await help_command(update, context)
    else:
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Открыть приложение",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Я бот для сервиса Travel Companion. Используйте кнопки ниже или команды:\n\n"
            "/start - Главное меню\n"
            "/help - Помощь\n"
            "/about - О проекте\n"
            "/app - Открыть приложение\n"
            "/profile - Ваш профиль\n"
            "/stats - Статистика\n"
            "/my_trips - Мои поездки",
            reply_markup=reply_markup
        )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка при обработке сообщения: {context.error}")
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Произошла ошибка. Пожалуйста, попробуйте еще раз позже."
            )
        except:
            pass

# =============== ЗАПУСК БОТА ===============
def main():
    """Запуск бота"""
    print("=" * 60)
    print("🤖 ЗАПУСК TELEGRAM БОТА ДЛЯ TRAVEL COMPANION")
    print("=" * 60)
    
    # Проверка конфигурации
    print("🔧 Конфигурация:")
    print(f"   Бот токен: {'✅ Установлен' if BOT_TOKEN else '❌ Отсутствует'}")
    print(f"   Mini App URL: {MINI_APP_URL}")
    print(f"   Database URL: {'✅ PostgreSQL' if DATABASE_URL and 'postgres' in DATABASE_URL else '⚠️  SQLite (локально)'}")
    
    if not BOT_TOKEN:
        print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    print("\n📱 Функционал бота:")
    print("   • /start - Главное меню с регистрацией")
    print("   • /help - Подробная справка")
    print("   • /about - Информация о проекте")
    print("   • /app - Быстрый доступ к приложению")
    print("   • /profile - Профиль пользователя")
    print("   • /stats - Статистика системы")
    print("   • /my_trips - Мои поездки")
    print("=" * 60)
    
    try:
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Регистрируем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("app", app_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("profile", profile_command))
        application.add_handler(CommandHandler("my_trips", my_trips_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Обработчик ошибок
        application.add_error_handler(error_handler)
        
        print("✅ Бот запущен успешно!")
        print("🔄 Ожидание сообщений...")
        print("⚠️  Для остановки нажмите Ctrl+C")
        print("=" * 60)
        
        # Запускаем бота
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
        
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()