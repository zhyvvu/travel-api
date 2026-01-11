# main.py - ОПТИМИЗИРОВАННЫЙ API ДЛЯ TELEGRAM WEB APP
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, and_, func
from datetime import datetime, timedelta
import database
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import json
import hashlib
import hmac
import os
import sys

# Добавляем текущую директорию в путь для импорта
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from extract_city import extract_city

UserCar = database.UserCar

# Telegram Bot Token для верификации данных (если нужно)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Pydantic схемы
class TelegramUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: Optional[str] = None
    is_premium: Optional[bool] = None
    photo_url: Optional[str] = None

class LoginRequest(BaseModel):
    initData: Optional[str] = None
    user: Optional[TelegramUser] = None

class DriverTripCreate(BaseModel):
    departure_date: datetime
    departure_time: str = Field(..., pattern=r'^([0-1][0-9]|2[0-3]):[0-5][0-9]$')
    start_address: str
    start_lat: Optional[float] = None
    start_lng: Optional[float] = None
    finish_address: str
    finish_lat: Optional[float] = None
    finish_lng: Optional[float] = None
    available_seats: int = Field(..., ge=1, le=10)
    price_per_seat: float = Field(..., gt=0)
    comment: Optional[str] = None

class BookingCreate(BaseModel):
    driver_trip_id: int
    booked_seats: int = Field(1, ge=1, le=10)
    notes: Optional[str] = None

class UserUpdate(BaseModel):
    phone: Optional[str] = None
    has_car: Optional[bool] = None
    car_model: Optional[str] = None
    car_color: Optional[str] = None
    car_plate: Optional[str] = None
    car_type: Optional[str] = None
    car_seats: Optional[int] = None

class SearchQuery(BaseModel):
    from_city: str
    to_city: str
    date: str
    passengers: int = 1
    max_price: Optional[float] = None

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


def main():
    # Создаем таблицы если их нет
    try:
        database.Base.metadata.create_all(bind=database.engine)
        logger.info("✅ Таблицы базы данных созданы/проверены")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")

# Функция для проверки Telegram Web App данных (опционально)
def verify_telegram_data(init_data: str, bot_token: str) -> bool:
    """Проверка подписи данных от Telegram"""
    try:
        # Разбираем данные
        pairs = init_data.split('&')
        data_dict = {}
        hash_value = None
        
        for pair in pairs:
            key, value = pair.split('=')
            if key == 'hash':
                hash_value = value
            else:
                data_dict[key] = value
        
        if not hash_value:
            return False
        
        # Создаем строку для проверки
        check_string = '\n'.join([f"{k}={data_dict[k]}" for k in sorted(data_dict.keys())])
        
        # Вычисляем секретный ключ
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        
        # Вычисляем хеш
        calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        
        return calculated_hash == hash_value
    except:
        return False

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Таблицы создаются через миграции Alembic
    # (выполняется в render.yaml на этапе сборки)
    print("✅ Сервер запущен с миграциями Alembic")
    yield
    # При остановке
    print("👋 Сервер останавливается")

app = FastAPI(
    title="Travel Companion API",
    version="3.0",
    description="API для сервиса поиска попутчиков с Telegram авторизацией",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем все источники для простоты
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Middleware для обработки Telegram данных
@app.middleware("http")
async def add_telegram_user(request: Request, call_next):
    """Извлекаем данные пользователя Telegram из заголовков"""
    try:
        # Пытаемся получить telegram_id из заголовков
        telegram_id = request.headers.get("X-Telegram-User-Id")
        if telegram_id:
            request.state.telegram_id = int(telegram_id)
        else:
            request.state.telegram_id = None
    except:
        request.state.telegram_id = None
    
    response = await call_next(request)
    return response

# Главная страница
@app.get("/")
def home():
    return {
        "project": "Travel Companion",
        "version": "3.0",
        "description": "Сервис поиска попутчиков с Telegram авторизацией",
        "status": "active",
        "timestamp": datetime.now().isoformat()
    }

# =============== TELEGRAM АВТОРИЗАЦИЯ ===============

@app.post("/api/auth/telegram")
async def telegram_auth(login_data: Dict[str, Any] = None, db: Session = Depends(database.get_db)):
    """Авторизация через Telegram Web App - упрощенная версия для разных форматов данных"""
    try:
        print(f"🔐 Auth request received. Data type: {type(login_data)}")
        print(f"🔐 Auth request data: {login_data}")
        
        # Пробуем разные форматы данных
        user_data = None
        
        # Формат 1: данные в ключе "user" (старый фронтенд)
        if login_data and 'user' in login_data:
            user_data = login_data['user']
            print(f"✅ Using 'user' key format: {user_data}")
        
        # Формат 2: данные напрямую в корне (новый фронтенд)
        elif login_data and 'id' in login_data and 'first_name' in login_data:
            user_data = login_data
            print(f"✅ Using direct user object format: {user_data}")
        
        # Формат 3: данные в старом формате LoginRequest
        elif login_data and 'initData' in login_data and 'user' in login_data:
            user_data = login_data['user']
            print(f"✅ Using LoginRequest format")
        
        if not user_data:
            print(f"❌ No user data found in request")
            raise HTTPException(status_code=400, detail="Необходимы данные пользователя")
        
        telegram_id = user_data.get('id')
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Отсутствует ID пользователя")
        
        print(f"🆔 Telegram ID: {telegram_id}")
        
        # Проверяем существование пользователя
        user = db.query(database.User).filter(
            database.User.telegram_id == telegram_id
        ).first()
        
        if not user:
            # Создаем нового пользователя
            user = database.User(
                telegram_id=telegram_id,
                username=user_data.get('username'),
                first_name=user_data.get('first_name', ''),
                last_name=user_data.get('last_name'),
                language_code=user_data.get('language_code', 'ru'),
                is_bot=False,
                registration_date=datetime.utcnow(),
                last_active=datetime.utcnow(),
                role=database.UserRole.PASSENGER
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            message = "Новый пользователь зарегистрирован"
            print(f"✅ New user created: {user.first_name} (ID: {user.id})")
        else:
            # Обновляем данные существующего пользователя
            user.username = user_data.get('username') or user.username
            user.first_name = user_data.get('first_name', user.first_name)
            user.last_name = user_data.get('last_name') or user.last_name
            user.language_code = user_data.get('language_code') or user.language_code
            user.last_active = datetime.utcnow()
            db.commit()
            message = "Пользователь авторизован"
            print(f"✅ User updated: {user.first_name} (ID: {user.id})")
        
        # Создаем токен сессии
        session_token = f"telegram_{telegram_id}_{datetime.utcnow().timestamp()}"
        
        return {
            "success": True,
            "message": message,
            "token": session_token,
            "user": {
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
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Auth error details: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка авторизации: {str(e)}")

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
    
    # Обновляем время последней активности
    user.last_active = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "user": {
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
            "role": user.role.value if user.role else None,
            "phone": user.phone,
            "registration_date": user.registration_date.isoformat() if user.registration_date else None,
            "last_active": user.last_active.isoformat() if user.last_active else None
        }
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
        # Обновляем только переданные поля
        update_dict = update_data.dict(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(user, key, value)
        
        # Если добавляем автомобиль, меняем роль
        if update_data.has_car and not user.has_car:
            if user.role == database.UserRole.PASSENGER:
                user.role = database.UserRole.BOTH
            elif user.role is None:
                user.role = database.UserRole.DRIVER
        
        # Если убираем автомобиль, меняем роль
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
    
    # Ищем подходящие поездки
    query = db.query(database.DriverTrip).filter(
        database.DriverTrip.status == database.TripStatus.ACTIVE,
        database.DriverTrip.available_seats >= search_query.passengers,
        database.DriverTrip.departure_date >= date_obj,
        database.DriverTrip.departure_date < date_obj + timedelta(days=1)
    )
    
    # Фильтр по городам
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
    
    # Сортировка по дате и цене
    query = query.order_by(
        database.DriverTrip.departure_date,
        database.DriverTrip.price_per_seat
    )
    
    trips = query.all()
    
    # Фильтр по цене
    if search_query.max_price:
        trips = [t for t in trips if t.price_per_seat <= search_query.max_price]
    
    result = []
    for trip in trips:
        # Получаем данные водителя
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
                "price_per_seat": trip.price_per_seat,
                "total_price": trip.price_per_seat * search_query.passengers
            },
            "details": {
                "distance": trip.route_distance,
                "duration": trip.route_duration,
                "comment": trip.comment,
                "allow_smoking": trip.allow_smoking,
                "allow_animals": trip.allow_animals
            },
            "car_info": {
                "model": driver.car_model,
                "color": driver.car_color,
                "type": driver.car_type.value if driver.car_type else None
            } if driver.has_car else None
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
    
    # Поездки как водителя
    driver_trips = db.query(database.DriverTrip).filter(
        database.DriverTrip.driver_id == user.id
    ).order_by(desc(database.DriverTrip.departure_date)).all()
    
    # Бронирования как пассажира
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
def create_trip(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    trip_data: DriverTripCreate = None,
    db: Session = Depends(database.get_db)
):
    """Создать новую поездку"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Создаем поездку
    trip_dict = trip_data.dict()
    trip_dict["driver_id"] = user.id
    
    # Автоматически определяем города
    trip_dict["start_city"] = extract_city(trip_data.start_address)
    trip_dict["finish_city"] = extract_city(trip_data.finish_address)
    
    # Рассчитываем общую цену
    trip_dict["total_price"] = trip_data.available_seats * trip_data.price_per_seat
    
    trip = database.DriverTrip(**trip_dict)
    
    db.add(trip)
    db.commit()
    db.refresh(trip)
    
    # Обновляем счетчик поездок пользователя
    user.total_driver_trips += 1
    db.commit()
    
    return {
        "success": True,
        "message": "Поездка создана успешно",
        "trip_id": trip.id,
        "trip": {
            "route": f"{trip.start_address} → {trip.finish_address}",
            "date": trip.departure_date.strftime("%d.%m.%Y %H:%M"),
            "seats": trip.available_seats,
            "price_per_seat": trip.price_per_seat
        }
    }

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
                "total_trips": driver.total_driver_trips,
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
                "price_per_seat": trip.price_per_seat,
                "total_price": trip.total_price
            },
            "details": {
                "distance": trip.route_distance,
                "duration": trip.route_duration,
                "comment": trip.comment,
                "allow_smoking": trip.allow_smoking,
                "allow_animals": trip.allow_animals,
                "allow_luggage": trip.allow_luggage,
                "allow_music": trip.allow_music
            },
            "car_info": {
                "model": driver.car_model,
                "color": driver.car_color,
                "plate": driver.car_plate,
                "type": driver.car_type.value if driver.car_type else None,
                "seats": driver.car_seats
            } if driver.has_car else None,
            "status": trip.status.value,
            "created_at": trip.created_at.isoformat() if trip.created_at else None
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
    
    # Находим поездку
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == booking_data.driver_trip_id,
        database.DriverTrip.status == database.TripStatus.ACTIVE
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена или недоступна")
    
    if trip.available_seats < booking_data.booked_seats:
        raise HTTPException(status_code=400, detail="Недостаточно свободных мест")
    
    # Проверяем, не забронировал ли уже пользователь эту поездку
    existing_booking = db.query(database.Booking).filter(
        database.Booking.driver_trip_id == booking_data.driver_trip_id,
        database.Booking.passenger_id == user.id,
        database.Booking.status == database.TripStatus.ACTIVE
    ).first()
    
    if existing_booking:
        raise HTTPException(status_code=400, detail="Вы уже забронировали эту поездку")
    
    # Создаем бронирование
    booking = database.Booking(
        driver_trip_id=booking_data.driver_trip_id,
        passenger_id=user.id,
        booked_seats=booking_data.booked_seats,
        price_agreed=trip.price_per_seat,
        notes=booking_data.notes,
        status=database.TripStatus.ACTIVE
    )
    
    # Обновляем количество свободных мест
    trip.available_seats -= booking_data.booked_seats
    if trip.available_seats <= 0:
        trip.status = database.TripStatus.COMPLETED
    
    db.add(booking)
    db.commit()
    db.refresh(booking)
    
    # Обновляем счетчик поездок пользователя
    user.total_passenger_trips += 1
    db.commit()
    
    return {
        "success": True,
        "message": "Место успешно забронировано",
        "booking_id": booking.id,
        "booking": {
            "trip_id": trip.id,
            "driver_name": f"{trip.driver.first_name} {trip.driver.last_name or ''}".strip(),
            "route": f"{trip.start_address} → {trip.finish_address}",
            "date": trip.departure_date.strftime("%d.%m.%Y %H:%M"),
            "seats": booking.booked_seats,
            "price": booking.price_agreed
        }
    }

@app.post("/api/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Отменить бронирование"""
    booking = db.query(database.Booking).filter(
        database.Booking.id == booking_id
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")
    
    # Находим пользователя
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем права: пользователь должен быть либо пассажиром, либо водителем поездки
    is_passenger = booking.passenger_id == user.id
    is_driver = booking.driver_trip.driver_id == user.id
    
    if not (is_passenger or is_driver):
        raise HTTPException(status_code=403, detail="Нет прав для отмены этого бронирования")
    
    # Обновляем статус
    booking.status = database.TripStatus.CANCELLED
    booking.cancelled_at = datetime.utcnow()
    
    # Возвращаем места, если отменяет пассажир
    if is_passenger:
        trip = booking.driver_trip
        if trip.status == database.TripStatus.COMPLETED:
            trip.status = database.TripStatus.ACTIVE
        trip.available_seats += booking.booked_seats
    
    db.commit()
    
    return {
        "success": True,
        "message": "Бронирование отменено"
    }

# =============== СТАТИСТИКА И СИСТЕМА ===============

@app.get("/stats")
def stats(db: Session = Depends(database.get_db)):
    """Статистика системы"""
    stats_data = {
        "database": "SQLite (travel_companion.db)",
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

# =============== АВТОМОБИЛИ ПОЛЬЗОВАТЕЛЯ ===============

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
    
    # Получаем автомобили пользователя
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
            "is_default": car.is_default,
            "created_at": car.created_at.isoformat() if car.created_at else None
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
    
    # Если это первый автомобиль, делаем его по умолчанию
    if car_data.is_default:
        # Снимаем флаг default с других автомобилей
        existing_cars = db.query(UserCar).filter(
            UserCar.user_id == user.id,
            UserCar.is_default == True
        ).all()
        
        for car in existing_cars:
            car.is_default = False
    
    # Создаем автомобиль
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
    db.refresh(car)
    
    # Обновляем флаг has_car у пользователя
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

@app.put("/api/users/cars/{car_id}")
def update_user_car(
    car_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    car_data: CarUpdate = None,
    db: Session = Depends(database.get_db)
):
    """Обновить автомобиль пользователя"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    car = db.query(UserCar).filter(
        UserCar.id == car_id,
        UserCar.user_id == user.id
    ).first()
    
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    
    # Если устанавливаем как автомобиль по умолчанию
    if car_data.is_default is True:
        # Снимаем флаг default с других автомобилей
        other_cars = db.query(UserCar).filter(
            UserCar.user_id == user.id,
            UserCar.id != car_id,
            UserCar.is_default == True
        ).all()
        
        for other_car in other_cars:
            other_car.is_default = False
    
    # Обновляем поля
    update_dict = car_data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(car, key, value)
    
    car.updated_at = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "message": "Автомобиль обновлен"
    }

@app.delete("/api/users/cars/{car_id}")
def delete_user_car(
    car_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Удалить автомобиль пользователя"""
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    car = db.query(UserCar).filter(
        UserCar.id == car_id,
        UserCar.user_id == user.id
    ).first()
    
    if not car:
        raise HTTPException(status_code=404, detail="Автомобиль не найден")
    
    # Если удаляем автомобиль по умолчанию, назначаем другой
    if car.is_default:
        other_car = db.query(UserCar).filter(
            UserCar.user_id == user.id,
            UserCar.id != car_id,
            UserCar.is_active == True
        ).first()
        
        if other_car:
            other_car.is_default = True
    
    # Мягкое удаление (деактивация)
    car.is_active = False
    car.updated_at = datetime.utcnow()
    
    # Проверяем, остались ли активные автомобили
    active_cars = db.query(UserCar).filter(
        UserCar.user_id == user.id,
        UserCar.is_active == True
    ).count()
    
    if active_cars == 0:
        user.has_car = False
    
    db.commit()
    
    return {
        "success": True,
        "message": "Автомобиль удален"
    }

@app.get("/api/users/profile-full")
def get_full_user_profile(
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Получить полный профиль пользователя с автомобилями и поездками"""
    print(f"📱 Запрос профиля для telegram_id={telegram_id}")
    
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        print(f"❌ Пользователь {telegram_id} не найден")
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    print(f"✅ Найден пользователь: {user.first_name} {user.last_name}")
    
    try:
        # Получаем автомобили
        cars = db.query(UserCar).filter(
            UserCar.user_id == user.id,
            UserCar.is_active == True
        ).order_by(UserCar.is_default.desc()).all()
        print(f"🚗 Найдено автомобилей: {len(cars)}")
        
        # Получаем поездки как водитель
        driver_trips = db.query(database.DriverTrip).filter(
            database.DriverTrip.driver_id == user.id
        ).order_by(database.DriverTrip.departure_date.desc()).limit(10).all()
        print(f"🚙 Найдено поездок как водитель: {len(driver_trips)}")
        
        # Получаем бронирования как пассажир
        passenger_bookings = db.query(database.Booking).filter(
            database.Booking.passenger_id == user.id
        ).order_by(database.Booking.booked_at.desc()).limit(10).all()
        print(f"👤 Найдено бронирований как пассажир: {len(passenger_bookings)}")
        
        # Формируем результат
        cars_result = []
        for car in cars:
            cars_result.append({
                "id": car.id,
                "model": car.model,
                "color": car.color,
                "license_plate": car.license_plate,
                "car_type": car.car_type,
                "year": car.year,
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
                "passengers_count": len(trip.bookings) if trip.bookings else 0
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
                    "date": trip.departure_date.strftime("%d.%m.%Y %H:%M") if trip.departure_date else "Не указано",
                    "seats": booking.booked_seats,
                    "price": booking.price_agreed or (trip.price_per_seat if trip else 0),
                    "status": booking.status.value if booking.status else "active"
                })
        
        result = {
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
        
        print(f"✅ Профиль сформирован успешно")
        return result
        
    except Exception as e:
        print(f"❌ Ошибка при формировании профиля: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

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
            "registration_date": user.registration_date.isoformat() if user.registration_date else None
        })
    
    return {
        "success": True,
        "count": len(result),
        "users": result
    }

@app.put("/api/bookings/{booking_id}")
def update_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    update_data: BookingUpdate = None,
    db: Session = Depends(database.get_db)
):
    """Обновить бронирование (только пассажир)"""
    booking = db.query(database.Booking).filter(
        database.Booking.id == booking_id
    ).first()
    
    if not booking:
        raise HTTPException(status_code=404, detail="Бронирование не найдено")
    
    # Находим пользователя
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем права: только пассажир может менять свое бронирование
    if booking.passenger_id != user.id:
        raise HTTPException(status_code=403, detail="Нет прав для изменения этого бронирования")
    
    # Проверяем, что поездка еще не началась
    trip = booking.driver_trip
    if trip.departure_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Невозможно изменить бронирование, поездка уже началась")
    
    # Проверяем статус
    if booking.status != database.TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Бронирование не активно")
    
    changes = {}
    
    # Обновляем количество мест
    if update_data and update_data.booked_seats is not None:
        old_seats = booking.booked_seats
        new_seats = update_data.booked_seats
        seat_diff = new_seats - old_seats
        
        # Проверяем доступность мест
        if trip.available_seats < seat_diff:
            raise HTTPException(status_code=400, detail="Недостаточно свободных мест")
        
        # Обновляем количество свободных мест
        trip.available_seats -= seat_diff
        booking.booked_seats = new_seats
        changes["seats"] = f"{old_seats} → {new_seats}"
        
        # Если не осталось мест, меняем статус поездки
        if trip.available_seats <= 0:
            trip.status = database.TripStatus.COMPLETED
    
    # Обновляем заметки
    if update_data and update_data.notes is not None:
        booking.notes = update_data.notes
        changes["notes"] = "обновлены"
    
    if changes:
        booking.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": "Бронирование обновлено",
            "changes": changes,
            "booking": {
                "id": booking.id,
                "seats": booking.booked_seats,
                "price": booking.price_agreed,
                "status": booking.status.value,
                "notes": booking.notes
            }
        }
    
    return {
        "success": False,
        "message": "Нет изменений для обновления"
    }

@app.put("/api/trips/{trip_id}")
def update_driver_trip(
    trip_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    update_data: DriverTripUpdate = None,
    db: Session = Depends(database.get_db)
):
    """Обновить поездку (только водитель)"""
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == trip_id
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена")
    
    # Находим пользователя
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем права: только водитель может менять свою поездку
    if trip.driver_id != user.id:
        raise HTTPException(status_code=403, detail="Нет прав для изменения этой поездки")
    
    # Проверяем, что поездка еще не началась
    if trip.departure_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Невозможно изменить поездку, она уже началась")
    
    # Проверяем статус
    if trip.status != database.TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Поездка не активна")
    
    changes = {}
    
    if update_data:
        # Обновляем количество мест
        if update_data.available_seats is not None:
            # Проверяем, что новое количество мест не меньше уже забронированных
            total_booked = sum(b.booked_seats for b in trip.bookings)
            if update_data.available_seats < total_booked:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Невозможно уменьшить количество мест до {update_data.available_seats}, уже забронировано {total_booked}"
                )
            
            old_seats = trip.available_seats
            trip.available_seats = update_data.available_seats
            changes["seats"] = f"{old_seats} → {update_data.available_seats}"
        
        # Обновляем цену
        if update_data.price_per_seat is not None:
            old_price = trip.price_per_seat
            trip.price_per_seat = update_data.price_per_seat
            trip.total_price = trip.available_seats * update_data.price_per_seat
            changes["price"] = f"{old_price} → {update_data.price_per_seat}"
        
        # Обновляем дату и время
        if update_data.departure_date is not None:
            # Проверяем, что новая дата не в прошлом
            if update_data.departure_date < datetime.utcnow():
                raise HTTPException(status_code=400, detail="Дата поездки не может быть в прошлом")
            
            old_date = trip.departure_date
            trip.departure_date = update_data.departure_date
            changes["date"] = f"{old_date.strftime('%d.%m.%Y')} → {update_data.departure_date.strftime('%d.%m.%Y')}"
        
        if update_data.departure_time is not None:
            old_time = trip.departure_time
            trip.departure_time = update_data.departure_time
            changes["time"] = f"{old_time} → {update_data.departure_time}"
        
        # Обновляем комментарий
        if update_data.comment is not None:
            trip.comment = update_data.comment
            changes["comment"] = "обновлен"
        
        # Обновляем адреса
        if update_data.start_address is not None:
            trip.start_address = update_data.start_address
            trip.start_city = extract_city(update_data.start_address)
            changes["start_address"] = "обновлен"
        
        if update_data.finish_address is not None:
            trip.finish_address = update_data.finish_address
            trip.finish_city = extract_city(update_data.finish_address)
            changes["finish_address"] = "обновлен"
    
    if changes:
        trip.updated_at = datetime.utcnow()
        db.commit()
        
        return {
            "success": True,
            "message": "Поездка обновлена",
            "changes": changes,
            "trip": {
                "id": trip.id,
                "available_seats": trip.available_seats,
                "price_per_seat": trip.price_per_seat,
                "departure_date": trip.departure_date.isoformat() if trip.departure_date else None,
                "departure_time": trip.departure_time,
                "comment": trip.comment,
                "start_address": trip.start_address,
                "finish_address": trip.finish_address,
                "status": trip.status.value
            }
        }
    
    return {
        "success": False,
        "message": "Нет изменений для обновления"
    }

@app.post("/api/trips/{trip_id}/cancel")
def cancel_driver_trip(
    trip_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Отменить поездку (водитель)"""
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == trip_id
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена")
    
    # Находим пользователя
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем права
    if trip.driver_id != user.id:
        raise HTTPException(status_code=403, detail="Нет прав для отмены этой поездки")
    
    # Проверяем, что поездка еще не началась
    if trip.departure_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Невозможно отменить поездку, она уже началась")
    
    # Проверяем статус
    if trip.status == database.TripStatus.CANCELLED:
        return {"success": True, "message": "Поездка уже отменена"}
    
    if trip.status != database.TripStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Поездка не активна")
    
    # Отменяем поездку
    trip.status = database.TripStatus.CANCELLED
    trip.updated_at = datetime.utcnow()
    
    # Отменяем все бронирования этой поездки
    for booking in trip.bookings:
        if booking.status == database.TripStatus.ACTIVE:
            booking.status = database.TripStatus.CANCELLED
            booking.cancelled_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "success": True,
        "message": "Поездка и все связанные бронирования отменены",
        "cancelled_bookings": len([b for b in trip.bookings if b.status == database.TripStatus.CANCELLED])
    }

@app.get("/api/trips/{trip_id}/bookings")
def get_trip_bookings(
    trip_id: int,
    telegram_id: int = Query(..., description="Telegram ID пользователя"),
    db: Session = Depends(database.get_db)
):
    """Получить все бронирования поездки (только для водителя)"""
    trip = db.query(database.DriverTrip).filter(
        database.DriverTrip.id == trip_id
    ).first()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Поездка не найдена")
    
    # Находим пользователя
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    # Проверяем права
    if trip.driver_id != user.id:
        raise HTTPException(status_code=403, detail="Нет прав для просмотра бронирований этой поездки")
    
    bookings = []
    for booking in trip.bookings:
        passenger = booking.passenger
        bookings.append({
            "id": booking.id,
            "passenger": {
                "id": passenger.id,
                "name": f"{passenger.first_name} {passenger.last_name or ''}".strip(),
                "phone": passenger.phone,
                "rating": passenger.passenger_rating
            },
            "seats": booking.booked_seats,
            "price": booking.price_agreed,
            "status": booking.status.value,
            "booked_at": booking.booked_at.isoformat() if booking.booked_at else None,
            "notes": booking.notes
        })
    
    return {
        "success": True,
        "count": len(bookings),
        "bookings": bookings
    }

# =============== HEALTH CHECK ===============

@app.get("/health")
def health_check(db: Session = Depends(database.get_db)):
    """Проверка состояния API и базы данных"""
    try:
        # Простой запрос к базе
        result = db.execute("SELECT 1").fetchone()
        return {
            "status": "healthy", 
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy", 
            "database": "disconnected", 
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# Точка входа
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)