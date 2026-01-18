# minimal_bot.py - БЕЗОПАСНАЯ ВЕРСИЯ ТЕЛЕГРАМ БОТА ДЛЯ TRAVEL COMPANION
import logging
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime
import sys
import traceback
from sqlalchemy import text
import time
from typing import Optional
import json

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Проверяем наличие database.py
database_path = os.path.join(os.path.dirname(__file__), 'database.py')
if not os.path.exists(database_path):
    logging.warning(f"⚠️  Файл database.py не найден по пути: {database_path}")
    # Создаем простую заглушку для базы данных
    class DatabaseStub:
        class User:
            telegram_id = None
            username = None
            first_name = None
            last_name = None
            language_code = None
            is_bot = None
            registration_date = None
            last_active = None
            role = None
            has_car = False
            car_model = None
            car_color = None
            car_plate = None
            car_type = None
            car_seats = None
            phone = None
            total_driver_trips = 0
            total_passenger_trips = 0
            driver_rating = 0.0
            passenger_rating = 0.0
        
        class UserRole:
            PASSENGER = "passenger"
            DRIVER = "driver"
        
        class DriverTrip:
            id = None
            driver_id = None
            driver = None
            start_address = ""
            finish_address = ""
            departure_date = None
            available_seats = 0
            price_per_seat = 0
            status = None
            bookings = []
        
        class TripStatus:
            ACTIVE = "active"
            COMPLETED = "completed"
            CANCELLED = "cancelled"
        
        class Booking:
            id = None
            passenger_id = None
            driver_trip_id = None
            driver_trip = None
            booked_seats = 0
            price_agreed = 0
            status = None
            booked_at = None
        
        class engine:
            pass
        
        @staticmethod
        def Base():
            class BaseStub:
                metadata = type('metadata', (), {'create_all': lambda x: None})()
            return BaseStub()
    
    database = DatabaseStub()
    logging.info("✅ Используется заглушка для базы данных")
else:
    try:
        import database
        logging.info("✅ База данных успешно импортирована")
    except Exception as e:
        logging.error(f"❌ Ошибка импорта database.py: {e}")
        # Используем заглушку при ошибке импорта
        class DatabaseStub:
            class User:
                telegram_id = None
                username = None
                first_name = None
                last_name = None
                language_code = None
                is_bot = None
                registration_date = None
                last_active = None
                role = None
                has_car = False
                car_model = None
                car_color = None
                car_plate = None
                car_type = None
                car_seats = None
                phone = None
                total_driver_trips = 0
                total_passenger_trips = 0
                driver_rating = 0.0
                passenger_rating = 0.0
            
            class UserRole:
                PASSENGER = "passenger"
                DRIVER = "driver"
            
            class DriverTrip:
                id = None
                driver_id = None
                driver = None
                start_address = ""
                finish_address = ""
                departure_date = None
                available_seats = 0
                price_per_seat = 0
                status = None
                bookings = []
            
            class TripStatus:
                ACTIVE = "active"
                COMPLETED = "completed"
                CANCELLED = "cancelled"
            
            class Booking:
                id = None
                passenger_id = None
                driver_trip_id = None
                driver_trip = None
                booked_seats = 0
                price_agreed = 0
                status = None
                booked_at = None
            
            class engine:
                pass
            
            @staticmethod
            def Base():
                class BaseStub:
                    metadata = type('metadata', (), {'create_all': lambda x: None})()
                return BaseStub()
        
        database = DatabaseStub()
        logging.info("✅ Используется заглушка для базы данных из-за ошибки импорта")

load_dotenv()

# =============== НАСТРОЙКИ ===============
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://zhyvvu.github.io/travel-companion-app/")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Проверка обязательных переменных
if not BOT_TOKEN:
    logging.critical("❌ TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
    print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
    print("   Создайте файл .env и добавьте TELEGRAM_BOT_TOKEN=ваш_токен")
    exit(1)

if not DATABASE_URL:
    logging.warning("⚠️  DATABASE_URL не установлен. Бот будет работать в упрощенном режиме")

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
    try:
        from sqlalchemy.orm import Session
        return Session(database.engine)
    except:
        return None

# =============== НОВЫЕ ФУНКЦИИ ДЛЯ WEB APP АВТОРИЗАЦИИ ===============

def create_user_response(user):
    """Создать JSON-ответ с данными пользователя"""
    return {
        "success": True,
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "username": user.username or "",
            "language_code": user.language_code or "ru",
            "is_premium": getattr(user, 'is_premium', False),
            "role": user.role if hasattr(user, 'role') else "passenger",
            "has_car": getattr(user, 'has_car', False),
            "car_model": getattr(user, 'car_model', None),
            "car_color": getattr(user, 'car_color', None),
            "car_plate": getattr(user, 'car_plate', None),
            "car_type": getattr(user, 'car_type', None),
            "car_seats": getattr(user, 'car_seats', None),
            "total_driver_trips": getattr(user, 'total_driver_trips', 0),
            "total_passenger_trips": getattr(user, 'total_passenger_trips', 0),
            "driver_rating": float(getattr(user, 'driver_rating', 5.0)),
            "passenger_rating": float(getattr(user, 'passenger_rating', 5.0))
        },
        "token": f"tg_{user.telegram_id}_{int(time.time())}"
    }

# =============== WEB HANDLERS ДЛЯ FASTAPI (добавим в main.py) ===============
# Эти функции будут вызываться из main.py

def handle_telegram_auth(user_data: dict):
    """
    Обработка авторизации через Telegram WebApp
    """
    try:
        logger.info(f"📱 Запрос авторизации: {user_data}")
        
        # Извлекаем данные пользователя из разных форматов
        if "user" in user_data:
            # Формат: { "user": { ... } }
            telegram_user = user_data["user"]
        else:
            # Формат: данные пользователя напрямую
            telegram_user = user_data
        
        telegram_id = int(telegram_user.get("id"))
        
        if not telegram_id:
            logger.error("❌ Telegram ID is required")
            return {"success": False, "error": "Telegram ID is required"}
        
        # Получаем сессию базы данных
        db = get_db_session()
        if not db:
            logger.error("❌ Database connection failed")
            # Возвращаем тестового пользователя
            return {
                "success": True,
                "user": {
                    "id": 1,
                    "telegram_id": telegram_id,
                    "first_name": telegram_user.get("first_name", "Тестовый"),
                    "last_name": telegram_user.get("last_name", "Пользователь"),
                    "username": telegram_user.get("username", ""),
                    "language_code": telegram_user.get("language_code", "ru"),
                    "is_premium": telegram_user.get("is_premium", False),
                    "role": "passenger",
                    "has_car": False
                },
                "token": f"test_{telegram_id}_{int(time.time())}"
            }
        
        try:
            # Ищем существующего пользователя
            user = db.query(database.User).filter(
                database.User.telegram_id == telegram_id
            ).first()
            
            if not user:
                # Создаем нового пользователя
                logger.info(f"👤 Создание нового пользователя: {telegram_id}")
                
                # Проверяем наличие необходимых атрибутов в модели
                user_data_dict = {
                    "telegram_id": telegram_id,
                    "first_name": telegram_user.get("first_name", ""),
                    "last_name": telegram_user.get("last_name", ""),
                    "username": telegram_user.get("username", ""),
                    "language_code": telegram_user.get("language_code", "ru"),
                    "registration_date": datetime.utcnow(),
                    "last_active": datetime.utcnow()
                }
                
                # Добавляем дополнительные поля, если они есть в модели
                if hasattr(database.User, 'is_premium'):
                    user_data_dict['is_premium'] = telegram_user.get("is_premium", False)
                
                if hasattr(database.User, 'role'):
                    user_data_dict['role'] = getattr(database, 'UserRole', type('obj', (), {'PASSENGER': 'passenger'})()).PASSENGER
                
                if hasattr(database.User, 'is_bot'):
                    user_data_dict['is_bot'] = telegram_user.get("is_bot", False)
                
                # Создаем пользователя
                user = database.User(**user_data_dict)
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info(f"✅ Пользователь создан: {user.id}")
                
            else:
                # Обновляем существующего пользователя
                logger.info(f"🔄 Обновление пользователя: {user.id}")
                user.first_name = telegram_user.get("first_name", user.first_name)
                user.last_name = telegram_user.get("last_name", user.last_name)
                user.username = telegram_user.get("username", user.username)
                user.language_code = telegram_user.get("language_code", user.language_code)
                user.last_active = datetime.utcnow()
                
                if hasattr(user, 'is_premium'):
                    user.is_premium = telegram_user.get("is_premium", getattr(user, 'is_premium', False))
                
                db.commit()
                logger.info(f"✅ Пользователь обновлен: {user.id}")
            
            # Создаем ответ
            response = create_user_response(user)
            logger.info(f"✅ Авторизация успешна для пользователя: {telegram_id}")
            
            return response
            
        except Exception as db_error:
            logger.error(f"❌ Ошибка работы с БД: {db_error}")
            return {"success": False, "error": f"Database error: {str(db_error)}"}
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"❌ Ошибка авторизации: {e}")
        traceback.print_exc()
        return {"success": False, "error": str(e)}

def handle_simple_auth(user_data: dict):
    """
    Упрощенная авторизация для тестирования
    """
    try:
        telegram_id = user_data.get("telegram_id")
        if not telegram_id:
            return {"success": False, "error": "No telegram_id"}
        
        logger.info(f"🔄 Упрощенная авторизация для: {telegram_id}")
        
        # Проверяем базу данных
        db = get_db_session()
        if db:
            try:
                user = db.query(database.User).filter(
                    database.User.telegram_id == telegram_id
                ).first()
                
                if user:
                    response = create_user_response(user)
                    db.close()
                    return response
                    
                # Если пользователя нет, создаем
                user = database.User(
                    telegram_id=telegram_id,
                    first_name=user_data.get("first_name", "Пользователь"),
                    last_name=user_data.get("last_name", ""),
                    username=user_data.get("username", ""),
                    registration_date=datetime.utcnow(),
                    last_active=datetime.utcnow()
                )
                
                if hasattr(database.User, 'role'):
                    user.role = getattr(database, 'UserRole', type('obj', (), {'PASSENGER': 'passenger'})()).PASSENGER
                
                if hasattr(database.User, 'language_code'):
                    user.language_code = user_data.get("language_code", "ru")
                
                db.add(user)
                db.commit()
                db.refresh(user)
                
                response = create_user_response(user)
                db.close()
                return response
                
            except Exception as db_error:
                logger.error(f"❌ Ошибка БД в простой авторизации: {db_error}")
                db.close()
        
        # Если БД недоступна, возвращаем тестовые данные
        logger.info("ℹ️ БД недоступна, возвращаем тестового пользователя")
        return {
            "success": True,
            "user": {
                "id": 999,
                "telegram_id": telegram_id,
                "first_name": user_data.get("first_name", "Тестовый"),
                "last_name": user_data.get("last_name", "Пользователь"),
                "username": user_data.get("username", "test_user"),
                "language_code": user_data.get("language_code", "ru"),
                "is_premium": False,
                "role": "passenger",
                "has_car": False,
                "total_driver_trips": 0,
                "total_passenger_trips": 0,
                "driver_rating": 5.0,
                "passenger_rating": 5.0
            },
            "token": f"simple_{telegram_id}_{int(time.time())}"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка простой авторизации: {e}")
        return {"success": False, "error": str(e)}

def handle_debug_check_auth(telegram_id: Optional[int] = None):
    """Эндпоинт для отладки авторизации"""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "telegram_id": telegram_id,
        "has_user": telegram_id is not None,
        "cors_enabled": True,
        "service": "Travel Companion Auth",
        "version": "3.0"
    }

# =============== ОБРАБОТЧИКИ ТЕЛЕГРАМ БОТА ===============

async def help_no_db_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопки помощи при отсутствии БД"""
    query = update.callback_query
    await query.answer()
    
    help_text = """
🆘 *Режим без базы данных*

Бот работает в ограниченном режиме из-за проблем с подключением к базе данных.

*Что доступно:*
• Открытие Web App приложения
• Основные команды (/help, /about, /app)
• Общение с ботом

*Что недоступно:*
• Сохранение профиля
• Создание и поиск поездок
• Статистика
• История поездок

*Решение:*
1. Проверьте подключение к интернету
2. Убедитесь, что база данных запущена
3. Перезапустите бота позже

Для продолжения используйте кнопку "Открыть Travel Companion" ниже.
"""
    
    keyboard = [[
        InlineKeyboardButton(
            "🚗 Открыть Travel Companion",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        help_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветствие и кнопка Mini App"""
    user = update.effective_user
    
    try:
        logger.info(f"Пользователь {user.id} ({user.username}) запустил бота")
        
        welcome_msg = ""
        db = None
        
        # Проверяем доступность базы данных из контекста бота
        db_available = False
        try:
            if context.bot_data and 'db_available' in context.bot_data:
                db_available = context.bot_data['db_available']
        except:
            pass
        
        if db_available:
            try:
                db = get_db_session()
                if db is None:
                    raise Exception("Сессия БД не создана")
                
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
                        last_name=user.last_name or "",
                        language_code=user.language_code or "ru",
                        is_bot=user.is_bot or False,
                        registration_date=datetime.utcnow(),
                        last_active=datetime.utcnow(),
                        role=getattr(database, 'UserRole', type('obj', (), {'PASSENGER': 'passenger'})()).PASSENGER
                    )
                    db.add(new_user)
                    db.commit()
                    welcome_msg = "🎉 Добро пожаловать! Вы зарегистрированы в системе!"
                    logger.info(f"Создан новый пользователь: {user.id}")
                else:
                    # Обновляем время последней активности
                    existing_user.last_active = datetime.utcnow()
                    existing_user.first_name = user.first_name or existing_user.first_name
                    existing_user.last_name = user.last_name or existing_user.last_name
                    existing_user.username = user.username or existing_user.username
                    db.commit()
                    welcome_msg = "👋 С возвращением!"
                    logger.info(f"Пользователь обновлен: {user.id}")
                    
            except Exception as db_error:
                logger.error(f"Ошибка работы с БД в start: {db_error}")
                welcome_msg = "👋 Добро пожаловать! (ограниченный режим - БД недоступна)"
                db_available = False
            finally:
                if db:
                    try:
                        db.close()
                    except:
                        pass
        else:
            welcome_msg = "👋 Добро пожаловать! (режим без базы данных)"
            logger.info(f"Пользователь {user.id} - режим без БД")
        
        welcome_text = f"""
👋 Привет, {user.first_name or 'друг'}! {welcome_msg}

🚗 Travel Companion — сервис поиска попутчиков для путешествий!

✨ Что умеет бот:
• 🔍 Найти поездку с попутчиками
• 🚗 Создать свою поездку
• 👥 Найти пассажиров для своей машины
• 💬 Общаться с попутчиками
• ⭐ Оставлять отзывы и рейтинги

🎯 Как начать:
1. Нажмите кнопку "Открыть приложение" ниже
2. В приложении авторизуйтесь через Telegram
3. Начните искать поездки или создавайте свои!

📱 Быстрые команды:
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
        
        # Добавляем кнопку "Помощь" если БД недоступна
        if not db_available:
            keyboard.append([
                InlineKeyboardButton(
                    "🆘 Помощь (без БД)",
                    callback_data="help_no_db"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode=None,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Критическая ошибка в start command: {e}")
        traceback.print_exc()
        
        # Упрощенное сообщение на случай критической ошибки
        try:
            keyboard = [[
                InlineKeyboardButton(
                    "🚗 Открыть Travel Companion",
                    web_app=WebAppInfo(url=MINI_APP_URL)
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            simple_text = f"""
👋 Привет, {user.first_name or 'друг'}!

🚗 Travel Companion — сервис поиска попутчиков для путешествий!

Нажмите кнопку ниже, чтобы открыть приложение и начать пользоваться сервисом!

📱 Основные команды:
/start - Главное меню
/help - Помощь
/about - О проекте
/app - Открыть приложение
"""
            
            await update.message.reply_text(
                simple_text,
                reply_markup=reply_markup,
                parse_mode=None
            )
            logger.info(f"Упрощенное сообщение отправлено пользователю {user.id}")
            
        except Exception as final_error:
            logger.critical(f"Даже упрощенное сообщение не отправилось: {final_error}")
            try:
                await update.message.reply_text(
                    f"Привет! Я бот Travel Companion. Используйте /help для помощи."
                )
            except:
                pass

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил помощь")
    
    help_text = """
🆘 Помощь по Travel Companion

Основные возможности:
• Поиск поездок — найдите попутчиков по нужному маршруту
• Создание поездок — предложите свою поездку и найдите пассажиров
• Бронирование — забронируйте место в поездке
• Рейтинги — оставляйте отзывы после поездок

Как использовать:
1. Нажмите кнопку "Открыть Travel Companion"
2. Разрешите доступ к вашим данным Telegram
3. Заполните профиль (особенно если вы водитель)
4. Начните искать или создавать поездки!

Команды бота:
/start - Главное меню
/help - Эта справка
/about - О проекте
/app - Быстрый доступ к приложению
/profile - Ваш профиль
/stats - Статистика системы
/my_trips - Мои поездки
"""
    
    await update.message.reply_text(help_text, parse_mode=None)

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил информацию о проекте")
    
    about_text = """
📱 Travel Companion

Версия: 3.0
Разработчик: Команда Travel Companion

О проекте:
Travel Companion — это сервис для поиска попутчиков в путешествиях. 
Мы помогаем людям находить попутчиков для совместных поездок, 
экономить на путешествиях и находить новых друзей.

Основные функции:
• Умный поиск поездок по маршруту и дате
• Создание собственных поездок
• Система бронирования и подтверждения
• Система рейтингов и отзывов
• Поддержка Telegram Web App

Технологии:
• Backend: Python, FastAPI, SQLAlchemy
• Frontend: HTML/CSS/JavaScript, Telegram Web App
• База данных: PostgreSQL
• Хостинг: GitHub Pages + Render.com
"""
    
    await update.message.reply_text(about_text, parse_mode=None)

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
    
    db_available = False
    try:
        if context.bot_data and 'db_available' in context.bot_data:
            db_available = context.bot_data['db_available']
    except:
        pass
    
    if not db_available:
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Открыть Travel Companion",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📊 *Статистика недоступна*\n\n"
            "База данных временно недоступна. Статистика системы не может быть получена.\n\n"
            "Попробуйте позже или используйте приложение:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    db = get_db_session()
    
    try:
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
💾 *База данных:* {'PostgreSQL' if DATABASE_URL and 'postgres' in DATABASE_URL else 'SQLite'}
"""
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("😕 Произошла ошибка при получении статистики.")
    finally:
        if db:
            db.close()

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /profile - профиль пользователя"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил профиль")
    
    db_available = False
    try:
        if context.bot_data and 'db_available' in context.bot_data:
            db_available = context.bot_data['db_available']
    except:
        pass
    
    if not db_available:
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Открыть Travel Companion",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👤 *Профиль недоступен*\n\n"
            "База данных временно недоступна. Ваш профиль не может быть загружен.\n\n"
            "Попробуйте позже или используйте приложение:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    db = get_db_session()
    
    try:
        db_user = db.query(database.User).filter(
            database.User.telegram_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы в системе.\n"
                "Используйте /start для регистрации."
            )
            return
        
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
        if db:
            db.close()

async def my_trips_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /my_trips - мои поездки"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} запросил свои поездки")
    
    db_available = False
    try:
        if context.bot_data and 'db_available' in context.bot_data:
            db_available = context.bot_data['db_available']
    except:
        pass
    
    if not db_available:
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Открыть Travel Companion",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📍 *Мои поездки недоступны*\n\n"
            "База данных временно недоступна. Ваши поездки не могут быть загружены.\n\n"
            "Попробуйте позже или используйте приложение:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    db = get_db_session()
    
    try:
        db_user = db.query(database.User).filter(
            database.User.telegram_id == user.id
        ).first()
        
        if not db_user:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы в системе.\n"
                "Используйте /start для регистрации."
            )
            return
        
        driver_trips = db.query(database.DriverTrip).filter(
            database.DriverTrip.driver_id == db_user.id
        ).order_by(database.DriverTrip.departure_date.desc()).limit(5).all()
        
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
        if db:
            db.close()

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
    
    print("🔧 Конфигурация:")
    print(f"   Бот токен: {'✅ Установлен' if BOT_TOKEN else '❌ Отсутствует'}")
    print(f"   Mini App URL: {MINI_APP_URL}")
    print(f"   Database URL: {'Установлен' if DATABASE_URL else '❌ Не установлен'}")
    
    if DATABASE_URL:
        if "postgresql" in DATABASE_URL or "postgres://" in DATABASE_URL:
            print("   Тип БД: PostgreSQL")
        elif "sqlite" in DATABASE_URL:
            print("   Тип БД: SQLite")
        else:
            print("   Тип БД: Неизвестен")
    
    if not BOT_TOKEN:
        print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
        print("   Создайте файл .env и добавьте TELEGRAM_BOT_TOKEN=ваш_токен")
        return
    
    print("\n🗄️  Инициализация базы данных...")
    db_available = True
    
    try:
        from sqlalchemy.orm import Session
        from sqlalchemy import text
        
        test_session = Session(database.engine)
        test_session.execute(text("SELECT 1"))
        test_session.close()
        print("✅ Подключение к базе данных успешно")
        
    except Exception as e:
        print(f"❌ ОШИБКА подключения к базе: {e}")
        db_available = False
    
    if db_available:
        try:
            print("📋 Создание таблиц...")
            database.Base.metadata.create_all(bind=database.engine)
            print("✅ Таблицы базы данных созданы/проверены")
            
        except Exception as e:
            print(f"❌ ОШИБКА создания таблиц: {e}")
            db_available = False
    
    if not db_available:
        print("\n⚠️  Бот запускается без базы данных!")
        print("   Функционал будет ограничен:")
        print("   - Регистрация пользователей не будет сохраняться")
        print("   - Статистика недоступна")
        print("   - Поездки не будут сохраняться")
        print("   - Профили будут временными")
        
        continue_choice = input("\n   Продолжить? (y/n): ").lower()
        if continue_choice != 'y':
            print("❌ Завершение работы...")
            return
        print("🔄 Продолжаем в режиме без базы данных...")
    
    print("\n📱 Функционал бота:")
    print("   • /start - Главное меню с регистрацией")
    print("   • /help - Подробная справка")
    print("   • /about - Информация о проекте")
    print("   • /app - Быстрый доступ к приложению")
    print("   • /profile - Профиль пользователя")
    print("   • /stats - Статистика системы")
    print("   • /my_trips - Мои поездки")
    
    print("\n🌐 WEB APP API функции:")
    print("   • handle_telegram_auth() - Полная авторизация Telegram")
    print("   • handle_simple_auth() - Упрощенная авторизация")
    print("   • handle_debug_check_auth() - Отладка авторизации")
    print("=" * 60)
    
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        
        application.bot_data['db_available'] = db_available
        
        print("🔗 Регистрация обработчиков команд...")
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("about", about_command))
        application.add_handler(CommandHandler("app", app_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("profile", profile_command))
        application.add_handler(CommandHandler("my_trips", my_trips_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(CallbackQueryHandler(help_no_db_callback, pattern="^help_no_db$"))
        
        application.add_error_handler(error_handler)
        
        print("✅ Бот запущен успешно!")
        print("🔄 Ожидание сообщений...")
        print("⚠️  Для остановки нажмите Ctrl+C")
        print("=" * 60)
        
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=0.5,
            timeout=30
        )
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Бот остановлен пользователем")
        print("👋 До свидания!")
        
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    main()