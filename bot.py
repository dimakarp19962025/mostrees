# -*- coding: utf-8 -*-
"""
Created on Thu Jul 10 16:08:07 2025

@author: da.karpov1
"""
import os
import sqlite3
import json
import uuid
from datetime import datetime
from collections import defaultdict
import telebot
import yadisk
from telebot import types
from telebot.types import WebAppInfo

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_TOKEN = '7618578466:AAFgJSo-i2ivp99CzYmMrXrUgiz2XdePXhg'
YADISK_TOKEN = os.environ.get('YADISK_TOKEN')
YADISK_TOKEN = 'y0__xDi3dehqveAAhjK7Dggg9ee4hNhR445wsdmacsXIuSLAxczwKiDzw'
# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
y = yadisk.YaDisk(YADISK_TOKEN) 

# Настройка базы данных
DB_PATH = 'trees.db'
LOCAL_PHOTOS='Фото'
if not os.path.exists(LOCAL_PHOTOS):
    os.mkdir(LOCAL_PHOTOS)


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE NOT NULL,
            role TEXT DEFAULT 'user',
            districts TEXT,
            fullname TEXT,
            contacts TEXT,
            consent BOOLEAN DEFAULT 0,
            stats TEXT DEFAULT '{"added":0,"approved":0,"rejected":0,"duplicates":0}'
        )
        ''')
        
        # Таблица деревьев
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tree_id TEXT UNIQUE,
            lat REAL,
            lng REAL,
            status TEXT DEFAULT 'pending', -- pending/approved/rejected/duplicate
            type TEXT, -- alive/dead/attention/special
            photos TEXT, -- JSON array of file_ids
            comments TEXT,
            district TEXT,
            created_by TEXT,
            verified_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица запросов на проверку
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS verification_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE,
            tree_id TEXT,
            user_id TEXT,
            action TEXT, -- add/update/delete
            status TEXT DEFAULT 'pending', -- pending/approved/rejected
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()

# Инициализация БД при запуске
init_db()

# Списки округов и районов Москвы
MOSCOW_DISTRICTS = {
    "ЦАО": [
        "Арбат",
        "Басманный",
        "Замоскворечье",
        "Красносельский",
        "Мещанский",
        "Пресненский",
        "Таганский",
        "Тверской",
        "Хамовники",
        "Якиманка"
    ],
    "САО": [
        "Аэропорт",
        "Беговой",
        "Бескудниковский",
        "Войковский",
        "Восточное Дегунино",
        "Головинский",
        "Дмитровский",
        "Западное Дегунино",
        "Коптево",
        "Левобережный",
        "Молжаниновский",
        "Савеловский",
        "Сокол",
        "Тимирязевский",
        "Ховрино",
        "Хорошевский"
    ],
    "СВАО": [
        "Алексеевский",
        "Алтуфьевский",
        "Бабушкинский",
        "Бибирево",
        "Бутырский",
        "Лианозово",
        "Лосиноостровский",
        "Марфино",
        "Марьина роща",
        "Останкинский",
        "Отрадное",
        "Ростокино",
        "Свиблово",
        "Северный",
        "Северное Медведково",
        "Южное Медведково",
        "Ярославский"
    ],
    "ВАО": [
        "Богородское",
        "Вешняки",
        "Восточный",
        "Восточное Измайлово",
        "Гольяново",
        "Ивановское",
        "Измайлово",
        "Косино-Ухтомский",
        "Метрогородок",
        "Новогиреево",
        "Новокосино",
        "Перово",
        "Преображенское",
        "Северное Измайлово",
        "Соколиная гора",
        "Сокольники"
    ],
    "ЮВАО": [
        "Выхино-Жулебино",
        "Капотня",
        "Кузьминки",
        "Лефортово",
        "Люблино",
        "Марьино",
        "Некрасовка",
        "Нижегородский",
        "Печатники",
        "Рязанский",
        "Текстильщики",
        "Южнопортовый"
    ],
    "ЮАО": [
        "Бирюлево Восточное",
        "Бирюлево Западное",
        "Братеево",
        "Даниловский",
        "Донской",
        "Зябликово",
        "Москворечье-Сабурово",
        "Нагатино-Садовники",
        "Нагатинский затон",
        "Нагорный",
        "Орехово-Борисово Северное",
        "Орехово-Борисово Южное",
        "Царицыно",
        "Чертаново Северное",
        "Чертаново Центральное",
        "Чертаново Южное"
    ],
    "ЮЗАО": [
        "Академический",
        "Гагаринский",
        "Зюзино",
        "Коньково",
        "Котловка",
        "Ломоносовский",
        "Обручевский",
        "Северное Бутово",
        "Теплый Стан",
        "Черемушки",
        "Южное Бутово",
        "Ясенево"
    ],
    "ЗАО": [
        "Внуково",
        "Дорогомилово",
        "Крылатское",
        "Кунцево",
        "Можайский",
        "Ново-Переделкино",
        "Очаково-Матвеевское",
        "Проспект Вернадского",
        "Раменки",
        "Солнцево",
        "Тропарево-Никулино",
        "Филевский парк",
        "Фили-Давыдково"
    ],
    "СЗАО": [
        "Куркино",
        "Митино",
        "Покровское-Стрешнево",
        "Северное Тушино",
        "Строгино",
        "Хорошево-Мневники",
        "Щукино",
        "Южное Тушино"
    ],
    "ЗелАО": [
        "Крюково",
        "Матушкино",
        "Савелки",
        "Силино",
        "Старое Крюково"
    ],
    "Троицкий АО":["Троицкий административный округ"],
    "Новомосковский АО": ["Новомосковский административный округ"]
}
#   web_app=WebAppInfo(url="https://your-domain.com/webapp")


import geopandas as gpd
from shapely.geometry import Point

# Загрузка данных (предварительно скачайте файл районов)
# Пример файла: 'mos_districts.geojson' из https://gis-lab.info/qa/data-mos.html
districts_gdf = gpd.read_file("moscow_districts.geojson")

def get_moscow_district(lat: float, lon: float) -> str:
    """Определяет район Москвы по координатам.
    
    Args:
        lat (float): Широта в WGS84 (например, 55.751244)
        lon (float): Долгота в WGS84 (например, 37.618423)
    
    Returns:
        str: Название района или None, если точка вне границ.
    """
    point = Point(lon, lat)
    
    # Проверка принадлежности к полигонам районов
    for idx, row in districts_gdf.iterrows():
        if row['geometry'].contains(point):
            return row['district']  # Название района из столбца 'name'
    
    return None


def upload_image(local_path: str, remote_folder: str = "/Фото"):
    """
    Загружает изображение на Яндекс.Диск
    :param local_path: Локальный путь к файлу
    :param remote_folder: Папка на Яндекс.Диске (создаст если не существует)
    """
    # Проверка существования файла
    if not os.path.isfile(local_path):
        raise FileNotFoundError(f"Локальный файл не найден: {local_path}")
    
    # Получаем имя файла из пути
    filename = os.path.basename(local_path)
    remote_path = f"{remote_folder}/{filename}"
    
    # Создаем папку если нужно
    if not y.exists(remote_folder):
        y.mkdir(remote_folder)
    
    # Загрузка файла
    try:
        y.upload(local_path, remote_path)
        print(f"Файл успешно загружен: {remote_path}")
        return remote_path
    except yadisk.exceptions.ParentNotFoundError:
        print(f"Ошибка: Родительская папка не существует")
    except yadisk.exceptions.PathExistsError:
        print(f"Ошибка: Файл уже существует на Диске")

def download_image(filename: str, local_folder: str = "downloads", remote_folder: str = "/Фото"):
    """
    Скачивает изображение с Яндекс.Диска
    :param filename: Имя файла на Диске
    :param local_folder: Локальная папка для сохранения
    :param remote_folder: Папка на Яндекс.Диске
    """
    remote_path = f"{remote_folder}/{filename}"
    local_path = os.path.join(local_folder, filename)
    
    # Проверка существования на Диске
    if not y.exists(remote_path):
        raise FileNotFoundError(f"Файл не найден на Диске: {remote_path}")
    
    # Создаем локальную папку если нужно
    os.makedirs(local_folder, exist_ok=True)
    
    # Скачивание файла
    try:
        y.download(remote_path, local_path)
        print(f"Файл успешно скачан: {local_path}")
        return local_path
    except yadisk.exceptions.PathNotFoundError:
        print(f"Ошибка: Файл не найден на Диске")



# Состояния пользователей для FSM
user_states = defaultdict(dict)

# Вспомогательные функции
def get_db_connection():
    return sqlite3.connect(DB_PATH)

def update_user_stats(user_id, stat_type):
    """Обновление статистики пользователя"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT stats FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            stats = json.loads(result[0])
            stats[stat_type] = stats.get(stat_type, 0) + 1
            cursor.execute('UPDATE users SET stats = ? WHERE telegram_id = ?', 
                          (json.dumps(stats), user_id))
            conn.commit()

def save_tree(user_id, tree_data):
    """Сохранение дерева в базу данных"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Определение района по координатам (упрощённо)
        district = what_district(lat, long)
        if district is None:
            return False
        
        cursor.execute('''
        INSERT INTO trees (tree_id, lat, lng, type, photos, comments, district, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(uuid.uuid4()),
            tree_data.get('lat'),
            tree_data.get('lng'),
            tree_data.get('type'),
            json.dumps(tree_data.get('photos', [])),
            tree_data.get('comments'),
            district,
            user_id
        ))
        
        conn.commit()
        update_user_stats(user_id, 'added')
        return True

# ===== РЕГИСТРАЦИЯ ХРАНИТЕЛЯ =====
@bot.message_handler(commands=['guardian'])
def start_guardian(message):
    """Начало процесса регистрации Хранителя"""
    user_id = str(message.from_user.id)
    user_states[user_id] = {"state": "guardian_consent"}
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Да"), types.KeyboardButton("Нет"))
    
    bot.send_message(
        message.chat.id,
        "Вы готовы стать Хранителем района? Если да, то мы попросим ваши персональные и контактные данные, "
        "в соответствии со 152-ФЗ. Вы согласны?",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_consent')
def handle_guardian_consent(message):
    """Обработка согласия на обработку данных"""
    user_id = str(message.from_user.id)
    
    if message.text.lower() == "да":
        user_states[user_id]["state"] = "guardian_district"
        
        # Создаем клавиатуру с округами
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(*[types.KeyboardButton(district) for district in MOSCOW_DISTRICTS.keys()])
        
        bot.send_message(
            message.chat.id,
            "Выберите административный округ Москвы:",
            reply_markup=markup
        )
    else:
        del user_states[user_id]
        bot.send_message(
            message.chat.id,
            "Регистрация отменена. Если передумаете - используйте /guardian снова.",
            reply_markup=types.ReplyKeyboardRemove()
        )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_district')
def handle_guardian_district(message):
    """Обработка выбора округа"""
    user_id = str(message.from_user.id)
    district = message.text
    
    if district in MOSCOW_DISTRICTS:
        user_states[user_id]["district"] = district
        user_states[user_id]["state"] = "guardian_subdistrict"
        
        # Создаем клавиатуру с районами выбранного округа
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(*[types.KeyboardButton(sub) for sub in MOSCOW_DISTRICTS[district]])
        
        bot.send_message(
            message.chat.id,
            f"Теперь выберите район в округе {district}:",
            reply_markup=markup
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Такого округа нет в списке. Пожалуйста, выберите округ из предложенных."
        )


@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_subdistrict')
def handle_guardian_subdistrict(message):
    """Обработка выбора района"""
    user_id = str(message.from_user.id)
    subdistrict = message.text
    district = user_states[user_id].get("district", "")
    
    # Проверяем, что выбранный район принадлежит выбранному округу
    if district and subdistrict in MOSCOW_DISTRICTS.get(district, []):
        user_states[user_id]["subdistrict"] = subdistrict
        user_states[user_id]["state"] = "guardian_fullname"
        
        bot.send_message(
            message.chat.id,
            "Отлично! Теперь введите ваше ФИО (полностью):",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        bot.send_message(
            message.chat.id,
            f"❌ Район {subdistrict} не принадлежит округу {district}. Пожалуйста, выберите район из списка."
        )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_fullname')
def handle_guardian_fullname(message):
    """Обработка ввода ФИО"""
    user_id = str(message.from_user.id)
    user_states[user_id]["fullname"] = message.text
    user_states[user_id]["state"] = "guardian_contacts"
    
    bot.send_message(
        message.chat.id,
        "Теперь введите ваши контактные данные (email и телефон через запятую):\n"
        "Пример: myemail@example.com, +79161234567"
    )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_contacts')
def handle_guardian_contacts(message):
    """Обработка контактных данных"""
    user_id = str(message.from_user.id)
    
    # Сохраняем данные в базу
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Сохраняем пользователя как хранителя
        cursor.execute('''
        INSERT OR REPLACE INTO users (telegram_id, role, districts, fullname, contacts, consent)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            "guardian",
            json.dumps([user_states[user_id]["subdistrict"]]),
            user_states[user_id]["fullname"],
            message.text,
            1  # Согласие на обработку данных
        ))
        conn.commit()
    
    # Отправляем подтверждение
    bot.send_message(
        message.chat.id,
        f"✅ Регистрация завершена!\n\n"
        f"Вы стали Хранителем района: {user_states[user_id]['subdistrict']}\n"
        f"Ваше ФИО: {user_states[user_id]['fullname']}\n"
        f"Ваши контакты: {message.text}\n\n"
        "Ожидайте звонка от координатора в ближайшее время!"
    )
    
    # Очищаем состояние
    del user_states[user_id]

# ===== ДОБАВЛЕНИЕ ДЕРЕВА ЧЕРЕЗ ДИАЛОГ =====
@bot.message_handler(commands=['addtree'])
def start_add_tree(message):
    """Начало процесса добавления дерева"""
    user_id = str(message.from_user.id)
    user_states[user_id] = {
        "state": "tree_photo",
        "tree_data": {}
    }
    
    bot.send_message(
        message.chat.id,
        "Давайте добавим новое дерево! Пожалуйста, отправьте фотографию дерева:"
    )

@bot.message_handler(content_types=['photo'], 
                    func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'tree_photo')
def handle_tree_photo(message):
    """Обработка фотографии дерева"""
    user_id = str(message.from_user.id)
    
    # Сохраняем file_id самой качественной версии фото
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Добавляем фото в данные дерева
    if 'tree_data' not in user_states[user_id]:
        user_states[user_id]['tree_data'] = {}
    
    if 'photos' not in user_states[user_id]['tree_data']:
        user_states[user_id]['tree_data']['photos'] = []
    
    user_states[user_id]['tree_data']['photos'].append(file_id)
    user_states[user_id]['state'] = "tree_location"
    photo.save(LOCAL_PHOTOS+f'/{file_id}.jpg')
    # Предлагаем кнопку для отправки локации
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Отправить локацию", request_location=True))
    
    bot.send_message(
        message.chat.id,
        "Отлично! Теперь отправьте местоположение дерева:",
        reply_markup=markup
    )

@bot.message_handler(content_types=['location'], 
                    func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'tree_location')
def handle_tree_location(message):
    """Обработка локации дерева"""
    user_id = str(message.from_user.id)
    location = message.location
    
    # Сохраняем координаты
    user_states[user_id]['tree_data']['lat'] = location.latitude
    user_states[user_id]['tree_data']['lng'] = location.longitude
    user_states[user_id]['state'] = "tree_type"
    
    # Предлагаем выбрать тип дерева
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("Дерево в безопасности"),
        types.KeyboardButton("Дерево под угрозой"),
        types.KeyboardButton("Дерево под срочной угрозой"),
        types.KeyboardButton("Дерево погибло")
    )
    
    bot.send_message(
        message.chat.id,
        "Выберите состояние дерева:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'tree_type')
def handle_tree_type(message):
    """Обработка типа дерева"""
    user_id = str(message.from_user.id)
    tree_type = message.text
    
    # Маппинг текста на значение
    type_mapping = {
        "Дерево в безопасности": "alive",
        "Дерево погибло": "dead",
        "Дерево под угрозой": "attention",
        "Дерево под срочной угрозой": "special"
    }
    
    if tree_type in type_mapping:
        user_states[user_id]['tree_data']['type'] = type_mapping[tree_type]
        user_states[user_id]['state'] = "tree_comments"
        
        bot.send_message(
            message.chat.id,
            "Добавьте комментарии (если есть):",
            reply_markup=types.ReplyKeyboardRemove()
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Пожалуйста, выберите тип из предложенных вариантов."
        )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'tree_comments')
def handle_tree_comments(message):
    """Обработка комментариев и сохранение дерева"""
    user_id = str(message.from_user.id)
    
    # Сохраняем комментарии
    user_states[user_id]['tree_data']['comments'] = message.text
    
    # Сохраняем дерево в базу
    if save_tree(user_id, user_states[user_id]['tree_data']):
        bot.send_message(
            message.chat.id,
            "✅ Дерево успешно добавлено! Оно появится на карте после проверки хранителем."
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Произошла ошибка при сохранении дерева. Попробуйте позже."
        )
    
    # Очищаем состояние
    del user_states[user_id]

# ===== WEBAPP И КАРТА =====
@bot.message_handler(commands=['/start'])
def send_welcome(message):
    """Обработка команды /start"""
    user_id = str(message.from_user.id)
    
    # Проверяем, зарегистрирован ли пользователь
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
    
    role = user[0] if user else "user"
    
    # Кнопка для открытия карты
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "Открыть карту деревьев", 
        web_app=WebAppInfo(url="https://your-domain.com/webapp")
    ))
    
    # Дополнительные команды для хранителей
    if role == "guardian":
        markup.add(types.InlineKeyboardButton("Модерация запросов", callback_data="moderation"))
    
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! Добро пожаловать в систему мониторинга деревьев Москвы.",
        reply_markup=markup
    )

# ===== СТАТИСТИКА =====
@bot.message_handler(commands=['/stats'])
def show_stats(message):
    """Показать статистику пользователя"""
    user_id = str(message.from_user.id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT stats FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result:
            stats = json.loads(result[0])
            response = (
                "📊 Ваша статистика:\n\n"
                f"Добавлено деревьев: {stats.get('added', 0)}\n"
                f"Одобрено запросов: {stats.get('approved', 0)}\n"
                f"Отклонено запросов: {stats.get('rejected', 0)}\n"
                f"Обнаружено дубликатов: {stats.get('duplicates', 0)}"
            )
        else:
            response = "Статистика не найдена. Начните с добавления деревьев!"
    
    bot.send_message(message.chat.id, response)

# ===== МОДЕРАЦИЯ ДЛЯ ХРАНИТЕЛЕЙ =====
@bot.callback_query_handler(func=lambda call: call.data == "moderation")
def show_moderation_menu(call):
    """Показать меню модерации для хранителей"""
    user_id = str(call.from_user.id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Получаем запросы на модерацию в районах хранителя
        cursor.execute('SELECT districts FROM users WHERE telegram_id = ?', (user_id,))
        districts = json.loads(cursor.fetchone()[0])
        
        cursor.execute('''
        SELECT vr.id, t.type, t.comments, t.photos 
        FROM verification_requests vr
        JOIN trees t ON vr.tree_id = t.tree_id
        WHERE vr.status = 'pending' AND t.district IN ({})
        '''.format(','.join(['?']*len(districts))), districts)
        
        requests = cursor.fetchall()
    
    if requests:
        # Отправляем первый запрос на модерацию
        request = requests[0]
        photos = json.loads(request[3])
        
        # Создаем медиа-группу с фотографиями
        media = [types.InputMediaPhoto(photo) for photo in photos[:10]]
        
        # Клавиатура для действий
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{request[0]}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{request[0]}"),
            types.InlineKeyboardButton("🚫 Дубликат", callback_data=f"duplicate_{request[0]}")
        )
        
        bot.send_media_group(call.message.chat.id, media)
        bot.send_message(
            call.message.chat.id,
            f"Запрос на модерацию:\nТип: {request[1]}\nКомментарий: {request[2]}",
            reply_markup=markup
        )
        
        # Сохраняем остальные запросы в состоянии
        user_states[user_id]['pending_requests'] = requests[1:]
    else:
        bot.send_message(call.message.chat.id, "Нет запросов на модерацию в ваших районах.")

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_', 'reject_', 'duplicate_')))
def handle_moderation_decision(call):
    """Обработка решения хранителя"""
    user_id = str(call.from_user.id)
    request_id = call.data.split('_')[1]
    decision = call.data.split('_')[0]
    
    # Обновляем статус запроса
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Обновляем статус запроса
        cursor.execute('''
        UPDATE verification_requests 
        SET status = ?, verified_by = ?
        WHERE id = ?
        ''', (decision, user_id, request_id))
        
        # Если одобрено, обновляем статус дерева
        if decision == "approve":
            cursor.execute('''
            UPDATE trees t
            SET status = 'approved'
            WHERE tree_id = (
                SELECT tree_id FROM verification_requests WHERE id = ?
            )
            ''', (request_id,))
        
        conn.commit()
    
    # Обновляем статистику хранителя
    update_user_stats(user_id, 'approved' if decision == "approve" else 'rejected')
    
    # Проверяем, есть ли еще запросы
    if user_states.get(user_id, {}).get('pending_requests'):
        next_request = user_states[user_id]['pending_requests'].pop(0)
        
        # Отправляем следующий запрос...
        # (код аналогичен show_moderation_menu)
        
        bot.answer_callback_query(call.id, "Решение принято!")
    else:
        bot.send_message(call.message.chat.id, "Модерация завершена!")
        del user_states[user_id]['pending_requests']

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
