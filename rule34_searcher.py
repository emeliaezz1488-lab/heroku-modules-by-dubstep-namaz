# meta developer: @dubstep_namaz1337
# meta banner: https://raw.githubusercontent.com/emeliaezz1488-lab/heroku-modules-by-dubstep-namaz/main/Banners/logo.png
"""
Модуль для поиска изображений и видео на Rule34, Danbooru и Pixiv (тут ище мангу можно искать бееее).

Команды:
- .r34 [теги] [кол-во] - поиск на Rule34
- .danbooru [теги] [кол-во] - поиск на Danbooru
- .pixiv [теги] [кол-во] - поиск на Pixiv (нужен refresh_token)
- .pixivnsfw [теги] [кол-во] - Pixiv R-18
- .pixivmanga [теги] - R-18 манга Pixiv

Триггер-слова (автоматический поиск, источник — default_source в конфиге):
- "фута" - поиск по тегу futa (картинки)
- "фембой" - поиск по тегу femboy (картинки)
- "фута" + "фембой" (или "фута+фембой") - видео по тегам futa femboy video
- "порно" - случайное видео
- "r34 [теги] [кол-во]" - поиск Rule34 (без точки)
- "pixiv [теги] [кол-во]" - поиск Pixiv (без точки)
- "pixivnsfw [теги] [кол-во]" - Pixiv R-18 (без точки)
- "pixivmanga [теги]" - R-18 манга Pixiv (без точки)
"""

import random
import re
import io
import os
import tempfile
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

PIXIV_REFERER = "https://www.pixiv.net/"

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
    """Поиск изображений и видео на Rule34, Danbooru и Pixiv"""
    
    strings = {
        "name": "Rule34Searcher",
        "not_found": "Ничего не найдено!",
        "searching": "Ищем...",
        "error": "Ошибка: {}",
        "usage_r34": "Использование: .r34 [теги] [кол-во]\nПример: .r34 anime 2",
        "usage_danbooru": "Использование: .danbooru [теги] [кол-во]\nПример: .danbooru anime 2",
        "usage_pixiv": "Использование: .pixiv [теги] [кол-во]\nПример: .pixiv 1girl 2",
        "usage_pixiv_nsfw": "Использование: .pixivnsfw [теги] [кол-во]\nПример: .pixivnsfw femboy 2",
        "usage_pixiv_manga": "Использование: .pixivmanga [теги]\nПример: .pixivmanga futanari\n(только R-18 манга)",
        "pixiv_no_token": "Pixiv: укажи refresh_token в настройках модуля (pixiv_refresh_token)",
        "pixiv_error": "Ошибка Pixiv: {}",
        "pixiv_manga_need_pillow": "Для манги нужен Pillow на сервере: pip install Pillow",
        "pixiv_manga_album": "📖 <b>{}</b> ({} стр.)",
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
        "usage_danbooru": "Usage: .danbooru [tags] [count]\nExample: .danbooru anime 2",
        "usage_pixiv": "Usage: .pixiv [tags] [count]\nExample: .pixiv 1girl 2",
        "usage_pixiv_nsfw": "Usage: .pixivnsfw [tags] [count]\nExample: .pixivnsfw femboy 2",
        "usage_pixiv_manga": "Usage: .pixivmanga [tags]\nExample: .pixivmanga futanari\n(R-18 manga only)",
        "pixiv_no_token": "Pixiv: set refresh_token in module config (pixiv_refresh_token)",
        "pixiv_error": "Pixiv error: {}",
        "pixiv_manga_need_pillow": "Pixiv manga requires Pillow: pip install Pillow",
        "pixiv_manga_album": "📖 <b>{}</b> ({} pages)",
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
            loader.ConfigValue(
                "default_source",
                "rule34",
                "Источник по умолчанию (rule34/danbooru/pixiv)",
                validator=loader.validators.Choice(["rule34", "danbooru", "pixiv"]),
            ),
            loader.ConfigValue(
                "pixiv_refresh_token",
                "",
                "Pixiv refresh_token (из gppt / get_pixiv_token.py)",
                validator=loader.validators.String(),
            ),
            loader.ConfigValue(
                "pixiv_manga_max_pages",
                40,
                "Макс. страниц манги",
                validator=loader.validators.Integer(minimum=2, maximum=100),
            ),
        )
        self._cache = {}
        self._pixiv_api = None
        self._pixiv_token_cached = ""
        self._pixiv_auth_at = 0.0
        self._pixiv_refresh_task = None
        self.PIXIV_ACCESS_TTL = 3000  # access_token ~1ч, обновляем заранее
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
        if self._get_pixiv_refresh_token():
            asyncio.create_task(self._warm_pixiv_api())
            self._pixiv_refresh_task = asyncio.create_task(self._pixiv_token_refresh_loop())

    async def on_unload(self):
        if self._pixiv_refresh_task and not self._pixiv_refresh_task.done():
            self._pixiv_refresh_task.cancel()

    async def _pixiv_token_refresh_loop(self):
        """Фоновое обновление access_token, чтобы Pixiv не отваливался через ~1 час."""
        while True:
            try:
                await asyncio.sleep(self.PIXIV_ACCESS_TTL)
                await utils.run_sync(lambda: self._ensure_pixiv_api_sync(force_refresh=True))
                print("[Rule34Searcher] Pixiv access_token refreshed")
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Rule34Searcher] Pixiv background refresh failed: {e}")

    async def _warm_pixiv_api(self):
        """Заранее авторизоваться в Pixiv, чтобы первая команда не ждала auth."""
        try:
            await utils.run_sync(self._ensure_pixiv_api_sync)
        except Exception as e:
            print(f"[Rule34Searcher] Pixiv warm-up failed: {e}")

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
            
            # Один быстрый запрос без повторов
            try:
                response = requests.get(url, params=params, headers=headers, timeout=5)
                response.raise_for_status()
                return response
            except Exception as e:
                print(f"[Rule34Searcher] Request failed: {e}")
                raise e
        
        try:
            return await utils.run_sync(_request)
        except Exception as e:
            print(f"[Rule34Searcher] _make_request exception: {e}")
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

    async def _search_danbooru(self, tags: str, limit: int = 100) -> List[Dict]:
        """Поиск на Danbooru с полной поддержкой прокси и API"""
        # Для Danbooru используем только базовые теги без дополнительных фильтров
        # Парсим теги из запроса
        query_parts = tags.split() if tags else []
        include_tags = []
        
        for part in query_parts:
            if not part.startswith('-'):
                include_tags.append(part)
        
        # Строим поисковый запрос (только включающие теги)
        search_tags = ' '.join(include_tags).strip()
        
        # Параметры запроса (БЕЗ login и api_key в параметрах)
        url = "https://danbooru.donmai.us/posts.json"
        params = {
            'limit': min(limit, 20),
            'tags': search_tags if search_tags else None,
        }
        
        # Убираем пустые параметры
        params = {k: v for k, v in params.items() if v is not None}
        
        print(f"[Rule34Searcher] Danbooru request URL: {url}")
        print(f"[Rule34Searcher] Danbooru params: {params}")
        
        # Используем специальный метод с HTTP Basic Auth
        response = await self._make_danbooru_request(url, params)
        if not response:
            print(f"[Rule34Searcher] Danbooru: No response from API")
            return []
        
        print(f"[Rule34Searcher] Danbooru response status: {response.status_code}")
        print(f"[Rule34Searcher] Danbooru response text (first 500 chars): {response.text[:500]}")
        
        try:
            # Парсим JSON ответ
            data = response.json()
            print(f"[Rule34Searcher] Danbooru: Received {len(data)} posts")
            posts = []
            
            # Ключ для отслеживания повторов
            tag_key = "danbooru_" + (search_tags if search_tags else "random")
            recent_ids = self._recent_posts[tag_key]
            
            for post in data:
                post_id = str(post.get("id", ""))
                
                # Пропускаем если уже показывали недавно
                if post_id in recent_ids:
                    continue
                
                # Получаем URL изображения (приоритет: file_url > large_file_url > preview_file_url)
                image_url = post.get('file_url') or post.get('large_file_url') or post.get('preview_file_url')
                
                if not image_url:
                    print(f"[Rule34Searcher] Danbooru: Post {post_id} has no image URL")
                    continue
                
                # Парсим теги
                tag_string = post.get('tag_string', '')
                tags_list = tag_string.split() if tag_string else []
                
                posts.append({
                    "file_url": image_url,
                    "tags": tags_list,
                    "rating": post.get("rating", ""),
                    "id": post_id,
                })
            
            print(f"[Rule34Searcher] Danbooru: Returning {len(posts)} posts after filtering")
            return posts
        except Exception as e:
            # Логируем ошибку для отладки
            print(f"[Rule34Searcher] Error parsing Danbooru response: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _get_pixiv_refresh_token(self) -> str:
        config_token = (self.config.get("pixiv_refresh_token") or "").strip()
        db_token = ""
        if getattr(self, "_db", None):
            db_token = (self._db.get(__name__, "pixiv_refresh_token_active", "") or "").strip()
        return db_token or config_token

    def _save_pixiv_refresh_token(self, refresh_token: str):
        token = (refresh_token or "").strip()
        if not token or not getattr(self, "_db", None):
            return
        self._db.set(__name__, "pixiv_refresh_token_active", token)

    def _pixiv_fetch_limit(self, send_count: int) -> int:
        """Pixiv отдаёт ~30 работ за запрос — не качаем лишние страницы."""
        return min(max(int(send_count) * 10, 12), 30)

    def _reset_pixiv_api(self):
        self._pixiv_api = None
        self._pixiv_token_cached = ""
        self._pixiv_auth_at = 0.0

    def _ensure_pixiv_api_sync(self, force_refresh: bool = False):
        from pixivpy3 import AppPixivAPI

        refresh_token = self._get_pixiv_refresh_token()
        if not refresh_token:
            raise ValueError("pixiv_refresh_token_missing")

        now = time.time()
        auth_expired = (now - self._pixiv_auth_at) >= self.PIXIV_ACCESS_TTL
        need_auth = (
            force_refresh
            or self._pixiv_api is None
            or self._pixiv_token_cached != refresh_token
            or auth_expired
        )

        if not need_auth:
            return self._pixiv_api

        if self._pixiv_api is None:
            self._pixiv_api = AppPixivAPI(timeout=12)

        self._pixiv_api.auth(refresh_token=refresh_token)
        new_refresh = getattr(self._pixiv_api, "refresh_token", None)
        if new_refresh:
            self._save_pixiv_refresh_token(new_refresh)

        self._pixiv_token_cached = self._get_pixiv_refresh_token()
        self._pixiv_auth_at = now
        return self._pixiv_api

    @staticmethod
    def _pixiv_validate_result(result) -> None:
        if result is None:
            raise ValueError("pixiv_empty_response")

        if isinstance(result, dict):
            if result.get("error") or result.get("has_error"):
                raise ValueError(f"pixiv_api_error: {result.get('error', result)}")

        for attr in ("error", "has_error", "errors"):
            if getattr(result, attr, None):
                raise ValueError(f"pixiv_api_error: {getattr(result, attr)}")

    @staticmethod
    def _pixiv_image_urls_to_url(image_urls) -> Optional[str]:
        if not image_urls:
            return None
        if isinstance(image_urls, dict):
            return (
                image_urls.get("medium")
                or image_urls.get("large")
                or image_urls.get("square_medium")
                or image_urls.get("original")
            )
        return (
            getattr(image_urls, "medium", None)
            or getattr(image_urls, "large", None)
            or getattr(image_urls, "square_medium", None)
            or getattr(image_urls, "original", None)
        )

    @staticmethod
    def _pixiv_illust_url(illust) -> Optional[str]:
        meta_pages = getattr(illust, "meta_pages", None) or []
        if meta_pages:
            urls = meta_pages[0].get("image_urls") if isinstance(meta_pages[0], dict) else getattr(
                meta_pages[0], "image_urls", None
            )
            return Rule34Searcher._pixiv_image_urls_to_url(urls)

        return Rule34Searcher._pixiv_image_urls_to_url(
            getattr(illust, "image_urls", None),
        )

    @classmethod
    def _pixiv_all_page_urls(cls, illust) -> List[str]:
        urls: List[str] = []
        meta_pages = getattr(illust, "meta_pages", None) or []
        for page in meta_pages:
            image_urls = page.get("image_urls") if isinstance(page, dict) else getattr(page, "image_urls", None)
            url = cls._pixiv_image_urls_to_url(image_urls)
            if url and not url.lower().endswith(".zip"):
                urls.append(url)

        if not urls:
            single = cls._pixiv_illust_url(illust)
            if single:
                urls.append(single)
        return urls

    def _search_pixiv_sync(
        self,
        tags: str,
        limit: int,
        video_only: bool = False,
        max_pages: int = 2,
        r18_only: bool = False,
        manga_only: bool = False,
    ) -> List[Dict]:
        api = self._ensure_pixiv_api_sync()
        word = tags.strip() if tags else ("うごイラ" if video_only else "1girl")

        prefix = "pixiv"
        if manga_only and r18_only:
            prefix = "pixiv_manga_r18"
        elif manga_only:
            prefix = "pixiv_manga"
        elif r18_only:
            prefix = "pixiv_r18"
        tag_key = f"{prefix}_{word}" if word else f"{prefix}_random"
        recent_ids = self._recent_posts[tag_key]
        posts: List[Dict] = []
        next_qs = {
            "word": word,
            "search_target": "partial_match_for_tags",
            "sort": "date_desc",
        }
        pages = 0
        api_max_pages = 4 if manga_only else max_pages

        while next_qs and len(posts) < limit and pages < api_max_pages:
            pages += 1
            result = api.search_illust(**next_qs)
            self._pixiv_validate_result(result)
            illusts = getattr(result, "illusts", None) or []
            if not illusts and isinstance(result, dict):
                illusts = result.get("illusts", [])

            for illust in illusts:
                if len(posts) >= limit:
                    break

                post_id = str(getattr(illust, "id", "") or "")
                if post_id and post_id in recent_ids:
                    continue

                illust_type = getattr(illust, "type", "") or ""
                x_restrict = int(getattr(illust, "x_restrict", 0) or 0)

                if r18_only and x_restrict < 1:
                    continue

                if manga_only:
                    if illust_type != "manga":
                        continue
                    page_count = int(getattr(illust, "page_count", 1) or 1)
                    if page_count < 2:
                        continue

                if video_only and illust_type != "ugoira":
                    continue

                file_url = self._pixiv_illust_url(illust)
                if not file_url:
                    continue

                if file_url.lower().endswith(".zip"):
                    continue

                raw_tags = getattr(illust, "tags", None) or []
                if isinstance(raw_tags, str):
                    tags_list = raw_tags.split()
                else:
                    tags_list = list(raw_tags)

                posts.append({
                    "file_url": file_url,
                    "tags": tags_list,
                    "rating": str(x_restrict),
                    "id": post_id,
                    "media_type": illust_type,
                    "title": getattr(illust, "title", "") or "",
                    "page_count": int(getattr(illust, "page_count", 1) or 1),
                })

            if len(posts) >= limit:
                break

            next_qs = api.parse_qs(getattr(result, "next_url", None))
            if not illusts:
                break

        return posts

    async def _search_pixiv(
        self,
        tags: str,
        limit: Optional[int] = None,
        video_only: bool = False,
        send_count: int = 1,
        r18_only: bool = False,
        manga_only: bool = False,
    ) -> List[Dict]:
        if not self._get_pixiv_refresh_token():
            print("[Rule34Searcher] Pixiv: refresh_token not configured")
            return []

        fetch_limit = limit if limit is not None else self._pixiv_fetch_limit(send_count)

        def _run_search():
            last_error = None
            for attempt in range(3):
                try:
                    return self._search_pixiv_sync(
                        tags,
                        min(fetch_limit, 30),
                        video_only,
                        r18_only=r18_only,
                        manga_only=manga_only,
                    )
                except Exception as e:
                    last_error = e
                    print(f"[Rule34Searcher] Pixiv search attempt {attempt + 1} failed: {e}")
                    self._reset_pixiv_api()
                    if attempt < 2:
                        try:
                            self._ensure_pixiv_api_sync(force_refresh=True)
                        except Exception as auth_err:
                            print(f"[Rule34Searcher] Pixiv re-auth failed: {auth_err}")
            if last_error:
                raise last_error
            return []

        try:
            return await utils.run_sync(_run_search)
        except Exception as e:
            print(f"[Rule34Searcher] Pixiv search error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _download_pixiv_image_sync(self, url: str) -> bytes:
        headers = get_request_headers(self.config["proxy_rotate_ua"])
        headers["Referer"] = PIXIV_REFERER
        response = requests.get(url, headers=headers, timeout=45)
        response.raise_for_status()
        data = response.content
        if len(data) < 128:
            raise ValueError("pixiv_image_too_small")
        sniff = data[:256].lower()
        if sniff.startswith(b"<!doctype") or sniff.startswith(b"<html"):
            raise ValueError("pixiv_download_blocked")
        return data

    def _create_pixiv_manga_album_sync(
        self,
        tags: str,
        max_pages: int,
    ) -> Optional[Dict]:
        candidates = self._search_pixiv_sync(
            tags,
            limit=30,
            max_pages=4,
            manga_only=True,
            r18_only=True,
        )
        if not candidates:
            return None

        random.shuffle(candidates)
        api = self._ensure_pixiv_api_sync()
        tag_key = f"pixiv_manga_r18_{tags.strip()}" if tags.strip() else "pixiv_manga_r18_random"
        recent_ids = self._recent_posts[tag_key]

        for candidate in candidates:
            post_id = candidate.get("id", "")
            if post_id and post_id in recent_ids:
                continue

            detail = api.illust_detail(post_id)
            self._pixiv_validate_result(detail)
            illust = getattr(detail, "illust", None)
            if not illust:
                continue

            if int(getattr(illust, "x_restrict", 0) or 0) < 1:
                continue

            page_urls = self._pixiv_all_page_urls(illust)
            if len(page_urls) < 2:
                continue

            page_urls = page_urls[:max_pages]
            title = (getattr(illust, "title", None) or tags or "Pixiv Manga").strip()

            pages_data: List[bytes] = []
            try:
                for page_url in page_urls:
                    raw = self._download_pixiv_image_sync(page_url)
                    pages_data.append(raw)
            except Exception as e:
                print(f"[Rule34Searcher] Manga download failed for {post_id}: {e}")
                continue

            if len(pages_data) < 2:
                continue

            if post_id:
                recent_ids.append(post_id)

            return {
                "title": title,
                "pages": pages_data,
                "id": post_id,
            }

        return None

    async def _send_pixiv_manga_album(self, message: Message, tags: str):
        max_pages = self.config["pixiv_manga_max_pages"]

        try:
            result = await utils.run_sync(
                self._create_pixiv_manga_album_sync,
                tags,
                max_pages,
            )
        except Exception as e:
            print(f"[Rule34Searcher] Pixiv manga error: {e}")
            import traceback
            traceback.print_exc()
            err = str(e)
            if "pillow" in err.lower() or "webp" in err.lower():
                await utils.answer(message, self.strings("pixiv_manga_need_pillow"))
            else:
                await utils.answer(message, self.strings("pixiv_error").format(err))
            return

        if not result:
            await utils.answer(message, self.strings("not_found"))
            return

        caption = self.strings("pixiv_manga_album").format(
            result["title"],
            len(result["pages"]),
        )
        files = []
        for index, page_data in enumerate(result["pages"], start=1):
            bio = io.BytesIO(page_data)
            bio.name = f"page_{index}.jpg"
            files.append(bio)
        sent = await message.client.send_file(
            message.peer_id,
            files,
            caption=caption,
            parse_mode="html",
            reply_to=getattr(message, "reply_to_msg_id", None),
        )

        try:
            await message.delete()
        except Exception:
            pass

    async def _search_posts(
        self,
        source: str,
        tags: str,
        limit: int,
        video_only: bool = False,
        send_count: int = 1,
    ) -> List[Dict]:
        if source == "danbooru":
            posts = await self._search_danbooru(tags, limit)
        elif source == "pixiv":
            posts = await self._search_pixiv(tags, video_only=video_only, send_count=send_count)
        else:
            posts = await self._search_rule34(tags, limit)

        if video_only and posts and source != "pixiv":
            video_posts = []
            for post in posts:
                file_url = post.get("file_url", "")
                file_ext = file_url.lower().split("?")[0].split(".")[-1]
                if file_ext in ["mp4", "webm", "mov", "avi", "mkv"]:
                    video_posts.append(post)
            if not video_posts:
                for post in posts:
                    file_url = post.get("file_url", "")
                    if any(ext in file_url.lower() for ext in [".mp4", ".webm", ".mov", ".avi", ".mkv"]):
                        video_posts.append(post)
            posts = video_posts if video_posts else posts

        return posts

    async def _make_danbooru_request(self, url: str, params: dict = None) -> Optional[requests.Response]:
        """Выполнить HTTP запрос к Danbooru с HTTP Basic Auth"""
        def _request():
            headers = {
                "User-Agent": "Rule34Searcher/1.0 (by DubstepNamaz on Danbooru)",
                "Accept": "application/json",
            }
            
            try:
                # Используем HTTP Basic Authentication
                from requests.auth import HTTPBasicAuth
                auth = HTTPBasicAuth('DubstepNamaz', '5qAAyDRZ22DFp8thwVXqGrfk')
                
                response = requests.get(url, params=params, headers=headers, auth=auth, timeout=10)
                response.raise_for_status()
                return response
            except Exception as e:
                print(f"[Rule34Searcher] Danbooru request failed: {e}")
                raise e
        
        try:
            return await utils.run_sync(_request)
        except Exception as e:
            print(f"[Rule34Searcher] _make_danbooru_request exception: {e}")
            return None

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

    def _video_has_audio(self, url: str) -> bool:
        # Быстрая проверка по сети: есть ли у видео аудиодорожка.
        # Делается через ffprobe прямо по URL (без полной загрузки файла).
        # При любой неудаче возвращаем True, чтобы не тормозить отправку:
        # такое видео уйдёт по URL как раньше.
        import shutil
        import subprocess
        if not shutil.which("ffprobe"):
            return True
        try:
            ua = get_random_user_agent()
            probe = subprocess.run(
                [
                    "ffprobe", "-user_agent", ua,
                    "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=index",
                    "-of", "csv=p=0",
                    url,
                ],
                capture_output=True, timeout=30,
            )
            if probe.returncode != 0:
                return True
            return bool(probe.stdout.strip())
        except Exception as e:
            print(f"[Rule34Searcher] ffprobe url failed: {e}")
            return True

    def _make_streamable_mp4(self, media_bytes: bytes, ext: str) -> Optional[bytes]:
        # Возвращает mp4-байты, которые Telegram покажет как ВИДЕО, а не гифку.
        # Telegram считает анимацией .gif и видео без аудио, поэтому добавляем
        # тихую аудиодорожку. Чтобы было быстро, видеопоток по возможности
        # копируем без перекодирования (-c:v copy); полный libx264 — только если
        # копирование невозможно (например, .gif или .webm). Нужен ffmpeg.
        import shutil
        import subprocess
        ext = (ext or "").lower()
        if not shutil.which("ffmpeg"):
            print("[Rule34Searcher] ffmpeg не найден — отправляю медиа как есть")
            return media_bytes if ext == "mp4" else None
        tmp_in = None
        tmp_out = None
        try:
            with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as f_in:
                f_in.write(media_bytes)
                tmp_in = f_in.name
            has_audio = False
            if shutil.which("ffprobe"):
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error",
                        "-select_streams", "a",
                        "-show_entries", "stream=index",
                        "-of", "csv=p=0",
                        tmp_in,
                    ],
                    capture_output=True, timeout=60,
                )
                has_audio = bool(probe.stdout.strip())
            if ext == "mp4" and has_audio:
                return media_bytes
            tmp_out = tmp_in + ".out.mp4"

            def build(copy_video):
                cmd = ["ffmpeg", "-y", "-i", tmp_in]
                if not has_audio:
                    cmd += [
                        "-f", "lavfi",
                        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                        "-shortest",
                    ]
                cmd += ["-movflags", "+faststart"]
                if copy_video:
                    cmd += ["-c:v", "copy"]
                else:
                    cmd += [
                        "-pix_fmt", "yuv420p",
                        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        "-c:v", "libx264",
                        "-preset", "veryfast",
                    ]
                cmd += ["-c:a", "aac", tmp_out]
                return cmd

            result = None
            if ext in ("mp4", "mov", "mkv"):
                result = subprocess.run(build(True), capture_output=True, timeout=300)
            if result is None or result.returncode != 0:
                result = subprocess.run(build(False), capture_output=True, timeout=300)
            if result.returncode != 0:
                print(f"[Rule34Searcher] ffmpeg error: {result.stderr.decode(errors='ignore')[:300]}")
                return media_bytes if ext == "mp4" else None
            with open(tmp_out, "rb") as f:
                return f.read()
        except Exception as e:
            print(f"[Rule34Searcher] _make_streamable_mp4 failed: {e}")
            return media_bytes if ext == "mp4" else None
        finally:
            for p in (tmp_in, tmp_out):
                if p and os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

    async def _send_posts(self, message: Message, posts: List[Dict], requested_tags: str, count: int):
        """Отправка постов (изображения и видео)"""
        if not posts:
            print(f"[Rule34Searcher] _send_posts: No posts provided")
            await utils.answer(message, self.strings("not_found"))
            return
        
        print(f"[Rule34Searcher] _send_posts: Received {len(posts)} posts, need to send {count}")
        
        # Перемешиваем посты для случайности
        random.shuffle(posts)
        
        # Ключ для отслеживания повторов
        tag_key = requested_tags.strip() if requested_tags.strip() else "random"
        recent_ids = self._recent_posts[tag_key]
        
        sent_count = 0
        sent_messages = []
        attempts = 0
        max_attempts = min(len(posts), count * 20)  # Увеличили до 20x
        
        for post in posts:
            if sent_count >= count:
                break
                
            if attempts >= max_attempts:
                print(f"[Rule34Searcher] Reached max attempts ({max_attempts})")
                break
                
            attempts += 1
            
            file_url = post.get("file_url")
            post_id = post.get("id", "")
            
            if not file_url:
                print(f"[Rule34Searcher] Post {post_id} has no file_url")
                continue
            
            # Проверяем не показывали ли недавно
            if post_id in recent_ids:
                print(f"[Rule34Searcher] Post {post_id} was recently shown, skipping")
                continue
            
            caption = self._format_caption(post, requested_tags)
            
            try:
                # Определяем тип файла по расширению
                file_ext = file_url.lower().split('?')[0].split('.')[-1]
                is_video = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi', 'mkv']
                
                print(f"[Rule34Searcher] Attempt {attempts}: Sending {file_ext} file (video={is_video}): {file_url[:80]}...")
                
                # Видео отправляем так, чтобы Telegram не показывал его как гифку.
                # Telegram считает анимацией .gif и любое видео без аудиодорожки.
                # Поэтому: .gif всегда перекодируем; для остальных видео сначала
                # быстро проверяем по сети наличие звука и трогаем файл только если
                # звука нет (добавляем тихую дорожку без перекодирования). Видео
                # со звуком шлём по URL.
                is_video_ext = file_ext in ['mp4', 'webm', 'gif', 'mov', 'avi', 'mkv']
                sent_msg = None
                if is_video_ext:
                    if file_ext == "gif":
                        needs_fix = True
                    else:
                        has_audio = await utils.run_sync(self._video_has_audio, file_url)
                        needs_fix = not has_audio
                    if needs_fix:
                        media_bytes = await self._download_file(file_url)
                        if media_bytes:
                            mp4_bytes = await utils.run_sync(
                                self._make_streamable_mp4, media_bytes, file_ext
                            )
                            if mp4_bytes:
                                bio = io.BytesIO(mp4_bytes)
                                bio.name = f"{post_id or 'video'}.mp4"
                                sent_msg = await message.client.send_file(
                                    message.peer_id,
                                    bio,
                                    caption=caption,
                                    parse_mode="html",
                                    reply_to=getattr(message, "reply_to_msg_id", None),
                                    supports_streaming=True,
                                    force_document=False,
                                )
                if sent_msg is None:
                    # Картинки, видео со звуком, либо фолбэк при неудаче конвертации.
                    sent_msg = await message.client.send_file(
                        message.peer_id,
                        file_url,
                        caption=caption,
                        parse_mode="html",
                        reply_to=getattr(message, "reply_to_msg_id", None),
                        supports_streaming=is_video_ext,
                    )

                sent_messages.append(sent_msg)
                sent_count += 1
                
                # Добавляем ID в список недавно показанных
                if post_id:
                    recent_ids.append(post_id)
                
                print(f"[Rule34Searcher] Successfully sent post {post_id} ({sent_count}/{count})")
                    
            except Exception as e:
                # Логируем ошибку для отладки
                error_msg = str(e)
                print(f"[Rule34Searcher] Error sending file {file_url[:80]}...: {error_msg}")
                import traceback
                traceback.print_exc()
                
                # Пропускаем этот пост и пробуем следующий
                continue
        
        print(f"[Rule34Searcher] Finished: sent {sent_count}/{count}, attempts {attempts}/{max_attempts}")
        
        if sent_count == 0:
            await utils.answer(
                message,
                f"❌ Не удалось отправить медиа.\nНайдено постов: {len(posts)}\n"
                f"Попыток отправки: {attempts}\n\n"
                "Возможные причины:\n• Файлы слишком большие\n"
                "• Telegram не может загрузить файлы\n• Все файлы битые\n"
                "• Все посты уже показывались",
            )
        else:
            await message.delete()

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

    def _parse_tags_and_count(self, args: str) -> Tuple[str, int]:
        """Разбор тегов и количества (последнее отдельное число — кол-во постов)."""
        args = args.strip()
        if not args:
            return "", self.config["send_count"]

        parts = args.rsplit(maxsplit=1)
        count = self.config["send_count"]

        if len(parts) == 2 and parts[1].isdigit():
            tags = parts[0]
            count = min(int(parts[1]), 10)
        else:
            tags = args

        return tags, count

    def _is_futa_femboy_combo(self, text_lower: str) -> bool:
        """Триггер «фута+фембой»: оба слова или явная запись с плюсом."""
        if "фута+фембой" in text_lower or "футафембой" in text_lower:
            return True
        return "фута" in text_lower and "фембой" in text_lower

    async def _search_and_send_by_trigger(
        self,
        message: Message,
        search_tag: str,
        video_only: bool = False,
        keep_search_tags: bool = False,
    ):
        """Поиск и отправка по триггеру"""
        # Проверка на спам
        user_id = message.sender_id
        chat_id = message.peer_id
        
        if await self._check_spam(user_id, chat_id):
            return
        
        # Сохраняем оригинальный тег для подписи
        display_tag = search_tag
        
        # Если нужны только видео, добавляем специальные теги для поиска
        if video_only and not keep_search_tags:
            # Ищем с тегами video или animated для гарантии видео
            video_tags = ["video", "animated", "webm", "mp4"]
            search_tag = random.choice(video_tags)
            # Для "порно" не показываем технический тег в подписи
            display_tag = ""
        
        source = self.config["default_source"]
        if source == "pixiv" and not self._get_pixiv_refresh_token():
            return

        posts = await self._search_posts(
            source,
            search_tag,
            self.config["posts_count"],
            video_only=video_only,
            send_count=1,
        )

        if not posts:
            return
        
        # Отправка одного поста с правильным тегом для подписи
        await self._send_posts(message, posts, display_tag, 1)

    async def _search_and_send_r34_chat(self, message: Message, args: str):
        """Поиск по триггеру «r34 [теги] [кол-во]» в чате."""
        user_id = message.sender_id
        chat_id = message.peer_id

        if await self._check_spam(user_id, chat_id):
            return

        tags, count = self._parse_tags_and_count(args)
        if not tags:
            return

        posts = await self._search_rule34(tags, self.config["posts_count"])
        await self._send_posts(message, posts, tags, count)

    async def _search_and_send_pixiv_chat(self, message: Message, args: str):
        """Поиск по триггеру «pixiv [теги] [кол-во]» в чате."""
        user_id = message.sender_id
        chat_id = message.peer_id

        if await self._check_spam(user_id, chat_id):
            return

        if not self._get_pixiv_refresh_token():
            return

        tags, count = self._parse_tags_and_count(args)
        if not tags:
            return

        posts = await self._search_pixiv(tags, send_count=count)
        await self._send_posts(message, posts, tags, count)

    async def _search_and_send_pixiv_nsfw_chat(self, message: Message, args: str):
        """Поиск по триггеру «pixivnsfw [теги] [кол-во]»."""
        user_id = message.sender_id
        chat_id = message.peer_id

        if await self._check_spam(user_id, chat_id):
            return

        if not self._get_pixiv_refresh_token():
            return

        tags, count = self._parse_tags_and_count(args)
        if not tags:
            return

        posts = await self._search_pixiv(tags, send_count=count, r18_only=True)
        await self._send_posts(message, posts, tags, count)

    async def _send_pixiv_manga_chat(self, message: Message, args: str):
        """Поиск по триггеру «pixivmanga [теги]»."""
        user_id = message.sender_id
        chat_id = message.peer_id

        if await self._check_spam(user_id, chat_id):
            return

        if not self._get_pixiv_refresh_token():
            return

        tags = args.strip()
        if not tags:
            return

        await self._send_pixiv_manga_album(message, tags)

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

            # «фута+фембой» — видео по futa + femboy (до одиночных триггеров)
            if self._is_futa_femboy_combo(text_lower):
                await self._search_and_send_by_trigger(
                    message,
                    "futa femboy video",
                    video_only=True,
                    keep_search_tags=True,
                )
                return

            # «r34 теги [кол-во]» — как команда .r34
            r34_match = re.match(r"^r34\s+(.+)$", message.text.strip(), re.IGNORECASE)
            if r34_match:
                await self._search_and_send_r34_chat(message, r34_match.group(1))
                return

            # «pixivnsfw теги [кол-во]» — R-18 Pixiv
            pixiv_nsfw_match = re.match(
                r"^pixivnsfw\s+(.+)$", message.text.strip(), re.IGNORECASE
            )
            if pixiv_nsfw_match:
                await self._search_and_send_pixiv_nsfw_chat(message, pixiv_nsfw_match.group(1))
                return

            # «pixivmanga теги» — манга
            pixiv_manga_match = re.match(
                r"^pixivmanga\s+(.+)$", message.text.strip(), re.IGNORECASE
            )
            if pixiv_manga_match:
                await self._send_pixiv_manga_chat(message, pixiv_manga_match.group(1))
                return

            # «pixiv теги [кол-во]» — как команда .pixiv
            pixiv_match = re.match(r"^pixiv\s+(.+)$", message.text.strip(), re.IGNORECASE)
            if pixiv_match:
                await self._search_and_send_pixiv_chat(message, pixiv_match.group(1))
                return
            
            # Потом одиночные триггеры
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
        
        tags, count = self._parse_tags_and_count(args)
        
        # Убрали сообщение "Ищем..." для ускорения
        posts = await self._search_rule34(tags, self.config["posts_count"])
        
        # API уже обработал фильтрацию, не нужно дополнительно фильтровать
        await self._send_posts(message, posts, tags, count)

    @loader.command(
        ru_doc="Поиск на Danbooru",
        en_doc="Search on Danbooru",
    )
    async def danboorucmd(self, message: Message):
        """[теги] [кол-во] - Поиск на Danbooru"""
        # Проверяем вайтлист для команд
        if not self._is_chat_allowed(message.peer_id):
            chat_id_num = self._get_chat_id(message.peer_id)
            await utils.answer(message, self.strings("chat_not_whitelisted").format(chat_id_num))
            return
        
        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("usage_danbooru"))
            return
        
        tags, count = self._parse_tags_and_count(args)
        
        posts = await self._search_danbooru(tags, self.config["posts_count"])
        await self._send_posts(message, posts, tags, count)

    @loader.command(
        ru_doc="Поиск на Pixiv",
        en_doc="Search on Pixiv",
    )
    async def pixivcmd(self, message: Message):
        """[теги] [кол-во] - Поиск на Pixiv"""
        if not self._is_chat_allowed(message.peer_id):
            chat_id_num = self._get_chat_id(message.peer_id)
            await utils.answer(message, self.strings("chat_not_whitelisted").format(chat_id_num))
            return

        if not self._get_pixiv_refresh_token():
            await utils.answer(message, self.strings("pixiv_no_token"))
            return

        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("usage_pixiv"))
            return

        tags, count = self._parse_tags_and_count(args)

        try:
            posts = await self._search_pixiv(tags, send_count=count)
        except Exception as e:
            await utils.answer(message, self.strings("pixiv_error").format(str(e)))
            return

        await self._send_posts(message, posts, tags, count)

    @loader.command(
        ru_doc="Pixiv R-18 поиск",
        en_doc="Pixiv R-18 search",
    )
    async def pixivnsfwcmd(self, message: Message):
        """[теги] [кол-во] - Pixiv R-18"""
        if not self._is_chat_allowed(message.peer_id):
            chat_id_num = self._get_chat_id(message.peer_id)
            await utils.answer(message, self.strings("chat_not_whitelisted").format(chat_id_num))
            return

        if not self._get_pixiv_refresh_token():
            await utils.answer(message, self.strings("pixiv_no_token"))
            return

        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("usage_pixiv_nsfw"))
            return

        tags, count = self._parse_tags_and_count(args)

        try:
            posts = await self._search_pixiv(tags, send_count=count, r18_only=True)
        except Exception as e:
            await utils.answer(message, self.strings("pixiv_error").format(str(e)))
            return

        await self._send_posts(message, posts, tags, count)

    @loader.command(
        ru_doc="Pixiv R-18 манга",
        en_doc="Pixiv R-18 manga",
    )
    async def pixivmangacmd(self, message: Message):
        """[теги] - R-18 манга Pixiv"""
        if not self._is_chat_allowed(message.peer_id):
            chat_id_num = self._get_chat_id(message.peer_id)
            await utils.answer(message, self.strings("chat_not_whitelisted").format(chat_id_num))
            return

        if not self._get_pixiv_refresh_token():
            await utils.answer(message, self.strings("pixiv_no_token"))
            return

        args = utils.get_args_raw(message)
        if not args:
            await utils.answer(message, self.strings("usage_pixiv_manga"))
            return

        await self._send_pixiv_manga_album(message, args.strip())

