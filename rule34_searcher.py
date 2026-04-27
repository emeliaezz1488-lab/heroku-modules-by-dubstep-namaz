# meta developer: @dubstep_namaz1337
# meta banner: https://i.imgur.com/gallery/icon-of-rule34-FAzGMDE

"""
Модуль для поиска изображений и видео на Rule34.

Это порт плагина с exteraGram для Heroku UserBot.

Оригинальные разработчики: @ArThirtyFour | @KangelPlugins
Портировал: @dubstep_namaz1337

Триггер-слова (автоматический поиск):
- "фута" - поиск по тегу futa (картинки)
- "фембой" - поиск по тегу femboy (картинки)
- "порно" - случайное видео с Rule34
"""

import random
import requests
import asyncio
import json
import os
import time
import threading
import concurrent.futures
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple
from collections import defaultdict, deque
from herokutl.types import Message
from .. import loader, utils

# User-Agent список для ротации
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

def get_random_user_agent() -> str:
    """Получить случайный User-Agent"""
    return random.choice(USER_AGENTS)


def normalize_proxy_url(raw: str) -> Optional[str]:
    """Нормализация URL прокси"""
    try:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None

        if s.startswith("http://") or s.startswith("https://") or s.startswith("socks4://") or s.startswith("socks5://"):
            return s

        parts = s.split(":")
        if len(parts) == 2:
            host, port = parts
            if host and port:
                return f"http://{host}:{port}"
            return None

        if len(parts) == 4:
            host, port, user, pwd = parts
            if host and port and user and pwd:
                return f"http://{user}:{pwd}@{host}:{port}"
            return None

        return None
    except Exception:
        return None


def build_requests_proxies(proxy_url: Optional[str]) -> Optional[dict]:
    """Построить словарь прокси для requests"""
    p = normalize_proxy_url(proxy_url)
    if not p:
        return None
    return {"http": p, "https": p}


def check_single_proxy(proxy: str) -> Tuple[str, bool, float]:
    """Проверить один прокси"""
    start_time = time.time()
    
    try:
        proxy_dict = build_requests_proxies(proxy)
        if not proxy_dict:
            return proxy, False, 0
        
        response = requests.get(
            "https://yande.re",
            proxies=proxy_dict,
            timeout=3
        )
        
        if response.status_code == 200:
            response_time = time.time() - start_time
            return proxy, True, response_time
        else:
            return proxy, False, 0
            
    except Exception:
        return proxy, False, 0


def check_proxies_parallel(proxies: List[str], max_workers: int = 50, max_working: int = 20) -> List[Dict]:
    """Проверить прокси параллельно"""
    working_proxies = []
    working_proxies_lock = threading.Lock()
    stop_search = threading.Event()
    
    def check_proxy_wrapper(proxy):
        if stop_search.is_set():
            return proxy, False, 0
            
        proxy, is_working, response_time = check_single_proxy(proxy)
        
        if is_working:
            with working_proxies_lock:
                working_proxies.append({
                    "proxy": proxy,
                    "response_time": response_time
                })
                
                if len(working_proxies) >= max_working:
                    stop_search.set()
        
        return proxy, is_working, response_time
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_proxy = {executor.submit(check_proxy_wrapper, proxy): proxy for proxy in proxies}
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            if stop_search.is_set():
                for f in future_to_proxy:
                    f.cancel()
                break
    
    return working_proxies


def get_request_headers(rotate_ua: bool = True) -> dict:
    """Получить заголовки для запроса"""
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    if rotate_ua:
        headers["User-Agent"] = get_random_user_agent()
    else:
        headers["User-Agent"] = USER_AGENTS[0]
    
    return headers


def localise(key: str, lang: str = "ru") -> str:
    """Локализация строк"""
    locales = {
        "ru": {
            "not_found": "Ничего не найдено!",
            "not_found_filtered": "Ничего не найдено после фильтрации!",
            "request_error": "Ошибка при запросе: {e}",
            "xml_parse_error": "Ошибка при парсинге XML.",
            "general_data_error": "Произошла общая ошибка при получении данных: {e}",
            "unknown_site": "Неизвестный сайт для поиска.",
            "no_args": "Нет аргументов!",
            "usage": "Использование: .r34 [теги] [кол-во]\nПример: .r34 anime 2",
            "searching": "Ищем...",
            "post_found_header": "🔞 *Найден пост!*\n\n",
            "requested_tags_line": "🔍 *Запрошенные теги:* `{requested_tags_str}`\n\n",
            "post_tags_line": "🏷️ *Теги в посте:* `{post_tags}`\n\n",
            "rating_line": "🔞 *Рейтинг:* `{rating}`\n\n",
            "image_link_line": "🔗 *Ссылка:* [Открыть изображение]({image_url})",
            "site_blocked_rule34": "Rule34.xxx заблокирован! Включите VPN.",
            "site_blocked_yandere": "Yande.re заблокирован! Включите VPN.",
        },
        "en": {
            "not_found": "Nothing found!",
            "not_found_filtered": "Nothing found after filtering!",
            "request_error": "Request error: {e}",
            "xml_parse_error": "XML parse error.",
            "general_data_error": "An error occurred while fetching data: {e}",
            "unknown_site": "Unknown search site.",
            "no_args": "No arguments!",
            "usage": "Usage: .r34 [tags] [count]\nExample: .r34 anime 2",
            "searching": "Searching...",
            "post_found_header": "🔞 *Post found!*\n\n",
            "requested_tags_line": "🔍 *Requested tags:* `{requested_tags_str}`\n\n",
            "post_tags_line": "🏷️ *Tags in post:* `{post_tags}`\n\n",
            "rating_line": "🔞 *Rating:* `{rating}`\n\n",
            "image_link_line": "🔗 *Link:* [Open image]({image_url})",
            "site_blocked_rule34": "Rule34.xxx is blocked! Enable VPN.",
            "site_blocked_yandere": "Yande.re is blocked! Enable VPN.",
        }
    }
    return locales.get(lang, locales["en"]).get(key, key)


@loader.tds
class Rule34Searcher(loader.Module):
    """Поиск изображений и видео на Rule34"""
    
    strings = {
        "name": "Rule34Searcher",
        "not_found": "Ничего не найдено!",
        "searching": "Ищем...",
        "error": "Ошибка: {}",
        "usage_r34": "Использование: .r34 [теги] [кол-во]\nПример: .r34 anime 2",
        "proxy_update_started": "Обновление прокси началось...",
        "proxy_update_success": "Список прокси обновлен! Найдено {} рабочих прокси",
        "proxy_update_error": "Ошибка при обновлении прокси: {}",
        "whitelist_help": "❌ <b>Укажите аргумент для команды!</b>\n\n<b>Использование:</b>\n• <code>.whitelist add [chat_id]</code> - добавить чат\n• <code>.whitelist remove [chat_id]</code> - удалить чат\n• <code>.whitelist list</code> - показать список",
        "chat_not_whitelisted": "⚠️ <b>Чат не в вайтлисте!</b>\n\nДобавьте сначала этот чат в вайтлист:\n<code>.whitelist add {}</code>\n\nИли отключите вайтлист в конфиге модуля.",
        "current_chat_id": "Текущий чат ID",
        "whitelist_empty": "Вайтлист пуст",
        "add_chats_with_command": "Добавьте чаты командой",
        "chat_whitelist": "Вайтлист чатов",
        "total_chats": "Всего чатов",
        "whitelist": "Вайтлист",
        "enabled": "Включен",
        "disabled": "Выключен",
        "specify_chat_id": "Укажите ID чата!",
        "usage": "Использование",
        "example": "Пример",
        "invalid_chat_id_format": "Неверный формат ID чата!",
        "id_must_be_number": "ID должен быть числом.",
        "chat": "Чат",
        "already_in_whitelist": "уже в вайтлисте!",
        "total_in_whitelist": "Всего в вайтлисте",
        "chat_added_to_whitelist": "Чат добавлен в вайтлист!",
        "not_found_in_whitelist": "не найден в вайтлисте!",
        "remaining_in_whitelist": "Осталось в вайтлисте",
        "chat_removed_from_whitelist": "Чат удален из вайтлиста!",
        "unknown_argument": "Неизвестный аргумент",
        "available_arguments": "Доступные аргументы",
        "add_chat": "добавить чат",
        "remove_chat": "удалить чат",
        "show_list": "показать список",
    }
    
    strings_en = {
        "not_found": "Nothing found!",
        "searching": "Searching...",
        "error": "Error: {}",
        "usage_r34": "Usage: .r34 [tags] [count]\nExample: .r34 anime 2",
        "proxy_update_started": "Proxy update started...",
        "proxy_update_success": "Proxy list updated! Found {} working proxies",
        "proxy_update_error": "Proxy update error: {}",
        "whitelist_help": "❌ <b>Specify command argument!</b>\n\n<b>Usage:</b>\n• <code>.whitelist add [chat_id]</code> - add chat\n• <code>.whitelist remove [chat_id]</code> - remove chat\n• <code>.whitelist list</code> - show list",
        "chat_not_whitelisted": "⚠️ <b>Chat not in whitelist!</b>\n\nAdd this chat to whitelist first:\n<code>.whitelist add {}</code>\n\nOr disable whitelist in module config.",
        "current_chat_id": "Current chat ID",
        "whitelist_empty": "Whitelist is empty",
        "add_chats_with_command": "Add chats with command",
        "chat_whitelist": "Chat whitelist",
        "total_chats": "Total chats",
        "whitelist": "Whitelist",
        "enabled": "Enabled",
        "disabled": "Disabled",
        "specify_chat_id": "Specify chat ID!",
        "usage": "Usage",
        "example": "Example",
        "invalid_chat_id_format": "Invalid chat ID format!",
        "id_must_be_number": "ID must be a number.",
        "chat": "Chat",
        "already_in_whitelist": "already in whitelist!",
        "total_in_whitelist": "Total in whitelist",
        "chat_added_to_whitelist": "Chat added to whitelist!",
        "not_found_in_whitelist": "not found in whitelist!",
        "remaining_in_whitelist": "Remaining in whitelist",
        "chat_removed_from_whitelist": "Chat removed from whitelist!",
        "unknown_argument": "Unknown argument",
        "available_arguments": "Available arguments",
        "add_chat": "add chat",
        "remove_chat": "remove chat",
        "show_list": "show list",
    }

    def __init__(self):
        self.config = loader.ModuleConfig(
            loader.ConfigValue(
                "tags_in",
                "",
                "Теги для включения (через пробел)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "tags_ex",
                "",
                "Теги для исключения (через ;)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "antiai",
                True,
                "Фильтр AI-контента",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "posts_count",
                100,
                "Количество постов для поиска (макс: 1000)",
                validator=loader.validators.Integer(minimum=1, maximum=1000),
            ),
            loader.ConfigValue(
                "send_count",
                1,
                "Сколько постов отправлять (макс: 10)",
                validator=loader.validators.Integer(minimum=1, maximum=10),
            ),
            loader.ConfigValue(
                "use_proxy",
                False,
                "Использовать прокси",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "proxy_rotate",
                True,
                "Ротировать прокси",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "proxy_rotate_ua",
                True,
                "Ротировать User-Agent",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "proxy_source",
                "builtin",
                "Источник прокси (builtin/url/manual)",
                validator=loader.validators.Choice(["builtin", "url", "manual"]),
            ),
            loader.ConfigValue(
                "proxy_source_url",
                "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/all/data.txt",
                "URL списка прокси",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "proxy_manual_list",
                "",
                "Ручной список прокси (ip:port, по одному на строку)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "triggers_enabled",
                True,
                "Включить триггер-слова",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "spam_protection",
                True,
                "Включить анти-спам защиту",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "auto_delete",
                True,
                "Автоматически удалять отправленное медиа",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "auto_delete_delay",
                30,
                "Задержка в секундах перед автоудалением (0 для отключения)",
                validator=loader.validators.Integer(minimum=0),
            ),
            loader.ConfigValue(
                "download_before_send",
                False,
                "Скачивать файлы перед отправкой (медленнее, но надежнее)",
                validator=loader.validators.Boolean(),
            ),
            loader.ConfigValue(
                "chat_whitelist_enabled",
                True,
                "Включить вайтлист чатов (работать только в разрешенных чатах)",
                validator=loader.validators.Boolean(),
            ),
        )
        self._cache = {}
        self._working_proxies = []
        self._proxy_file = "booru_proxies.json"
        
        # Вайтлист чатов (будет загружаться из БД)
        self._chat_whitelist = set()
        
        # Система исключения повторов
        self._recent_posts = defaultdict(lambda: deque(maxlen=50))  # Храним последние 50 ID для каждого тега
        
        # Анти-спам система
        self._spam_events = defaultdict(deque)
        self._chat_spam_events = defaultdict(deque)
        self._spam_blocks = {}
        self._chat_spam_blocks = {}
        self._spam_lock = asyncio.Lock()
        
        self.SPAM_LIMIT = 3
        self.SPAM_WINDOW = 3
        self.BLOCK_DURATION = 15
        self.GLOBAL_LIMIT = 10
        self.GLOBAL_WINDOW = 10
        
        # Триггер-слова
        self.triggers = {
            "фута": "futa",
            "фембой": "femboy",
            "порно": "video"  # специальный маркер для видео
        }

    async def client_ready(self, client, db):
        """Инициализация при запуске"""
        self.client = client
        self._db = db
        # Загружаем вайтлист из БД
        self._chat_whitelist = set(self._db.get(__name__, "chat_whitelist", []))

    def _get_chat_id(self, peer_id) -> int:
        """Получить числовой ID чата из объекта Peer"""
        if hasattr(peer_id, 'channel_id'):
            return -1000000000000 - peer_id.channel_id
        elif hasattr(peer_id, 'chat_id'):
            return -peer_id.chat_id
        elif hasattr(peer_id, 'user_id'):
            return peer_id.user_id
        else:
            return peer_id

    def _is_chat_allowed(self, chat_id) -> bool:
        """Проверка разрешен ли чат"""
        if not self.config["chat_whitelist_enabled"]:
            return True  # Если вайтлист выключен, разрешены все чаты
        
        # Получаем числовой ID
        chat_id_num = self._get_chat_id(chat_id)
        
        return chat_id_num in self._chat_whitelist

    def _save_whitelist(self):
        """Сохранить вайтлист в БД"""
        self._db.set(__name__, "chat_whitelist", list(self._chat_whitelist))

    def _save_proxies(self):
        """Сохранить рабочие прокси в файл"""
        try:
            proxy_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                self._proxy_file
            )
            with open(proxy_path, 'w', encoding='utf-8') as f:
                json.dump(self._working_proxies, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_proxies(self):
        """Загрузить рабочие прокси из файла"""
        try:
            proxy_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                self._proxy_file
            )
            if os.path.exists(proxy_path):
                with open(proxy_path, 'r', encoding='utf-8') as f:
                    self._working_proxies = json.load(f)
        except Exception:
            self._working_proxies = []

    def _get_working_proxy(self, test_url: str = "https://api.rule34.xxx/") -> Optional[dict]:
        """Получить рабочий прокси"""
        try:
            if not self._working_proxies:
                self._load_proxies()
            
            if self._working_proxies:
                random.shuffle(self._working_proxies)
                
                for proxy_info in self._working_proxies[:5]:
                    proxy = proxy_info['proxy']
                    proxy_dict = build_requests_proxies(proxy)
                    if not proxy_dict:
                        continue
                    headers = get_request_headers(self.config["proxy_rotate_ua"])
                    
                    try:
                        test_response = requests.get(test_url, proxies=proxy_dict, headers=headers, timeout=5)
                        if test_response.status_code == 200:
                            return proxy_dict
                    except Exception:
                        continue
            
            return None
            
        except Exception:
            return None

    async def _update_proxy_list(self):
        """Обновить список прокси"""
        def update_proxies_background():
            try:
                proxy_source = self.config["proxy_source"]
                proxies = []
                
                if proxy_source == "url":
                    url = self.config["proxy_source_url"]
                    response = requests.get(url, timeout=10)
                    response.raise_for_status()
                    raw_proxies = [line.strip() for line in response.text.split('\n') if line.strip()]
                    for proxy in raw_proxies:
                        norm = normalize_proxy_url(proxy)
                        if norm:
                            proxies.append(norm)
                
                elif proxy_source == "manual":
                    manual_list = self.config["proxy_manual_list"]
                    raw_proxies = [line.strip() for line in manual_list.split('\n') if line.strip()]
                    for proxy in raw_proxies:
                        norm = normalize_proxy_url(proxy)
                        if norm:
                            proxies.append(norm)
                
                if proxies:
                    working = check_proxies_parallel(proxies, max_workers=50, max_working=20)
                    self._working_proxies = working
                    self._save_proxies()
                    return len(working)
                
                return 0
            except Exception as e:
                raise e
        
        try:
            count = await utils.run_sync(update_proxies_background)
            return count
        except Exception as e:
            raise e

    async def _make_request(self, url: str, params: dict = None, use_proxy: bool = False) -> Optional[requests.Response]:
        """Выполнить HTTP запрос с поддержкой прокси"""
        def _request():
            headers = get_request_headers(self.config["proxy_rotate_ua"])
            
            # Сначала пробуем без прокси
            try:
                response = requests.get(url, params=params, headers=headers, timeout=5)
                response.raise_for_status()
                return response
            except Exception:
                # Если не удалось и включены прокси
                if use_proxy and self.config["use_proxy"]:
                    proxy_dict = self._get_working_proxy(url)
                    if proxy_dict:
                        response = requests.get(url, params=params, headers=headers, proxies=proxy_dict, timeout=10)
                        response.raise_for_status()
                        return response
                    else:
                        # Пробуем еще раз без прокси
                        response = requests.get(url, params=params, headers=headers, timeout=10)
                        response.raise_for_status()
                        return response
                else:
                    # Пробуем еще раз без прокси
                    response = requests.get(url, params=params, headers=headers, timeout=10)
                    response.raise_for_status()
                    return response
        
        try:
            return await utils.run_sync(_request)
        except Exception:
            return None

    async def _search_rule34(self, tags: str, limit: int = 100) -> List[Dict]:
        """Поиск на Rule34 с полной поддержкой прокси и API"""
        # Добавляем теги из конфига
        tags_in_setting = self.config["tags_in"]
        tags_ex_setting = self.config["tags_ex"]
        antiai = self.config["antiai"]
        
        # Парсим теги из запроса
        query_parts = tags.split() if tags else []
        include_tags = []
        exclude_tags = []
        
        for part in query_parts:
            if part.startswith('-'):
                exclude_tags.append(part[1:])
            else:
                include_tags.append(part)
        
        # Строим поисковый запрос
        search_tags = f"{tags_in_setting} {' '.join(include_tags)}".strip()
        
        # Добавляем исключающие теги
        all_exclude_tags = tags_ex_setting.split("; ") + exclude_tags
        tags_ex = [tag.strip() for tag in all_exclude_tags if tag.strip()]
        
        # Добавляем анти-AI теги только если включено
        if antiai:
            anti_ai_tags = ['-ai_generated', '-stable_diffusion', '-midjourney', '-artificial_intelligence', 
                          '-neural_network', '-machine_learning', '-deepfake', '-ai_art', '-ai-generated', 
                          '-generated_by_ai', '-dall_e', '-dalle', '-novelai', '-waifu_diffusion']
            search_tags += ' ' + ' '.join(anti_ai_tags)
        
        # Добавляем исключающие теги в запрос
        if tags_ex:
            exclude_tags_api = ['-' + tag for tag in tags_ex]
            search_tags += ' ' + ' '.join(exclude_tags_api)
        
        # Используем случайную страницу для разнообразия (от 0 до 10)
        random_page = random.randint(0, 10)
        
        # Параметры запроса с API ключом (БЕЗ json=1, чтобы получить XML)
        url = "https://api.rule34.xxx/index.php"
        params = {
            'page': 'dapi',
            's': 'post',
            'q': 'index',
            'limit': min(limit, 1000),  # API максимум 1000
            'pid': random_page,  # Случайная страница
            'tags': search_tags.strip() if search_tags.strip() else None,
            'api_key': 'd82f6db279ce94313e629e791533d456a4309dfeb528ddab6eee4b7472156f0def07ebfd3e64b9dddbf0d3b78f227ba8a5f386533ef1ccb1377d8a97481811dc',
            'user_id': '5255009'
        }
        
        # Убираем пустые параметры
        params = {k: v for k, v in params.items() if v is not None}
        
        response = await self._make_request(url, params, use_proxy=True)
        if not response:
            return []
        
        try:
            # Парсим XML ответ
            root = ET.fromstring(response.text)
            posts = []
            
            # Ключ для отслеживания повторов
            tag_key = search_tags.strip() if search_tags.strip() else "random"
            recent_ids = self._recent_posts[tag_key]
            
            for post in root.findall("post"):
                post_id = post.get("id", "")
                
                # Пропускаем если уже показывали недавно
                if post_id in recent_ids:
                    continue
                
                # Получаем URL изображения
                image_url = post.get('file_url') or post.get('sample_url')
                
                if not image_url:
                    continue
                
                # Парсим теги
                tags_str = post.get('tags', '')
                tags_list = tags_str.split() if tags_str else []
                
                posts.append({
                    "file_url": image_url,
                    "tags": tags_list,
                    "rating": post.get("rating", ""),
                    "id": post_id,
                })
            
            return posts
        except Exception as e:
            # Логируем ошибку для отладки
            print(f"[Rule34Searcher] Error parsing Rule34 response: {e}")
            return []

    def _format_caption(self, post: Dict, requested_tags: str) -> str:
        """Форматирование подписи к посту"""
        return "🔞 <b>Найден пост!</b>"

    async def _download_file(self, url: str) -> Optional[bytes]:
        """Скачать файл по URL"""
        try:
            def _download():
                headers = get_request_headers(self.config["proxy_rotate_ua"])
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                return response.content
            
            return await utils.run_sync(_download)
        except Exception as e:
            print(f"[Rule34Searcher] Error downloading file: {e}")
            return None

    async def _send_posts(self, message: Message, posts: List[Dict], requested_tags: str, count: int):
        """Отправка постов (изображения и видео)"""
        if not posts:
            await utils.answer(message, self.strings("not_found"))
            return
        
        # Перемешиваем посты для случайности
        random.shuffle(posts)
        
        # Ключ для отслеживания повторов
        tag_key = requested_tags.strip() if requested_tags.strip() else "random"
        recent_ids = self._recent_posts[tag_key]
        
        sent_count = 0
        sent_messages = []
        attempts = 0
        max_attempts = min(len(posts), count * 10)  # Пробуем до 10x больше постов чем нужно
        
        for post in posts:
            if sent_count >= count:
                break
                
            if attempts >= max_attempts:
                break
                
            attempts += 1
            
            file_url = post.get("file_url")
            post_id = post.get("id", "")
            
            if not file_url:
                continue
            
            caption = self._format_caption(post, requested_tags)
            
            try:
                # Определяем тип файла по расширению
                file_ext = file_url.lower().split('?')[0].split('.')[-1]
                is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi', 'mkv']
                
                # Если включено скачивание перед отправкой
                if self.config["download_before_send"]:
                    file_data = await self._download_file(file_url)
                    if not file_data:
                        continue
                    
                    # Отправляем скачанный файл
                    sent_msg = await message.client.send_file(
                        message.peer_id,
                        file_data,
                        caption=caption,
                        parse_mode="html",
                        reply_to=getattr(message, "reply_to_msg_id", None),
                        supports_streaming=is_video,
                        attributes=[],  # Telegram сам определит тип
                    )
                else:
                    # Отправляем файл по URL (быстрее)
                    sent_msg = await message.client.send_file(
                        message.peer_id,
                        file_url,
                        caption=caption,
                        parse_mode="html",
                        reply_to=getattr(message, "reply_to_msg_id", None),
                        supports_streaming=is_video,
                    )
                
                sent_messages.append(sent_msg)
                sent_count += 1
                
                # Добавляем ID в список недавно показанных
                if post_id:
                    recent_ids.append(post_id)
                    
            except Exception as e:
                # Логируем ошибку для отладки
                error_msg = str(e)
                print(f"[Rule34Searcher] Error sending file {file_url[:50]}...: {error_msg}")
                
                # Пропускаем этот пост и пробуем следующий
                continue
        
        if sent_count == 0:
            # Более информативное сообщение об ошибке
            await utils.answer(message, f"❌ Не удалось отправить медиа.\nНайдено постов: {len(posts)}\nПопыток отправки: {attempts}\n\nВозможные причины:\n• Файлы слишком большие\n• Telegram не может загрузить файлы\n• Все файлы битые")
        else:
            await message.delete()
            
            # Автоудаление если включено
            if self.config["auto_delete"] and self.config["auto_delete_delay"] > 0:
                await asyncio.sleep(self.config["auto_delete_delay"])
                for msg in sent_messages:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

    def _prune_spam_events(self, events, current_time, window):
        """Очистка старых событий спама"""
        while events and current_time - events[0] > window:
            events.popleft()

    def _is_spam_blocked(self, blocks, key, current_time):
        """Проверка блокировки спама"""
        block_until = blocks.get(key)
        if not block_until:
            return False
        if current_time < block_until:
            return True
        del blocks[key]
        return False

    def _spam_user_key(self, user_id, chat_id):
        """Генерация ключа для пользователя"""
        if user_id is None:
            return f"unknown:{chat_id}"
        return f"{user_id}:{chat_id}"

    async def _check_spam(self, user_id, chat_id):
        """Проверка на спам"""
        if not self.config["spam_protection"]:
            return False
        
        current_time = time.time()
        user_key = self._spam_user_key(user_id, chat_id)
        chat_key = str(chat_id)
        
        async with self._spam_lock:
            if self._is_spam_blocked(self._chat_spam_blocks, chat_key, current_time):
                return True
            if self._is_spam_blocked(self._spam_blocks, user_key, current_time):
                return True
            
            user_events = self._spam_events[user_key]
            chat_events = self._chat_spam_events[chat_key]
            
            self._prune_spam_events(user_events, current_time, self.SPAM_WINDOW)
            self._prune_spam_events(chat_events, current_time, self.GLOBAL_WINDOW)
            
            if len(user_events) >= self.SPAM_LIMIT:
                self._spam_blocks[user_key] = current_time + self.BLOCK_DURATION
                user_events.clear()
                return True
            
            if len(chat_events) >= self.GLOBAL_LIMIT:
                self._chat_spam_blocks[chat_key] = current_time + self.BLOCK_DURATION
                chat_events.clear()
                return True
            
            user_events.append(current_time)
            chat_events.append(current_time)
            return False

    async def _search_and_send_by_trigger(self, message: Message, search_tag: str, video_only: bool = False):
        """Поиск и отправка по триггеру"""
        # Проверка на спам
        user_id = message.sender_id
        chat_id = message.peer_id
        
        if await self._check_spam(user_id, chat_id):
            return
        
        # Сохраняем оригинальный тег для подписи
        display_tag = search_tag
        
        # Если нужны только видео, добавляем специальные теги для поиска
        if video_only:
            # Ищем с тегами video или animated для гарантии видео
            video_tags = ["video", "animated", "webm", "mp4"]
            search_tag = random.choice(video_tags)
            # Для "порно" не показываем технический тег в подписи
            display_tag = ""
        
        # Поиск постов
        posts = await self._search_rule34(search_tag, self.config["posts_count"])
        
        # Дополнительная фильтрация только видео если нужно
        if video_only and posts:
            video_posts = []
            for post in posts:
                file_url = post.get("file_url", "")
                file_ext = file_url.lower().split('?')[0].split('.')[-1]
                if file_ext in ['mp4', 'webm', 'mov', 'avi', 'mkv']:
                    video_posts.append(post)
            
            # Если после фильтрации ничего не осталось, пробуем еще раз с другим тегом
            if not video_posts and posts:
                # Пробуем найти хоть что-то с расширением видео
                for post in posts:
                    file_url = post.get("file_url", "")
                    if any(ext in file_url.lower() for ext in ['.mp4', '.webm', '.mov', '.avi', '.mkv']):
                        video_posts.append(post)
            
            posts = video_posts if video_posts else posts
        
        if not posts:
            return
        
        # Отправка одного поста с правильным тегом для подписи
        await self._send_posts(message, posts, display_tag, 1)

    @loader.watcher()
    async def watcher(self, message: Message):
        """Отслеживание триггер-слов"""
        try:
            if not self.config["triggers_enabled"]:
                return
            
            if not message.text:
                return
            
            # Игнорируем команды
            if message.text.startswith("."):
                return
            
            # Игнорируем свои сообщения
            if message.out:
                return
            
            # Проверяем вайтлист чатов
            if not self._is_chat_allowed(message.peer_id):
                return
            
            text_lower = message.text.lower()
            
            # Проверяем триггер-слова в определенном порядке
            # Сначала проверяем "порно" (чтобы не путалось с другими)
            if "порно" in text_lower:
                await self._search_and_send_by_trigger(message, "", video_only=True)
                return
            
            # Потом остальные триггеры
            if "фута" in text_lower:
                await self._search_and_send_by_trigger(message, "futa", video_only=False)
                return
                
            if "фембой" in text_lower:
                await self._search_and_send_by_trigger(message, "femboy", video_only=False)
                return
                
        except Exception as e:
            print(f"[Rule34Searcher] Watcher error: {e}")

    @loader.command(
        ru_doc="Управление вайтлистом чатов",
        en_doc="Manage chat whitelist",
    )
    async def whitelistcmd(self, message: Message):
        """[add/remove/list] [chat_id] - Управление вайтлистом чатов"""
        args = utils.get_args_raw(message)
        
        # Получаем числовой ID текущего чата
        current_chat_id = self._get_chat_id(message.peer_id)
        
        if not args:
            help_text = self.strings("whitelist_help")
            await utils.answer(
                message,
                f"{help_text}\n\n<b>{self.strings('current_chat_id')}:</b> <code>{current_chat_id}</code>"
            )
            return
        
        parts = args.split(maxsplit=1)
        action = parts[0].lower()
        
        if action == "list":
            if not self._chat_whitelist:
                await utils.answer(
                    message,
                    f"📋 <b>{self.strings('whitelist_empty')}</b>\n\n"
                    f"{self.strings('add_chats_with_command')}:\n"
                    "<code>.whitelist add [chat_id]</code>"
                )
                return
            
            whitelist_text = f"📋 <b>{self.strings('chat_whitelist')}:</b>\n\n"
            for chat_id in sorted(self._chat_whitelist):
                try:
                    chat = await message.client.get_entity(chat_id)
                    chat_name = getattr(chat, 'title', getattr(chat, 'username', 'Unknown'))
                    whitelist_text += f"• <code>{chat_id}</code> - {chat_name}\n"
                except Exception:
                    whitelist_text += f"• <code>{chat_id}</code>\n"
            
            whitelist_text += f"\n<b>{self.strings('total_chats')}:</b> {len(self._chat_whitelist)}"
            whitelist_enabled = "✅ " + self.strings('enabled') if self.config['chat_whitelist_enabled'] else "❌ " + self.strings('disabled')
            whitelist_text += f"\n<b>{self.strings('whitelist')}:</b> {whitelist_enabled}"
            
            await utils.answer(message, whitelist_text)
            return
        
        if action == "add":
            if len(parts) < 2:
                await utils.answer(
                    message,
                    f"❌ <b>{self.strings('specify_chat_id')}</b>\n\n"
                    f"<b>{self.strings('usage')}:</b>\n"
                    "<code>.whitelist add [chat_id]</code>\n\n"
                    f"<b>{self.strings('example')}:</b>\n"
                    "<code>.whitelist add -1001234567890</code>\n\n"
                    f"<b>{self.strings('current_chat_id')}:</b> <code>{current_chat_id}</code>"
                )
                return
            
            try:
                chat_id = int(parts[1])
            except ValueError:
                await utils.answer(
                    message, 
                    f"❌ <b>{self.strings('invalid_chat_id_format')}</b>\n\n"
                    f"{self.strings('id_must_be_number')}"
                )
                return
            
            if chat_id in self._chat_whitelist:
                await utils.answer(
                    message, 
                    f"⚠️ {self.strings('chat')} <code>{chat_id}</code> {self.strings('already_in_whitelist')}"
                )
                return
            
            self._chat_whitelist.add(chat_id)
            self._save_whitelist()
            
            await utils.answer(
                message,
                f"✅ <b>{self.strings('chat_added_to_whitelist')}</b>\n\n"
                f"<b>ID:</b> <code>{chat_id}</code>\n"
                f"<b>{self.strings('total_in_whitelist')}:</b> {len(self._chat_whitelist)}"
            )
            return
        
        if action == "remove":
            if len(parts) < 2:
                await utils.answer(
                    message,
                    f"❌ <b>{self.strings('specify_chat_id')}</b>\n\n"
                    f"<b>{self.strings('usage')}:</b>\n"
                    "<code>.whitelist remove [chat_id]</code>\n\n"
                    f"<b>{self.strings('example')}:</b>\n"
                    "<code>.whitelist remove -1001234567890</code>"
                )
                return
            
            try:
                chat_id = int(parts[1])
            except ValueError:
                await utils.answer(
                    message, 
                    f"❌ <b>{self.strings('invalid_chat_id_format')}</b>\n\n"
                    f"{self.strings('id_must_be_number')}"
                )
                return
            
            if chat_id not in self._chat_whitelist:
                await utils.answer(
                    message, 
                    f"⚠️ {self.strings('chat')} <code>{chat_id}</code> {self.strings('not_found_in_whitelist')}"
                )
                return
            
            self._chat_whitelist.remove(chat_id)
            self._save_whitelist()
            
            await utils.answer(
                message,
                f"✅ <b>{self.strings('chat_removed_from_whitelist')}</b>\n\n"
                f"<b>ID:</b> <code>{chat_id}</code>\n"
                f"<b>{self.strings('remaining_in_whitelist')}:</b> {len(self._chat_whitelist)}"
            )
            return
        
        await utils.answer(
            message,
            f"❌ <b>{self.strings('unknown_argument')}:</b> <code>{action}</code>\n\n"
            f"<b>{self.strings('available_arguments')}:</b>\n"
            f"• <code>add</code> - {self.strings('add_chat')}\n"
            f"• <code>remove</code> - {self.strings('remove_chat')}\n"
            f"• <code>list</code> - {self.strings('show_list')}"
        )

    @loader.command(
        ru_doc="Обновить список прокси",
        en_doc="Update proxy list",
    )
    async def updateproxycmd(self, message: Message):
        """Обновить список прокси"""
        await utils.answer(message, self.strings("proxy_update_started"))
        
        try:
            count = await self._update_proxy_list()
            await utils.answer(message, self.strings("proxy_update_success").format(count))
        except Exception as e:
            await utils.answer(message, self.strings("proxy_update_error").format(str(e)))

    @loader.command(
        ru_doc="Тест API Rule34",
        en_doc="Test Rule34 API",
    )
    async def testr34cmd(self, message: Message):
        """[тег] - Тест API Rule34 (показывает сырой ответ)"""
        args = utils.get_args_raw(message)
        if not args:
            args = "anime"
        
        await utils.answer(message, f"Тестируем API с тегом: {args}")
        
        url = "https://api.rule34.xxx/index.php"
        params = {
            'page': 'dapi',
            's': 'post',
            'q': 'index',
            'limit': 5,
            'tags': args,
            'api_key': 'd82f6db279ce94313e629e791533d456a4309dfeb528ddab6eee4b7472156f0def07ebfd3e64b9dddbf0d3b78f227ba8a5f386533ef1ccb1377d8a97481811dc',
            'user_id': '5255009'
        }
        
        response = await self._make_request(url, params, use_proxy=True)
        
        if not response:
            await utils.answer(message, "❌ Не удалось получить ответ от API")
            return
        
        try:
            # Парсим XML
            root = ET.fromstring(response.text)
            posts = root.findall("post")
            
            result = f"✅ Ответ получен!\n\n"
            result += f"Формат: XML\n"
            result += f"Количество постов: {len(posts)}\n\n"
            
            if posts:
                result += f"Первый пост:\n"
                first_post = posts[0]
                result += f"ID: {first_post.get('id')}\n"
                result += f"file_url: {first_post.get('file_url', 'нет')[:50]}...\n"
                result += f"sample_url: {first_post.get('sample_url', 'нет')[:50]}...\n"
                result += f"rating: {first_post.get('rating', 'нет')}\n"
                tags = first_post.get('tags', '')
                result += f"tags (первые 100 символов): {tags[:100]}...\n"
            
            await utils.answer(message, result)
        except Exception as e:
            await utils.answer(message, f"❌ Ошибка парсинга: {e}\n\nСырой ответ (первые 500 символов):\n{response.text[:500]}")

    @loader.command(
        ru_doc="Поиск на Rule34",
        en_doc="Search on Rule34",
    )
    async def r34cmd(self, message: Message):
        """[теги] [кол-во] - Поиск на Rule34"""
        # Проверяем вайтлист для команд
        if not self._is_chat_allowed(message.peer_id):
            chat_id_num = self._get_chat_id(message.peer_id)
            await utils.answer(message, self.strings("chat_not_whitelisted").format(chat_id_num))
            return
        
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("usage_r34"))
            return
        
        parts = args.rsplit(maxsplit=1)
        count = self.config["send_count"]
        
        if len(parts) == 2 and parts[1].isdigit():
            tags = parts[0]
            count = min(int(parts[1]), 10)
        else:
            tags = args
        
        await utils.answer(message, self.strings("searching"))
        
        posts = await self._search_rule34(tags, self.config["posts_count"])
        
        # API уже обработал фильтрацию, не нужно дополнительно фильтровать
        await self._send_posts(message, posts, tags, count)


