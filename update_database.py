# update_database.py - добавление таблицы автомобилей
import database
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

# Новая таблица для автомобилей
class UserCar(Base):
    __tablename__ = "user_cars"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Основные данные
    model = Column(String(100), nullable=False)
    color = Column(String(50))
    license_plate = Column(String(20), unique=True)
    car_type = Column(String(20))  # sedan, suv, etc.
    year = Column(Integer)
    seats = Column(Integer, default=4)
    
    # Дополнительная информация
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    # Системные поля
    created_at = Column(database.DateTime, default=datetime.utcnow)
    updated_at = Column(database.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def update_database():
    """Добавляем таблицу user_cars и обновляем users"""
    try:
        # Создаем новую таблицу
        UserCar.__table__.create(database.engine)
        print("✅ Таблица user_cars создана")
        
        # Обновляем существующих пользователей
        db = database.SessionLocal()
        
        # Переносим данные автомобилей из users в user_cars
        users_with_cars = db.query(database.User).filter(
            database.User.has_car == True,
            database.User.car_model.isnot(None)
        ).all()
        
        for user in users_with_cars:
            if user.car_model:
                car = UserCar(
                    user_id=user.id,
                    model=user.car_model,
                    color=user.car_color,
                    license_plate=user.car_plate,
                    car_type=user.car_type.value if user.car_type else None,
                    seats=user.car_seats or 4,
                    is_default=True,
                    is_active=True
                )
                db.add(car)
        
        db.commit()
        print(f"✅ Перенесено {len(users_with_cars)} автомобилей")
        db.close()
        
    except Exception as e:
        print(f"❌ Ошибка обновления БД: {e}")

if __name__ == "__main__":
    update_database()