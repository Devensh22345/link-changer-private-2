import telebot
import random
import string
import time
import datetime
import pymongo
from pymongo import MongoClient
import os
from telebot import types
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN', "8150393989:AAHkqny2jOM3NxbVSNMOT6IGYJ6FNyQb5cY")
USER_BOT_TOKEN = os.environ.get('USER_BOT_TOKEN', "7833128310:AAGHDWq_ExDuX6aTkfmuGhIo8Onlwhsdx84")  # User bot token
ADMIN_IDS = [int(id) for id in os.environ.get('ADMIN_IDS', '6872968794').split(',') if id]
LOG_CHANNEL = os.environ.get('LOG_CHANNEL', "-1002628986986")
MONGO_URI = os.environ.get('MONGODB_URI', 'mongodb+srv://link:link@cluster0.swqv8gk.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')


# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client.evolution_links_db
users_collection = db.users
channels_collection = db.channels
links_collection = db.links
stats_collection = db.stats
deep_links_collection = db.deep_links

# Enable middleware
apihelper.ENABLE_MIDDLEWARE = True

# Initialize admin bot
bot = telebot.TeleBot(BOT_TOKEN)

# Initialize user bot
user_bot = telebot.TeleBot(USER_BOT_TOKEN)

# Dictionary to store channel links and cooldowns
channel_links = {}
user_cooldowns = {}

# Load existing deep links from database
def load_deep_links():
    for link in deep_links_collection.find():
        unique_id = link["_id"]
        channel_links[unique_id] = {
            "channel_id": link["channel_id"],
            "expiration_time": link["expiration_time"],
            "deep_link": link["deep_link"],
            "type": link["type"]
        }

# Convert UTC to IST
def utc_to_ist(timestamp):
    utc_time = datetime.datetime.utcfromtimestamp(timestamp)
    ist_time = utc_time + datetime.timedelta(hours=5, minutes=30)  # IST is UTC+5:30
    return ist_time.strftime("%Y-%m-%d %H:%M:%S")

# Check if user is admin
def is_admin(user_id):
    return user_id in ADMIN_IDS

# Update user stats
def update_user(user):
    user_data = {
        "user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "last_activity": time.time(),
        "status": "active"
    }
    
    existing_user = users_collection.find_one({"user_id": user.id})
    if not existing_user:
        user_data["joined"] = time.time()
        user_data["links_requested"] = 0
        user_data["successful_joins"] = 0
        users_collection.insert_one(user_data)
        
        # Update daily stats for new users
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        stats_collection.update_one(
            {"date": today},
            {"$inc": {"new_users": 1}},
            upsert=True
        )
    else:
        users_collection.update_one(
            {"user_id": user.id},
            {"$set": {
                "last_activity": time.time(),
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name
            }}
        )

# Generate invite link for channel
def generate_private_link(channel_id, is_request=False):
    """Generates a new private invite link for a channel."""
    try:
        if is_request:
            # Request link with 10-minute expiry, no member limit
            link = bot.create_chat_invite_link(
                chat_id=channel_id, 
                expire_date=int(time.time()) + 600,  # 10-minute expiry
                member_limit=None,
                creates_join_request=True 
            )
        else:
            # Private link with 10-minute expiry, 1 member limit
            link = bot.create_chat_invite_link(
                chat_id=channel_id, 
                expire_date=int(time.time()) + 600,  # 10-minute expiry
                member_limit=1
            )
        
        # Log link generation
        links_collection.insert_one({
            "channel_id": channel_id,
            "link": link.invite_link,
            "created_at": time.time(),
            "expires_at": int(time.time()) + 600,
            "type": "request" if is_request else "private"
        })
        
        # Update channel stats
        channels_collection.update_one(
            {"channel_id": channel_id},
            {"$inc": {"links_generated": 1}}
        )
        
        # Update daily stats
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        stats_collection.update_one(
            {"date": today},
            {"$inc": {"links_generated": 1}},
            upsert=True
        )
        
        return link.invite_link
    except Exception as e:
        print(f"Error generating invite link: {e}")
        return None

# Log to channel
def send_log(message):
    if LOG_CHANNEL:
        try:
            bot.send_message(LOG_CHANNEL, message, parse_mode="Markdown")
        except Exception as e:
            print(f"Error sending log: {e}")

# Pin message in log channel
def pin_log(message):
    if LOG_CHANNEL:
        try:
            msg = bot.send_message(LOG_CHANNEL, message, parse_mode="Markdown")
            bot.pin_chat_message(LOG_CHANNEL, msg.message_id)
        except Exception as e:
            print(f"Error pinning log: {e}")

# Command handlers
# Middleware to check if user is admin for admin bot
@bot.middleware_handler(update_types=['message'])
def admin_only_middleware(bot_instance, message):
    if not is_admin(message.from_user.id):
        # Skip processing for non-admins
        return False
    return True
    
# User bot start command
@user_bot.message_handler(commands=['start'])
def user_start_command(message):
    """Handles the /start command for user bot."""
    user = message.from_user
    update_user(user)
    
    # Check if it's a deep link
    if len(message.text.split()) > 1:
        deep_link_suffix = message.text.split()[1]
        
        # Check for private_ or request_ prefix
        if deep_link_suffix.startswith("private_") or deep_link_suffix.startswith("request_"):
            user_handle_deeplink(message)
            return

    # Regular start command (no special suffix)
    markup = types.InlineKeyboardMarkup(row_width=2)
    anime_button = types.InlineKeyboardButton("🔥 𝐀𝐧𝐢𝐦𝐞 𝐢𝐧 𝐇𝐢𝐧𝐝𝐢", url="https://t.me/Anime_Hindi_Ace")
    chat_button = types.InlineKeyboardButton("💬 𝐂𝐡𝐚𝐭 𝐆𝐫𝐨𝐮𝐩", url="https://t.me/Ace_anime_group")
    markup.add(anime_button, chat_button)

    message_text = (
    "⛩️⛩️ **𝗡𝗲𝘄 𝗔𝗻𝗶𝗺𝗲 𝗶𝗻 𝗛𝗶𝗻𝗱𝗶** ⛩️⛩️\n"
    "[👉 https://t.me/Anime_Hindi_Ace](👉https://t.me/Anime_Hindi_Ace)\n\n"
    "💬 **𝗔𝗻𝗶𝗺𝗲 𝗦𝗲𝗮𝗿𝗰𝗵 𝗮𝗻𝗱 𝗖𝗵𝗮𝘁 𝗚𝗿𝗼𝘂𝗽** 💬\n"
    "[👉 https://t.me/Ace_Anime_Group](https://t.me/Ace_Anime_Group)\n\n"
    "🍑 **𝗔𝗱𝘂𝗹𝘁 𝗔𝗻𝗶𝗺𝗲 𝗶𝗻 𝗵𝗶𝗻𝗱𝗶 [𝟭𝟴+]** 🍑\n"
    "[👉 https://t.me/+pzFZ6pEJ7Nc2MjY1](https://t.me/+pzFZ6pEJ7Nc2MjY1)"
    )

    sent_msg = user_bot.reply_to(message, message_text, parse_mode="Markdown", reply_markup=markup)
    
    # Schedule message deletion after 10 minutes
    threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()

# Function to handle deep links for user bot
def user_handle_deeplink(message):
    """Handles deep link activation for user bot."""
    user = message.from_user
    update_user(user)
    
    parts = message.text.split()
    if len(parts) != 2:
        return
    
    deep_link_text = parts[1]
    link_type = "private" if deep_link_text.startswith("private_") else "request"
    deep_link_suffix = deep_link_text[len("private_"):] if link_type == "private" else deep_link_text[len("request_"):]
    
    # Check if link exists and is valid
    if deep_link_suffix not in channel_links:
        sent_msg = user_bot.reply_to(message, "Invalid link.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
        return
    
    link_data = channel_links[deep_link_suffix]
    
    # Check if link has expired
    if link_data["expiration_time"] < time.time():
        sent_msg = user_bot.reply_to(message, "The link has expired.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
        return
    
    # Check cooldown
    current_time = time.time()
    if user.id in user_cooldowns and current_time - user_cooldowns[user.id] < 10:
        remaining = int(10 - (current_time - user_cooldowns[user.id]))
        sent_msg = user_bot.reply_to(message, f"Please wait {remaining} seconds before requesting another link.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
        return
    
    # Generate appropriate link based on type
    is_request = link_type == "request"
    channel_id = link_data["channel_id"]
    private_link = generate_private_link(channel_id, is_request)
    
    if private_link:
        # Update user cooldown
        user_cooldowns[user.id] = current_time
        
        # Update user stats
        users_collection.update_one(
            {"user_id": user.id},
            {"$inc": {"links_requested": 1}}
        )
        
        # Update channel clicks
        channels_collection.update_one(
            {"channel_id": channel_id},
            {"$inc": {"clicks": 1}}
        )
        
        # Create button with the permanent deep link
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Get this again", url=link_data["deep_link"]))
        
        sent_msg = user_bot.reply_to(
            message,
            f"<b>⛩️ Join Channel to watch Anime⛩️</b>\n"
            f"<b>👉{private_link}</b>\n"
            f"<b>👉{private_link}</b>",
            parse_mode="HTML",
            reply_markup=markup
        )
        
        # Schedule message deletion after 10 minutes
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
    else:
        sent_msg = user_bot.reply_to(message, "Failed to generate a link. Please try again later.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()

# Function to delete messages
def delete_message(bot_instance, chat_id, message_id):
    try:
        bot_instance.delete_message(chat_id, message_id)
    except Exception as e:
        print(f"Failed to delete message: {e}")

# Button handler stays the same
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Handles button callbacks."""
    if call.data == "about":
        # Get stats
        user_count = users_collection.count_documents({"status": {"$ne": "banned"}})
        channel_count = channels_collection.count_documents({})

        about_text = (
            "📌 About Evolution Links\n"
            f"‣ Made By: @pixeltiny\n"
            f"‣ Version: 1.0\n"
            f"‣ Stats: {user_count} users | {channel_count} channels\n"
            "Ciao!!"
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(about_text, call.message.chat.id, call.message.message_id)

    elif call.data == "close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

@bot.message_handler(commands=['channelpost'])
def channelpost_command(message):
    """Handles the /channelpost command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "Invalid command. Usage: /channelpost <channel_id>")
            return
        
        channel_id = int(args[1])
        
        # Check if the user is an admin in the channel
        try:
            chat_member = bot.get_chat_member(channel_id, message.from_user.id)
            if chat_member.status not in ["administrator", "creator"]:
                bot.reply_to(message, "You are not an admin in this channel.")
                return
        except Exception as e:
            print(f"Error checking admin status: {e}")
            bot.reply_to(message, "Error checking admin status. Make sure the bot is an admin in the channel and try again.")
            return

        # Generate a unique deep link for the channel
        unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        deep_link = f"https://t.me/{user_bot.get_me().username}?start=private_{unique_id}"

        # Store the link information in memory and database
        link_data = {
            "channel_id": channel_id,
            "expiration_time": time.time() + 86400 * 300,  # 30 days expiration for the deep link
            "deep_link": deep_link,
            "type": "private"  # or "request"
        }
        channel_links[unique_id] = link_data

        # Save to MongoDB
        deep_links_collection.update_one(
            {"_id": unique_id},
            {"$set": link_data},
            upsert=True
        )

        
        # Store channel information in MongoDB if it doesn't exist
        channel_info = channels_collection.find_one({"channel_id": channel_id})
        if not channel_info:
            chat_info = bot.get_chat(channel_id)
            channels_collection.insert_one({
                "channel_id": channel_id,
                "title": chat_info.title,
                "username": chat_info.username,
                "added_by": message.from_user.id,
                "added_at": time.time(),
                "clicks": 0,
                "joins": 0,
                "links_generated": 0
            })
            
            # Log new channel registration
            channel_title = chat_info.title
            username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
            log_msg = f"📌 New Channel Registered\nID: {channel_id}\nTitle: {channel_title}\nBy: {username}"
            send_log(log_msg)
        
        bot.reply_to(message, f"Permanent link generated:\n{deep_link}")
        
        # Log link creation
        channel_title = bot.get_chat(channel_id).title
        username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
        expire_time = utc_to_ist(time.time() + 86400 * 30)
        log_msg = f"🔗 New Link Created\nChannel: {channel_title}\nType: Private Link\nGenerated by: {username}\nExpires: {expire_time}"
        send_log(log_msg)
        
    except (ValueError, IndexError):
        bot.reply_to(message, "Invalid channel ID provided.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        bot.reply_to(message, "An unexpected error occurred. Please try again later.")

@bot.message_handler(commands=['reqpost'])
def reqpost_command(message):
    """Handles the /reqpost command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    try:
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "Invalid command. Usage: /reqpost <channel_id>")
            return
        
        channel_id = int(args[1])
        
        # Check if the user is an admin in the channel
        try:
            chat_member = bot.get_chat_member(channel_id, message.from_user.id)
            if chat_member.status not in ["administrator", "creator"]:
                bot.reply_to(message, "You are not an admin in this channel.")
                return
        except Exception as e:
            print(f"Error checking admin status: {e}")
            bot.reply_to(message, "Error checking admin status. Make sure the bot is an admin in the channel and try again.")
            return
        
        # Generate a unique deep link for the channel
        unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        deep_link = f"https://t.me/{user_bot.get_me().username}?start=request_{unique_id}"
        
        # Store the link information in memory and database
        # Store the link information in memory and database
        link_data = {
            "channel_id": channel_id,
            "expiration_time": time.time() + 86400 * 300,  # 30 days expiration for the deep link
            "deep_link": deep_link,
            "type": "request"  # or "request"
        }
        channel_links[unique_id] = link_data

        # Save to MongoDB
        deep_links_collection.update_one(
        {"_id": unique_id},
        {"$set": link_data},
        upsert=True
        )
        
        # Store channel information in MongoDB if it doesn't exist
        channel_info = channels_collection.find_one({"channel_id": channel_id})
        if not channel_info:
            chat_info = bot.get_chat(channel_id)
            channels_collection.insert_one({
                "channel_id": channel_id,
                "title": chat_info.title,
                "username": chat_info.username,
                "added_by": message.from_user.id,
                "added_at": time.time(),
                "clicks": 0,
                "joins": 0,
                "links_generated": 0
            })
            
            # Log new channel registration
            channel_title = chat_info.title
            username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
            log_msg = f"📌 New Channel Registered\nID: {channel_id}\nTitle: {channel_title}\nBy: {username}"
            send_log(log_msg)
        
        bot.reply_to(message, f"Permanent request link generated:\n{deep_link}")
        
        # Log link creation
        channel_title = bot.get_chat(channel_id).title
        username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
        expire_time = utc_to_ist(time.time() + 86400 * 30)
        log_msg = f"🔗 New Link Created\nChannel: {channel_title}\nType: Request Link\nGenerated by: {username}\nExpires: {expire_time}"
        send_log(log_msg)
        
    except (ValueError, IndexError):
        bot.reply_to(message, "Invalid channel ID provided.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        bot.reply_to(message, "An unexpected error occurred. Please try again later.")

@bot.message_handler(func=lambda message: message.text and message.text.startswith("/start private_") or message.text.startswith("/start request_"))
def handle_deeplink_message(message):
    """Handles deep link activation."""
    user = message.from_user
    update_user(user)
    
    parts = message.text.split()
    if len(parts) != 2:
        return
    
    deep_link_text = parts[1]
    link_type = "private" if deep_link_text.startswith("private_") else "request"
    deep_link_suffix = deep_link_text[len("private_"):] if link_type == "private" else deep_link_text[len("request_"):]
    
    # Check if link exists and is valid
    if deep_link_suffix not in channel_links:
        bot.reply_to(message, "Invalid link.")
        return
    
    link_data = channel_links[deep_link_suffix]
    
    # Check if link has expired
    if link_data["expiration_time"] < time.time():
        bot.reply_to(message, "The link has expired.")
        return
    
    # Check cooldown
    current_time = time.time()
    if user.id in user_cooldowns and current_time - user_cooldowns[user.id] < 10:
        remaining = int(10 - (current_time - user_cooldowns[user.id]))
        bot.reply_to(message, f"Please wait {remaining} seconds before requesting another link.")
        return
    
    # Generate appropriate link based on type
    is_request = link_type == "request"
    channel_id = link_data["channel_id"]
    private_link = generate_private_link(channel_id, is_request)
    
    if private_link:
        # Update user cooldown
        user_cooldowns[user.id] = current_time
        
        # Update user stats
        users_collection.update_one(
            {"user_id": user.id},
            {"$inc": {"links_requested": 1}}
        )
        
        # Update channel clicks
        channels_collection.update_one(
            {"channel_id": channel_id},
            {"$inc": {"clicks": 1}}
        )
        
        # Create button with the permanent deep link
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Get this again", url=link_data["deep_link"]))
        
        bot.reply_to(
        message,
        f"<b>⛩️ Join Channel to watch Anime⛩️</b>\n"
        f"<b>👉{private_link}</b>\n"
        f"<b>👉{private_link}</b>",
        parse_mode="HTML",
        reply_markup=markup
        )
    else:
        bot.reply_to(message, "Failed to generate a link. Please try again later.")






# Start the bot
# Start the bots
if __name__ == "__main__":
    # Initialize stats for today
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    stats_collection.update_one(
        {"date": today},
        {"$setOnInsert": {
            "new_users": 0,
            "links_generated": 0,
            "successful_joins": 0
        }},
        upsert=True
    )
    
    # Load existing deep links
    load_deep_links()
    
    send_log("🚀 Bots started!")
    print("Bots are running...")
    
    # Start user bot in a separate thread
    threading.Thread(target=user_bot.infinity_polling, daemon=True).start()
    
    # Start admin bot in the main thread
    bot.infinity_polling()
