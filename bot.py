import telebot
import json
import os
import math
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ---------------- CONFIGURATION ---------------- #
# Get Token from Environment Variable (Best for Docker)
BOT_TOKEN = os.getenv("BOT_TOKEN") 

if not BOT_TOKEN:
    # Fallback for local testing if you run without Docker/Env
    print("⚠️ Warning: BOT_TOKEN env var not set. Using placeholder.")
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = telebot.TeleBot(BOT_TOKEN)

# ---------------- STATE MANAGEMENT ---------------- #
# Stores user session data.
# Structure: { chat_id: { 'mode': '...', 'data': ... } }
user_states = {}

# ---------------- HELPER FUNCTIONS ---------------- #

def load_json_content(file_info):
    """Downloads and parses JSON file from Telegram servers."""
    try:
        downloaded_file = bot.download_file(file_info.file_path)
        data = json.loads(downloaded_file.decode('utf-8'))
        return data
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return None

def cleanup_state(chat_id):
    """Removes user data from memory to free up RAM."""
    if chat_id in user_states:
        del user_states[chat_id]

# ---------------- HANDLERS ---------------- #

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "<b>JSON Tool Bot</b>\n\n"
        "<b>1. Merge Files (No Duplicates)</b>\n"
        "   /merge - Combine multiple files into one unique list.\n\n"
        "<b>2. Subtract Links (Main - Others)</b>\n"
        "   /operation - Remove processed links from a main file.\n\n"
        "<b>3. Split JSON</b>\n"
        "   /split [n] - Split a file into n equal parts.\n"
        "   (e.g., /split 5)"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# --- 1. MERGE LOGIC ---

@bot.message_handler(commands=['merge'])
def init_merge(message):
    # We use a SET to automatically handle uniqueness
    user_states[message.chat.id] = {
        'mode': 'merge', 
        'merged_data': set() 
    }
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("/done"))
    
    bot.reply_to(
        message, 
        "🔗 <b>Merge Mode (No Duplicates)</b> started.\n"
        "Upload your JSON files one by one.\n"
        "Duplicates will be auto-removed.\n"
        "Type /done when finished.", 
        parse_mode="HTML",
        reply_markup=markup
    )

# --- 2. SPLIT LOGIC ---

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

# --- 3. SUBTRACT LOGIC ---

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

    # >>> FINALIZING MERGE <<<
    if state['mode'] == 'merge':
        data_set = state['merged_data']
        if not data_set:
            bot.reply_to(message, "⚠️ No data collected.")
            return
            
        bot.send_message(chat_id, f"⚙️ Saving merged file ({len(data_set)} unique items)...")
        
        # Convert Set back to List for JSON export
        final_list = []
        for item in data_set:
            # Check if we stored it as a special stringified JSON object
            if isinstance(item, str) and item.startswith("JSON_OBJ:"):
                try:
                    # Remove prefix and decode back to dict
                    original_obj = json.loads(item[9:]) 
                    final_list.append(original_obj)
                except:
                    final_list.append(item) # Fallback
            else:
                final_list.append(item)
        
        filename = f"Merged_{len(final_list)}_unique.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=2)
            
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="✅ Files Merged (Duplicates Removed)")
            
        os.remove(filename)
        cleanup_state(chat_id)

    # >>> FINALIZING SUBTRACTION <<<
    elif state['mode'] in ['op_main', 'op_filter']:
        if not state['main_data']:
            bot.reply_to(message, "⚠️ No Main file uploaded.")
            return

        bot.send_message(chat_id, "⚙️ Calculating difference...")
        
        main_list = state['main_data']
        filter_set = state['filter_set']
        
        # Logic: Keep item if it is NOT in the filter set
        # We need to handle potential complex objects in main_list too
        final_list = []
        for item in main_list:
            check_val = item
            if isinstance(item, (dict, list)):
                check_val = json.dumps(item, sort_keys=True)
            
            if check_val not in filter_set:
                final_list.append(item)
        
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

# --- UNIVERSAL FILE HANDLER ---

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

    # >>> MODE: MERGE <<<
    if state['mode'] == 'merge':
        initial_count = len(state['merged_data'])
        
        for item in data:
            # Handle Dictionaries by converting to string for Set storage
            if isinstance(item, (dict, list)):
                item_str = "JSON_OBJ:" + json.dumps(item, sort_keys=True)
                state['merged_data'].add(item_str)
            else:
                state['merged_data'].add(item)
                
        new_count = len(state['merged_data'])
        added = new_count - initial_count
        skipped = len(data) - added
        
        bot.reply_to(
            message, 
            f"➕ Processed file.\n"
            f"Unique added: {added}\n"
            f"Duplicates ignored: {skipped}\n"
            f"Total unique: {new_count}\n"
            f"Upload next or /done."
        )

    # >>> MODE: SPLIT <<<
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

    # >>> MODE: OP MAIN <<<
    elif state['mode'] == 'op_main':
        state['main_data'] = data
        state['mode'] = 'op_filter'
        
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("/done"))
        bot.reply_to(message, f"✅ Main loaded ({len(data)} items).\nNow upload filter files.", reply_markup=markup)

    # >>> MODE: OP FILTER <<<
    elif state['mode'] == 'op_filter':
        count = 0
        for item in data:
            if isinstance(item, (dict, list)):
                state['filter_set'].add(json.dumps(item, sort_keys=True))
            else:
                state['filter_set'].add(item)
            count += 1
        bot.reply_to(message, f"🗑️ Added {count} items to filter. Upload next or /done.")

# ---------------- STARTUP ---------------- #
print("Bot is running...")
bot.infinity_polling()
