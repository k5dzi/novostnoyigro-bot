from flask import Flask, jsonify
import logging
import threading
import time
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Глобальная переменная для бота
news_bot = None
bot_thread = None


def run_bot():
    """Запускает бота в отдельном потоке"""
    global news_bot
    try:
        # Импортируем здесь чтобы избежать циклических импортов
        from bot import NewsBot
        news_bot = NewsBot()
        logger.info("🚀 Запускаем бота...")
        news_bot.run()
    except Exception as e:
        logger.error(f"❌ Ошибка в боте: {e}")


@app.route('/')
def health_check():
    """Проверка здоровья приложения для Render"""
    return jsonify({
        'status': 'running',
        'service': 'Telegram News Bot',
        'timestamp': time.time(),
        'bot_status': 'active' if news_bot else 'starting'
    })


@app.route('/health')
def health():
    """Эндпоинт для проверки работоспособности"""
    return 'OK', 200


@app.route('/stats')
def get_stats():
    """Статистика бота"""
    if news_bot and hasattr(news_bot, 'db'):
        try:
            reserve_count = news_bot.db.get_reserve_count()
            return jsonify({
                'reserve_news': reserve_count,
                'status': 'active'
            })
        except Exception as e:
            return jsonify({'error': str(e)})
    return jsonify({'status': 'bot_not_initialized'})


def start_bot():
    """Запуск бота в фоновом потоке"""
    global bot_thread
    if bot_thread and bot_thread.is_alive():
        logger.info("✅ Бот уже запущен")
        return

    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("🚀 Бот запущен в фоновом режиме")


# Запускаем бот при старте приложения
start_bot()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🌐 Запускаем веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)