# main.py - ОПТИМИЗИРОВАННЫЙ API ДЛЯ TELEGRAM WEB APP
import threading
import time
from sqlalchemy import text
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_
from datetime import datetime, timedelta
import database
from typing import List, Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import json
import hashlib
import hmac
import os
import sys

from minimal_bot import (
    handle_telegram_auth, 
    handle_simple_auth, 
    handle_debug_check_auth
)

def format_user_response(user: database.User) -> dict:
    """Форматирует ответ с данными пользователя"""
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "has_car": user.has_car,
        "car_info": {
            "model": user.car_model,
            "color": user.car_color,
            "plate": user.car_plate,
            "type": user.car_type.value if user.car_type else None,
            "seats": user.car_seats
        } if user.has_car else None,
        "ratings": {
            "driver": user.driver_rating,
            "passenger": user.passenger_rating
        },
        "stats": {
            "driver_trips": user.total_driver_trips,
            "passenger_trips": user.total_passenger_trips
        },
        "role": user.role.value if user.role else "passenger",
        "phone": user.phone
    }

def format_trip_response(trip: database.DriverTrip) -> dict:
    """Форматирует ответ с данными поездки"""
    driver = trip.driver
    return {
        "id": trip.id,
        "driver": {
            "id": driver.id,
            "name": f"{driver.first_name} {driver.last_name or ''}".strip(),
            "rating": driver.driver_rating,
            "phone": driver.phone
        },
        "route": {
            "from": trip.start_address,
            "to": trip.finish_address,
            "from_city": trip.start_city,
            "to_city": trip.finish_city
        },
        "departure": {
            "date": trip.departure_date.strftime("%Y-%m-%d"),
            "time": trip.departure_time,
            "datetime": trip.departure_date.strftime("%d.%m.%Y %H:%M")
        },
        "seats": {
            "available": trip.available_seats,
            "price_per_seat": trip.price_per_seat
        },
        "details": {
            "comment": trip.comment
        },
        "car_info": {
            "model": driver.car_model,
            "color": driver.car_color,
            "plate": driver.car_plate,
            "type": driver.car_type.value if driver.car_type else None
        } if driver.has_car else None,
        "status": trip.status.value,
        "estimated_arrival": trip.estimated_arrival.isoformat() if hasattr(trip, 'estimated_arrival') and trip.estimated_arrival else None
    }

def update_trip_statuses(db: Session):
    """Автоматическое завершение поездок по истечении времени"""
    now = datetime.utcnow()
    
    # В твоей базе модель называется DriverTrip
    trips = db.query(database.DriverTrip).filter(
        database.DriverTrip.status == database.TripStatus.ACTIVE
    ).all()
    
    for trip in trips:
        # Время завершения = Выезд + Длительность (из БД) + 15 мин запас
        duration = trip.route_duration or 0
        arrival_time = trip.departure_date + timedelta(minutes=duration + 15)
        
        if arrival_time < now:
            trip.status = database.TripStatus.COMPLETED
            print(f"Поездка {trip.id} автоматически завершена")
            
    db.commit()

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from extract_city import extract_city
except ImportError:
    # Заглушка если extract_city не существует
    def extract_city(address):
        return address.split(',')[0] if address else ""

UserCar = database.UserCar

# Telegram Bot Token для верификации данных (если нужно)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


# =============== PYDANTIC МОДЕЛИ ===============

# 1. СНАЧАЛА базовые модели для карт
class MapPoint(BaseModel):
    lat: float
    lng: float
    address: Optional[str] = None

class RouteData(BaseModel):
    start_point: MapPoint
    finish_point: MapPoint
    distance: Optional[float] = None  # километры
    duration: Optional[int] = None    # минуты
    polyline: Optional[str] = None    # геометрия маршрута

# 2. Telegram модели
class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = "ru"  # Добавил значение по умолчанию
    is_premium: bool = False  # Значение по умолчанию
    photo_url: Optional[str] = None

class LoginRequest(BaseModel):
    initData: Optional[str] = None
    user: Optional[TelegramUser] = None

# 3. Поездки
class TripCreate(BaseModel):
    from_city: str
    to_city: str
    departure_time: str
    route_duration: Optional[int] = 0  # Добавили для приема времени с фронтенда
    seats_available: int = Field(gt=0)
    price: float = Field(ge=0)
    description: Optional[str] = None
    route_data: Optional[Dict[str, Any]] = None

class BookingCreate(BaseModel):
    driver_trip_id: int
    booked_seats: int = Field(1, ge=1, le=10)
    notes: Optional[str] = None

# 4. Пользователи
class UserUpdate(BaseModel):
    phone: Optional[str] = None
    has_car: Optional[bool] = None
    car_model: Optional[str] = None
    car_color: Optional[str] = None
    car_plate: Optional[str] = None
    car_type: Optional[str] = None
    car_seats: Optional[int] = None

# 5. Поиск
class SearchQuery(BaseModel):
    from_city: str
    to_city: str
    date: str
    passengers: int = 1
    max_price: Optional[float] = None

# 6. Автомобили
class CarCreate(BaseModel):
    model: str
    color: Optional[str] = None
    license_plate: Optional[str] = None
    car_type: Optional[str] = None
    year: Optional[int] = None
    seats: int = 4
    is_default: bool = False

class CarUpdate(BaseModel):
    model: Optional[str] = None
    color: Optional[str] = None
    license_plate: Optional[str] = None
    car_type: Optional[str] = None
    year: Optional[int] = None
    seats: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

# 7. Обновления
class BookingUpdate(BaseModel):
    booked_seats: Optional[int] = Field(None, ge=1, le=10)
    notes: Optional[str] = None

class DriverTripUpdate(BaseModel):
    available_seats: Optional[int] = Field(None, ge=1, le=10)
    price_per_seat: Optional[float] = Field(None, gt=0)
    departure_date: Optional[datetime] = None
    departure_time: Optional[str] = Field(None, pattern=r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$')
    comment: Optional[str] = None
    start_address: Optional[str] = None
    finish_address: Optional[str] = None

# =============== FASTAPI APP ===============
app = FastAPI(
    title="Travel Companion API",
    version="3.0",
    description="API для сервиса поиска попутчиков с Telegram авторизацией"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://zhyvvu.github.io",  # Ваш GitHub Pages
        "https://zhyvvu.github.io/travel-companion-app/",
        "http://localhost:5500",      # Для локальной разработки
        "http://localhost:8000",
        "*"  # На время отладки, потом удалите
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware для обработки Telegram данных
@app.middleware("http")
async def add_telegram_user(request: Request, call_next):
    """Извлекаем данные пользователя Telegram из заголовков"""
    try:
        telegram_id = request.headers.get("X-Telegram-User-Id")
        if telegram_id:
            request.state.telegram_id = int(telegram_id)
        else:
            request.state.telegram_id = None
    except:
        request.state.telegram_id = None
    
    response = await call_next(request)
    return response

# =============== STARTUP EVENT ===============
@app.on_event("startup")
async def startup_event():
    """Создание таблиц, проверка структуры БД и запуск фоновых задач"""
    print("=" * 60)
    print("🚀 ЗАПУСК TRAVEL COMPANION API (Версия с картами)")
    print("=" * 60)
    
    try:
        # 1. Создаем таблицы в базе данных
        print("🗄️  Создание/проверка таблиц базы данных...")
        database.Base.metadata.create_all(bind=database.engine)
        print("✅ Таблицы базы данных созданы/проверены")
        
        # 2. Проверяем подключение к базе данных
        print("🔌 Проверка подключения к базе данных...")
        from sqlalchemy import text
        
        session = database.SessionLocal()
        try:
            result = session.execute(text("SELECT 1"))
            session.commit()
            
            if result.scalar() == 1:
                print("✅ Подключение к базе данных успешно")
            else:
                print("⚠️  Неожиданный результат проверки БД")
                
        except Exception as e:
            print(f"❌ Ошибка подключения к базе: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            session.close()
        
        # 3. ПРОВЕРЯЕМ И ДОБАВЛЯЕМ ОТСУТСТВУЮЩИЕ ПОЛЯ ДЛЯ КАРТ
        print("🔄 Проверяем и добавляем поля для карт...")
        session = database.SessionLocal()
        try:
            # Список полей для проверки/добавления
            fields_to_add = [
                {
                    'name': 'estimated_arrival',
                    'type': 'TIMESTAMP',
                    'description': 'Предполагаемое время прибытия'
                },
                {
                    'name': 'start_coordinates',
                    'type': 'JSONB' if 'postgresql' in os.getenv('DATABASE_URL', '') else 'JSON',
                    'description': 'Координаты начала маршрута'
                },
                {
                    'name': 'finish_coordinates',
                    'type': 'JSONB' if 'postgresql' in os.getenv('DATABASE_URL', '') else 'JSON',
                    'description': 'Координаты конца маршрута'
                },
                {
                    'name': 'route_polyline',
                    'type': 'TEXT',
                    'description': 'Закодированная геометрия маршрута'
                }
            ]
            
            added_fields = []
            
            for field in fields_to_add:
                try:
                    # Проверяем существует ли поле в таблице driver_trips
                    result = session.execute(text(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'driver_trips' 
                        AND column_name = '{field['name']}'
                    """))
                    
                    if not result.fetchone():
                        print(f"   ➕ Добавляем поле: {field['name']} ({field['description']})")
                        
                        # Добавляем поле в таблицу
                        if 'postgresql' in os.getenv('DATABASE_URL', ''):
                            # Для PostgreSQL
                            session.execute(text(f"""
                                ALTER TABLE driver_trips 
                                ADD COLUMN {field['name']} {field['type']}
                            """))
                        else:
                            # Для SQLite
                            session.execute(text(f"""
                                ALTER TABLE driver_trips 
                                ADD COLUMN {field['name']} {field['type']}
                            """))
                        
                        session.commit()
                        added_fields.append(field['name'])
                        print(f"   ✅ Поле {field['name']} успешно добавлено")
                    else:
                        print(f"   ✓ Поле {field['name']} уже существует")
                        
                except Exception as field_error:
                    print(f"   ⚠️  Ошибка при работе с полем {field['name']}: {str(field_error)[:100]}")
                    session.rollback()
            
            if added_fields:
                print(f"✅ Добавлены новые поля: {', '.join(added_fields)}")
            else:
                print("✅ Все необходимые поля уже существуют")
            
            # Проверяем общую структуру таблицы driver_trips
            print("\n📊 Структура таблицы driver_trips:")
            result = session.execute(text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'driver_trips'
                ORDER BY column_name
            """))
            
            columns = result.fetchall()
            print(f"   Всего столбцов: {len(columns)}")
            
            # Отображаем только поля связанные с картами
            map_columns = [col for col in columns if any(field in col[0] for field in 
                          ['coordinates', 'polyline', 'estimated', 'route_'])]
            
            for col in map_columns:
                print(f"   • {col[0]}: {col[1]}")
            
        except Exception as e:
            print(f"⚠️  Ошибка проверки структуры БД: {e}")
        finally:
            session.close()
        
        # 4. ЗАПУСКАЕМ ФОНОВУЮ ЗАДАЧУ ДЛЯ ОБНОВЛЕНИЯ СТАТУСОВ
        print("\n🔄 Запуск фоновой задачи для обновления статусов...")
        try:
            # Функция для фоновой задачи
            def update_trip_statuses_task():
                """Фоновая задача для автоматического обновления статусов поездок"""
                import time
                from datetime import datetime, timedelta
                
                print("   📡 Фоновая задача запущена")
                
                # Счетчик циклов для логирования
                cycle_count = 0
                
                while True:
                    cycle_count += 1
                    current_time = datetime.utcnow()
                    
                    # Создаем новую сессию для каждого цикла
                    db_session = None
                    try:
                        db_session = database.SessionLocal()
                        
                        # 4.1. Обновляем поездки, которые должны начаться (ACTIVE → IN_PROGRESS)
                        active_trips = db_session.query(database.DriverTrip).filter(
                            database.DriverTrip.status == database.TripStatus.ACTIVE,
                            database.DriverTrip.departure_date <= current_time
                        ).all()
                        
                        if active_trips:
                            print(f"   🚗 {len(active_trips)} поездок начинаются...")
                            for trip in active_trips:
                                trip.status = database.TripStatus.IN_PROGRESS
                                trip.updated_at = current_time
                        
                        # 4.2. Обновляем поездки, которые должны завершиться (IN_PROGRESS → COMPLETED)
                        in_progress_trips = db_session.query(database.DriverTrip).filter(
                            database.DriverTrip.status == database.TripStatus.IN_PROGRESS
                        ).all()
                        
                        completed_count = 0
                        for trip in in_progress_trips:
                            # Определяем время завершения поездки
                            arrival_time = None
                            
                            # Пытаемся использовать estimated_arrival если поле существует
                            try:
                                if hasattr(trip, 'estimated_arrival') and trip.estimated_arrival:
                                    arrival_time = trip.estimated_arrival
                            except:
                                pass
                            
                            # Если estimated_arrival не доступен, используем расчетное время
                            if not arrival_time:
                                if hasattr(trip, 'route_duration') and trip.route_duration:
                                    # Используем длительность маршрута
                                    arrival_time = trip.departure_date + timedelta(minutes=trip.route_duration)
                                else:
                                    # По умолчанию: 3 часа
                                    arrival_time = trip.departure_date + timedelta(hours=3)
                            
                            # Если время прибытия прошло, завершаем поездку
                            if arrival_time <= current_time:
                                trip.status = database.TripStatus.COMPLETED
                                trip.updated_at = current_time
                                completed_count += 1
                        
                        if completed_count > 0:
                            print(f"   ✅ {completed_count} поездок завершены")
                        
                        # Коммитим изменения
                        db_session.commit()
                        
                        # 4.3. Логируем статистику каждые 10 циклов (≈10 минут)
                        if cycle_count % 10 == 0:
                            try:
                                stats = {
                                    "active": db_session.query(database.DriverTrip).filter(
                                        database.DriverTrip.status == database.TripStatus.ACTIVE
                                    ).count(),
                                    "in_progress": db_session.query(database.DriverTrip).filter(
                                        database.DriverTrip.status == database.TripStatus.IN_PROGRESS
                                    ).count(),
                                    "completed": db_session.query(database.DriverTrip).filter(
                                        database.DriverTrip.status == database.TripStatus.COMPLETED
                                    ).count(),
                                    "cancelled": db_session.query(database.DriverTrip).filter(
                                        database.DriverTrip.status == database.TripStatus.CANCELLED
                                    ).count(),
                                }
                                
                                print(f"   📊 Статистика: "
                                      f"ACTIVE={stats['active']}, "
                                      f"IN_PROGRESS={stats['in_progress']}, "
                                      f"COMPLETED={stats['completed']}, "
                                      f"CANCELLED={stats['cancelled']} "
                                      f"({datetime.now().strftime('%H:%M:%S')})")
                            except Exception as stats_error:
                                print(f"   ⚠️  Ошибка статистики: {stats_error}")
                        
                        # 4.4. Закрываем сессию
                        db_session.close()
                        
                        # 4.5. Ждем 60 секунд перед следующей проверкой
                        time.sleep(60)
                        
                    except Exception as task_error:
                        print(f"   ❌ Ошибка в фоновой задаче (цикл {cycle_count}): {task_error}")
                        
                        # Закрываем сессию если она открыта
                        if db_session:
                            try:
                                db_session.rollback()
                                db_session.close()
                            except:
                                pass
                        
                        # Ждем дольше при ошибке
                        time.sleep(30)
            
            # Запускаем фоновую задачу в отдельном потоке
            import threading
            background_thread = threading.Thread(
                target=update_trip_statuses_task,
                daemon=True,  # Поток завершится при завершении основного процесса
                name="TripStatusUpdater"
            )
            background_thread.start()
            
            print("✅ Фоновая задача для обновления статусов запущена")
            print(f"   Поток: {background_thread.name} (ID: {background_thread.ident})")
            print(f"   Интервал проверки: 60 секунд")
            
        except Exception as e:
            print(f"❌ Ошибка запуска фоновой задачи: {e}")
            import traceback
            traceback.print_exc()
        
        # 5. ВЫВОДИМ ИНФОРМАЦИЮ О КОНФИГУРАЦИИ
        print("\n⚙️  Конфигурация системы:")
        
        # Информация о БД
        db_url = os.getenv("DATABASE_URL", "")
        if "postgresql" in db_url:
            print(f"   База данных: PostgreSQL")
            # Маскируем пароль в URL для безопасности
            if "@" in db_url:
                parts = db_url.split("@")
                if ":" in parts[0]:
                    user_part = parts[0].split(":")[0]
                    masked_url = f"{user_part}:****@{parts[1]}"
                    print(f"   URL: {masked_url}")
        else:
            print(f"   База данных: SQLite")
        
        # Другие настройки
        print(f"   Хост: 0.0.0.0")
        print(f"   Порт: {os.getenv('PORT', 8000)}")
        print(f"   Токен Telegram бота: {'✅ Установлен' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ Отсутствует'}")
        
        # Проверяем ключ Яндекс.Карт
        yandex_key = os.getenv("YANDEX_MAPS_API_KEY")
        if yandex_key:
            # Показываем только часть ключа для безопасности
            key_preview = yandex_key[:8] + "..." + yandex_key[-4:] if len(yandex_key) > 12 else yandex_key
            print(f"   Ключ Яндекс.Карт: ✅ ({key_preview})")
        else:
            print(f"   Ключ Яндекс.Карт: ⚠️  Не установлен")
            print(f"      Установите переменную окружения YANDEX_MAPS_API_KEY")
        
        print("=" * 60)
        print("✅ Сервер успешно запущен и готов к работе!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Критическая ошибка при запуске: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 60)
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Действия при остановке сервера"""
    print("\n" + "=" * 60)
    print("🛑 ОСТАНОВКА TRAVEL COMPANION API")
    print("=" * 60)
    
    try:
        # Закрываем все соединения с базой данных
        print("🔌 Закрытие соединений с базой данных...")
        
        # Можно добавить логику для graceful shutdown
        # Например, ожидание завершения фоновых задач
        
        print("✅ Соединения закрыты")
        
    except Exception as e:
        print(f"⚠️  Ошибка при остановке: {e}")
    
    print("👋 Сервер остановлен")
    print("=" * 60)
# =============== РОУТЫ ===============

@app.get("/")
def home():
    return {
        "project": "Travel Companion",
        "version": "3.0",
        "description": "Сервис поиска попутчиков с Telegram авторизацией и картами",
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "docs": "/docs",
        "health": "/health",
        "api_base": "/api"
    }

# =============== TELEGRAM АВТОРИЗАЦИЯ ===============
@app.post("/api/auth/telegram")
async def telegram_auth(login_data: Dict[str, Any] = None, db: Session = Depends(database.get_db)):
    """Авторизация через Telegram WebApp"""
    try:
        print(f"🔐 Auth request received")
        
        user_data = None
        
        # Разные форматы данных
        if login_data and 'user' in login_data:
            user_data = login_data['user']
            print(f"✅ Using 'user' key format")
        elif login_data and 'id' in login_data and 'first_name' in login_data:
            user_data = login_data
            print(f"✅ Using direct user object format")
        elif login_data and 'initData' in login_data and 'user' in login_data:
            user_data = login_data['user']
            print(f"✅ Using LoginRequest format")
        
        if not user_data:
            print(f"❌ No user data found")
            raise HTTPException(status_code=400, detail="Необходимы данные пользователя")
        
        # Используем улучшенную функцию из minimal_bot.py
        auth_result = handle_telegram_auth(user_data)
        
        if auth_result.get("success"):
            print(f"✅ Auth successful for Telegram ID: {user_data.get('id')}")
            return auth_result
        else:
            print(f"❌ Auth failed: {auth_result.get('error')}")
            raise HTTPException(status_code=401, detail=auth_result.get('error', 'Auth failed'))
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Auth error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Ошибка авторизации: {str(e)}")
    
@app.post("/api/auth/simple")
async def simple_auth(user_data: dict):
    """Упрощенная авторизация для тестирования"""
    try:
        print(f"🔄 Simple auth request: {user_data.get('telegram_id')}")
        result = handle_simple_auth(user_data)
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get('error', 'Auth failed'))
            
        return result
        
    except Exception as e:
        print(f"❌ Simple auth error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug/check-auth")
async def debug_check_auth(telegram_id: Optional[int] = Query(None)):
    """Эндпоинт для отладки авторизации"""
    return handle_debug_check_auth(telegram_id)

@app.get("/api/auth/me")
def get_current_user(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Получить данные текущего пользователя"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    user.last_active = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "user": format_user_response(user)
    }

# =============== ПОЛЬЗОВАТЕЛИ ===============
@app.put("/api/users/update")
def update_user_profile(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    update_data: UserUpdate = None,
    db: Session = Depends(database.get_db)
):
    """Обновить профиль пользователя"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if update_data:
        update_dict = update_data.dict(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(user, key, value)
        
        if update_data.has_car and not user.has_car:
            if user.role == database.UserRole.PASSENGER:
                user.role = database.UserRole.BOTH
            elif user.role is None:
                user.role = database.UserRole.DRIVER
        
        if update_data.has_car is False and user.has_car:
            if user.role == database.UserRole.DRIVER:
                user.role = database.UserRole.PASSENGER
            elif user.role == database.UserRole.BOTH:
                user.role = database.UserRole.PASSENGER
    
    user.last_active = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "message": "Профиль обновлен",
        "user": {
            "has_car": user.has_car,
            "car_model": user.car_model,
            "car_color": user.car_color,
            "car_plate": user.car_plate,
            "phone": user.phone,
            "role": user.role.value if user.role else None
        }
    }

# =============== ПОЕЗДКИ ===============
@app.post("/api/trips/search")
def search_trips(
    search_query: SearchQuery,
    db: Session = Depends(database.get_db)
):
    """Поиск доступных поездок"""
    try:
        date_obj = datetime.strptime(search_query.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты. Используйте YYYY-MM-DD")
    
    # Базовый запрос
    query = db.query(database.DriverTrip).filter(
        database.DriverTrip.status == database.TripStatus.ACTIVE,
        database.DriverTrip.available_seats >= search_query.passengers,
        database.DriverTrip.departure_date >= date_obj,
        database.DriverTrip.departure_date < date_obj + timedelta(days=1)
    )
    
    # Добавляем фильтры по городам
    if search_query.from_city:
        query = query.filter(or_(
            database.DriverTrip.start_city.ilike(f"%{search_query.from_city}%"),
            database.DriverTrip.start_address.ilike(f"%{search_query.from_city}%")
        ))
    
    if search_query.to_city:
        query = query.filter(or_(
            database.DriverTrip.finish_city.ilike(f"%{search_query.to_city}%"),
            database.DriverTrip.finish_address.ilike(f"%{search_query.to_city}%")
        ))
    
    # Фильтр по цене
    if search_query.max_price:
        query = query.filter(database.DriverTrip.price_per_seat <= search_query.max_price)
    
    # Сортировка
    trips = query.order_by(
        database.DriverTrip.departure_date,
        database.DriverTrip.price_per_seat
    ).all()
    
    # Формируем ответ
    result = []
    for trip in trips:
        driver = trip.driver
        result.append({
            "id": trip.id,
            "driver": {
                "id": driver.id,
                "name": f"{driver.first_name} {driver.last_name or ''}".strip(),
                "rating": driver.driver_rating,
                "avatar_initials": f"{driver.first_name[0]}{driver.last_name[0] if driver.last_name else ''}"
            },
            "route": {
                "from": trip.start_address,
                "to": trip.finish_address,
                "from_city": trip.start_city,
                "to_city": trip.finish_city
            },
            "departure": {
                "date": trip.departure_date.strftime("%Y-%m-%d"),
                "time": trip.departure_time,
                "datetime": trip.departure_date.strftime("%d.%m.%Y %H:%M")
            },
            "seats": {
                "available": trip.available_seats,
                "price_per_seat": trip.price_per_seat
            },
            "car_info": {
                "model": driver.car_model,
                "color": driver.car_color
            } if driver.has_car else None,
            "details": {
                "comment": trip.comment
            },
            "status": trip.status.value,
            "estimated_arrival": trip.estimated_arrival.isoformat() if hasattr(trip, 'estimated_arrival') and trip.estimated_arrival else None
        })
    
    return {
        "success": True,
        "count": len(result),
        "trips": result
    }

@app.get("/api/trips/my")
def get_my_trips(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Получить мои поездки"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    driver_trips = db.query(database.DriverTrip).filter(
        database.DriverTrip.driver_id == user.id
    ).order_by(desc(database.DriverTrip.departure_date)).all()
    
    passenger_bookings = db.query(database.Booking).filter(
        database.Booking.passenger_id == user.id
    ).order_by(desc(database.Booking.booked_at)).all()
    
    result = {
        "as_driver": [],
        "as_passenger": []
    }
    
    for trip in driver_trips:
        result["as_driver"].append({
            "id": trip.id,
            "route": {
                "from": trip.start_address,
                "to": trip.finish_address
            },
            "date": trip.departure_date.strftime("%d.%m.%Y %H:%M"),
            "available_seats": trip.available_seats,
            "price_per_seat": trip.price_per_seat,
            "status": trip.status.value,
            "bookings_count": len(trip.bookings)
        })
    
    for booking in passenger_bookings:
        trip = booking.driver_trip
        result["as_passenger"].append({
            "id": booking.id,
            "trip_id": trip.id,
            "driver_name": f"{trip.driver.first_name} {trip.driver.last_name or ''}".strip(),
            "route": {
                "from": trip.start_address,
                "to": trip.finish_address
            },
            "date": trip.departure_date.strftime("%d.%m.%Y %H:%M"),
            "seats": booking.booked_seats,
            "price": booking.price_agreed or trip.price_per_seat,
            "status": booking.status.value
        })
    
    return {
        "success": True,
        "user_id": user.id,
        "trips": result
    }

@app.post("/api/trips/create")
def create_trip(trip_data: TripCreate, db: Session = Depends(database.get_db), user_id: int = Query(...)):
    user = db.query(database.User).filter(database.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Извлекаем координаты для удобства
    start_coords = trip_data.route_data.get('start_point', {})
    finish_coords = trip_data.route_data.get('finish_point', {})

    # Собираем данные СТРОГО по твоей модели DriverTrip
    new_trip_data = {
        "driver_id": user.id,
        
        # Локации (используем данные из route_data)
        "start_address": start_coords.get('address', 'Точка на карте'),
        "start_city": start_coords.get('city', 'Не указан'),
        "start_lat": start_coords.get('lat'),
        "start_lng": start_coords.get('lng'),
        
        "finish_address": finish_coords.get('address', 'Точка на карте'),
        "finish_city": finish_coords.get('city', 'Не указан'),
        "finish_lat": finish_coords.get('lat'),
        "finish_lng": finish_coords.get('lng'),
        
        # Данные маршрута
        "route_distance": trip_data.route_data.get('distance', 0),
        "route_duration": trip_data.route_duration,
        "start_coordinates": start_coords, # JSON поле
        "finish_coordinates": finish_coords, # JSON поле
        
        # Детали поездки (названия полей из твоей модели)
        "available_seats": trip_data.seats_available,
        "price_per_seat": trip_data.price,
        "comment": trip_data.description,
        
        # Статус
        "status": database.TripStatus.ACTIVE,
    }
    
    # Обработка даты (твоя логика)
    try:
        # Принимаем строку вида "2023-10-27T12:00" или "2023-10-27 12:00"
        raw_dt = trip_data.departure_time.replace('T', ' ')
        # Убираем лишние символы, если они просочились (Z или +00:00)
        raw_dt = raw_dt.replace('Z', '').split('+')[0]
        
        departure_dt = datetime.fromisoformat(raw_dt)
        
        new_trip_data["departure_date"] = departure_dt
        new_trip_data["departure_time"] = departure_dt.strftime("%H:%M")
    except Exception as e:
        print(f"❌ Ошибка парсинга даты: {e}")
        # Заглушка: текущее время + 3 часа (если не вышло распарсить)
        new_trip_data["departure_date"] = datetime.now()
        new_trip_data["departure_time"] = datetime.now().strftime("%H:%M")

    # Создаем объект модели
    try:
        db_trip = database.DriverTrip(**new_trip_data)
        db.add(db_trip)
        db.commit()
        db.refresh(db_trip)
        return {"success": True, "trip_id": db_trip.id}
    except Exception as db_e:
        db.rollback()
        print(f"❌ Ошибка базы данных: {db_e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(db_e)}")
    
    #db.add(db_trip)
    #db.commit()
    #db.refresh(db_trip)
    #return {"success": True, "trip_id": db_trip.id}

@app.get("/api/trips/{trip_id}")
def get_trip_details(
    trip_id: int,
    db: Session = Depends(database.get_db)
):
    """Получить детали поездки"""
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == trip_id
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена")
    
    driver = trip.driver
    
    return {
        "success": True,
        "trip": {
            "id": trip.id,
            "driver": {
                "id": driver.id,
                "name": f"{driver.first_name} {driver.last_name or ''}".strip(),
                "rating": driver.driver_rating,
                "phone": driver.phone
            },
            "route": {
                "from": trip.start_address,
                "to": trip.finish_address,
                "from_city": trip.start_city,
                "to_city": trip.finish_city
            },
            "departure": {
                "date": trip.departure_date.strftime("%Y-%m-%d"),
                "time": trip.departure_time,
                "datetime": trip.departure_date.strftime("%d.%m.%Y %H:%M")
            },
            "seats": {
                "available": trip.available_seats,
                "price_per_seat": trip.price_per_seat
            },
            "details": {
                "comment": trip.comment
            },
            "car_info": {
                "model": driver.car_model,
                "color": driver.car_color,
                "plate": driver.car_plate,
                "type": driver.car_type.value if driver.car_type else None
            } if driver.has_car else None,
            "status": trip.status.value
        }
    }

# =============== БРОНИРОВАНИЯ ===============
@app.post("/api/bookings/create")
def create_booking(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    booking_data: BookingCreate = None,
    db: Session = Depends(database.get_db)
):
    """Создать бронирование"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == booking_data.driver_trip_id,
        database.DriverTrip.status == database.TripStatus.ACTIVE
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена или недоступна")
    
    if trip.available_seats < booking_data.booked_seats:
        raise HTTPException(status_code=400, detail="Недостаточно свободных мест")
    
    existing_booking = db.query(database.Booking).filter(
        database.Booking.driver_trip_id == booking_data.driver_trip_id,
        database.Booking.passenger_id == user.id,
        database.Booking.status == database.TripStatus.ACTIVE
    ).first()
    
    if existing_booking:
        raise HTTPException(status_code=400, detail="Вы уже забронировали эту поездку")
    
    booking = database.Booking(
        driver_trip_id=booking_data.driver_trip_id,
        passenger_id=user.id,
        booked_seats=booking_data.booked_seats,
        price_agreed=trip.price_per_seat,
        notes=booking_data.notes,
        status=database.TripStatus.ACTIVE
    )
    
    trip.available_seats -= booking_data.booked_seats
    if trip.available_seats <= 0:
        trip.status = database.TripStatus.COMPLETED
    
    db.add(booking)
    db.commit()
    db.refresh(booking)
    
    user.total_passenger_trips += 1
    db.commit()
    
    return {
        "success": True,
        "message": "Место успешно забронировано",
        "booking_id": booking.id
    }

# =============== ОТМЕНА ПОЕЗДКИ ВОДИТЕЛЯ ===============
@app.post("/api/trips/{trip_id}/cancel")
def cancel_driver_trip(
    trip_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Отменить поездку водителя"""
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == trip_id
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена")
    
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if trip.driver_id != user.id:
        raise HTTPException(status_code=403, detail="Вы не можете отменить чужую поездку")
    
    if trip.status != database.TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Поездка уже не активна")
    
    # Отменяем все бронирования этой поездки
    cancelled_bookings = 0
    for booking in trip.bookings:
        if booking.status == database.TripStatus.ACTIVE:
            booking.status = database.TripStatus.CANCELLED
            booking.cancelled_at = datetime.utcnow()
            cancelled_bookings += 1
    
    # Меняем статус поездки
    trip.status = database.TripStatus.CANCELLED
    db.commit()
    
    return {
        "success": True,
        "message": "Поездка отменена",
        "cancelled_bookings": cancelled_bookings
    }

# =============== СТАТИСТИКА ===============
@app.get("/stats")
def stats(db: Session = Depends(database.get_db)):
    """Статистика системы"""
    try:
        stats_data = {
            "database": "PostgreSQL" if "postgresql" in os.getenv("DATABASE_URL", "") else "SQLite",
            "timestamp": datetime.now().isoformat(),
            "tables": {
                "users": db.query(database.User).count(),
                "drivers": db.query(database.User).filter(database.User.has_car == True).count(),
                "passengers": db.query(database.User).filter(database.User.has_car == False).count(),
                "driver_trips": db.query(database.DriverTrip).count(),
                "active_trips": db.query(database.DriverTrip).filter(
                    database.DriverTrip.status == database.TripStatus.ACTIVE
                ).count(),
                "bookings": db.query(database.Booking).count(),
                "active_bookings": db.query(database.Booking).filter(
                    database.Booking.status == database.TripStatus.ACTIVE
                ).count()
            }
        }
        return stats_data
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# =============== АВТОМОБИЛИ ===============
@app.get("/api/users/cars")
def get_user_cars(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Получить автомобили пользователя"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    cars = db.query(UserCar).filter(
        UserCar.user_id == user.id,
        UserCar.is_active == True
    ).order_by(UserCar.is_default.desc(), UserCar.created_at).all()
    
    result = []
    for car in cars:
        result.append({
            "id": car.id,
            "model": car.model,
            "color": car.color,
            "license_plate": car.license_plate,
            "car_type": car.car_type,
            "year": car.year,
            "seats": car.seats,
            "is_default": car.is_default
        })
    
    return {
        "success": True,
        "count": len(result),
        "cars": result
    }

@app.post("/api/users/cars")
def create_user_car(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    car_data: CarCreate = None,
    db: Session = Depends(database.get_db)
):
    """Добавить автомобиль пользователю"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    if car_data.is_default:
        existing_cars = db.query(UserCar).filter(
            UserCar.user_id == user.id,
            UserCar.is_default == True
        ).all()
        
        for car in existing_cars:
            car.is_default = False
    
    car = UserCar(
        user_id=user.id,
        model=car_data.model,
        color=car_data.color,
        license_plate=car_data.license_plate,
        car_type=car_data.car_type,
        year=car_data.year,
        seats=car_data.seats,
        is_default=car_data.is_default,
        is_active=True
    )
    
    db.add(car)
    db.commit()
    
    user.has_car = True
    if not user.car_model:
        user.car_model = car_data.model
        user.car_color = car_data.color
        user.car_plate = car_data.license_plate
        user.car_seats = car_data.seats
    
    db.commit()
    
    return {
        "success": True,
        "message": "Автомобиль добавлен",
        "car_id": car.id
    }

# =============== ПРОФИЛЬ ===============
@app.get("/api/users/profile-full")
def get_full_user_profile(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Получить полный профиль пользователя"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Автомобили
    cars = db.query(UserCar).filter(
        UserCar.user_id == user.id,
        UserCar.is_active == True
    ).order_by(UserCar.is_default.desc()).all()
    
    # Поездки как водитель
    driver_trips = db.query(database.DriverTrip).filter(
        database.DriverTrip.driver_id == user.id
    ).order_by(database.DriverTrip.departure_date.desc()).limit(10).all()
    
    # Бронирования как пассажир
    passenger_bookings = db.query(database.Booking).filter(
        database.Booking.passenger_id == user.id
    ).order_by(database.Booking.booked_at.desc()).limit(10).all()
    
    cars_result = []
    for car in cars:
        cars_result.append({
            "id": car.id,
            "model": car.model,
            "color": car.color,
            "license_plate": car.license_plate,
            "car_type": car.car_type,
            "seats": car.seats,
            "is_default": car.is_default
        })
    
    driver_trips_result = []
    for trip in driver_trips:
        driver_trips_result.append({
            "id": trip.id,
            "from": trip.start_address,
            "to": trip.finish_address,
            "date": trip.departure_date.strftime("%d.%m.%Y %H:%M"),
            "seats": trip.available_seats,
            "price": trip.price_per_seat,
            "status": trip.status.value if trip.status else "active",
            "passengers_count": len(trip.bookings)
        })
    
    passenger_trips_result = []
    for booking in passenger_bookings:
        trip = booking.driver_trip
        if trip and trip.driver:
            passenger_trips_result.append({
                "id": booking.id,
                "trip_id": trip.id,
                "driver_name": f"{trip.driver.first_name} {trip.driver.last_name or ''}".strip(),
                "from": trip.start_address,
                "to": trip.finish_address,
                "date": trip.departure_date.strftime("%d.%m.%Y %H:%M") if trip.departure_date else "",
                "seats": booking.booked_seats,
                "price": booking.price_agreed or (trip.price_per_seat if trip else 0),
                "status": booking.status.value if booking.status else "active"
            })
    
    return {
        "success": True,
        "user": {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "phone": user.phone,
            "role": user.role.value if user.role else "passenger",
            "ratings": {
                "driver": user.driver_rating,
                "passenger": user.passenger_rating
            },
            "stats": {
                "driver_trips": user.total_driver_trips,
                "passenger_trips": user.total_passenger_trips
            }
        },
        "cars": cars_result,
        "driver_trips": driver_trips_result,
        "passenger_trips": passenger_trips_result
    }

# =============== HEALTH CHECK ===============
@app.get("/health")
def health_check(db: Session = Depends(database.get_db)):
    """Проверка состояния API"""
    try:
        # Проверяем подключение к БД
        db.execute("SELECT 1")
        db_status = "connected"
    except:
        db_status = "disconnected"
    
    return {
        "status": "healthy",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "Travel Companion API",
        "version": "3.0"
    }

@app.get("/api/debug/users")
def debug_users(db: Session = Depends(database.get_db)):
    """Показать всех пользователей (для отладки)"""
    users = db.query(database.User).all()
    
    result = []
    for user in users:
        result.append({
            "id": user.id,
            "telegram_id": user.telegram_id,
            "first_name": user.first_name,
            "username": user.username,
            "has_car": user.has_car,
            "registration_date": user.registration_date.isoformat() if user.registration_date else None
        })
    
    return {
        "success": True,
        "count": len(result),
        "users": result
    }

@app.post("/api/trips/update-statuses")
def manual_update_statuses(db: Session = Depends(database.get_db)):
    """Ручное обновление статусов поездок (для отладки)"""
    try:
        update_trip_statuses(db)
        return {"success": True, "message": "Статусы обновлены"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =============== ЗАПУСК СЕРВЕРА ===============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)