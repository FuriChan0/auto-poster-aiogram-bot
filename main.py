import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, InputMediaVideo
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

load_dotenv()

# ========================================================================
# ИНИЦИАЛИЗАЦИЯ
# ========================================================================
bot = Bot(
    token=os.getenv("BOT_TOKEN"),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Поддержка нескольких администраторов
ADMIN_IDS = [int(id_str.strip()) for id_str in os.getenv("ADMIN_IDS", "").split(",") if id_str.strip()]

CONFIG_FILE = "config.json"
POSTS_FILE = "posts.json"

# ========================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================================================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def load_config():
    if not os.path.exists(CONFIG_FILE):
        default = {
            "channel_id": os.getenv("CHANNEL_ID") or "",
            "publish_times": ["09:00", "13:00", "17:00", "21:00"],
            "standard_text": "<b>Стандартный</b> текст"
        }
        save_config(default)
        return default
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_posts():
    if not os.path.exists(POSTS_FILE):
        return []
    try:
        with open(POSTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_posts(posts):
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)

def get_next_publish_time(times, existing_posts):
    """Получаем следующее свободное время для публикации"""
    now = datetime.now()
    times = sorted([datetime.strptime(t, "%H:%M").time() for t in times])
    
    # Получаем все занятые времена
    busy_times = set()
    for post in existing_posts:
        try:
            post_time = datetime.strptime(post["time"], "%H:%M %d.%m.%Y")
            busy_times.add(post_time.strftime("%H:%M %d.%m.%Y"))
        except:
            continue
    
    # Проверяем следующие 7 дней
    for day in range(8):
        current_date = now.date() + timedelta(days=day)
        
        for time in times:
            publish_time = datetime.combine(current_date, time)
            
            # Пропускаем прошедшее время сегодня
            if day == 0 and publish_time < now:
                continue
                
            time_str = publish_time.strftime("%H:%M %d.%m.%Y")
            if time_str not in busy_times:
                return time_str
    
    # Если все времена заняты, возвращаем первое время через неделю
    next_week = now.date() + timedelta(days=7)
    return datetime.combine(next_week, times[0]).strftime("%H:%M %d.%m.%Y")

# ========================================================================
# СОСТОЯНИЯ
# ========================================================================
class PostState(StatesGroup):
    waiting_media = State()

class ConfigState(StatesGroup):
    waiting_channel = State()
    waiting_times = State()
    waiting_text = State()

class ViewPostsState(StatesGroup):
    viewing = State()

# ========================================================================
# КЛАВИАТУРЫ
# ========================================================================
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отложить посты в канал ⌛")],
        [KeyboardButton(text="Запланированные публикации 📝")],
        [KeyboardButton(text="Настройка ⚙️")]
    ],
    resize_keyboard=True
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Закончить ✅")]],
    resize_keyboard=True
)

config_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Изменить канал")],
        [KeyboardButton(text="Изменить время публикаций")],
        [KeyboardButton(text="Изменить текст публикации")],
        [KeyboardButton(text="Назад в меню")]
    ],
    resize_keyboard=True
)

view_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="◀️ Предыдущая"), KeyboardButton(text="Следующая ▶️")],
        [KeyboardButton(text="Отменить ❌"), KeyboardButton(text="Готово ✅")]
    ],
    resize_keyboard=True
)

# ========================================================================
# ХЕНДЛЕРЫ
# ========================================================================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await message.answer("Доступ разрешен! Добро пожаловать :)", reply_markup=main_kb)

@dp.message(F.text == "Отложить посты в канал ⌛")
async def schedule_mode(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    config = load_config()
    if not config.get("channel_id"):
        await message.answer("Сначала настройте канал в настройках!")
        return
    
    posts = load_posts()
    next_time = get_next_publish_time(config["publish_times"], posts)
    
    # Форматируем время для отображения
    next_time_obj = datetime.strptime(next_time, "%H:%M %d.%m.%Y")
    time_str = next_time_obj.strftime("%H:%M")
    day_str = next_time_obj.strftime("%d.%m.%Y")
    
    await state.set_state(PostState.waiting_media)
    await message.answer(
        f"⏰ Планирую пост на {time_str} {day_str}.\nОтправьте фото/видео/альбом (необходимо после альбома отправить любое текстовое сообщение).",
        reply_markup=cancel_kb
    )

@dp.message(PostState.waiting_media, F.text == "Закончить ✅")
async def finish_schedule(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await state.clear()
    await message.answer("Режим отложки завершён ✅", reply_markup=main_kb)

# Переменная для хранения данных об альбомах
albums_data = {}

@dp.message(PostState.waiting_media, F.media_group_id)
async def handle_album_start(message: types.Message, state: FSMContext):
    """Начало получения альбома"""
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    media_group_id = message.media_group_id
    
    if media_group_id not in albums_data:
        albums_data[media_group_id] = {
            "media": [],
            "caption": message.caption or "",
            "created_at": datetime.now(),
            "user_id": message.from_user.id
        }
    
    # Добавляем медиа в альбом
    if message.photo:
        albums_data[media_group_id]["media"].append({
            "kind": "photo",
            "file_id": message.photo[-1].file_id
        })
    elif message.video:
        albums_data[media_group_id]["media"].append({
            "kind": "video", 
            "file_id": message.video.file_id
        })
    
    # Ждем немного, чтобы получить все медиа из альбома
    await asyncio.sleep(1)

@dp.message(PostState.waiting_media, F.content_type.in_({"photo", "video"}))
async def handle_single_media(message: types.Message, state: FSMContext):
    """Обработчик одиночных медиа"""
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    # Если это часть альбома, пропускаем обработку как одиночное медиа
    if message.media_group_id:
        return
    
    config = load_config()
    posts = load_posts()
    
    publish_time = get_next_publish_time(config["publish_times"], posts)
    
    post = {
        "time": publish_time,
        "type": "single",
        "media": [{
            "kind": "photo" if message.content_type == "photo" else "video",
            "file_id": message.photo[-1].file_id if message.content_type == "photo" else message.video.file_id
        }],
        "caption": (message.caption or "") + "\n\n" + config["standard_text"]
    }
    
    posts.append(post)
    save_posts(posts)
    
    # Форматируем время для отображения
    publish_time_obj = datetime.strptime(publish_time, "%H:%M %d.%m.%Y")
    time_str = publish_time_obj.strftime("%H:%M")
    day_str = publish_time_obj.strftime("%d.%m.%Y")
    
    next_time = get_next_publish_time(config["publish_times"], posts)
    next_time_obj = datetime.strptime(next_time, "%H:%M %d.%m.%Y")
    next_time_str = next_time_obj.strftime("%H:%M %d.%m.%Y")
    
    await message.answer(
        f"✅ Пост запланирован на {time_str} {day_str}\n"
        f"⏰ Ожидаю пост на следующее доступное время: {next_time_str}",
        reply_markup=cancel_kb
    )

@dp.message(PostState.waiting_media)
async def handle_text_or_album_completion(message: types.Message, state: FSMContext):
    """Обработчик текстовых сообщений и завершения альбомов"""
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    # Сначала проверяем, есть ли необработанные альбомы для этого пользователя
    current_time = datetime.now()
    user_albums = {k: v for k, v in albums_data.items() if v["user_id"] == message.from_user.id}
    
    for media_group_id, album_data in list(user_albums.items()):
        # Проверяем, прошло ли достаточно времени с момента создания альбома
        if (current_time - album_data["created_at"]).total_seconds() > 2 and album_data["media"]:
            # Обрабатываем альбом
            config = load_config()
            posts = load_posts()
            
            publish_time = get_next_publish_time(config["publish_times"], posts)
            
            post = {
                "time": publish_time,
                "type": "album",
                "media": album_data["media"],
                "caption": (album_data["caption"] or "") + "\n\n" + config["standard_text"]
            }
            
            posts.append(post)
            save_posts(posts)
            
            # Форматируем время для отображения
            publish_time_obj = datetime.strptime(publish_time, "%H:%M %d.%m.%Y")
            time_str = publish_time_obj.strftime("%H:%M")
            day_str = publish_time_obj.strftime("%d.%m.%Y")
            
            next_time = get_next_publish_time(config["publish_times"], posts)
            next_time_obj = datetime.strptime(next_time, "%H:%M %d.%m.%Y")
            next_time_str = next_time_obj.strftime("%H:%M %d.%m.%Y")
            
            await message.answer(
                f"✅ Альбом ({len(album_data['media'])} медиа) запланирован на {time_str} {day_str}\n"
                f"⏰ Ожидаю пост на следующее доступное время: {next_time_str}",
                reply_markup=cancel_kb
            )
            
            # Удаляем обработанный альбом
            del albums_data[media_group_id]
            return
    
    # Если это просто текстовое сообщение
    if message.text and not message.media_group_id:
        config = load_config()
        posts = load_posts()
        
        publish_time = get_next_publish_time(config["publish_times"], posts)
        
        post = {
            "time": publish_time,
            "type": "text",
            "text": message.text + "\n\n" + config["standard_text"]
        }
        
        posts.append(post)
        save_posts(posts)
        
        # Форматируем время для отображения
        publish_time_obj = datetime.strptime(publish_time, "%H:%M %d.%m.%Y")
        time_str = publish_time_obj.strftime("%H:%M")
        day_str = publish_time_obj.strftime("%d.%m.%Y")
        
        next_time = get_next_publish_time(config["publish_times"], posts)
        next_time_obj = datetime.strptime(next_time, "%H:%M %d.%m.%Y")
        next_time_str = next_time_obj.strftime("%H:%M %d.%m.%Y")
        
        await message.answer(
            f"✅ Текст запланирован на {time_str} {day_str}\n"
            f"⏰ Ожидаю пост на следующее доступное время: {next_time_str}",
            reply_markup=cancel_kb
        )

@dp.message(F.text == "Запланированные публикации 📝")
async def list_posts(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    posts = load_posts()
    if not posts:
        return await message.answer("Нет запланированных постов.")
    
    await state.set_state(ViewPostsState.viewing)
    await state.update_data(index=0)
    await show_post(message.chat.id, 0)

@dp.message(ViewPostsState.viewing, F.text == "Следующая ▶️")
async def next_post(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    data = await state.get_data()
    idx = min(len(load_posts()) - 1, data.get("index", 0) + 1)
    await state.update_data(index=idx)
    await show_post(message.chat.id, idx)

@dp.message(ViewPostsState.viewing, F.text == "◀️ Предыдущая")
async def prev_post(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    data = await state.get_data()
    idx = max(0, data.get("index", 0) - 1)
    await state.update_data(index=idx)
    await show_post(message.chat.id, idx)

@dp.message(ViewPostsState.viewing, F.text == "Отменить ❌")
async def delete_post(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    data = await state.get_data()
    idx = data.get("index", 0)
    posts = load_posts()
    
    if 0 <= idx < len(posts):
        posts.pop(idx)
        save_posts(posts)
        
        if not posts:
            await state.clear()
            return await message.answer("Все посты удалены.", reply_markup=main_kb)
        
        idx = max(0, idx - 1)
        await state.update_data(index=idx)
        await show_post(message.chat.id, idx)

@dp.message(ViewPostsState.viewing, F.text == "Готово ✅")
async def finish_view(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await state.clear()
    await message.answer("Возврат в меню ✅", reply_markup=main_kb)

async def show_post(chat_id: int, idx: int):
    posts = load_posts()
    if idx >= len(posts):
        return
    
    post = posts[idx]
    await bot.send_message(chat_id, f"Пост на {post['time']}:")
    
    if post["type"] == "single":
        media = post["media"][0]
        if media["kind"] == "photo":
            await bot.send_photo(chat_id, media["file_id"], caption=post["caption"], parse_mode=ParseMode.HTML)
        else:
            await bot.send_video(chat_id, media["file_id"], caption=post["caption"], parse_mode=ParseMode.HTML)
    elif post["type"] == "album":
        media_group = []
        for i, m in enumerate(post["media"]):
            if m["kind"] == "photo":
                media_group.append(InputMediaPhoto(
                    media=m["file_id"], 
                    caption=post["caption"] if i == 0 else None,
                    parse_mode=ParseMode.HTML
                ))
            else:
                media_group.append(InputMediaVideo(
                    media=m["file_id"], 
                    caption=post["caption"] if i == 0 else None,
                    parse_mode=ParseMode.HTML
                ))
        await bot.send_media_group(chat_id, media_group)
    elif post["type"] == "text":
        await bot.send_message(chat_id, post["text"], parse_mode=ParseMode.HTML)
    
    await bot.send_message(chat_id, f"Просмотр {idx+1}/{len(posts)}", reply_markup=view_kb)

@dp.message(F.text == "Настройка ⚙️")
async def settings_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    config = load_config()
    await message.answer(
        f"<b>Текущие настройки:</b>\n"
        f"<b>Канал:</b> {config['channel_id']}\n"
        f"<b>Время:</b> {', '.join(config['publish_times'])}\n"
        f"<b>Текст:</b> {config['standard_text']}",
        reply_markup=config_kb
    )

@dp.message(F.text == "Изменить канал")
async def change_channel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await state.set_state(ConfigState.waiting_channel)
    await message.answer("Отправьте новый ID канала:")

@dp.message(ConfigState.waiting_channel)
async def set_channel(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    config = load_config()
    config["channel_id"] = message.text.strip()
    save_config(config)
    await state.clear()
    await message.answer("✅ Канал изменён!", reply_markup=config_kb)

@dp.message(F.text == "Изменить время публикаций")
async def change_times(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await state.set_state(ConfigState.waiting_times)
    await message.answer("Отправьте список времени в формате HH:MM через запятую (например: <code>09:00, 13:00, 17:00</code>)")

@dp.message(ConfigState.waiting_times)
async def set_times(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    try:
        times = [t.strip() for t in message.text.split(",")]
        # Проверяем формат времени
        for time in times:
            datetime.strptime(time, "%H:%M")
        
        config = load_config()
        config["publish_times"] = times
        save_config(config)
        await state.clear()
        await message.answer("✅ Время публикаций изменено!", reply_markup=config_kb)
    except ValueError:
        await message.answer("❌ Неверный формат времени. Используйте HH:MM")

@dp.message(F.text == "Изменить текст публикации")
async def change_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await state.set_state(ConfigState.waiting_text)
    await message.answer("Отправьте новый текст публикации (поддерживаются HTML теги):")

@dp.message(ConfigState.waiting_text)
async def set_text(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    config = load_config()
    config["standard_text"] = message.text
    save_config(config)
    await state.clear()
    await message.answer("✅ Текст изменён!", reply_markup=config_kb)

@dp.message(F.text == "Назад в меню")
async def back_to_menu(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("Доступ запрещен!")
    
    await state.clear()
    await message.answer("Возврат в главное меню ✅", reply_markup=main_kb)

# ========================================================================
# ПЛАНИРОВЩИК
# ========================================================================
async def scheduler_task():
    """Задача для планировщика публикаций"""
    while True:
        try:
            now = datetime.now()
            posts = load_posts()
            config = load_config()
            
            if not config.get("channel_id"):
                await asyncio.sleep(60)
                continue
                
            for post in posts[:]:
                try:
                    post_time = datetime.strptime(post["time"], "%H:%M %d.%m.%Y")
                    
                    # Если время публикации наступило
                    if now >= post_time and (now - post_time).total_seconds() < 60:
                        try:
                            if post["type"] == "single":
                                media = post["media"][0]
                                if media["kind"] == "photo":
                                    await bot.send_photo(
                                        config["channel_id"], 
                                        media["file_id"], 
                                        caption=post["caption"],
                                        parse_mode=ParseMode.HTML
                                    )
                                else:
                                    await bot.send_video(
                                        config["channel_id"], 
                                        media["file_id"], 
                                        caption=post["caption"],
                                        parse_mode=ParseMode.HTML
                                    )
                            elif post["type"] == "album":
                                media_group = []
                                for i, m in enumerate(post["media"]):
                                    if m["kind"] == "photo":
                                        media_group.append(InputMediaPhoto(
                                            media=m["file_id"], 
                                            caption=post["caption"] if i == 0 else None,
                                            parse_mode=ParseMode.HTML
                                        ))
                                    else:
                                        media_group.append(InputMediaVideo(
                                            media=m["file_id"], 
                                            caption=post["caption"] if i == 0 else None,
                                            parse_mode=ParseMode.HTML
                                        ))
                                await bot.send_media_group(config["channel_id"], media_group)
                            elif post["type"] == "text":
                                await bot.send_message(
                                    config["channel_id"],
                                    post["text"],
                                    parse_mode=ParseMode.HTML
                                )
                            
                            # Удаляем опубликованный пост
                            posts.remove(post)
                            save_posts(posts)
                            
                        except Exception as e:
                            logging.error(f"Ошибка публикации: {e}")
                            
                except Exception as e:
                    logging.error(f"Ошибка обработки поста: {e}")
                    
            await asyncio.sleep(30)  # Проверяем каждые 30 секунд
            
        except Exception as e:
            logging.error(f"Ошибка в планировщике: {e}")
            await asyncio.sleep(60)

# ========================================================================
# ЗАПУСК
# ========================================================================
async def main():
    """Основная функция"""
    asyncio.create_task(scheduler_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    asyncio.run(main())