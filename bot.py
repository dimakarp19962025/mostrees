# -*- coding: utf-8 -*-
"""
Created on Thu Jul 10 16:08:07 2025

@author: da.karpov1
"""

# start stats guardian addtree - commands
# CHANGE TOKEN BEFOREHAND!
# Добавить функционал для Администратора приложения подтверждать или не подтверждать кандидатов в Хранители
import os
import requests
import sqlite3
import json
import uuid
from datetime import datetime
from collections import defaultdict
import telebot
import yadisk
from telebot import types
from telebot.types import WebAppInfo
import geopandas as gpd
from shapely.geometry import Point

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_TOKEN = '7618578466:AAFgJSo-i2ivp99CzYmMrXrUgiz2XdePXhg'
YADISK_TOKEN = os.environ.get('YADISK_TOKEN')
YADISK_TOKEN = 'y0__xDi3dehqveAAhjWhTkghrfZ7BNOdwab2B-c-cEwy8tTKdNPIiOZAw'
# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
y = yadisk.YaDisk(YADISK_TOKEN) 

# Константы ролей
ROLES = {
    'user': 0,
    'guardian_pending': 1,
    'guardian': 2,
    'superguardian': 3,
    'admin': 4
}

MAX_DISTRICTS_PER_GUARDIAN = 1  # Максимальное количество районов
ADMIN_ID = '169878591'

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
            role INTEGER DEFAULT 0,  -- 0=user, 1=guardian_pending, 2=guardian, 3=superguardian, 4=admin
            districts TEXT,
            fullname TEXT,
            phone TEXT,
            email TEXT,
            approved_by TEXT,  -- Кто одобрил хранителя
            stats TEXT DEFAULT '{"added":0,"approved":0,"rejected":0,"duplicates":0}'
        )
        ''')
                
        # Таблица деревьев
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS trees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tree_id TEXT UNIQUE,
            latitude REAL,
            longitude REAL,
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

def is_user(user_id):
    """
    Возвращает полную информацию о пользователе в виде словаря.
    Возвращает None, если пользователь не найден.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Получаем все данные о пользователе
        cursor.execute('''
        SELECT id, telegram_id, role, districts, fullname, phone, email, approved_by, stats
        FROM users 
        WHERE telegram_id = ?
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        
        if user_data:
            # Преобразуем в словарь с понятными ключами
            columns = [column[0] for column in cursor.description]
            user_dict = dict(zip(columns, user_data))
            
            # Преобразуем JSON-поля в объекты Python
            if user_dict.get('districts'):
                user_dict['districts'] = json.loads(user_dict['districts'])
            if user_dict.get('stats'):
                user_dict['stats'] = json.loads(user_dict['stats'])
                
            return user_dict
        return None
def change_user_data(user_id, fullname=None,email=None,phone=None,districts=[]):
    """
    Удаляет персональные данные пользователя из системы (GDPR compliance).
    Сохраняет только telegram_id и статистику.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        if fullname is not None:
            cursor.execute('''
            UPDATE users 
            SET 
                fullname = ?,
            WHERE telegram_id = ?
            ''', (fullname, user_id))
        if email is not None:
            cursor.execute('''
            UPDATE users 
            SET 
                email = ?,
            WHERE telegram_id = ?
            ''', (email, user_id))
        if phone is not None:
            cursor.execute('''
            UPDATE users 
            SET 
                phone = ?,
            WHERE telegram_id = ?
            ''', (phone, user_id))
                                                
        conn.commit()
        return True

def get_districts(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        return result and result[0] >= ROLES['guardian']    

def is_admin(user_id):
    return user_id == ADMIN_ID # This is me

def is_superguardian(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        return result and result[0] >= ROLES['superguardian']

def is_guardian(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        return result and result[0] >= ROLES['guardian']

def is_guardian_pending(user_id):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        return result and result[0] >= ROLES['guardian_pending']


def add_new_user_if_not_exists(telegram_id):
    """
    Добавляет нового пользователя с указанным telegram_id и ролью 0 (обычный пользователь),
    если пользователь с таким telegram_id еще не существует в базе.
    
    Возвращает:
        True - если пользователь был добавлен
        False - если пользователь уже существует
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Проверяем существование пользователя
        cursor.execute('SELECT COUNT(*) FROM users WHERE telegram_id = ?', (telegram_id,))
        exists = cursor.fetchone()[0] > 0
        
        if not exists:
            # Добавляем нового пользователя
            cursor.execute('''
            INSERT INTO users (
                telegram_id, 
                role,
                districts,
                fullname,
                phone,
                email,
                approved_by,
                stats
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                telegram_id,
                ROLES['user'],  # роль 0 - обычный пользователь
                None,           # districts
                None,           # fullname
                None,           # phone
                None,           # email
                None,           # approved_by
                json.dumps({    # пустая статистика
                    "added": 0,
                    "approved": 0,
                    "rejected": 0,
                    "duplicates": 0
                })
            ))
            conn.commit()
            return True
        return False

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
    "Новомосковский АО": ["Новомосковский административный округ"],
    "Не Москва":["Не Москва"]
}
web_app=WebAppInfo(url="https://your-domain.com/webapp")


@bot.message_handler(func=lambda message: message.text.lower() == "назад")
def handle_back_button(message):
    """Обработка кнопки 'Назад' для возврата в главное меню"""
    user_id = str(message.from_user.id)
    
    # Сбрасываем состояние пользователя
    if user_id in user_states:
        del user_states[user_id]
    send_welcome(message)

# Загрузка данных (предварительно скачайте файл районов)
# Пример файла: 'mos_districts.geojson' из https://gis-lab.info/qa/data-mos.html
districts_gdf = gpd.read_file("moscow_districts.geojson")

def get_moscow_district(latitude: float, longitude: float) -> str:
    """Определяет район Москвы по координатам.
    
    Args:
        latitude (float): Широта в WGS84 (например, 55.751244)
        longitude (float): Долгота в WGS84 (например, 37.618423)
    
    Returns:
        str: Название района или None, если точка вне границ.
    """
    point = Point(longitude, latitude)
    
    # Проверка принадлежности к полигонам районов
    for idx, row in districts_gdf.iterrows():
        if row['geometry'].contains(point):
            return row['district']  # Название района из столбца 'name'
    
    return "Не Москва"


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
        district = get_moscow_district(latitude=tree_data.get('latitude'), longitude=tree_data.get('longitude'))
        
        if district is None:
            return False
        
        cursor.execute('''
        INSERT INTO trees (tree_id, latitude, longitude, type, photos, comments, district, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            str(uuid.uuid4()),
            tree_data.get('latitude',-1),
            tree_data.get('longitude', -1),
            tree_data.get('type'),
            json.dumps(tree_data.get('photos', [])),
            tree_data.get('comments'),
            district,
            user_id
        ))
        
        conn.commit()
        print('Добавлено дерево!!!')
        print(user_id)
        r0=conn.cursor().execute('SELECT stats FROM users WHERE telegram_id = ?', (user_id,)).fetchone()
        update_user_stats(user_id, 'added')
        r1=conn.cursor().execute('SELECT stats FROM users WHERE telegram_id = ?', (user_id,)).fetchone()
        print('before')
        print(r0)
        print('after')
        print(r1)
        assert r0!=r1
        return True

# ===== РЕГИСТРАЦИЯ ХРАНИТЕЛЯ =====
@bot.message_handler(commands=['guardian'])
def start_guardian(message):
    print('Call start_guardian')
    print(message)
    """Начало процесса регистрации Хранителя"""
    user_id = str(message.from_user.id)
    if is_guardian_pending(user_id):
        bot.send_message(message.chat.id, 'Ваша заявка рассматривается. Ожидайте ответа')
        bot.send_message(message.chat.id, f'Данные заявки {is_user(user_id)}')
    elif is_guardian(user_id):
        bot.send_message(message.chat.id, 'Вы уже Хранитель района')
    else:
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
    print('Call handle_guardian_consent')
    print(message)
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
    print('Call handle_guardian_district')
    print(message)
    """Обработка выбора округа"""
    user_id = str(message.from_user.id)
    district = message.text
    
    if district in MOSCOW_DISTRICTS:
        user_states[user_id]["current_district"] = district
        user_states[user_id]["state"] = "guardian_subdistrict"
        
        # Создаем клавиатуру с районами выбранного округа
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(*[types.KeyboardButton(sub) for sub in MOSCOW_DISTRICTS[district]])

        bot.send_message(
            message.chat.id,
            f"Теперь выберите район в округе {district}:",
            reply_markup=markup
        )
    elif district in ['Назад', '❌ Отмена','✅ Завершить выбор']:
        send_welcome(message)
    else:
        bot.send_message(
            message.chat.id,
            "❌ Такого округа нет в списке. Пожалуйста, выберите округ из предложенных."
        )


def show_district_selection(user_id):
    print('Call show_district_selection')
    print(user_id)    
    """Показывает клавиатуру для выбора округов и районов с ограничениями"""
    try:
        # Проверяем текущее количество выбранных районов
        current_count = len(user_states[user_id].get("districts", []))
        
        # Создаем клавиатуру
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True, 
            row_width=2,
            one_time_keyboard=False
        )
        
        # Добавляем кнопки округов
        districts_buttons = []
        for district in MOSCOW_DISTRICTS.keys():
            # Проверяем, есть ли в округе доступные районы
            available_subdistricts = [
                sub for sub in MOSCOW_DISTRICTS[district] 
                if f"{district}, {sub}" not in user_states[user_id].get("districts", [])
            ]
            
            if available_subdistricts:
                districts_buttons.append(types.KeyboardButton(district))
        
        # Разбиваем на ряды по 2 кнопки
        for i in range(0, len(districts_buttons), 2):
            row = districts_buttons[i:i+2]
            markup.add(*row)
        
        # Добавляем кнопки управления
        if current_count > 0:
            markup.add(types.KeyboardButton("✅ Завершить выбор"))
            
            # Показываем информацию о текущем выборе
            selected_text = "\n".join(
                f"• {d}" for d in user_states[user_id]["districts"]
            )
            message_text = (
                f"Вы выбрали {current_count}/{MAX_DISTRICTS_PER_GUARDIAN} районов:\n"
                f"{selected_text}\n\n"
                "Выберите следующий округ:"
            )
        else:
            message_text = "Выберите административный округ Москвы:"
        
        # Добавляем кнопку отмены
        markup.add(types.KeyboardButton("❌ Отмена"))
        
        # Проверяем ограничение по количеству районов
        if current_count >= MAX_DISTRICTS_PER_GUARDIAN:
            bot.send_message(
                user_id,
                f"❌ Вы достигли максимума в {MAX_DISTRICTS_PER_GUARDIAN} районов. "
                "Нажмите '✅ Завершить выбор' чтобы продолжить.",
                reply_markup=markup
            )
        else:
            bot.send_message(
                user_id,
                message_text,
                reply_markup=markup
            )
            
    except Exception as e:
        print(f"Error in show_district_selection: {str(e)}")
        bot.send_message(
            user_id,
            "⚠️ Произошла ошибка при загрузке районов. Попробуйте позже.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        # Сбрасываем состояние при ошибке
        if user_id in user_states:
            del user_states[user_id]

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_subdistrict')
def handle_guardian_subdistrict(message):
    print('Call handle_guardian_subdistrict')
    print(message)
    user_id = str(message.from_user.id)
    subdistrict = message.text
    district = user_states[user_id].get("current_district", "")
    
    # Проверка ограничения
    current_count = len(user_states[user_id].get("districts", []))
    if current_count >= MAX_DISTRICTS_PER_GUARDIAN:
        bot.send_message(
            user_id,
            f"❌ Вы не можете добавить более {MAX_DISTRICTS_PER_GUARDIAN} районов. "
            "Нажмите '✅ Завершить выбор' чтобы продолжить."
        )
        show_district_selection(user_id)
        return
    
    if district and subdistrict in MOSCOW_DISTRICTS.get(district, []):
        full_district_name = f"{district}, {subdistrict}"
        
        if "districts" not in user_states[user_id]:
            user_states[user_id]["districts"] = []
            
        user_states[user_id]["districts"].append(full_district_name)
        user_states[user_id]["state"] = "guardian_fullname"
        
        bot.send_message(
            user_id,
            f"✅ Район '{full_district_name}' добавлен! ",
            reply_markup=types.ReplyKeyboardRemove()
        )
        handle_guardian_fullname(message)
    else:
        bot.send_message(
            user_id,
            f"❌ Район '{subdistrict}' не принадлежит округу '{district}'. Пожалуйста, выберите район из списка."
        )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_fullname')
def handle_guardian_fullname(message):
    print('Call handle_guardian_fullname')
    print(message)
    bot.send_message(
        message.chat.id,
        "Введите вашу фамилию, имя, отчество. Как Вас звать-величать?"
    )
    user_id = str(message.from_user.id)    
    user_states[user_id]["state"] = "guardian_phone"

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_phone')
def handle_guardian_phone(message):
    print('Call handle_guardian_phone')
    print(message)
    user_id = str(message.from_user.id)    
    user_states[user_id]['fullname'] = message.text
    bot.send_message(
        message.chat.id,
        "Введите ваш сотовый номер. Начинаться должен с +7."
    )
    user_states[user_id]["state"] = "guardian_email"

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_email')
def handle_guardian_email(message):
    print('Call handle_guardian_email')
    print(message)
    user_id = str(message.from_user.id)    
    if message.text[:2]!='+7' or len(message.text.replace(' ', ''))!=12:
        bot.send_message(message.chat.id, 'Номер должен начинаться с +7 и состоять из 10 цифр после +7. Иные номера не поддерживаются')
        user_states[user_id]["state"] = "guardian_email"
    else:
        user_states[user_id]['phone'] = message.text
        bot.send_message(
            message.chat.id,
            "Введите ваш email."
        )
        user_states[user_id]["state"] = "guardian_write_data"


@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'guardian_write_data')
def handle_guardian_data(message):
    print('Call handle_guardian_data')
    print(message)
    user_id = str(message.from_user.id)

    if '@' not in message.text:
        bot.send_message(message.chat.id, 'Email должен содержать @')
        user_states[user_id]["state"] = "guardian_email"
    else:
        user_states[user_id]['email'] = message.text
        # Сохраняем как ожидающего подтверждения
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT OR REPLACE INTO users (
                telegram_id, role, districts, fullname, phone, email
            ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                ROLES['guardian_pending'],
                json.dumps(user_states[user_id]["districts"]),
                user_states[user_id]["fullname"],
                user_states[user_id]['phone'],
                user_states[user_id]['email']
            ))
            conn.commit()
    
        # Уведомляем администраторов
        notify_admins(user_id, user_states[user_id]["districts"],
                    user_states[user_id]["fullname"], message.text)
        
        bot.send_message(
            message.chat.id,
            "✅ Ваша заявка подана на рассмотрение! "
            "Администратор свяжется с вами после проверки."
        )
        
        # Очищаем состояние
        del user_states[user_id]


def notify_admins(new_user_id, district, fullname, contact_raw_data):
    """Уведомляем администраторов о новой заявке"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM users WHERE role >= ?', (ROLES['superguardian'],))
        admins = cursor.fetchall()
        
        for (admin_id,) in admins:
            try:
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_guardian:{new_user_id}"),
                    types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_guardian:{new_user_id}")
                )
                
                bot.send_message(
                    admin_id,
                    f"Новая заявка на хранителя района {district}!\n"
                    f"Пользователь ID: {new_user_id}\n"
                    f"ФИО: {fullname}\n"
                    f"Контактные данные {contact_raw_data}\n"
                    "Пожалуйста, рассмотрите заявку:",
                    reply_markup=markup
                )
            except Exception as e:
                print(f"Error notifying admin {admin_id}: {e}")


# ===== ДОБАВЛЕНИЕ ДЕРЕВА ЧЕРЕЗ ДИАЛОГ =====
@bot.message_handler(commands=['addtree'], func = lambda message: any([x in message.text for x in ['addtree', 'Добавить дерево']]))
def start_add_tree(message):
    """Начало процесса добавления дерева"""
    user_id = str(message.from_user.id)
    user_states[user_id] = {
        "state": "tree_photo",
        "tree_data": {}
    }
    
    # IF user NOT IN base - ADD HIM!
    add_new_user_if_not_exists(user_id)
    
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
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
    # Генерируем уникальное имя файла
    file_name = f"tree_{message.message_id}_{message.from_user.id}.jpg"
    image_data = requests.get(file_url).content
    file_path = os.path.join('Фото', file_name)
    with open(file_path, 'wb') as f:
        f.write(image_data)
    #remote_path = f"/Фото/{file_name}"
    #try:
    #    y.upload(file_path, remote_path)
    #    yandex_url = f"https://disk.yandex.ru/client/disk{remote_path}"
    #except Exception as e:
    #    print(f"Ошибка загрузки на Яндекс.Диск: {e}")
    #    yandex_url = ''
    
        
    # Добавляем фото в данные дерева
    if 'tree_data' not in user_states[user_id]:
        user_states[user_id]['tree_data'] = {}
    user_states[user_id]['tree_data']['photos'] = {
        'file_id': file_id,
        'local_path': file_path,
        #'yandex_url': yandex_url
    }
    user_states[user_id]['state'] = "tree_location"
    # Предлагаем кнопку для отправки локации
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Отправить свою локацию", request_location=True))    
    bot.send_message(
        message.chat.id,
        "Отлично! Теперь отправьте локацию дерева. Если Вы рядом с ним, отправьте свою локацию. Если нет, прикрепите локацию к сообщению.",
        reply_markup=markup
    )

@bot.message_handler(content_types=['location'], 
                    func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'tree_location')
def handle_tree_location(message):
    """Обработка локации дерева"""
    user_id = str(message.from_user.id)
    location = message.location
    print(location)
    # Сохраняем координаты
    user_states[user_id]['tree_data']['latitude'] = location.latitude
    user_states[user_id]['tree_data']['longitude'] = location.longitude
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
            "Район пока не поддерживается!"
        )
    
    # Очищаем состояние
    del user_states[user_id]

# ===== WEBAPP И КАРТА =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = str(message.from_user.id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT role FROM users WHERE telegram_id = ?', (user_id,))
        user = cursor.fetchone()
    
    role = user[0] if user else ROLES['user']
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Добавить дерево", callback_data="addtree"))

    markup.add(types.InlineKeyboardButton(
        "Открыть карту деревьев", 
        web_app=WebAppInfo(url="https://your-domain.com/webapp")
    ))
    # Дополнительные возможности для хранителей и администраторов
    if  int(role) >= ROLES['guardian']:
        markup.add(types.InlineKeyboardButton("Модерация запросов", callback_data="moderation"))
        if int(role) == ROLES['guardian']:
            markup.add(types.InlineKeyboardButton("Мои районы", callback_data="my_districts"))
    else:
        markup.add(types.InlineKeyboardButton("Стать Хранителем", callback_data="guardian"))
    markup.add(types.InlineKeyboardButton("Моя статистика", callback_data="stats"))
    if int(role) >= ROLES['admin']:
        markup.add(types.InlineKeyboardButton("Панель администратора", callback_data="admin_panel"))
    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! Добро пожаловать в систему мониторинга деревьев Москвы.",
        reply_markup=markup
    )

# ===== СТАТИСТИКА =====
@bot.message_handler(commands=['stats'])
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
        
        ver_requests = cursor.fetchall()
    
    if ver_requests:
        # Отправляем первый запрос на модерацию
        request = ver_requests[0]
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
        user_states[user_id]['pending_requests'] = ver_requests[1:]
    else:
        bot.send_message(call.message.chat.id, "Нет запросов на модерацию в ваших районах.")

@bot.message_handler(commands=['my_districts'])
def manage_districts(message):
    user_id = str(message.from_user.id)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT districts FROM users WHERE telegram_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            bot.reply_to(message, "У вас нет назначенных районов")
            return
        
        districts = json.loads(result[0])
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        # Кнопки для удаления районов
        for district in districts:
            markup.add(types.KeyboardButton(f"❌ Удалить {district}"))
        
        # Кнопка добавления нового района (если не достигнут лимит)
        if len(districts) < MAX_DISTRICTS_PER_GUARDIAN:
            markup.add(types.KeyboardButton("➕ Добавить район"))
        
        markup.add(types.KeyboardButton("✅ Завершить"))
        markup.add(types.KeyboardButton("Назад"))  # Добавляем кнопку Назад

        user_states[user_id] = {
            "state": "managing_districts",
            "current_districts": districts
        }
        
        bot.send_message(
            message.chat.id,
            "🏙️ Управление вашими районами:\n" + "\n".join([f"- {d}" for d in districts]),
            reply_markup=markup
        )

@bot.message_handler(func=lambda message: 
                    user_states.get(str(message.from_user.id), {}).get('state') == 'managing_districts')
def handle_district_management(message):
    user_id = str(message.from_user.id)
    text = message.text
    
    if text == "➕ Добавить район":
        user_states[user_id]["state"] = "adding_district"
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(*[types.KeyboardButton(district) for district in MOSCOW_DISTRICTS.keys()])
        bot.send_message(
            message.chat.id,
            "Выберите административный округ:",
            reply_markup=markup
        )
    
    elif text == "✅ Завершить":
        # Сохраняем изменения
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE users SET districts = ? WHERE telegram_id = ?',
                (json.dumps(user_states[user_id]["current_districts"]), user_id)
            )
            conn.commit()
        
        del user_states[user_id]
        bot.send_message(
            message.chat.id,
            "✅ Ваши районы успешно обновлены!",
            reply_markup=types.ReplyKeyboardRemove()
        )
    
    elif text.startswith("❌ Удалить "):
        district_to_remove = text[11:]
        if district_to_remove in user_states[user_id]["current_districts"]:
            user_states[user_id]["current_districts"].remove(district_to_remove)
            
            # Обновляем сообщение
            response = "🏙️ Управление вашими районами:\n" + "\n".join(
                [f"- {d}" for d in user_states[user_id]["current_districts"]] or ["Нет районов"])
            
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for district in user_states[user_id]["current_districts"]:
                markup.add(types.KeyboardButton(f"❌ Удалить {district}"))
            
            if len(user_states[user_id]["current_districts"]) < MAX_DISTRICTS_PER_GUARDIAN:
                markup.add(types.KeyboardButton("➕ Добавить район"))
            
            markup.add(types.KeyboardButton("✅ Завершить"))
            markup.add(types.KeyboardButton("Назад"))  # Добавляем кнопку Назад

            bot.send_message(
                message.chat.id,
                f"✅ Район '{district_to_remove}' удален!\n\n{response}",
                reply_markup=markup
            )
        else:
            bot.send_message(message.chat.id, "❌ Этот район не найден в вашем списке")

@bot.message_handler(commands=['init_admin'])
def init_admin(message):
    user_id = str(message.from_user.id)
    assert user_id == ADMIN_ID
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE role = ?', (ROLES['admin'],))
        admin_count = cursor.fetchone()[0]
        
        if admin_count > 0:
            bot.reply_to(message, "❌ Администратор уже существует")
            return
        
        # Назначаем первого администратора
        cursor.execute('''
        INSERT INTO users (telegram_id, role)
        VALUES (?, ?)
        ''', (user_id, ROLES['admin']))
        conn.commit()
        
        bot.reply_to(message, "✅ Вы назначены первым администратором системы!")



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

@bot.callback_query_handler(func=lambda call: call.data.startswith(('approve_guardian:', 'reject_guardian:')))
def handle_guardian_decision(call):
    action, target_id = call.data.split(':')
    admin_id = str(call.from_user.id)
    
    if not is_admin(admin_id):
        bot.answer_callback_query(call.id, "⛔ У вас нет прав администратора!")
        return
    
    new_role = ROLES['guardian'] if action == "approve_guardian" else ROLES['user']
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE users 
        SET role = ?, approved_by = ?
        WHERE telegram_id = ?
        ''', (new_role, admin_id, target_id))
        conn.commit()
        
        # Уведомляем пользователя
        try:
            if action == "approve_guardian":
                bot.send_message(
                    target_id, 
                    "🎉 Поздравляем! Ваша заявка на хранителя одобрена. "
                    "Теперь вы можете проверять деревья в выбранных районах."
                )
            else:
                bot.send_message(
                    target_id, 
                    "❌ Ваша заявка на хранителя отклонена. "
                    "Вы можете подать заявку повторно через некоторое время."
                )
        except Exception as e:
            print(f"Error notifying user: {e}")
        
        bot.answer_callback_query(call.id, "Решение принято!")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\nРешение: {'Одобрено' if action == 'approve_guardian' else 'Отклонено'}",
            reply_markup=None
        )

@bot.message_handler(commands=['admin_panel'])
def admin_panel(message):
    user_id = str(message.from_user.id)
    
    if not is_admin(user_id):
        print(user_id)
        bot.reply_to(message, "⛔ Только для администраторов")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("Управление хранителями", callback_data="admin_manage_guardians"),
        types.InlineKeyboardButton("Управление суперхранителями", callback_data="admin_manage_supers"),
        types.InlineKeyboardButton("Просмотр статистики", callback_data="admin_view_stats")
    )
    
    bot.send_message(
        message.chat.id,
        "⚙️ Панель администратора:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_actions(call):
    user_id = str(call.from_user.id)
    action = call.data.split('_')[1]
    
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "⛔ Доступ запрещен")
        return
    
    if action == "manage_guardians":
        # Показать список хранителей с возможностью управления
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT telegram_id, fullname, districts FROM users WHERE role = ?', (ROLES['guardian'],))
            guardians = cursor.fetchall()
            
            response = "🧑‍🌾 Список хранителей:\n\n"
            for g in guardians:
                response += f"ID: {g[0]}\nИмя: {g[1]}\nРайоны: {g[2]}\n\n"
                response += f"Действия: "
                response += f"[Повысить](/promote_to_super_{g[0]}) "
                response += f"[Снять](/revoke_guardian_{g[0]})\n\n"
            
            bot.send_message(call.message.chat.id, response, parse_mode="Markdown")
    
@bot.message_handler(commands=['change_fullname'])
def change_name(message):
    if not is_admin(str(message.from_user_id)):
        return
    tg_id=message.text.split('_')[-2]
    new_fullname=message.text.split('_')[-1]
    change_user_data(user_id=int(tg_id),fullname=new_fullname)

@bot.message_handler(commands=['change_email'])
def change_email(message):
    if not is_admin(str(message.from_user_id)):
        return
    tg_id=message.text.split(' ')[-2]
    new_email=message.text.split(' ')[-1]
    change_user_data(user_id=int(tg_id),email=new_email)

@bot.message_handler(commands=['change_phone'])
def change_phone(message):
    if not is_admin(str(message.from_user_id)):
        return
    tg_id=message.text.split(' ')[-2]
    new_phone=message.text.split(' ')[-1]
    change_user_data(user_id=int(tg_id),phone=new_phone)
  
  


@bot.message_handler(commands=['promote_to_super_'])
def promote_to_super(message):
    user_id = str(message.from_user.id)
    target_id = message.text.split('_')[-1]
    
    if not is_admin(user_id):
        return
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE users 
        SET role = ?, approved_by = ?
        WHERE telegram_id = ?
        ''', (ROLES['superguardian'], user_id, target_id))
        conn.commit()
        
        bot.reply_to(message, f"✅ Пользователь {target_id} теперь суперхранитель!")
        try:
            bot.send_message(
                target_id,
                "🎉 Вы назначены суперхранителем! Теперь вы можете одобрять заявки других хранителей."
            )
        except:
            pass

@bot.message_handler(commands=['revoke_super_'])
def revoke_super(message):
    user_id = str(message.from_user.id)
    target_id = message.text.split('_')[-1]
    
    if not is_admin(user_id):
        return
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        UPDATE users 
        SET role = ?
        WHERE telegram_id = ? AND role = ?
        ''', (ROLES['guardian'], target_id, ROLES['superguardian']))
        conn.commit()
        
        if cursor.rowcount > 0:
            bot.reply_to(message, f"✅ Роль суперхранителя для {target_id} отозвана!")
            try:
                bot.send_message(
                    target_id,
                    "ℹ️ Ваша роль суперхранителя была отозвана администратором."
                )
            except:
                pass
        else:
            bot.reply_to(message, "❌ Пользователь не найден или не является суперхранителем")


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = str(call.from_user.id)
    data = call.data
    
    if data == "addtree":
        start_add_tree(call.message)
    elif data == "guardian":
        start_guardian(call.message)
    elif data == "moderation":
        show_moderation_menu(call)
    elif data == "my_districts":
        manage_districts(call.message)
    elif data == "stats":
        show_stats(call.message)
    elif data == "admin_panel":
        admin_panel(call.message)
    elif data.startswith("approve_"):
        handle_moderation_decision(call)
    elif data.startswith("reject_"):
        handle_moderation_decision(call)
    elif data.startswith("duplicate_"):
        handle_moderation_decision(call)
    elif data.startswith("approve_guardian:"):
        handle_guardian_decision(call)
    elif data.startswith("reject_guardian:"):
        handle_guardian_decision(call)



# Запуск бота
if __name__ == '__main__':
    print("Бот запущен... ПОМЕНЯТЬ ТОКЕН ДО ВЫХОДА БОТА В СВЕТ И ЗАПРИВАТИТЬ И ВСЕ ПРОТЕСТИТЬ")
    bot.infinity_polling()

# start stats guardian addtree - commands
