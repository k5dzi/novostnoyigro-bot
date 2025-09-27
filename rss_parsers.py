import feedparser
import aiohttp
import asyncio
from datetime import datetime, timedelta

RSS_SOURCES = [
    {
        'name': 'DTF Игры',
        'url': 'https://dtf.ru/r/games/go',  # Исправленная ссылка
        'category': 'games'
    },
    {
        'name': 'StopGame',
        'url': 'https://stopgame.ru/rss/news.xml',
        'category': 'news'
    },
    {
        'name': 'Igromania',
        'url': 'https://www.igromania.ru/rss/news.xml',
        'category': 'news'
    },
    {
        'name': 'Kanobu',
        'url': 'https://kanobu.ru/rss/news.xml',
        'category': 'news'
    },
    {
        'name': 'Cybersport.ru',
        'url': 'https://www.cybersport.ru/rss',
        'category': 'esports'
    }
]


async def parse_rss_feeds():
    """Парсим RSS-ленты"""
    news = []

    for source in RSS_SOURCES:
        try:
            print(f"📡 Парсим RSS: {source['name']}")
            feed = feedparser.parse(source['url'])

            # Проверяем успешность парсинга
            if feed.bozo == 1:  # есть ошибки в RSS
                print(f"⚠️ Ошибка RSS {source['name']}: {feed.bozo_exception}")
                continue

            for entry in feed.entries[:15]:  # Берем 15 последних
                # Безопасная проверка даты
                published_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        published_time = datetime(*entry.published_parsed[:6])
                        # Проверяем свежесть (не старше 48 часов)
                        if datetime.now() - published_time > timedelta(hours=48):
                            continue
                    except (TypeError, ValueError):
                        pass

                news.append({
                    'title': entry.title,
                    'link': entry.link,
                    'description': getattr(entry, 'summary', ''),
                    'source': source['name'],
                    'category': source['category'],
                    'published': published_time,
                    'image_url': find_image_in_entry(entry)
                })

        except Exception as e:
            print(f"❌ Ошибка парсинга {source['name']}: {e}")

    print(f"✅ RSS новостей собрано: {len(news)}")
    return news


def find_image_in_entry(entry):
    """Ищем картинку в RSS-записи"""
    try:
        # Проверяем медиа-контент
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('image'):
                    return media['url']

        # Проверяем ссылки
        if hasattr(entry, 'links'):
            for link in entry.links:
                if hasattr(link, 'type') and link.type and 'image' in link.type:
                    return link.href

        # Проверяем контент
        if hasattr(entry, 'content'):
            for content in entry.content:
                if 'image' in getattr(content, 'type', ''):
                    return getattr(content, 'value', '')

    except Exception as e:
        print(f"⚠️ Ошибка поиска картинки: {e}")

    return None