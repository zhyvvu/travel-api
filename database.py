# database.py - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ ДЛЯ TELEGRAM WEB APP
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Float, ForeignKey, Text, Enum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import enum
import json

# SQLite база
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./travel_companion.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Enums ---
class UserRole(str, enum.Enum):
    DRIVER = "driver"
    PASSENGER = "passenger"
    BOTH = "both"

class TripStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    IN_PROGRESS = "in_progress"

class CarType(str, enum.Enum):
    SEDAN = "sedan"
    HATCHBACK = "hatchback"
    SUV = "suv"
    MINIVAN = "minivan"
    OTHER = "other"

# --- Таблица пользователей ---
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    phone = Column(String(20))
    language_code = Column(String(10))
    
    # Данные автомобиля (для водителей)
    car_model = Column(String(100))
    car_color = Column(String(50))
    car_plate = Column(String(20))
    car_type = Column(Enum(CarType))
    car_year = Column(Integer)
    car_seats = Column(Integer, default=4)
    has_car = Column(Boolean, default=False)
    
    # Рейтинги
    driver_rating = Column(Float, default=5.0)
    passenger_rating = Column(Float, default=5.0)
    total_driver_trips = Column(Integer, default=0)
    total_passenger_trips = Column(Integer, default=0)
    
    # Системные поля
    registration_date = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    role = Column(Enum(UserRole), default=UserRole.PASSENGER)
    is_bot = Column(Boolean, default=False)
    
    # Связи
    driver_trips = relationship("DriverTrip", back_populates="driver", cascade="all, delete-orphan")
    passenger_trips = relationship("PassengerTrip", back_populates="passenger", cascade="all, delete-orphan")
    reviews_received = relationship("Review", foreign_keys="Review.reviewed_user_id", back_populates="reviewed_user")
    reviews_given = relationship("Review", foreign_keys="Review.reviewer_user_id", back_populates="reviewer")
    bookings_as_passenger = relationship("Booking", foreign_keys="Booking.passenger_id", back_populates="passenger")

# --- Таблица поездок водителей ---
class DriverTrip(Base):
    __tablename__ = "driver_trips"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Дата и время
    departure_date = Column(DateTime, nullable=False)
    departure_time = Column(String(10))  # "HH:MM"
    
    # Локации
    start_address = Column(String(500), nullable=False)
    start_lat = Column(Float)
    start_lng = Column(Float)
    start_city = Column(String(100))
    
    finish_address = Column(String(500), nullable=False)
    finish_lat = Column(Float)
    finish_lng = Column(Float)
    finish_city = Column(String(100))
    
    # Маршрут
    route_points = Column(JSON)
    route_distance = Column(Float)  # км
    route_duration = Column(Integer)  # минуты
    polyline = Column(Text)
    
    # Детали поездки
    available_seats = Column(Integer, nullable=False, default=3)
    price_per_seat = Column(Float)
    total_price = Column(Float)
    comment = Column(Text)
    
    # Ограничения и опции
    max_passengers_back = Column(Integer, default=2)
    allow_smoking = Column(Boolean, default=False)
    allow_animals = Column(Boolean, default=False)
    allow_luggage = Column(Boolean, default=True)
    allow_music = Column(Boolean, default=True)
    allow_stops = Column(Boolean, default=True)
    
    # Статус
    status = Column(Enum(TripStatus), default=TripStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    driver = relationship("User", back_populates="driver_trips")
    bookings = relationship("Booking", back_populates="driver_trip", cascade="all, delete-orphan")

# --- Таблица запросов пассажиров ---
class PassengerTrip(Base):
    __tablename__ = "passenger_trips"
    
    id = Column(Integer, primary_key=True, index=True)
    passenger_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Дата и время
    desired_date = Column(DateTime, nullable=False)
    desired_time = Column(String(10))  # "HH:MM"
    time_flexibility = Column(Integer, default=30)  # ± минуты
    
    # Локации
    start_address = Column(String(500), nullable=False)
    start_lat = Column(Float)
    start_lng = Column(Float)
    start_city = Column(String(100))
    
    finish_address = Column(String(500), nullable=False)
    finish_lat = Column(Float)
    finish_lng = Column(Float)
    finish_city = Column(String(100))
    
    # Детали запроса
    required_seats = Column(Integer, default=1)
    max_price = Column(Float)
    preferred_gender = Column(String(10))  # male/female/any
    comment = Column(Text)
    
    # Статус
    status = Column(Enum(TripStatus), default=TripStatus.ACTIVE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    passenger = relationship("User", back_populates="passenger_trips")
    bookings = relationship("Booking", back_populates="passenger_trip", cascade="all, delete-orphan")

# --- Таблица бронирований ---
class Booking(Base):
    __tablename__ = "bookings"
    
    id = Column(Integer, primary_key=True, index=True)
    driver_trip_id = Column(Integer, ForeignKey("driver_trips.id", ondelete="CASCADE"), nullable=False)
    passenger_trip_id = Column(Integer, ForeignKey("passenger_trips.id", ondelete="CASCADE"))
    passenger_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Детали бронирования
    booked_seats = Column(Integer, default=1)
    price_agreed = Column(Float)
    meeting_point = Column(String(500))
    notes = Column(Text)
    
    # Статус бронирования
    status = Column(Enum(TripStatus), default=TripStatus.ACTIVE)
    booked_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime)
    cancelled_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Связи
    driver_trip = relationship("DriverTrip", back_populates="bookings")
    passenger_trip = relationship("PassengerTrip", back_populates="bookings")
    passenger = relationship("User", foreign_keys=[passenger_id], back_populates="bookings_as_passenger")
    review = relationship("Review", uselist=False, back_populates="booking", cascade="all, delete-orphan")

# --- Таблица отзывов ---
class Review(Base):
    __tablename__ = "reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), unique=True)
    
    # Кто оценивает и кого
    reviewer_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    reviewed_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Рейтинги (1-5)
    rating = Column(Integer, nullable=False)
    punctuality = Column(Integer)
    comfort = Column(Integer)
    communication = Column(Integer)
    
    # Отзыв
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_anonymous = Column(Boolean, default=False)
    
    # Связи
    booking = relationship("Booking", back_populates="review")
    reviewer = relationship("User", foreign_keys=[reviewer_user_id], back_populates="reviews_given")
    reviewed_user = relationship("User", foreign_keys=[reviewed_user_id], back_populates="reviews_received")

# --- Таблица сообщений ---
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"))
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    sender = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])

# Создаем таблицы
def create_tables():
    Base.metadata.create_all(bind=engine)
    print("✅ Таблицы созданы:")
    print("   - users (пользователи)")
    print("   - driver_trips (поездки водителей)")
    print("   - passenger_trips (запросы пассажиров)")
    print("   - bookings (бронирования)")
    print("   - reviews (отзывы)")
    print("   - messages (сообщения)")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Функция для создания тестовых данных (оставляем на случай ручного тестирования)
def create_test_data():
    db = SessionLocal()
    try:
        print("📊 Создание тестовых данных...")
        
        # Проверяем, есть ли уже пользователи
        if db.query(User).count() == 0:
            # Добавляем тестового водителя
            driver = User(
                telegram_id=1001,
                username="test_driver",
                first_name="Иван",
                last_name="Тестовый",
                phone="+79161234567",
                has_car=True,
                car_model="Toyota Camry",
                car_color="Черный",
                car_plate="А123АА777",
                car_type=CarType.SEDAN,
                car_seats=4,
                role=UserRole.DRIVER
            )
            db.add(driver)
            db.commit()
            print("✅ Тестовый водитель создан")
            
        db.close()
    except Exception as e:
        print(f"⚠️  Ошибка создания тестовых данных: {e}")
        db.rollback()