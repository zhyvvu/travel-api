# minimal_bot.py - ТЕЛЕГРАМ БОТ ДЛЯ TRAVEL COMPANION
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import os

# Настройки
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7440722159:AAH3mLjWboLCBVmOvozdpX7MRo1_Os-fWaQ")  # ⚠️ ЗАМЕНИТЕ на реальный токен!
MINI_APP_URL = "https://zhyvvu.github.io/travel-companion-app/"  # ⚠️ ЗАМЕНИТЕ на ваш URL

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start - приветствие и кнопка Mini App"""
    user = update.effective_user
    
    # Приветственное сообщение
    welcome_text = f"""
👋 Привет, {user.first_name}!

🚗 Добро пожаловать в *Travel Companion* — сервис поиска попутчиков для путешествий!

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

⚡ *Быстрые команды:*
/start - Показать это сообщение
/help - Получить справку
/about - О проекте
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
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = """
🆘 *Помощь по Travel Companion*

*Основные возможности:*
• *Поиск поездок* — найдите попутчиков по нужному маршруту
• *Создание поездок* — предложите свою поездку и найдите пассажиров
• *Бронирование* — забронируйте место в поездке
• *Чат* — общайтесь с водителями и пассажирами
• *Рейтинги* — оставляйте отзывы после поездок

*Как использовать:*
1. Нажмите кнопку *"Открыть Travel Companion"*
2. Разрешите доступ к вашим данным Telegram
3. Заполните профиль (особенно если вы водитель)
4. Начните искать или создавать поездки!

*Безопасность:*
• Все пользователи проходят авторизацию через Telegram
• Вы видите рейтинги и отзывы о попутчиках
• Общение происходит только после бронирования

*Поддержка:*
Если у вас возникли проблемы, напишите нам: @travel_companion_support

*Команды бота:*
/start - Главное меню
/help - Эта справка
/about - О проекте
"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /about"""
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
• Встроенный чат для общения
• Система рейтингов и отзывов
• Поддержка Telegram Web App

*Технологии:*
• Backend: Python, FastAPI, SQLAlchemy
• Frontend: HTML/CSS/JavaScript, Telegram Web App
• База данных: SQLite
• Хостинг: GitHub Pages + Heroku/Render

*Контакты:*
• Поддержка: @travel_companion_support
• Исходный код: GitHub
• Документация: в разработке

*Благодарности:*
Спасибо, что используете Travel Companion! 
Ваши отзывы и предложения помогают нам становиться лучше! 🚀
"""
    
    keyboard = [[
        InlineKeyboardButton(
            "⭐ Оценить приложение",
            callback_data="rate_app"
        ),
        InlineKeyboardButton(
            "📢 Поделиться с друзьями",
            switch_inline_query="Попробуйте Travel Companion — сервис поиска попутчиков!"
        )
    ]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        about_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка данных из Web App"""
    data = update.effective_message.web_app_data.data
    logger.info(f"Получены данные из Web App: {data}")
    
    # Здесь можно обрабатывать данные из Mini App
    await update.message.reply_text(
        "✅ Данные из приложения получены. Спасибо за использование Travel Companion!",
        parse_mode='Markdown'
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    text = update.message.text
    
    if "привет" in text.lower() or "hello" in text.lower():
        await update.message.reply_text(
            "Привет! Напишите /start чтобы открыть меню приложения 🚗"
        )
    elif "поездк" in text.lower() or "попутчик" in text.lower():
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
    else:
        keyboard = [[
            InlineKeyboardButton(
                "🚗 Открыть приложение",
                web_app=WebAppInfo(url=MINI_APP_URL)
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Я не совсем понимаю ваш запрос. Попробуйте открыть приложение для полного доступа ко всем функциям:",
            reply_markup=reply_markup
        )

def main():
    """Запуск бота"""
    print("=" * 60)
    print("🤖 ЗАПУСК TELEGRAM БОТА ДЛЯ TRAVEL COMPANION")
    print("=" * 60)
    
    if BOT_TOKEN == "ВАШ_ТОКЕН_БОТА":
        print("❌ ОШИБКА: Замените BOT_TOKEN на реальный токен!")
        print("ℹ️  Получите токен у @BotFather в Telegram")
        return
    
    print(f"🔗 Mini App URL: {MINI_APP_URL}")
    print("📱 Функционал бота:")
    print("   • /start - Главное меню с кнопкой Mini App")
    print("   • /help - Подробная справка")
    print("   • /about - Информация о проекте")
    print("   • Обработка текстовых сообщений")
    print("=" * 60)
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен!")
    print("🔄 Ожидание сообщений...")
    print("⚠️  Для остановки нажмите Ctrl+C")
    print("=" * 60)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()