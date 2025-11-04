import logging
import re
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = os.environ.get('8459410209:AAEjnWq7LPdfX8Cgi8qVnHiPN9Tkn-QieFw')
SPREADSHEET_ID = os.environ.get('1dAPn19W8fxhkFw_tjEpuOJne91pU1Oyt97ycHSSlvbU')
RANGE_NAME = 'Data!A:E'

# Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = Credentials.from_service_account_file('credentials.json', scopes=SCOPES)
sheets_service = build('sheets', 'v4', credentials=creds)

# Загрузка данных
def load_data():
    result = sheets_service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=RANGE_NAME
    ).execute()
    values = result.get('values', [])
    vsp_map = {}
    city_map = {}

    for row in values[1:]:
        if len(row) >= 5:
            vsp = row[0].strip()
            fio = row[1].strip()
            contact = row[2].strip()
            mobile = row[3].strip()
            city = row[4].strip()
            if not vsp or not fio:
                continue
            record = {'vsp': vsp, 'fio': fio, 'contact': contact, 'mobile': mobile, 'city': city}
            vsp_map[vsp] = record
            if city:
                if city not in city_map:
                    city_map[city] = []
                city_map[city].append(record)
    return vsp_map, city_map

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
        "• Код ВСП — например, `8369/069`\n"
        "• Или город — например, `Салехард`\n\n"
        "Я найду куратора и контакты!",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vsp_map, city_map = load_data()
    text = update.message.text.strip()

    # Поиск по ВСП
    vsp_match = re.search(r'\b(\d{4}/\d{4})\b', text)
    if vsp_match:
        vsp = vsp_match.group(1)
        record = vsp_map.get(vsp)
        if record:
            city_part = f" г. {record['city']}" if record['city'] else ''
            response = (
                f"✅ **ВСП {vsp}{city_part}**\n\n"
                f"👤 **{record['fio']}**\n"
                f"📞 **Контакт:** {record['contact']}\n"
                f"📱 **Мобильный:** {record['mobile']}"
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
            "Попробуйте: *Салехард*, *8369/069*",
            parse_mode="Markdown"
        )
        return

    if len(records) == 1:
        r = records[0]
        response = (
            f"✅ **ВСП {r['vsp']} г. {r['city']}**\n\n"
            f"👤 **{r['fio']}**\n"
            f"📞 **Контакт:** {r['contact']}\n"
            f"📱 **Мобильный:** {r['mobile']}"
        )
    else:
        vsp_list = ", ".join(r['vsp'] for r in records)
        response = (
            f"📌 В городе **{records[0]['city']}** найдено несколько кураторов.\n"
            f"Пожалуйста, уточните **номер ВСП** (например, `{records[0]['vsp']}`).\n\n"
            f"Доступные ВСП: {vsp_list}"
        )
    await update.message.reply_text(response, parse_mode="Markdown")

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()