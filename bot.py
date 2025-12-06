import telebot
import json
import os
import math
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ---------------- CONFIGURATION ---------------- #
# Uses environment variable for Docker compatibility
BOT_TOKEN = os.getenv("BOT_TOKEN") 
if not BOT_TOKEN:
    # Fallback for local testing if env var not set
    print("Warning: BOT_TOKEN env var not set.")
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = telebot.TeleBot(BOT_TOKEN)

# ---------------- STATE MANAGEMENT ---------------- #
# Modes: 'split', 'op_main', 'op_filter', 'merge'
user_states = {}

# ---------------- HELPER FUNCTIONS ---------------- #

def load_json_content(file_info):
    """Downloads and parses JSON file."""
    downloaded_file = bot.download_file(file_info.file_path)
    try:
        data = json.loads(downloaded_file.decode('utf-8'))
        return data
    except Exception as e:
        print(f"Error: {e}")
        return None

def cleanup_state(chat_id):
    if chat_id in user_states:
        del user_states[chat_id]

# ---------------- HANDLERS ---------------- #

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "<b>JSON Tool Bot</b>\n\n"
        "<b>1. Subtract Links (Main - Others)</b>\n"
        "   /operation - Filter items out of a main file.\n\n"
        "<b>2. Merge Files (A + B + C...)</b>\n"
        "   /merge - Combine multiple files into one.\n\n"
        "<b>3. Split JSON</b>\n"
        "   /split [n] - Split a file into n equal parts.\n"
        "   (e.g., /split 5)"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# --- MERGE LOGIC (NEW) ---

@bot.message_handler(commands=['merge'])
def init_merge(message):
    user_states[message.chat.id] = {
        'mode': 'merge', 
        'merged_data': []
    }
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("/done"))
    
    bot.reply_to(
        message, 
        "🔗 <b>Merge Mode</b> started.\n"
        "Upload your JSON files one by one.\n"
        "They will be combined into a single list.\n"
        "Type /done when finished.", 
        parse_mode="HTML",
        reply_markup=markup
    )

# --- SPLIT LOGIC ---

@bot.message_handler(commands=['split'])
def init_split(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Please specify N. Example: `/split 5`")
            return
        
        n = int(args[1])
        if n < 1:
            bot.reply_to(message, "⚠️ N must be greater than 0.")
            return

        user_states[message.chat.id] = {'mode': 'split', 'split_n': n}
        bot.reply_to(message, f"✂️ Ready to split into {n} files. Please upload your JSON file now.")
        
    except ValueError:
        bot.reply_to(message, "⚠️ Invalid number. Example: `/split 5`")

# --- OPERATION (SUBTRACT) LOGIC ---

@bot.message_handler(commands=['operation'])
def init_operation(message):
    user_states[message.chat.id] = {
        'mode': 'op_main', 
        'main_data': [], 
        'filter_set': set()
    }
    bot.reply_to(message, "1️⃣ <b>Step 1:</b> Upload the <b>MAIN</b> JSON file.", parse_mode="HTML")

# --- GENERIC /DONE HANDLER ---

@bot.message_handler(commands=['done'])
def finalize_action(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)

    if not state:
        bot.reply_to(message, "⚠️ No active operation.")
        return

    # FINALIZING MERGE
    if state['mode'] == 'merge':
        final_list = state['merged_data']
        if not final_list:
            bot.reply_to(message, "⚠️ No data collected.")
            return
            
        bot.send_message(chat_id, f"⚙️ Saving merged file ({len(final_list)} items)...")
        
        filename = f"Merged_{len(final_list)}_items.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=2)
            
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="✅ Files Merged Successfully")
            
        os.remove(filename)
        cleanup_state(chat_id)

    # FINALIZING SUBTRACTION
    elif state['mode'] in ['op_main', 'op_filter']:
        if not state['main_data']:
            bot.reply_to(message, "⚠️ No Main file uploaded.")
            return

        bot.send_message(chat_id, "⚙️ calculating difference...")
        
        main_list = state['main_data']
        filter_set = state['filter_set']
        
        # Keep items NOT in the filter set
        final_list = [item for item in main_list if item not in filter_set]
        
        removed_count = len(main_list) - len(final_list)
        
        filename = f"Result_{len(final_list)}_items.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=2)
        
        with open(filename, 'rb') as f:
            caption = (
                f"✅ <b>Done!</b>\n"
                f"Original: {len(main_list)}\n"
                f"Removed: {removed_count}\n"
                f"Remaining: {len(final_list)}"
            )
            bot.send_document(chat_id, f, caption=caption, parse_mode="HTML")
        
        os.remove(filename)
        cleanup_state(chat_id)

# --- FILE HANDLER ---

@bot.message_handler(content_types=['document'])
def handle_files(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    
    if not state:
        bot.reply_to(message, "⚠️ Select a command: /merge, /operation, or /split n")
        return

    file_info = bot.get_file(message.document.file_id)
    data = load_json_content(file_info)

    if data is None or not isinstance(data, list):
        bot.reply_to(message, "❌ Error: File must be a valid JSON List `[...]`.")
        return

    # MODE: MERGE
    if state['mode'] == 'merge':
        state['merged_data'].extend(data)
        bot.reply_to(message, f"➕ Added {len(data)} items. Total: {len(state['merged_data'])}. Upload next or /done.")

    # MODE: SPLIT
    elif state['mode'] == 'split':
        n = state['split_n']
        total_items = len(data)
        bot.send_message(chat_id, f"✂️ Splitting {total_items} items into {n} files...")
        
        chunk_size = math.ceil(total_items / n)
        
        for i in range(n):
            start = i * chunk_size
            end = start + chunk_size
            chunk = data[start:end]
            if not chunk: break
                
            fname = f"Part_{i+1}.json"
            with open(fname, 'w', encoding='utf-8') as f:
                json.dump(chunk, f, indent=2)
            with open(fname, 'rb') as f:
                bot.send_document(chat_id, f, caption=f"Part {i+1} ({len(chunk)})")
            os.remove(fname)
            
        cleanup_state(chat_id)

    # MODE: OP MAIN
    elif state['mode'] == 'op_main':
        state['main_data'] = data
        state['mode'] = 'op_filter'
        
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("/done"))
        bot.reply_to(message, f"✅ Main loaded ({len(data)} items).\nNow upload filter files.", reply_markup=markup)

    # MODE: OP FILTER
    elif state['mode'] == 'op_filter':
        count = 0
        for item in data:
            if isinstance(item, (dict, list)):
                state['filter_set'].add(json.dumps(item, sort_keys=True))
            else:
                state['filter_set'].add(item)
            count += 1
        bot.reply_to(message, f"🗑️ Added {count} items to filter. Upload next or /done.")

# ---------------- POLLING ---------------- #
print("Bot is running...")
bot.infinity_polling()
