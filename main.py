# main.py - ОПТИМИЗИРОВАННЫЙ API ДЛЯ TELEGRAM WEB APP
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

    # Добавить валидацию
    @validator('departure_date')
    def validate_departure_date(cls, v):
        # Убедиться, что дата корректна
        if v < datetime.now():
            raise ValueError('Дата должна быть в будущем')
        return v

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

# =============== FASTAPI APP ===============
app = FastAPI(
    title="Travel Companion API",
    version="3.0",
    description="API для сервиса поиска попутчиков с Telegram авторизацией"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
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
    """Создание таблиц при запуске"""
    print("=" * 60)
    print("🚀 ЗАПУСК TRAVEL COMPANION API")
    print("=" * 60)
    
    try:
        # Создаем таблицы
        database.Base.metadata.create_all(bind=database.engine)
        print("✅ Таблицы базы данных созданы/проверены")
        
        # Проверяем подключение
        from sqlalchemy import text
        session = database.SessionLocal()
        try:
            session.execute(text("SELECT 1"))
            session.commit()
            print("✅ Подключение к базе данных успешно")
        except Exception as e:
            print(f"❌ Ошибка подключения к базе: {e}")
        finally:
            session.close()
            
    except Exception as e:
        print(f"❌ Ошибка инициализации базы данных: {e}")
        import traceback
        traceback.print_exc()
    
    print("=" * 60)

@app.on_event("shutdown")
async def shutdown_event():
    """Действия при остановке"""
    print("👋 Сервер останавливается")

# =============== РОУТЫ ===============

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
    """Авторизация через Telegram Web App"""
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
            print(f"✅ New user created: {user.first_name}")
        else:
            # Обновляем данные
            user.username = user_data.get('username') or user.username
            user.first_name = user_data.get('first_name', user.first_name)
            user.last_name = user_data.get('last_name') or user.last_name
            user.language_code = user_data.get('language_code') or user.language_code
            user.last_active = datetime.utcnow()
            db.commit()
            message = "Пользователь авторизован"
            print(f"✅ User updated: {user.first_name}")
        
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
        print(f"❌ Auth error: {str(e)}")
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
            "phone": user.phone
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
    
    query = db.query(database.DriverTrip).filter(
        database.DriverTrip.status == database.TripStatus.ACTIVE,
        database.DriverTrip.available_seats >= search_query.passengers,
        database.DriverTrip.departure_date >= date_obj,
        database.DriverTrip.departure_date < date_obj + timedelta(days=1)
    )
    
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
    
    query = query.order_by(
        database.DriverTrip.departure_date,
        database.DriverTrip.price_per_seat
    )
    
    trips = query.all()
    
    if search_query.max_price:
        trips = [t for t in trips if t.price_per_seat <= search_query.max_price]
    
    result = []
    for trip in trips:
        driver = trip.driver
        
        result.append({
            "id": trip.id,
            "driver": {
                "id": driver.id,
                "name": f"{driver.first_name} {driver.last_name or ''}".strip(),
                "rating": driver.driver_rating
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
            }
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
    
    trip_dict = trip_data.dict()
    trip_dict["driver_id"] = user.id
    trip_dict["start_city"] = extract_city(trip_data.start_address)
    trip_dict["finish_city"] = extract_city(trip_data.finish_address)
    trip_dict["total_price"] = trip_data.available_seats * trip_data.price_per_seat
    
    trip = database.DriverTrip(**trip_dict)
    
    db.add(trip)
    db.commit()
    db.refresh(trip)
    
    user.total_driver_trips += 1
    db.commit()
    
    return {
        "success": True,
        "message": "Поездка создана успешно",
        "trip_id": trip.id
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
    
    user = db.query(database.User).filter(
        database.User.telegram_id == telegram_id
    ).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    
    is_passenger = booking.passenger_id == user.id
    is_driver = booking.driver_trip.driver_id == user.id
    
    if not (is_passenger or is_driver):
        raise HTTPException(status_code=403, detail="Нет прав для отмены этого бронирования")
    
    booking.status = database.TripStatus.CANCELLED
    booking.cancelled_at = datetime.utcnow()
    
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
def health_check():
    """Проверка состояния API"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
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

# =============== ЗАПУСК СЕРВЕРА ===============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False)