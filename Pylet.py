import telebot
from telebot import types
import random
import threading
import time

TOKEN = '6999677790:AAEK39B36J8q5-yMeb98RF-OY_mdj9Qoem4'  # <-- Замените на токен вашего бота
bot = telebot.TeleBot(TOKEN)

CHAMBERS = 6
MAX_HP = 10
MAX_PLAYERS = 8
JOIN_TIME = 30  # секунд на подключение в мульти

# --- Хранилища игр ---
bot_games = {}      # user_id -> игра с ботом
multi_games = {}    # chat_id -> мульти игра


def create_magazine():
    bullets = ['боевой'] + ['холостой'] * (CHAMBERS - 1)
    random.shuffle(bullets)
    return bullets


def get_bullet(magazine):
    if not magazine:
        magazine.extend(create_magazine())
    return magazine.pop()


def mention(user):
    if user.username:
        return f"@{user.username}"
    else:
        return user.first_name or "Игрок"


# --- Главное меню ---
def main_menu_markup():
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("▶ Играть с ботом", callback_data='start_bot'),
        types.InlineKeyboardButton("👥 Мультиплеер", callback_data='start_multi_lobby')
    )
    markup.row(
        types.InlineKeyboardButton("❓ Помощь", callback_data='help'),
        types.InlineKeyboardButton("⏹ Выход", callback_data='exit')
    )
    return markup


@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "Добро пожаловать! Выберите режим игры:", reply_markup=main_menu_markup())


@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):
    data = call.data
    user_id = call.from_user.id
    chat_id = call.message.chat.id

    # --- Главное меню ---
    if data == 'main_menu':
        bot.edit_message_text("Главное меню. Выберите режим игры:", chat_id=chat_id, message_id=call.message.message_id,
                              reply_markup=main_menu_markup())
        bot.answer_callback_query(call.id)
        return

    if data == 'help':
        help_text = (
            "Правила игры с ботом:\n"
            "- Вы и бот по очереди стреляете из револьвера.\n"
            "- В барабане 1 боевой патрон, остальные холостые.\n"
            "- Можно стрелять в себя или в бота.\n"
            "- Если выстрел боевой, игрок теряет 1 HP.\n"
            "- Цель — остаться живым.\n\n"
            "Правила мультиплеера:\n"
            "- До 8 игроков подключаются в лобби.\n"
            "- 30 секунд на подключение.\n"
            "- Игроки по очереди стреляют друг в друга или в себя.\n"
            "- Кнопка 'Стоп' запускает голосование на остановку игры.\n"
            "- Побеждает последний выживший.\n\n"
            "Нажмите «⬅️ Назад» для возврата."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data='main_menu'))
        bot.edit_message_text(help_text, chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    if data == 'exit':
        # Завершить все игры пользователя
        if user_id in bot_games:
            del bot_games[user_id]

        if chat_id in multi_games:
            mg = multi_games[chat_id]
            if user_id in mg['players']:
                mg['players'].remove(user_id)
            if user_id in mg.get('hp', {}):
                del mg['hp'][user_id]

        bot.edit_message_text("Игра завершена. Возврат в главное меню.", chat_id=chat_id, message_id=call.message.message_id,
                              reply_markup=main_menu_markup())
        bot.answer_callback_query(call.id)
        return

    # --- Игра с ботом ---
    if data == 'start_bot':
        if user_id in bot_games:
            bot.answer_callback_query(call.id, "Игра уже запущена.", show_alert=True)
            return
        bot_games[user_id] = {
            'hp': {user_id: MAX_HP, 0: MAX_HP},
            'turn': 0,  # 0 - игрок, 1 - бот
            'magazine': create_magazine(),
            'chat_id': chat_id,
            'message_id': None
        }
        bot.answer_callback_query(call.id, "Игра с ботом началась! Ваш ход.")
        send_bot_game_message(user_id)
        return

    # Ходы в игре с ботом
    if data.startswith('bot_shoot_') or data == 'bot_stop' or data == 'main_menu':
        if user_id not in bot_games:
            bot.answer_callback_query(call.id, "Игра с ботом не запущена.", show_alert=True)
            return
        game = bot_games[user_id]

        if data == 'main_menu':
            # Завершить игру и показать меню
            del bot_games[user_id]
            bot.edit_message_text("Выход в главное меню.", chat_id=chat_id, message_id=call.message.message_id,
                                  reply_markup=main_menu_markup())
            bot.answer_callback_query(call.id)
            return

        if data == 'bot_stop':
            del bot_games[user_id]
            bot.edit_message_text("Вы сдались. Игра окончена.", chat_id=chat_id, message_id=call.message.message_id,
                                  reply_markup=main_menu_markup())
            bot.answer_callback_query(call.id)
            return

        if game['turn'] != 0:
            bot.answer_callback_query(call.id, "Сейчас не ваш ход.", show_alert=True)
            return

        target = None
        if data == 'bot_shoot_self':
            target = user_id
        elif data == 'bot_shoot_bot':
            target = 0
        else:
            bot.answer_callback_query(call.id, "Неизвестное действие.", show_alert=True)
            return

        bullet = get_bullet(game['magazine'])
        text = f"Вы выстрелили {'в себя' if target == user_id else 'в бота'}. Патрон — {bullet}."

        if bullet == 'боевой':
            game['hp'][target] -= 1
            text += f"\n{'Вы' if target == user_id else 'Бот'} получили урон! HP: {game['hp'][target]}."
            game['turn'] = 1  # ход бота
        else:
            text += "\nХолостой патрон, урона нет."
            if target == user_id:
                game['turn'] = 0  # игрок ходит еще раз
            else:
                game['turn'] = 1

        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)

        if game['hp'][user_id] <= 0:
            bot.send_message(chat_id, "Вы проиграли! Игра окончена.")
            del bot_games[user_id]
            return
        elif game['hp'][0] <= 0:
            bot.send_message(chat_id, "Вы выиграли! Игра окончена.")
            del bot_games[user_id]
            return

        if game['turn'] == 1:
            # Ход бота через 2 секунды
            threading.Thread(target=bot_turn, args=(user_id,)).start()
        else:
            send_bot_game_message(user_id)
        return

    # --- Мультиплеер ---
    if data == 'start_multi_lobby':
        if chat_id in multi_games and not multi_games[chat_id]['started']:
            bot.answer_callback_query(call.id, "Лобби уже открыто, ждём игроков.")
            return
        if chat_id in multi_games and multi_games[chat_id]['started']:
            bot.answer_callback_query(call.id, "Игра уже идёт.")
            return

        multi_games[chat_id] = {
            'players': [],
            'hp': {},
            'turn_index': 0,
            'started': False,
            'magazine': create_magazine(),
            'message_id': call.message.message_id,
            'stop_votes': set(),
            'join_end_time': time.time() + JOIN_TIME
        }

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👤 Вступить в игру", callback_data='multi_join'))
        markup.add(types.InlineKeyboardButton("🚪 Отмена", callback_data='multi_cancel'))
        markup.add(types.InlineKeyboardButton("☰ Главное меню", callback_data='main_menu'))

        bot.edit_message_text(
            f"Мультиплеер: Подключение игроков (максимум {MAX_PLAYERS})\n"
            f"Время на подключение: {JOIN_TIME} секунд\n"
            f"Нажмите 'Вступить в игру', чтобы присоединиться.\n\n"
            f"Подключено игроков: 0",
            chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup
        )
        bot.answer_callback_query(call.id)

        # Запускаем таймер старта игры
        threading.Thread(target=multi_wait_and_start, args=(chat_id,)).start()
        return

    if data == 'multi_join':
        mg = multi_games.get(chat_id)
        if not mg or mg['started']:
            bot.answer_callback_query(call.id, "Лобби не активно.", show_alert=True)
            return

        if user_id in mg['players']:
            bot.answer_callback_query(call.id, "Вы уже в игре.", show_alert=True)
            return

        if len(mg['players']) >= MAX_PLAYERS:
            bot.answer_callback_query(call.id, "Максимум игроков достигнут.", show_alert=True)
            return

        mg['players'].append(user_id)
        mg['hp'][user_id] = MAX_HP

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👤 Вступить в игру", callback_data='multi_join'))
        markup.add(types.InlineKeyboardButton("🚪 Отмена", callback_data='multi_cancel'))
        markup.add(types.InlineKeyboardButton("☰ Главное меню", callback_data='main_menu'))

        bot.edit_message_text(
            f"Мультиплеер: Подключение игроков (максимум {MAX_PLAYERS})\n"
            f"Время на подключение: {JOIN_TIME} секунд\n"
            f"Нажмите 'Вступить в игру', чтобы присоединиться.\n\n"
            f"Подключено игроков: {len(mg['players'])}",
            chat_id=chat_id, message_id=mg['message_id'], reply_markup=markup
        )
        bot.answer_callback_query(call.id, "Вы подключились.")
        return

    if data == 'multi_cancel':
        mg = multi_games.get(chat_id)
        if not mg or mg['started']:
            bot.answer_callback_query(call.id, "Лобби не активно.", show_alert=True)
            return
        del multi_games[chat_id]
        bot.edit_message_text("Лобби отменено. Возврат в главное меню.", chat_id=chat_id, message_id=call.message.message_id,
                              reply_markup=main_menu_markup())
        bot.answer_callback_query(call.id)
        return

    # В мультиплеере игра идёт
    mg = multi_games.get(chat_id)
    if not mg or not mg['started']:
        bot.answer_callback_query(call.id, "Игра не активна.", show_alert=True)
        return

    if data == 'multi_stop':
        if user_id in mg['stop_votes']:
            bot.answer_callback_query(call.id, "Вы уже проголосовали за остановку.", show_alert=True)
            return
        mg['stop_votes'].add(user_id)
        votes = len(mg['stop_votes'])
        total = len(mg['players'])
        bot.answer_callback_query(call.id, f"Вы проголосовали за остановку. Голосов: {votes}/{total}")
        bot.send_message(chat_id, f"{mention(call.from_user)} проголосовал за остановку игры. ({votes}/{total})")

        if votes == total:
            bot.send_message(chat_id, "Все игроки согласны. Игра завершена.")
            end_multi_game(chat_id)
        return

    if data.startswith('multi_shoot_'):
        if user_id != mg['players'][mg['turn_index']]:
            bot.answer_callback_query(call.id, "Сейчас не ваш ход.", show_alert=True)
            return

        try:
            target_id = int(data.split('_')[2])
        except:
            bot.answer_callback_query(call.id, "Неверный игрок.", show_alert=True)
            return

        if target_id not in mg['players']:
            bot.answer_callback_query(call.id, "Игрок не найден.", show_alert=True)
            return

        bullet = get_bullet(mg['magazine'])
        shooter_mention = mention(call.from_user)
        target_mention = mention(bot.get_chat_member(chat_id, target_id).user)

        text = f"{shooter_mention} стреляет {'в себя' if user_id == target_id else f'в {target_mention}'}. Патрон — {bullet}."

        if bullet == 'боевой':
            mg['hp'][target_id] -= 1
            text += f"\n{target_mention} получил урон! HP: {mg['hp'][target_id]}."
        else:
            text += "\nХолостой патрон, урона нет."

        if mg['hp'][target_id] <= 0:
            text += f"\n{target_mention} выбыл из игры."
            mg['players'].remove(target_id)
            del mg['hp'][target_id]
            if target_id in mg['stop_votes']:
                mg['stop_votes'].remove(target_id)

        if len(mg['players']) <= 1:
            text += "\nИгра окончена."
            bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id)
            end_multi_game(chat_id)
            bot.answer_callback_query(call.id)
            return

        # Логика очереди ходов
        if user_id == target_id:
            if bullet == 'холостой':
                pass  # ход тот же
            else:
                mg['turn_index'] = (mg['turn_index'] + 1) % len(mg['players'])
        else:
            mg['turn_index'] = (mg['turn_index'] + 1) % len(mg['players'])

        mg['stop_votes'] = set()

        bot.edit_message_text(text, chat_id=chat_id, message_id=call.message.message_id)
        bot.answer_callback_query(call.id)

        time.sleep(2)
        send_multi_game_message(chat_id)
        return


def send_bot_game_message(user_id):
    game = bot_games.get(user_id)
    if not game:
        return
    chat_id = game['chat_id']
    hp = game['hp']
    turn = game['turn']

    text = f"Игра с ботом.\nВаш HP: {hp[user_id]}\nHP бота: {hp[0]}\n{'Ваш ход' if turn == 0 else 'Ход бота'}"

    markup = types.InlineKeyboardMarkup()
    if turn == 0:
        markup.row(
            types.InlineKeyboardButton("Выстрелить в себя", callback_data='bot_shoot_self'),
            types.InlineKeyboardButton("Выстрелить в бота", callback_data='bot_shoot_bot')
        )
        markup.row(types.InlineKeyboardButton("Сдаться", callback_data='bot_stop'))
        markup.row(types.InlineKeyboardButton("☰ Главное меню", callback_data='main_menu'))
    else:
        markup.row(types.InlineKeyboardButton("Ждем ход бота...", callback_data='noop'))

    msg = bot.send_message(chat_id, text, reply_markup=markup)
    game['message_id'] = msg.message_id


def bot_turn(user_id):
    time.sleep(2)
    game = bot_games.get(user_id)
    if not game:
        return
    chat_id = game['chat_id']
    hp = game['hp']

    target = random.choice([user_id, 0])
    bullet = get_bullet(game['magazine'])

    text = f"Бот стреляет {'в себя' if target == 0 else 'в вас'}. Патрон — {bullet}."

    if bullet == 'боевой':
        hp[target] -= 1
        text += f"\n{'Бот' if target == 0 else 'Вы'} получили урон! HP: {hp[target]}."

    if target == 0:
        if bullet == 'боевой':
            game['turn'] = 0
        else:
            game['turn'] = 1
    else:
        game['turn'] = 0

    bot.edit_message_text(text, chat_id=chat_id, message_id=game['message_id'])

    if hp[user_id] <= 0:
        bot.send_message(chat_id, "Вы проиграли! Игра окончена.")
        del bot_games[user_id]
        return
    elif hp[0] <= 0:
        bot.send_message(chat_id, "Вы выиграли! Игра окончена.")
        del bot_games[user_id]
        return

    send_bot_game_message(user_id)


def multi_wait_and_start(chat_id):
    time.sleep(JOIN_TIME)
    mg = multi_games.get(chat_id)
    if not mg or mg['started']:
        return

    if len(mg['players']) < 2:
        bot.edit_message_text("Недостаточно игроков для начала игры. Игра отменена.", chat_id=chat_id, message_id=mg['message_id'],
                              reply_markup=main_menu_markup())
        del multi_games[chat_id]
        return

    mg['started'] = True
    mg['turn_index'] = 0
    mg['stop_votes'] = set()
    send_multi_game_message(chat_id)


def send_multi_game_message(chat_id):
    mg = multi_games.get(chat_id)
    if not mg:
        return

    players = mg['players']
    hp = mg['hp']
    turn_index = mg['turn_index']
    current_player = players[turn_index]

    text = "Мультиплеерная игра.\n"
    for p in players:
        user = bot.get_chat_member(chat_id, p).user
        text += f"{mention(user)}: HP {hp[p]}\n"
    current_user = bot.get_chat_member(chat_id, current_player).user
    text += f"\nХод игрока {mention(current_user)}."

    markup = types.InlineKeyboardMarkup()
    row = []
    for p in players:
        user = bot.get_chat_member(chat_id, p).user
        btn_text = "Выстрелить в себя" if p == current_player else f"Выстрелить в {mention(user)}"
        row.append(types.InlineKeyboardButton(btn_text, callback_data=f"multi_shoot_{p}"))
        if len(row) == 3:
            markup.row(*row)
            row = []
    if row:
        markup.row(*row)

    markup.row(types.InlineKeyboardButton("🛑 Стоп", callback_data="multi_stop"))

    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=mg['message_id'], reply_markup=markup)
    except Exception:
        msg = bot.send_message(chat_id, text, reply_markup=markup)
        mg['message_id'] = msg.message_id


def end_multi_game(chat_id):
    mg = multi_games.get(chat_id)
    if not mg:
        return

    winner = None
    if len(mg['players']) == 1:
        winner = mg['players'][0]

    text = "Игра в мультиплеере окончена.\n"
    if winner:
        user = bot.get_chat_member(chat_id, winner).user
        text += f"Победитель — {mention(user)}!"
    else:
        text += "Победителей нет."

    try:
        bot.edit_message_text(text, chat_id=chat_id, message_id=mg['message_id'])
    except Exception:
        bot.send_message(chat_id, text)

    del multi_games[chat_id]

    bot.send_message(chat_id, "Главное меню. Выберите режим игры:", reply_markup=main_menu_markup())


if __name__ == '__main__':
    print("Бот запущен...")
    bot.infinity_polling()
