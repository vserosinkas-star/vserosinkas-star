import logging
import re
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from flask import Flask
import threading

import requests
import time
import os

app = Flask(__name__)

@app.route('/')
def home():
    return 'Dashboard is running!'

# === ДОБАВЬТЕ ЭТОТ КОД ===

def keep_alive():
    def ping():
        while True:
            try:
                # Автоматическое определение URL на Render
                url = os.environ.get('RENDER_EXTERNAL_URL', 'https://your-app-name.onrender.com')
                response = requests.get(url)
                print(f"Self-ping successful at {time.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                print(f"Self-ping failed: {e}")
            time.sleep(300)  # 5 минут
    
    thread = threading.Thread(target=ping)
    thread.daemon = True
    thread.start()

# === ВЫЗОВИТЕ ПРИ ЗАПУСКЕ ===

if __name__ == '__main__':
    keep_alive()  # ← Запускаем самопинг
    app.run(host='0.0.0.0', port=5000, debug=False)

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
RANGE_NAME = os.environ.get('RANGE_NAME', 'Data!A:E')

# Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Создаем Flask app для привязки порта
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот-куратор ВСП работает!"

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

def get_sheets_service():
    """Инициализация сервиса Google Sheets с обработкой ошибок"""
    try:
        # Проверяем наличие файла с учетными данными
        if not os.path.exists('credentials.json'):
            raise FileNotFoundError("Файл credentials.json не найден")
        
        creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        logging.error(f"Ошибка инициализации Google Sheets: {e}")
        return None

# Загрузка данных
def load_data():
    try:
        # Проверяем наличие обязательных переменных
        if not SPREADSHEET_ID:
            raise ValueError("SPREADSHEET_ID не установлен")
        
        sheets_service = get_sheets_service()
        if not sheets_service:
            return {}, {}
        
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME
        ).execute()
        
        values = result.get('values', [])
        vsp_map = {}
        city_map = {}

        if not values:
            logging.warning("Таблица пуста или не содержит данных")
            return {}, {}

        for row in values[1:]:  # Пропускаем заголовок
            if len(row) >= 5:
                vsp = row[0].strip() if len(row) > 0 else ''
                fio = row[1].strip() if len(row) > 1 else ''
                contact = row[2].strip() if len(row) > 2 else ''
                mobile = row[3].strip() if len(row) > 3 else ''
                city = row[4].strip() if len(row) > 4 else ''
                
                if not vsp or not fio:
                    continue
                    
                record = {'vsp': vsp, 'fio': fio, 'contact': contact, 'mobile': mobile, 'city': city}
                vsp_map[vsp] = record
                
                if city:
                    if city not in city_map:
                        city_map[city] = []
                    city_map[city].append(record)
                    
        logging.info(f"Загружено {len(vsp_map)} записей ВСП и {len(city_map)} городов")
        return vsp_map, city_map
        
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")
        return {}, {}

def normalize_city(city: str) -> str:
    if not city:
        return ''
    city = city.lower().strip()
    city = re.sub(r'(в\s+|во\s+|г\.?\s*|город\s*|городе\s*|г\s*)', '', city)
    city = re.sub(r'[еыуя]$', '', city)
    return city.capitalize()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот-куратор ВСП.\n\n"
        "Отправьте:\n"
        "• Код ВСП — например, `8647/06001`\n"
        "• Или город — например, `Салехард`\n\n"
        "Я найду куратора и контакты!",
        parse_mode="Markdown"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок"""
    logging.error(f"Exception occurred: {context.error}")
    
    # Отправляем сообщение пользователю при ошибке
    if update and hasattr(update, 'effective_chat'):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже."
            )
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение об ошибке: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        vsp_map, city_map = load_data()
        
        # Проверяем, загрузились ли данные
        if not vsp_map and not city_map:
            await update.message.reply_text(
                "❌ Временная проблема с доступом к данным. Пожалуйста, попробуйте позже.",
                parse_mode="Markdown"
            )
            return
            
        text = update.message.text.strip()

        # ИСПРАВЛЕННОЕ регулярное выражение для поиска ВСП
        # Ищет форматы: 8647/06001, 8598/00792, 5940/06052 и т.д.
        vsp_match = re.search(r'\b(\d{4}/\d{3,5})\b', text)  # От 3 до 5 цифр после слэша
        if vsp_match:
            vsp = vsp_match.group(1)
            record = vsp_map.get(vsp)
            if record:
                city_part = f" г. {record['city']}" if record['city'] else ''
                response = (
                    f"👌 **ВСП {vsp}{city_part}**\n\n"
                    f"🧑 **{record['fio']}**\n"
                    f"📞 **Контакт:** {record['contact'] or 'не указан'}\n"
                    f"📱 **Мобильный:** {record['mobile'] or 'не указан'}"
                )
            else:
                response = f"❌ ВСП **{vsp}** не найден."
            await update.message.reply_text(response, parse_mode="Markdown")
            return

        # Поиск по городу
        norm_query = normalize_city(text)
        records = None
        for city in city_map:
            if normalize_city(city) == norm_query:
                records = city_map[city]
                break

        if not records:
            await update.message.reply_text(
                f"❌ Не найдено кураторов по запросу «{text}».\n"
                "Попробуйте: *Салехард*, *8647/06001*",
                parse_mode="Markdown"
            )
            return

        if len(records) == 1:
            r = records[0]
            city_part = f" г. {r['city']}" if r['city'] else ''
            response = (
                f"👌 **ВСП {r['vsp']}{city_part}**\n\n"
                f"🧑 **{r['fio']}**\n"
                f"📞 **Контакт:** {r['contact'] or 'не указан'}\n"
                f"📱 **Мобильный:** {r['mobile'] or 'не указан'}"
            )
        else:
            vsp_list = ", ".join(r['vsp'] for r in records)
            response = (
                f"📌 В городе **{records[0]['city']}** найдено несколько кураторов.\n"
                f"Пожалуйста, уточните **номер ВСП** (например, `{records[0]['vsp']}`).\n\n"
                f"Доступные ВСП: {vsp_list}"
            )
        await update.message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logging.error(f"Ошибка в handle_message: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.",
            parse_mode="Markdown"
        )

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Проверяем обязательные переменные
    if not TELEGRAM_TOKEN:
        logging.error("TELEGRAM_TOKEN не установлен")
        return
        
    if not SPREADSHEET_ID:
        logging.error("SPREADSHEET_ID не установлен")
        return
    
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Создаем и настраиваем приложение бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)
    
    print("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
