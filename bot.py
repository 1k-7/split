import telebot
import json
import os
import math
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ---------------- CONFIGURATION ---------------- #
BOT_TOKEN = os.getenv("BOT_TOKEN") 

if not BOT_TOKEN:
    print("⚠️ Warning: BOT_TOKEN env var not set. Using placeholder.")
    BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

bot = telebot.TeleBot(BOT_TOKEN)

# ---------------- STATE MANAGEMENT ---------------- #
# Modes: 'merge', 'split', 'op_main', 'op_filter'
# New Modes: 'replace_step1' (waiting for find_text), 'replace_step2' (waiting for new_text), 'replace_ready'
user_states = {}

# ---------------- HELPER FUNCTIONS ---------------- #

def load_json_content(file_info):
    try:
        downloaded_file = bot.download_file(file_info.file_path)
        data = json.loads(downloaded_file.decode('utf-8'))
        return data
    except Exception as e:
        return None

def cleanup_state(chat_id):
    if chat_id in user_states:
        del user_states[chat_id]

# ---------------- HANDLERS ---------------- #

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    help_text = (
        "<b>JSON Tool Bot</b>\n\n"
        "<b>1. Find & Replace</b>\n"
        "   /replace - Replace text (e.g., domain names) in a file.\n\n"
        "<b>2. Merge Files (No Duplicates)</b>\n"
        "   /merge - Combine multiple files into one unique list.\n\n"
        "<b>3. Subtract Links (Main - Others)</b>\n"
        "   /operation - Remove processed links from a main file.\n\n"
        "<b>4. Split JSON</b>\n"
        "   /split [n] - Split a file into n equal parts.\n"
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# --- 1. REPLACE LOGIC (NEW) ---

@bot.message_handler(commands=['replace'])
def init_replace(message):
    user_states[message.chat.id] = {'mode': 'replace_step1'}
    bot.reply_to(message, "🔍 <b>Find & Replace</b>\n\nStep 1: Send the text you want to <b>FIND</b>.", parse_mode="HTML")

# --- 2. MERGE LOGIC ---

@bot.message_handler(commands=['merge'])
def init_merge(message):
    user_states[message.chat.id] = {'mode': 'merge', 'merged_data': set()}
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("/done"))
    bot.reply_to(message, "🔗 <b>Merge Mode</b> started.\nUpload files. Duplicates removed.\nType /done when finished.", parse_mode="HTML", reply_markup=markup)

# --- 3. SPLIT LOGIC ---

@bot.message_handler(commands=['split'])
def init_split(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Specify N. Example: `/split 5`")
            return
        n = int(args[1])
        if n < 1: return
        user_states[message.chat.id] = {'mode': 'split', 'split_n': n}
        bot.reply_to(message, f"✂️ Ready to split into {n} files. Upload JSON now.")
    except:
        bot.reply_to(message, "⚠️ Error.")

# --- 4. SUBTRACT LOGIC ---

@bot.message_handler(commands=['operation'])
def init_operation(message):
    user_states[message.chat.id] = {'mode': 'op_main', 'main_data': [], 'filter_set': set()}
    bot.reply_to(message, "1️⃣ <b>Step 1:</b> Upload the <b>MAIN</b> JSON file.", parse_mode="HTML")

# --- TEXT HANDLER (For Replace Steps) ---

@bot.message_handler(func=lambda message: message.content_type == 'text' and not message.text.startswith('/'))
def handle_text_inputs(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    
    if not state: 
        return

    # Handling REPLACE input steps
    if state['mode'] == 'replace_step1':
        state['find_text'] = message.text
        state['mode'] = 'replace_step2'
        bot.reply_to(message, f"✅ Finding: <code>{message.text}</code>\n\nStep 2: Send the text to <b>REPLACE IT WITH</b>.", parse_mode="HTML")
        
    elif state['mode'] == 'replace_step2':
        state['replace_text'] = message.text
        state['mode'] = 'replace_ready'
        find = state['find_text']
        rep = state['replace_text']
        bot.reply_to(message, f"🔄 Replacing: <code>{find}</code> ➡️ <code>{rep}</code>\n\nStep 3: Upload your JSON file now.", parse_mode="HTML")

# --- GENERIC /DONE HANDLER ---

@bot.message_handler(commands=['done'])
def finalize_action(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)

    if not state: return

    # FINALIZING MERGE
    if state['mode'] == 'merge':
        data_set = state['merged_data']
        if not data_set:
            bot.reply_to(message, "⚠️ No data.")
            return
            
        bot.send_message(chat_id, f"⚙️ Saving merged file ({len(data_set)} unique items)...")
        
        final_list = []
        for item in data_set:
            if isinstance(item, str) and item.startswith("JSON_OBJ:"):
                try:
                    final_list.append(json.loads(item[9:]))
                except:
                    final_list.append(item)
            else:
                final_list.append(item)
        
        filename = f"Merged_{len(final_list)}_unique.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=2)
            
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption="✅ Merge Complete")
        os.remove(filename)
        cleanup_state(chat_id)

    # FINALIZING SUBTRACTION
    elif state['mode'] in ['op_main', 'op_filter']:
        if not state['main_data']: return
        
        main_list = state['main_data']
        filter_set = state['filter_set']
        
        final_list = []
        for item in main_list:
            check_val = item
            if isinstance(item, (dict, list)):
                check_val = json.dumps(item, sort_keys=True)
            if check_val not in filter_set:
                final_list.append(item)
        
        filename = f"Result_{len(final_list)}_items.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(final_list, f, indent=2)
        
        with open(filename, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"✅ Done. Remaining: {len(final_list)}")
        os.remove(filename)
        cleanup_state(chat_id)

# --- FILE HANDLER ---

@bot.message_handler(content_types=['document'])
def handle_files(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    
    if not state:
        bot.reply_to(message, "⚠️ Select a command first.")
        return

    file_info = bot.get_file(message.document.file_id)
    data = load_json_content(file_info)

    if data is None or not isinstance(data, list):
        bot.reply_to(message, "❌ Error: File must be a valid JSON List `[...]`.")
        return

    # >>> MODE: REPLACE <<<
    if state['mode'] == 'replace_ready':
        find_str = state['find_text']
        rep_str = state['replace_text']
        count = 0
        
        new_data = []
        for item in data:
            if isinstance(item, str):
                if find_str in item:
                    item = item.replace(find_str, rep_str)
                    count += 1
                new_data.append(item)
            else:
                # Handle objects: Convert to string, replace, convert back
                # This is safer for links inside objects
                try:
                    s_item = json.dumps(item)
                    if find_str in s_item:
                        s_item = s_item.replace(find_str, rep_str)
                        item = json.loads(s_item)
                        count += 1
                    new_data.append(item)
                except:
                    new_data.append(item)

        bot.send_message(chat_id, f"✅ Replaced {count} occurrences.")
        
        fname = "Replaced_Output.json"
        with open(fname, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=2)
        with open(fname, 'rb') as f:
            bot.send_document(chat_id, f)
        os.remove(fname)
        cleanup_state(chat_id)

    # >>> MODE: MERGE <<<
    elif state['mode'] == 'merge':
        initial = len(state['merged_data'])
        for item in data:
            if isinstance(item, (dict, list)):
                state['merged_data'].add("JSON_OBJ:" + json.dumps(item, sort_keys=True))
            else:
                state['merged_data'].add(item)
        bot.reply_to(message, f"➕ Added unique items. Total: {len(state['merged_data'])}")

    # >>> MODE: SPLIT <<<
    elif state['mode'] == 'split':
        n = state['split_n']
        chunk_size = math.ceil(len(data) / n)
        for i in range(n):
            chunk = data[i*chunk_size : (i+1)*chunk_size]
            if not chunk: break
            fname = f"Part_{i+1}.json"
            with open(fname, 'w', encoding='utf-8') as f: json.dump(chunk, f, indent=2)
            with open(fname, 'rb') as f: bot.send_document(chat_id, f, caption=f"Part {i+1}")
            os.remove(fname)
        cleanup_state(chat_id)

    # >>> MODE: OP MAIN <<<
    elif state['mode'] == 'op_main':
        state['main_data'] = data
        state['mode'] = 'op_filter'
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("/done"))
        bot.reply_to(message, f"✅ Main loaded. Upload filters.", reply_markup=markup)

    # >>> MODE: OP FILTER <<<
    elif state['mode'] == 'op_filter':
        for item in data:
            if isinstance(item, (dict, list)):
                state['filter_set'].add(json.dumps(item, sort_keys=True))
            else:
                state['filter_set'].add(item)
        bot.reply_to(message, f"🗑️ Filter added. Upload next or /done.")

print("Bot is running...")
bot.infinity_polling()
