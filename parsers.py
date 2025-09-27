import requests
from bs4 import BeautifulSoup
import random
import time

# Глобальные настройки для избежания таймаутов на хостинге
REQUEST_TIMEOUT = 15
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def get_dtf_russian_news():
    """Парсер DTF (русский)"""
    try:
        url = "https://dtf.ru/games"
        print(f"🌐 Парсим DTF...")

        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()  # Проверяем статус ответа

        soup = BeautifulSoup(response.text, 'html.parser')
        news = []

        # Более гибкий поиск статей
        articles = soup.find_all('article')[:8]  # Уменьшили лимит для скорости

        for i, article in enumerate(articles):
            try:
                # Несколько вариантов поиска заголовка
                title_tag = (article.find('h2', class_='content-title') or
                             article.find('h3', class_='content-title') or
                             article.find('a', class_='content-link'))

                if title_tag:
                    link_tag = title_tag.find('a') if title_tag.name != 'a' else title_tag
                    if link_tag and link_tag.get('href'):
                        title = link_tag.text.strip()
                        if len(title) < 10:  # Слишком короткий заголовок - пропускаем
                            continue

                        link = link_tag['href']
                        if not link.startswith('http'):
                            link = "https://dtf.ru" + link

                        # Описание
                        description_tag = article.find('div', class_='content-description')
                        description = description_tag.text.strip()[
                                      :200] if description_tag else "Новость из мира видеоигр"

                        # Картинка
                        image_url = None
                        img_tag = article.find('img')
                        if img_tag and img_tag.get('src'):
                            image_url = img_tag['src']
                            if image_url.startswith('//'):
                                image_url = 'https:' + image_url
                            elif image_url.startswith('/'):
                                image_url = 'https://dtf.ru' + image_url

                        news.append({
                            'title': title,
                            'description': description,
                            'link': link,
                            'image_url': image_url,
                            'source': 'DTF',
                            'has_image': image_url is not None
                        })

            except Exception as e:
                print(f"⚠️ Ошибка обработки статьи {i}: {e}")
                continue

        print(f"✅ DTF новостей: {len(news)}")
        return news

    except requests.exceptions.Timeout:
        print("❌ Таймаут при парсинге DTF")
        return []
    except Exception as e:
        print(f"❌ Ошибка DTF: {e}")
        return []


def get_igromania_russian_news():
    """Парсер Игромании (русский)"""
    try:
        url = "https://www.igromania.ru/news/"
        print(f"🌐 Парсим Игроманию...")

        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        news = []

        articles = soup.find_all('div', class_='aubli_data')[:8]

        for article in articles:
            try:
                title_tag = article.find('a', class_='aubli_name')
                if title_tag:
                    title = title_tag.text.strip()
                    if len(title) < 10:
                        continue

                    link = title_tag['href']
                    if not link.startswith('http'):
                        link = 'https://www.igromania.ru' + link

                    # Описание
                    description_tag = article.find('div', class_='aubli_text')
                    description = description_tag.text.strip()[
                                  :200] if description_tag else "Последние новости игровой индустрии"

                    # Картинка
                    image_url = None
                    img_tag = article.find('img')
                    if img_tag and img_tag.get('src'):
                        image_url = img_tag['src']
                        if image_url.startswith('//'):
                            image_url = 'https:' + image_url

                    news.append({
                        'title': title,
                        'description': description,
                        'link': link,
                        'image_url': image_url,
                        'source': 'Игромания',
                        'has_image': image_url is not None
                    })

            except Exception as e:
                print(f"⚠️ Ошибка обработки статьи: {e}")
                continue

        print(f"✅ Игромания новостей: {len(news)}")
        return news

    except requests.exceptions.Timeout:
        print("❌ Таймаут при парсинге Игромании")
        return []
    except Exception as e:
        print(f"❌ Ошибка Игромании: {e}")
        return []


def get_kanobu_russian_news():
    """Парсер Канобу (русский) - УДАЛЯЕМ, так как есть RSS"""
    # На хостинге используем только RSS для скорости
    return []


def get_manual_russian_news():
    """Резервные новости на русском"""
    backup_news = [
        {
            'title': 'Cyberpunk 2077: Phantom Liberty - вышло новое обновление с исправлениями',
            'description': 'Разработчики выпустили масштабное обновление для дополнения Phantom Liberty',
            'link': 'https://www.cyberpunk.net',
            'image_url': None,
            'source': 'CD Projekt Red',
            'has_image': False
        },
        {
            'title': 'В Steam вышел новый хит - игра побила рекорды продаж',
            'description': 'Независимая студия представила проект, который покорил геймеров',
            'link': 'https://store.steampowered.com',
            'image_url': None,
            'source': 'Steam',
            'has_image': False
        }
    ]
    return backup_news


def get_all_gaming_news():
    """Основная функция - оптимизированная для хостинга"""
    print("🕸️  Быстрый парсинг новостей...")

    all_news = []

    # Только быстрые и надежные источники
    all_news.extend(get_dtf_russian_news())
    all_news.extend(get_igromania_russian_news())

    print(f"📊 Найдено новостей: {len(all_news)}")

    # Если ничего не нашли - используем резервные
    if not all_news:
        print("⚠️  Новости не найдены, используем резервные")
        all_news = get_manual_russian_news()

    # Быстрая фильтрация дубликатов
    unique_news = []
    seen_titles = set()

    for news in all_news:
        title_lower = news['title'].lower()
        if title_lower not in seen_titles:
            seen_titles.add(title_lower)
            unique_news.append(news)

    # Простой выбор новостей (без сложной логики)
    result = unique_news[:3]  # Просто берем первые 3

    print(f"✅ Выбрано для публикации: {len(result)}")
    return result


# Тест
if __name__ == "__main__":
    news = get_all_gaming_news()
    print(f"\n=== РЕЗУЛЬТАТ: {len(news)} новостей ===")
    for i, item in enumerate(news, 1):
        print(f"\n{i}. {item['source']}: {item['title']}")
        print(f"   Ссылка: {item['link']}")