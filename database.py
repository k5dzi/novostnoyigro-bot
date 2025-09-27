import sqlite3
import hashlib
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = 'news_bot.db'):
        self.db_path = db_path
        self.connection = None

    def get_connection(self):
        if not self.connection:
            try:
                self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
                self.connection.row_factory = sqlite3.Row
            except Exception as e:
                logger.error(f"Ошибка подключения к БД: {e}")
                raise
        return self.connection

    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Таблица опубликованных новостей
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

            # Таблица резервных новостей
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

    def mark_news_as_posted(self, news_data: Dict):
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                'INSERT INTO posted_news (id, title, link, source, category) VALUES (?, ?, ?, ?, ?)',
                (news_data['id'], news_data['title'], news_data['link'],
                 news_data['source'], news_data.get('category', 'general'))
            )
            conn.commit()
            logger.info(f"✅ Новость добавлена в опубликованные: {news_data['title'][:50]}...")
        except Exception as e:
            logger.error(f"❌ Ошибка добавления новости: {e}")
            conn.rollback()
        finally:
            cursor.close()

    def add_to_reserve(self, articles: List[Dict]):
        conn = self.get_connection()
        cursor = conn.cursor()
        added_count = 0

        try:
            for article in articles:
                if not self.is_news_posted(article['id']):
                    cursor.execute('SELECT id FROM news_reserve WHERE id = ?', (article['id'],))
                    if not cursor.fetchone():
                        cursor.execute(
                            '''INSERT INTO news_reserve 
                            (id, title, link, image_url, source, description, category) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (article['id'], article['title'], article['link'], article.get('image_url'),
                             article['source'], article.get('description', ''), article.get('category', 'general'))
                        )
                        added_count += 1

            conn.commit()
            logger.info(f"💾 В резерв добавлено новостей: {added_count}")

        except Exception as e:
            logger.error(f"❌ Ошибка добавления в резерв: {e}")
            conn.rollback()
        finally:
            cursor.close()

    def get_reserve_news(self, count: int = 1) -> List[Dict]:
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
                article = dict(row)
                articles.append(article)

                cursor.execute('UPDATE news_reserve SET used = TRUE WHERE id = ?', (article['id'],))

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

def generate_news_id(title: str, link: str) -> str:
    content = f"{title}{link}".encode('utf-8')
    return hashlib.md5(content).hexdigest()