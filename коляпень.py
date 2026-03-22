
import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder # Импортируем сборщик кнопок

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# ================= КОНФИГ (ЗАПОЛНИ СВОЕ) =================
TOKEN = "8608385024:AAEAomngZR-7bGPjQuxVfgmk0Qz13s6IOLs" 
ADMIN_ID = 5000488732
# =========================================================

# Подключение к базе данных
db = sqlite3.connect("products.db")
sql = db.cursor()

def init_db():
    sql.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        name TEXT,
        price_1_day INTEGER, price_3_days INTEGER, price_7_days INTEGER, price_30_days INTEGER
    )""")
    sql.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)")
    sql.execute("CREATE TABLE IF NOT EXISTS admin_users (user_id INTEGER PRIMARY KEY)")
    sql.execute("INSERT OR IGNORE INTO admin_users (user_id) VALUES (?)", (ADMIN_ID,))
    
    sql.execute("""CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        duration_days INTEGER,
        key_value TEXT UNIQUE,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )""")
    
    sql.execute("""CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        product_name TEXT,
        key_value TEXT,
        duration_days INTEGER,
        buy_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    db.commit()

init_db()

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- Состояния ---
class AddProduct(StatesGroup):
    # Убрали State для category, теперь он выбирается кнопкой, а не текстом
    category = State() # Оставил, но для хранения данных, не для текстового ввода
    name = State()
    p1 = State(); p3 = State(); p7 = State(); p30 = State()

class AddKey(StatesGroup):
    product_id = State(); duration_days = State(); key_value = State()

class UserPanelStates(StatesGroup):
    manage_balance_id = State(); manage_balance_amount = State()

class AdminStates(StatesGroup):
    add_admin = State()


# --- Вспомогательные функции ---
def is_admin(user_id):
    sql.execute("SELECT 1 FROM admin_users WHERE user_id = ?", (user_id,))
    return sql.fetchone() is not None

def main_menu_kb():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 Каталог", callback_data="catalog")],
        [types.InlineKeyboardButton(text="👤 Профиль", callback_data="profile"), 
         types.InlineKeyboardButton(text="🔑 Мои заказы", callback_data="my_orders")],
        [types.InlineKeyboardButton(text="💰 Баланс", callback_data="balance")]
    ])

async def return_to_admin_panel(entity):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_product_start")],
        [types.InlineKeyboardButton(text="🔑 Добавить ключи", callback_data="add_keys_start")],
        [types.InlineKeyboardButton(text="🗑️ Удалить товар", callback_data="delete_products_list")],
        [types.InlineKeyboardButton(text="👥 Упр. пользователями", callback_data="manage_users_menu")],
        [types.InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]
    ])
    if isinstance(entity, types.CallbackQuery): await entity.message.edit_text("⚙️ Админка", reply_markup=kb)
    else: await entity.answer("⚙️ Админка", reply_markup=kb)

# --- Обработчики ---

@dp.message(Command("start"))
async def start(message: types.Message):
    sql.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    db.commit()
    await message.answer("Добро пожаловать!", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu")
async def show_menu(call: types.CallbackQuery):
    await call.message.edit_text("Главное меню:", reply_markup=main_menu_kb())

@dp.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    sql.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    res = sql.fetchone()
    balance = res[0] if res else 0
    text = (f"<b>👤 Профиль</b>\n\n"
            f"🆔 Ваш ID: <code>{call.from_user.id}</code>\n"
            f"💰 Баланс: {balance}₽")
    await call.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")

# --- Мои заказы ---
@dp.callback_query(F.data == "my_orders")
async def my_orders(call: types.CallbackQuery):
    sql.execute("SELECT id, product_name, key_value, duration_days, buy_date FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 10", (call.from_user.id,))
    rows = sql.fetchall()
    
    if not rows:
        return await call.message.edit_text("У вас пока нет покупок.", reply_markup=main_menu_kb())

    text = "<b>📂 Ваши последние заказы:</b>\n\n"
    builder = InlineKeyboardBuilder()
    
    for r in rows:
        text += f"📦 {r[1]} ({r[3]} дн.)\n🔑 <code>{r[2]}</code>\n📅 {r[4]}\n\n"
        builder.row(types.InlineKeyboardButton(text=f"🗑️ Удалить заказ №{r[0]} из истории", callback_data=f"delete_order_{r[0]}"))
    
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu"))
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("delete_order_"))
async def delete_order(call: types.CallbackQuery):
    order_id = int(call.data.split("_")[2])
    sql.execute("DELETE FROM purchases WHERE id=? AND user_id=?", (order_id, call.from_user.id)) # Добавил проверку user_id
    db.commit()
    await call.answer("Заказ удален из истории.")
    await my_orders(call) # Просто вызываем заново обновление списка

@dp.callback_query(F.data == "catalog")
async def catalog(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Android", callback_data="category_android")],
        [types.InlineKeyboardButton(text="iOS", callback_data="category_ios")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")]
    ])
    await call.message.edit_text("Выберите категорию:", reply_markup=kb)

@dp.callback_query(F.data.startswith("category_"))
async def show_products(call: types.CallbackQuery):
    category = call.data.split("_")[1]
    sql.execute("SELECT id, name FROM products WHERE LOWER(category)=?", (category,))
    products = sql.fetchall()
    if not products:
        return await call.message.edit_text("Пусто.", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data="catalog")]]))
    
    kb = [[types.InlineKeyboardButton(text=f"{p[1]}", callback_data=f"item_{p[0]}")] for p in products]
    kb.append([types.InlineKeyboardButton(text="⬅️ Назад", callback_data="catalog")])
    await call.message.edit_text("Выберите товар:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("item_"))
async def item_details(call: types.CallbackQuery):
    pid = int(call.data.split("_")[1])
    sql.execute("SELECT * FROM products WHERE id=?", (pid,))
    item = sql.fetchone()

    builder = InlineKeyboardBuilder()
    durations = {1: item[3], 3: item[4], 7: item[5], 30: item[6]}
    
    for days, price_value in durations.items():
        try:
            # Преобразуем цену в число. Если не число или <= 0, не показываем кнопку.
            price_int = int(price_value)
            if price_int > 0:
                sql.execute("SELECT COUNT(*) FROM keys WHERE product_id=? AND duration_days=?", (pid, days))
                count = sql.fetchone()[0]
                status_text = f"({count} шт.)" if count > 0 else "(Нет в наличии)"
                builder.row(types.InlineKeyboardButton(text=f"{days} дн. — {price_int}₽ {status_text}", callback_data=f"buy_{pid}_{days}"))
        except (ValueError, TypeError):
            # Если цена невалидна, просто пропускаем этот срок
            logging.warning(f"Некорректная цена для товара {item[2]} на {days} дней: {price_value}. Кнопка не будет показана.")
            continue
            
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="catalog"))
    
    await call.message.edit_text(f"🛒 {item[2]}\nВыберите срок:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("buy_"))
async def buy(call: types.CallbackQuery):
    pid, days = map(int, call.data.split("_")[1:])
    sql.execute("SELECT * FROM products WHERE id=?", (pid,))
    item = sql.fetchone()
    
    # Теперь безопасное получение цены, с учетом возможных ошибок в базе
    try:
        price = int({1: item[3], 3: item[4], 7: item[5], 30: item[6]}[days])
    except (ValueError, TypeError):
        return await call.answer("Ошибка в цене товара. Свяжитесь с админом.", show_alert=True)

    sql.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    current_balance = sql.fetchone()[0]
    if current_balance < price:
        return await call.answer("Недостаточно средств!", show_alert=True)

    sql.execute("SELECT id, key_value FROM keys WHERE product_id=? AND duration_days=? LIMIT 1", (pid, days))
    key_data = sql.fetchone()
    if not key_data:
        return await call.answer("Нет ключей на этот срок.", show_alert=True)

    sql.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (price, call.from_user.id))
    sql.execute("DELETE FROM keys WHERE id=?", (key_data[0],))
    sql.execute("INSERT INTO purchases (user_id, product_name, key_value, duration_days) VALUES (?,?,?,?)", 
                (call.from_user.id, item[2], key_data[1], days))
    db.commit()

    await call.message.edit_text(f"✅ Успешно!\n\n📦 {item[2]}\n⏳ {days} дн.\n🔑 Ключ: <code>{key_data[1]}</code>", 
                                 reply_markup=main_menu_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "balance")
async def balance_info(call: types.CallbackQuery):
    sql.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    b = sql.fetchone()[0]
    await call.message.edit_text(f"💰 Ваш баланс: {b}₽\nДля пополнения напишите админу.", reply_markup=main_menu_kb())

# --- Админка ---

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if is_admin(message.from_user.id): await return_to_admin_panel(message)
    else: await message.answer("У вас нет доступа к админ-панели.")


@dp.callback_query(F.data == "manage_users_menu")
async def manage_users(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💰 Пополнить/Изменить баланс", callback_data="add_balance_user_start")],
        [types.InlineKeyboardButton(text="📋 Список всех балансов", callback_data="list_all_balances")],
        [types.InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin_start")],
        [types.InlineKeyboardButton(text="📋 Список админов", callback_data="list_admins")],
        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin")]
    ])
    await call.message.edit_text("👥 Управление пользователями", reply_markup=kb)

@dp.callback_query(F.data == "list_all_balances")
async def list_balances(call: types.CallbackQuery):
    sql.execute("SELECT user_id, balance FROM users")
    users = sql.fetchall()
    text = "<b>💰 Балансы пользователей:</b>\n\n"
    if not users:
        text += "Пользователей пока нет."
    else:
        for u in users:
            text += f"👤 <code>{u[0]}</code> — {u[1]}₽\n"
    await call.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_users_menu")]]), parse_mode="HTML")

# --- Список админов ---
@dp.callback_query(F.data == "list_admins")
async def list_admins(call: types.CallbackQuery):
    sql.execute("SELECT user_id FROM admin_users WHERE user_id != ?", (ADMIN_ID,))
    admin_ids = sql.fetchall()
    
    builder = InlineKeyboardBuilder()
    if not admin_ids:
        text = "Список других администраторов пуст."
    else:
        text = "<b>📋 Список администраторов (кроме тебя):</b>\n\n"
        for admin_id_tuple in admin_ids:
            admin_id = admin_id_tuple[0]
            text += f"👑 <code>{admin_id}</code>\n"
            builder.row(types.InlineKeyboardButton(text=f"🗑️ Удалить {admin_id}", callback_data=f"delete_admin_{admin_id}"))
    
    builder.row(types.InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_users_menu"))
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("delete_admin_"))
async def delete_admin(call: types.CallbackQuery):
    admin_id_to_delete = int(call.data.split("_")[2])
    
    # Только ты (главный админ) можешь удалять других
    if call.from_user.id == ADMIN_ID:
        sql.execute("DELETE FROM admin_users WHERE user_id=?", (admin_id_to_delete,))
        db.commit()
        await call.answer(f"Администратор {admin_id_to_delete} удален.")
        await list_admins(call) # Обновляем список админов
    else:
        await call.answer("У вас нет прав для удаления администраторов.", show_alert=True)


@dp.callback_query(F.data == "add_balance_user_start")
async def add_bal_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Введите ID пользователя:")
    await state.set_state(UserPanelStates.manage_balance_id)

@dp.message(UserPanelStates.manage_balance_id)
async def add_bal_id(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Введите сумму (чтобы убавить, пишите со знаком минус, например -100):")
    await state.set_state(UserPanelStates.manage_balance_amount)

@dp.message(UserPanelStates.manage_balance_amount)
async def add_bal_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        amount = int(message.text)
        user_id_to_manage = int(data['uid'])
        sql.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id_to_manage))
        db.commit()
        await message.answer(f"✅ Баланс пользователя {user_id_to_manage} обновлен на {amount}₽.")
    except ValueError:
        await message.answer("❌ Сумма или ID пользователя должны быть числом.")
    except Exception as e:
        logging.error(f"Ошибка при обновлении баланса: {e}")
        await message.answer("Произошла ошибка при обновлении баланса.")
    finally:
        await state.clear()
        await return_to_admin_panel(message)

@dp.callback_query(F.data == "add_admin_start")
async def add_admin_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("Введите ID пользователя для добавления в админы:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="⬅️ Назад", callback_data="manage_users_menu")]]))
    await state.set_state(AdminStates.add_admin) # Правильное состояние для админ-панели

@dp.message(AdminStates.add_admin)
async def add_admin_handler(message: types.Message, state: FSMContext):
    try:
        new_admin_id = int(message.text)
        if message.from_user.id != ADMIN_ID: # Только основной админ может добавлять
             await message.answer("У вас нет прав для добавления администраторов.")
             return
        
        sql.execute("INSERT OR IGNORE INTO admin_users (user_id) VALUES (?)", (new_admin_id,))
        db.commit()
        await message.answer(f"✅ Пользователь <code>{new_admin_id}</code> добавлен в администраторы.", parse_mode="HTML")
    except ValueError:
        await message.answer("❌ ID пользователя должен быть числом. Попробуйте снова.")
    except Exception as e:
        logging.error(f"Ошибка при добавлении админа: {e}")
        await message.answer("Произошла ошибка при добавлении администратора.")
    finally:
        await state.clear()
        await return_to_admin_panel(message)

# --- Обработчики добавления товаров (ИСПРАВЛЕН ВЫБОР КАТЕГОРИИ) ---
@dp.callback_query(F.data == "add_product_start")
async def add_product_start(call: types.CallbackQuery):
    await call.message.edit_text("Выберите категорию товара:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Android", callback_data="add_product_cat_android")],
        [types.InlineKeyboardButton(text="iOS", callback_data="add_product_cat_ios")]
    ]))
    # После выбора категории, состояние будет изменено в add_product_cat

@dp.callback_query(F.data.startswith("add_product_cat_"))
async def add_product_cat(call: types.CallbackQuery, state: FSMContext):
    category = call.data.split("_")[3] # Получаем "android" или "ios"
    await state.update_data(category=category)
    await call.message.answer(f"Выбрана категория: {category.capitalize()}\nТеперь введите название товара:")
    await state.set_state(AddProduct.name)

@dp.message(AddProduct.name)
async def add_p_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите цену за 1 день (число, 0 если не продаете):")
    await state.set_state(AddProduct.p1)

# Добавлена проверка на число для всех цен
@dp.message(AddProduct.p1)
async def add_p_p1(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): 
        return await message.answer("❌ Цена должна быть числом! Введите 0, если не хотите указывать цену за этот срок.")
    await state.update_data(p1=message.text)
    await message.answer("Введите цену за 3 дня (число, 0 если не продаете):")
    await state.set_state(AddProduct.p3)

@dp.message(AddProduct.p3)
async def add_p_p3(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): 
        return await message.answer("❌ Цена должна быть числом! Введите 0, если не хотите указывать цену за этот срок.")
    await state.update_data(p3=message.text)
    await message.answer("Введите цену за 7 дней (число, 0 если не продаете):")
    await state.set_state(AddProduct.p7)

@dp.message(AddProduct.p7)
async def add_p_p7(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): 
        return await message.answer("❌ Цена должна быть числом! Введите 0, если не хотите указывать цену за этот срок.")
    await state.update_data(p7=message.text)
    await message.answer("Введите цену за 30 дней (число, 0 если не продаете):")
    await state.set_state(AddProduct.p30)

@dp.message(AddProduct.p30)
async def add_p_fin(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): 
        return await message.answer("❌ Цена должна быть числом! Введите 0, если не хотите указывать цену за этот срок.")
    
    d = await state.get_data()
    sql.execute("INSERT INTO products (category, name, price_1_day, price_3_days, price_7_days, price_30_days) VALUES (?,?,?,?,?,?)",
                (d['category'], d['name'], d['p1'], d['p3'], d['p7'], message.text))
    db.commit()
    await message.answer("✅ Товар добавлен.")
    await state.clear()
    await return_to_admin_panel(message)


# --- Обработчики добавления ключей (без изменений) ---
@dp.callback_query(F.data == "add_keys_start")
async def add_k(call: types.CallbackQuery):
    sql.execute("SELECT id, name FROM products")
    items = sql.fetchall()
    builder = InlineKeyboardBuilder()
    if not items:
        builder.row(types.InlineKeyboardButton(text="Сначала добавьте товары!", callback_data="admin"))
    else:
        for i in items: builder.row(types.InlineKeyboardButton(text=i[1], callback_data=f"sk_{i[0]}"))
    builder.row(types.In)
@dp.callback_query(F.data.startswith("delp_"))
async def delete_confirm(call: types.CallbackQuery):
    pid = int(call.data.split("_")[1])
    sql.execute("DELETE FROM products WHERE id=?", (pid,))
    sql.execute("DELETE FROM keys WHERE product_id=?", (pid,))
    db.commit()
    await call.answer("Товар и его ключи удалены.")
    await delete_list(call)


async def main():
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")