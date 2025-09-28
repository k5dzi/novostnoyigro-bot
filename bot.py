import os
import asyncio
import logging
import schedule
import time
import sqlite3
import hashlib
import random
from datetime import datetime, timedelta
from telegram import Bot
from config import BOT_TOKEN, CHANNEL_ID, DB_CONFIG
import feedparser
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional

# ==================== НАСТРОЙКА ЛОГГИРОВАНИЯ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ==================== КОНФИГУРАЦИЯ ====================
class Config:
    BOT_TOKEN = BOT_TOKEN
    CHANNEL_ID = CHANNEL_ID

    # Базовые часы (с 7:00 до 00:00)
    BASE_HOURS = list(range(7, 24)) + [0]  # [7, 8, 9, ..., 23, 0]
    MAX_MESSAGE_LENGTH = 1024
    RSS_LIMIT = 15
    HTML_LIMIT = 10

    @staticmethod
    def generate_random_schedule():
        """Генерирует случайное расписание на день"""
        schedule_times = []
        for hour in Config.BASE_HOURS:
            # Случайные минуты от 0 до 55
            minutes = random.randint(0, 55)
            time_str = f"{hour:02d}:{minutes:02d}"
            schedule_times.append(time_str)
        return schedule_times


# ==================== МОДЕЛИ ДАННЫХ ====================
class NewsArticle:
    def __init__(self, title: str, link: str, source: str, category: str = "general",
                 description: str = "", image_url: str = None):
        self.title = title
        self.link = link
        self.source = source
        self.category = category
        self.description = description
        self.image_url = image_url
        self.id = self.generate_id()

    def generate_id(self) -> str:
        content = f"{self.title}{self.link}".encode('utf-8')
        return hashlib.md5(content).hexdigest()

    def to_dict(self) -> Dict:
        return {
            'title': self.title,
            'link': self.link,
            'source': self.source,
            'category': self.category,
            'description': self.description,
            'image_url': self.image_url,
            'id': self.id
        }


# ==================== БАЗА ДАННЫХ ====================
class DatabaseManager:
    def __init__(self):
        self.connection = None

    def get_connection(self):
        if not self.connection:
            try:
                self.connection = sqlite3.connect(DB_CONFIG['database'], check_same_thread=False)
            except Exception as e:
                logger.error(f"Ошибка подключения к БД: {e}")
                raise
        return self.connection

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posted_news (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL,
                    posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT,
                    category TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS news_reserve (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    link TEXT NOT NULL,
                    image_url TEXT,
                    source TEXT,
                    description TEXT,
                    category TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used BOOLEAN DEFAULT FALSE
                )
            ''')

            conn.commit()
            logger.info("✅ База данных SQLite инициализирована")

        except Exception as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}")
            conn.rollback()
        finally:
            cursor.close()

    def is_news_posted(self, news_id: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT id FROM posted_news WHERE id = ?', (news_id,))
            return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"❌ Ошибка проверки новости: {e}")
            return False
        finally:
            cursor.close()

    def mark_news_as_posted(self, article: NewsArticle):
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'INSERT INTO posted_news (id, title, link, source, category) VALUES (?, ?, ?, ?, ?)',
                (article.id, article.title, article.link, article.source, article.category)
            )
            conn.commit()
            logger.info(f"✅ Новость добавлена в опубликованные: {article.title[:50]}...")
        except Exception as e:
            logger.error(f"❌ Ошибка добавления новости: {e}")
            conn.rollback()
        finally:
            cursor.close()

    def add_to_reserve(self, articles: List[NewsArticle]):
        conn = self.get_connection()
        cursor = conn.cursor()
        added_count = 0

        try:
            for article in articles:
                if not self.is_news_posted(article.id):
                    cursor.execute('SELECT id FROM news_reserve WHERE id = ?', (article.id,))
                    if not cursor.fetchone():
                        cursor.execute(
                            '''INSERT INTO news_reserve 
                            (id, title, link, image_url, source, description, category) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (article.id, article.title, article.link, article.image_url,
                             article.source, article.description, article.category)
                        )
                        added_count += 1

            conn.commit()
            logger.info(f"💾 В резерв добавлено новостей: {added_count}")

        except Exception as e:
            logger.error(f"❌ Ошибка добавления в резерв: {e}")
            conn.rollback()
        finally:
            cursor.close()

    def get_reserve_news(self, count: int = 1) -> List[NewsArticle]:
        conn = self.get_connection()
        cursor = conn.cursor()
        articles = []

        try:
            cursor.execute('''
                SELECT id, title, link, image_url, source, description, category 
                FROM news_reserve 
                WHERE used = FALSE 
                ORDER BY added_at 
                LIMIT ?
            ''', (count,))

            for row in cursor.fetchall():
                news_id, title, link, image_url, source, description, category = row
                article = NewsArticle(title, link, source, category, description, image_url)
                article.id = news_id
                articles.append(article)

                cursor.execute('UPDATE news_reserve SET used = TRUE WHERE id = ?', (news_id,))

            conn.commit()
            logger.info(f"📥 Из резерва получено новостей: {len(articles)}")

        except Exception as e:
            logger.error(f"❌ Ошибка получения из резерва: {e}")
            conn.rollback()
        finally:
            cursor.close()

        return articles

    def get_reserve_count(self) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT COUNT(*) FROM news_reserve WHERE used = FALSE')
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"❌ Ошибка подсчета резерва: {e}")
            return 0
        finally:
            cursor.close()


# ==================== ПАРСЕРЫ НОВОСТЕЙ ====================
class NewsParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })


class RSSParser(NewsParser):
    RSS_SOURCES = [
        {'name': 'DTF Игры', 'url': 'https://dtf.ru/r/games/go', 'category': 'games'},
        {'name': 'StopGame', 'url': 'https://stopgame.ru/rss/news.xml', 'category': 'news'},
        {'name': 'Igromania', 'url': 'https://www.igromania.ru/rss/news.xml', 'category': 'news'},
        {'name': 'Kanobu', 'url': 'https://kanobu.ru/rss/news.xml', 'category': 'news'},
        {'name': 'Cybersport.ru', 'url': 'https://www.cybersport.ru/rss', 'category': 'esports'}
    ]

    async def parse_feeds(self) -> List[NewsArticle]:
        logger.info("📡 Запуск парсинга RSS-лент")
        all_articles = []

        for source in self.RSS_SOURCES:
            try:
                articles = await self.parse_single_feed(source)
                all_articles.extend(articles)
                logger.info(f"✅ {source['name']}: {len(articles)} новостей")
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга {source['name']}: {e}")

        logger.info(f"📡 Всего RSS-новостей: {len(all_articles)}")
        return all_articles

    async def parse_single_feed(self, source: Dict) -> List[NewsArticle]:
        articles = []

        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, source['url'])

        for entry in feed.entries[:Config.RSS_LIMIT]:
            if hasattr(entry, 'published_parsed'):
                published_time = datetime(*entry.published_parsed[:6])
                if datetime.now() - published_time > timedelta(hours=48):
                    continue

            article = NewsArticle(
                title=entry.title,
                link=entry.link,
                source=source['name'],
                category=source['category'],
                description=getattr(entry, 'summary', ''),
                image_url=self.find_image_in_entry(entry)
            )
            articles.append(article)

        return articles

    def find_image_in_entry(self, entry) -> Optional[str]:
        if hasattr(entry, 'links'):
            for link in entry.links:
                if hasattr(link, 'type') and link.type and 'image' in link.type:
                    return link.href

        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image'):
                    return media['url']

        return None


class HTMLParser(NewsParser):
    def parse_dtf(self) -> List[NewsArticle]:
        logger.info("🌐 Парсинг DTF HTML")
        articles = []

        try:
            url = "https://dtf.ru/games"
            response = self.session.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            for article_tag in soup.find_all('article')[:Config.HTML_LIMIT]:
                title_tag = article_tag.find('h2', class_='content-title')
                if not title_tag:
                    continue

                link_tag = title_tag.find('a')
                if not link_tag:
                    continue

                title = link_tag.text.strip()
                link = "https://dtf.ru" + link_tag['href']

                description_tag = article_tag.find('div', class_='content-description')
                description = description_tag.text.strip() if description_tag else ""

                image_url = None
                img_tag = article_tag.find('img')
                if img_tag and img_tag.get('src'):
                    image_url = img_tag['src']
                    if image_url.startswith('//'):
                        image_url = 'https:' + image_url

                article = NewsArticle(
                    title=title,
                    link=link,
                    source='DTF',
                    category='games',
                    description=description,
                    image_url=image_url
                )
                articles.append(article)

            logger.info(f"✅ DTF HTML: {len(articles)} новостей")

        except Exception as e:
            logger.error(f"❌ Ошибка парсинга DTF: {e}")

        return articles


# ==================== ОБРАБОТЧИК КОНТЕНТА ====================
class ContentEnhancer:
    CATEGORY_EMOJIS = {
        'games': '🎮',
        'news': '📰',
        'esports': '🏆',
        'general': '📢'
    }

    CATEGORY_DESCRIPTIONS = {
        'games': {
            'intro': '🎯 **Новость из мира видеоигр**'
        },
        'esports': {
            'intro': '🏆 **Новости киберспорта**'
        },
        'news': {
            'intro': '📢 **Актуальная новость**'
        }
    }

    def enhance(self, article: NewsArticle) -> Dict:
        category = article.category
        emoji = self.CATEGORY_EMOJIS.get(category, '📢')
        desc_config = self.CATEGORY_DESCRIPTIONS.get(category, self.CATEGORY_DESCRIPTIONS['news'])

        description = self._format_description(article, desc_config)
        link_text = self._format_link(article.link)

        return {
            'title': article.title,
            'description': description,
            'link_text': link_text,
            'image_url': article.image_url,
            'has_image': article.image_url is not None,
            'category': category,
            'emoji': emoji
        }

    def _format_description(self, article: NewsArticle, config: Dict) -> str:
        # Используем оригинальное описание или генерируем умное
        if article.description and len(article.description.strip()) > 50:
            description = self._clean_description(article.description)
        else:
            description = self._generate_smart_description(article.title)

        return f"""{config['intro']}

📊 {description}

💬 *Обсуждение в комментариях приветствуется!*

🌐 **Источник:** {article.source}"""

    def _clean_description(self, text: str) -> str:
        """Очищает описание от HTML-тегов"""
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        if len(text) > 400:
            text = text[:400] + '...'
        return text.strip()

    def _generate_smart_description(self, title: str) -> str:
        """Генерирует умное описание на основе заголовка"""
        title_lower = title.lower()

        if any(word in title_lower for word in ['анонс', 'показал', 'представил', 'анонсировал']):
            return "Разработчики поделились новыми деталями проекта. Сообщество активно обсуждает свежую информацию."
        elif any(word in title_lower for word in ['обновление', 'патч', 'версия']):
            return "Обновление принесло значительные изменения в игровой процесс и баланс."
        elif any(word in title_lower for word in ['трейлер', 'видео', 'геймплей']):
            return "Новый видеоматериал демонстрирует ключевые особенности и геймплей."
        elif any(word in title_lower for word in ['скидка', 'распродажа', 'sale']):
            return "Отличная возможность приобрести игру по выгодной цене."
        else:
            return "Свежая информация о событиях в игровой индустрии."

    def _format_link(self, link: str) -> str:
        if 'steam' in link.lower():
            return f"[🎮 Steam]({link})"
        elif 'dtf' in link.lower():
            return f"[📝 DTF]({link})"
        else:
            return f"[🌐 Читать далее]({link})"


# ==================== ТЕЛЕГРАМ БОТ ====================
class TelegramBot:
    def __init__(self):
        self.bot = Bot(token=Config.BOT_TOKEN)
        self.enhancer = ContentEnhancer()

    async def send_news(self, article: NewsArticle) -> bool:
        try:
            enhanced = self.enhancer.enhance(article)
            message = self._format_message(enhanced)

            if enhanced['has_image']:
                return await self._send_with_photo(message, enhanced)
            else:
                return await self._send_text_message(message)

        except Exception as e:
            logger.error(f"❌ Ошибка отправки новости: {e}")
            return False

    def _format_message(self, enhanced: Dict) -> str:
        message = f"""{enhanced['emoji']} **{enhanced['title']}**

{enhanced['description']}

🔗 {enhanced['link_text']}"""

        if len(message) > Config.MAX_MESSAGE_LENGTH:
            message = message[:Config.MAX_MESSAGE_LENGTH - 3] + "..."

        return message

    async def _send_with_photo(self, message: str, enhanced: Dict) -> bool:
        try:
            await self.bot.send_photo(
                chat_id=Config.CHANNEL_ID,
                photo=enhanced['image_url'],
                caption=message,
                parse_mode='Markdown'
            )
            return True
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить с фото: {e}")
            return await self._send_text_message(message)

    async def _send_text_message(self, message: str) -> bool:
        try:
            await self.bot.send_message(
                chat_id=Config.CHANNEL_ID,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки текста: {e}")
            return False


# ==================== ОСНОВНОЙ КЛАСС БОТА ====================
class NewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.telegram = TelegramBot()
        self.rss_parser = RSSParser()
        self.html_parser = HTMLParser()
        self.daily_schedule = []

    async def collect_news(self) -> List[NewsArticle]:
        logger.info("🕸️ Сбор новостей со всех источников")
        all_articles = []

        rss_articles = await self.rss_parser.parse_feeds()
        all_articles.extend(rss_articles)

        if len(all_articles) < 3:
            html_articles = self.html_parser.parse_dtf()
            all_articles.extend(html_articles)

        unique_articles = self._remove_duplicates(all_articles)
        logger.info(f"✅ Уникальных новостей: {len(unique_articles)}")

        return unique_articles

    def _remove_duplicates(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        seen_titles = set()
        unique_articles = []

        for article in articles:
            if article.title not in seen_titles:
                seen_titles.add(article.title)
                unique_articles.append(article)

        return unique_articles

    async def publish_news(self):
        logger.info("🚀 Запуск публикации новостей")

        try:


            fresh_articles = await self.collect_news()
            # ... остальной код

            if not fresh_articles:
                logger.warning("📭 Новости не найдены, используем резерв")
                fresh_articles = self._get_fallback_news()

            if len(fresh_articles) > 1:
                reserve_articles = fresh_articles[1:]
                self.db.add_to_reserve(reserve_articles)

            article_to_publish = await self._select_article_to_publish(fresh_articles)

            if not article_to_publish:
                logger.warning("📭 Нет подходящих новостей для публикации")
                return

            success = await self.telegram.send_news(article_to_publish)

            if success:
                self.db.mark_news_as_posted(article_to_publish)
                logger.info(f"✅ Новость опубликована: {article_to_publish.title[:50]}...")

                reserve_count = self.db.get_reserve_count()
                logger.info(f"💾 Новостей в резерве: {reserve_count}")
            else:
                logger.error("❌ Не удалось опубликовать новость")

        except Exception as e:
            logger.error(f"❌ Критическая ошибка публикации: {e}")

    async def _select_article_to_publish(self, fresh_articles: List[NewsArticle]) -> Optional[NewsArticle]:
        if fresh_articles:
            for article in fresh_articles:
                if not self.db.is_news_posted(article.id):
                    return article

        reserve_articles = self.db.get_reserve_news(1)
        if reserve_articles:
            return reserve_articles[0]

        return None

    def _get_fallback_news(self) -> List[NewsArticle]:
        return [NewsArticle(
            title='Игровая индустрия: последние новости и тренды',
            link='https://store.steampowered.com',
            source='Steam',
            category='games',
            description='Актуальные события из мира видеоигр'
        )]

    def setup_schedule(self):
        """Настраивает случайное расписание на день"""
        self.daily_schedule = Config.generate_random_schedule()

        # Очищаем старое расписание
        schedule.clear()

        # Создаем новое расписание
        for time_str in self.daily_schedule:
            schedule.every().day.at(time_str).do(lambda: asyncio.run(self.publish_news()))

        logger.info(f"⏰ Расписание на день настроено:")
        for i, time_str in enumerate(self.daily_schedule, 1):
            logger.info(f"   {i:2d}. {time_str}")

    def run(self):
        logger.info("🚀 Запуск умного бота новостей...")

        self.db.init_database()
        self.setup_schedule()

        # Первый запуск
        logger.info("🎯 Первый запуск публикации...")
        asyncio.run(self.publish_news())

        logger.info("\n⏰ Бот работает по расписанию...")
        logger.info("📅 Рабочее время: 7:00 - 00:00 (18 публикаций в день)")
        logger.info("🎲 Случайное время в течение каждого часа")
        logger.info("💾 Система резерва активна")
        logger.info("📡 Источники: RSS + HTML парсеры")
        logger.info("⏸️ Для остановки: Ctrl+C")

        # Основной цикл
        try:
            while True:
                schedule.run_pending()
                time.sleep(30)  # Проверяем каждые 30 секунд

                # Каждый день в 6:00 обновляем расписание
                if datetime.now().hour == 6 and datetime.now().minute == 0:
                    logger.info("🔄 Обновление расписания на новый день...")
                    self.setup_schedule()
                    time.sleep(60)  # Ждем минуту чтобы не сработало повторно

        except KeyboardInterrupt:
            logger.info("\n🛑 Бот остановлен пользователем")


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    bot = NewsBot()
    bot.run()