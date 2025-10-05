

import logging
import sqlite3
import os
from typing import Optional
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    LabeledPrice, Invoice
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters,
    ConversationHandler, PreCheckoutQueryHandler
)
import aiosqlite

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Настройки (заполни перед запуском) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN") or "REPLACE_WITH_YOUR_BOT_TOKEN"
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN") or "REPLACE_WITH_PROVIDER_TOKEN"
OWNER_ID = int(os.getenv("OWNER_ID") or 123456789)  # Telegram numeric id владельца

DB_PATH = "shop.db"

# ---------- Conversation states для добавления категории/товара ----------
(
    ADD_CAT_TITLE,
    ADD_PROD_CAT,
    ADD_PROD_TITLE,
    ADD_PROD_DESC,
    ADD_PROD_PRICE,
    ADD_PROD_PHOTO
) = range(6)

# ---------- Вспомогательные функции для работы с БД ----------
async def db_execute(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(query, params)
        await db.commit()

async def db_fetchone(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        row = await cur.fetchone()
        return row

async def db_fetchall(query: str, params: tuple = ()):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        rows = await cur.fetchall()
        return rows

# ---------- Команды владельца: добавить категорию ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я — бот-магазин.\n"
        "Доступные команды:\n"
        "/catalog — открыть каталог\n"
        "/myorders — посмотреть свои заказы (покупателя)\n\n"
        "Если вы владелец бота, используйте:\n"
        "/add_category — добавить категорию\n"
        "/add_product — добавить товар\n"
    )

# добавить категорию
async def add_category_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Команда доступна только владельцу.")
        return ConversationHandler.END
    await update.message.reply_text("Пришли название категории (например: «Телефоны»):")
    return ADD_CAT_TITLE

async def add_category_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    try:
        await db_execute("INSERT INTO categories (title) VALUES (?)", (title,))
        await update.message.reply_text(f"Категория '{title}' добавлена.")
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("Ошибка: возможно такая категория уже есть.")
    return ConversationHandler.END

# добавить продукт — шаги (владелец)
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Команда доступна только владельцу.")
        return ConversationHandler.END
    # получить категории
    rows = await db_fetchall("SELECT id, title FROM categories")
    if not rows:
        await update.message.reply_text("Сначала создайте хотя бы одну категорию (/add_category).")
        return ConversationHandler.END
    # клавиатура с категориями
    keyboard = [[InlineKeyboardButton(title, callback_data=f"cat_{cat_id}")] for cat_id, title in rows]
    await update.message.reply_text("Выберите категорию для товара:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_PROD_CAT

async def add_product_cat_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g., "cat_3"cat_id = int(data.split("_")[1])
    context.user_data["new_product"] = {"category_id": cat_id}
    await query.message.reply_text("Отправь название товара:")
    return ADD_PROD_TITLE

async def add_product_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    context.user_data["new_product"]["title"] = title
    await update.message.reply_text("Напиши описание товара:")
    return ADD_PROD_DESC

async def add_product_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    context.user_data["new_product"]["description"] = desc
    await update.message.reply_text("Укажи цену в рублях (например: 1499.50):")
    return ADD_PROD_PRICE

async def add_product_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", ".")
    try:
        price_float = float(text)
        # Telegram Invoices expect integer amount in smallest currency unit (kopecks)
        price_int = int(round(price_float * 100))
        context.user_data["new_product"]["price"] = price_int
        await update.message.reply_text("Пришли фотографию товара (можно отправить как фото).")
        return ADD_PROD_PHOTO
    except:
        await update.message.reply_text("Неправильный формат цены. Повтори ввод (например: 1499.50):")
        return ADD_PROD_PRICE

async def add_product_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # получить file_id (поддерживает photo или document)
    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("Отправь файл или фото товара.")
        return ADD_PROD_PHOTO

    p = context.user_data["new_product"]
    p["photo_file_id"] = file_id
    # сохранить в БД
    await db_execute(
        "INSERT INTO products (category_id, title, description, price, currency, photo_file_id) VALUES (?,?,?,?,?,?)",
        (p["category_id"], p["title"], p["description"], p["price"], "RUB", p["photo_file_id"])
    )
    await update.message.reply_text(f"Товар '{p['title']}' добавлен в категорию.")
    context.user_data.pop("new_product", None)
    return ConversationHandler.END

# просмотр каталога пользователем
async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await db_fetchall("SELECT id, title FROM categories")
    if not rows:
        await update.message.reply_text("Каталог пуст. Подождите, пока владелец добавит товары.")
        return
    keyboard = [[InlineKeyboardButton(title, callback_data=f"cat_view_{cat_id}")] for cat_id, title in rows]
    await update.message.reply_text("Категории:", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # cat_view_#
    cat_id = int(data.split("_")[-1])
    rows = await db_fetchall("SELECT id, title, price, currency, photo_file_id FROM products WHERE category_id = ?", (cat_id,))
    if not rows:
        await query.message.reply_text("В этой категории пока нет товаров.")
        return
    # показываем каждый товар с клавиатурой "Купить"
    for prod in rows:
        prod_id, title, price, currency, photo = prod
        # price is integer in kopecks
        rub = price / 100.0
        text = f"*{title}*\nЦена: {rub:.2f} {currency}"
        if photo:
            try:
                await context.bot.send_photo(chat_id=query.message.chat_id, photo=photo, caption=text, parse_mode="Markdown",
                                             reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Купить", callback_data=f"buy_{prod_id}")]]))
            except Exception as e:
                logger.exception(e)
                await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Купить", callback_data=f"buy_{prod_id}")]]))else:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Купить", callback_data=f"buy_{prod_id}")]]))

# начало процесса покупки — отправляем invoice
async def buy_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.split("_")[1])
    row = await db_fetchone("SELECT title, price, currency FROM products WHERE id = ?", (prod_id,))
    if not row:
        await query.message.reply_text("Товар не найден.")
        return
    title, price, currency = row
    # Telegram поддерживает LabeledPrice: в целых "копейках"
    prices = [LabeledPrice(label=title, amount=price)]
    payload = f"purchase_{prod_id}_{query.from_user.id}"
    # отправляем invoice
    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title=title,
        description=f"Покупка товара {title}",
        provider_token=PROVIDER_TOKEN,
        currency=currency,
        prices=prices,
        payload=payload,
        start_parameter=f"buy-{prod_id}"
    )

# PreCheckout — подтверждение платежа (обязательный handler)
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    # Здесь можно проверить payload и цену на сервере (защита от подделки)
    await query.answer(ok=True)

# successful payment
async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # update.message.successful_payment содержит детали
    user = update.message.from_user
    success = update.message.successful_payment
    payload = success.invoice_payload  # мы указывали payload
    provider_charge_id = success.provider_payment_charge_id
    total_amount = success.total_amount  # в копейках
    currency = success.currency

    # извлечь prod_id из payload
    # payload формат: purchase_{prod_id}_{buyer_tg_id}
    try:
        parts = payload.split("_")
        prod_id = int(parts[1])
    except Exception:
        prod_id = None

    # сохранить заказ в БД
    await db_execute(
        "INSERT INTO orders (user_tg_id, product_id, amount, currency, status, provider_payment_charge_id) VALUES (?,?,?,?,?,?)",
        (user.id, prod_id, total_amount, currency, "paid", provider_charge_id)
    )

    # уведомление покупателю
    await update.message.reply_text("Оплата прошла успешно! Спасибо за покупку. Владелец скоро свяжется с вами.")

    # уведомление владельцу — найти продукт и составить сообщение
    prod = await db_fetchone("SELECT title FROM products WHERE id = ?", (prod_id,))
    prod_title = prod[0] if prod else "неизвестный товар"
    order_info = (
        f"Новый заказ!\n\n"
        f"Покупатель: {user.full_name} (@{user.username} | id {user.id})\n"
        f"Товар: {prod_title}\n"
        f"Сумма: {total_amount/100:.2f} {currency}\n"
        f"Provider charge id: {provider_charge_id}\n"
    )
    # отправляем владельцу (личное сообщение)
    try:
        await context.bot.send_message(chat_id=OWNER_ID, text=order_info)
    except Exception as e:
        logger.exception(e)

# командa посмотреть свои заказы (покупатель)
async def myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = await db_fetchall("SELECT orders.id, products.title, orders.amount, orders.currency, orders.status, orders.created_at FROM orders JOIN products ON orders.product_id = products.id WHERE orders.user_tg_id = ? ORDER BY orders.created_at DESC", (user_id,))
    if not rows:
        await update.message.reply_text("У вас пока нет заказов.")
        return
    texts = []
    for r in rows:
        oid, title, amount, cur, status, created_at = r
        texts.append(f"#{oid} {title} — {amount/100:.2f} {cur} — {status} — {created_at}")
    await update.message.reply_text("\n".join(texts))

# списки для простоты (отобразить продукты владельцу)
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Только владельцу.")
        return
    rows = await db_fetchall("SELECT id, title, price, currency FROM products ORDER BY id DESC")
    if not rows:
        await update.message.reply_text("Нет товаров.")
        return
    texts = [f"{rid}. {title} — {price/100:.2f} {cur}" for (rid, title, price, cur) in rows]
    await update.message.reply_text("\n".join(texts))

# ---------- Регистрация handlers и запуск ----------
def main():
    # проверка настроек
    if BOT_TOKEN.startswith("REPLACE") or PROVIDER_TOKEN.startswith("REPLACE"):
        logger.warning("Установите BOT_TOKEN и PROVIDER_TOKEN в переменные среды или прямо в коде.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # базовые команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catalog", catalog))
    app.add_handler(CommandHandler("myorders", myorders))
    app.add_handler(CommandHandler("list_products", list_products))

    # owner: add_category
    addcat_conv = ConversationHandler(
        entry_points=[CommandHandler("add_category", add_category_start)],
        states={
            ADD_CAT_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_category_title)]
        },
        fallbacks=[]
    )
    app.add_handler(addcat_conv)

    # owner: add_product conversation
    addprod_conv = ConversationHandler(
        entry_points=[CommandHandler("add_product", add_product_start)],
        states={
            ADD_PROD_CAT: [CallbackQueryHandler(add_product_cat_chosen, pattern=r"^cat_\d+$")],
            ADD_PROD_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_title)],
            ADD_PROD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_desc)],
            ADD_PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_product_price)],
            ADD_PROD_PHOTO: [MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, add_product_photo)]
        },
        fallbacks=[]
    )
    app.add_handler(addprod_conv)

    # callbacks для просмотра категории / покупок
    app.add_handler(CallbackQueryHandler(view_category, pattern=r"^cat_view_\d+$"))
    app.add_handler(CallbackQueryHandler(buy_product, pattern=r"^buy_\d+$"))

    # платёжные обработчики
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

    # запускаем polling
    logger.info("Запуск бота...")
    app.run_polling()

if name == "__main__":
    main()