import telebot
import json
import os
import math
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ---------------- CONFIGURATION ---------------- #
# Replace the old token line with this:
BOT_TOKEN = os.getenv("BOT_TOKEN") 

if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN provided in environment variables")
bot = telebot.TeleBot(BOT_TOKEN)

# ---------------- STATE MANAGEMENT ---------------- #
# Stores user session data: 
# { chat_id: { 'mode': 'split'|'op_main'|'op_filter', 'data': ..., 'split_n': int } }
user_states = {}

# ---------------- HELPER FUNCTIONS ---------------- #

def load_json_content(file_info):
    """Downloads and parses JSON file from Telegram servers."""
    downloaded_file = bot.download_file(file_info.file_path)
    try:
        data = json.loads(downloaded_file.decode('utf-8'))
        return data
    except json.JSONDecodeError:
        return None
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
        "Use /operation to start.\n"
        "- Upload Main JSON\n"
        "- Upload Filter JSONs (processed files)\n"
        "- Type /done to calculate.\n\n"
        "<b>2. Split JSON</b>\n"
        "Use /split [n] (e.g., /split 5)\n"
        "- Upload the file to split it into n parts."
    )
    bot.reply_to(message, help_text, parse_mode="HTML")

# --- SPLIT LOGIC ---

@bot.message_handler(commands=['split'])
def init_split(message):
    try:
        # Parse 'n' from command
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

# --- OPERATION LOGIC ---

@bot.message_handler(commands=['operation'])
def init_operation(message):
    user_states[message.chat.id] = {
        'mode': 'op_main', 
        'main_data': [], 
        'filter_set': set()
    }
    bot.reply_to(message, "1️⃣ <b>Step 1:</b> Upload the <b>MAIN</b> JSON file (the source).", parse_mode="HTML")

@bot.message_handler(commands=['done'])
def finalize_operation(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)

    if not state or state.get('mode') not in ['op_main', 'op_filter']:
        bot.reply_to(message, "⚠️ No active operation. Use /operation to start.")
        return

    if not state['main_data']:
        bot.reply_to(message, "⚠️ You haven't uploaded a Main file yet.")
        return

    # Perform the subtraction
    bot.send_message(chat_id, "⚙️ Processing... Filtering links...")
    
    main_list = state['main_data']
    filter_set = state['filter_set']
    
    # Logic: Keep item if it is NOT in the filter set
    # Using string representation for safe comparison if items are complex
    final_list = [item for item in main_list if item not in filter_set]
    
    removed_count = len(main_list) - len(final_list)
    
    # Save result to file
    output_filename = f"Result_{len(final_list)}_items.json"
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(final_list, f, indent=2)
    
    # Send file
    with open(output_filename, 'rb') as f:
        caption = (
            f"✅ <b>Done!</b>\n"
            f"Original: {len(main_list)}\n"
            f"Removed: {removed_count}\n"
            f"Remaining: {len(final_list)}"
        )
        bot.send_document(chat_id, f, caption=caption, parse_mode="HTML")
    
    # Cleanup
    os.remove(output_filename)
    cleanup_state(chat_id)

# --- FILE HANDLER (The Core Logic) ---

@bot.message_handler(content_types=['document'])
def handle_files(message):
    chat_id = message.chat.id
    state = user_states.get(chat_id)
    
    if not state:
        bot.reply_to(message, "⚠️ Please select a command first (/operation or /split n).")
        return

    file_info = bot.get_file(message.document.file_id)
    data = load_json_content(file_info)

    if data is None:
        bot.reply_to(message, "❌ Error reading JSON. Ensure it is a valid JSON file.")
        return
    
    if not isinstance(data, list):
        bot.reply_to(message, "❌ Error: The JSON root must be a List `[...]`, not a Dictionary `{...}`.")
        return

    # MODE: SPLIT
    if state['mode'] == 'split':
        n = state['split_n']
        total_items = len(data)
        
        if total_items == 0:
            bot.reply_to(message, "The file is empty.")
            return

        bot.send_message(chat_id, f"✂️ Splitting {total_items} items into {n} files...")
        
        # Calculate chunk size (ceiling division)
        chunk_size = math.ceil(total_items / n)
        
        for i in range(n):
            start_idx = i * chunk_size
            end_idx = start_idx + chunk_size
            chunk = data[start_idx:end_idx]
            
            if not chunk:
                break # Stop if we run out of data before n
                
            part_name = f"Part_{i+1}.json"
            
            with open(part_name, 'w', encoding='utf-8') as f:
                json.dump(chunk, f, indent=2)
                
            with open(part_name, 'rb') as f:
                bot.send_document(chat_id, f, caption=f"Part {i+1} ({len(chunk)} items)")
            
            os.remove(part_name)
            
        bot.send_message(chat_id, "✅ Split complete.")
        cleanup_state(chat_id)

    # MODE: OPERATION (MAIN FILE)
    elif state['mode'] == 'op_main':
        state['main_data'] = data
        state['mode'] = 'op_filter' # Switch to waiting for filter files
        
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(KeyboardButton("/done"))
        
        bot.reply_to(
            message, 
            f"✅ <b>Main file loaded</b> ({len(data)} items).\n"
            "2️⃣ <b>Step 2:</b> Now upload the processed/filter files (one by one).\n"
            "Type /done when finished.",
            parse_mode="HTML",
            reply_markup=markup
        )

    # MODE: OPERATION (FILTER FILES)
    elif state['mode'] == 'op_filter':
        # Add these items to the filter set
        # We assume items are hashable (strings/numbers). 
        # If they are dicts, we might need to convert to JSON string to hash them.
        count = 0
        for item in data:
            # Handle unhashable types (like dicts) inside the list
            if isinstance(item, (dict, list)):
                # Convert to tuple/string representation for set hashing
                # This is a simple generic fix. 
                # Ideally, you just filter by ID or URL string.
                state['filter_set'].add(json.dumps(item, sort_keys=True))
            else:
                state['filter_set'].add(item)
            count += 1
            
        bot.reply_to(message, f"🗑️ Added {count} items to filter list. Upload next or type /done.")

# ---------------- POLLING ---------------- #
print("Bot is running...")
bot.infinity_polling()
