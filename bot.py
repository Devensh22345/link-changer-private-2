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

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN', "7430337602:AAHes470_Jry8lghlL4_bo49SKZ5W-stBYo")
USER_BOT_TOKEN = os.environ.get('USER_BOT_TOKEN', "7833128310:AAEoF3shK5Z3EFNsin1gr5BpQyjzLyzyc5A")  # User bot token
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
    anime_button = types.InlineKeyboardButton("🔥 𝐀𝐧𝐢𝐦𝐞 𝐢𝐧 𝐇𝐢𝐧𝐝𝐢", url="https://t.me/+2fsV4nzHvOs2OGNl")
    chat_button = types.InlineKeyboardButton("💬 𝐂𝐡𝐚𝐭 𝐆𝐫𝐨𝐮𝐩", url="https://t.me/dkanime_group")
    markup.add(anime_button, chat_button)

    message_text = (
    "⛩️⛩️ **𝗡𝗲𝘄 𝗔𝗻𝗶𝗺𝗲 𝗶𝗻 𝗛𝗶𝗻𝗱𝗶** ⛩️⛩️\n"
    "[👉 https://t.me/+2fsV4nzHvOs2OGNl](👉https://t.me/+2fsV4nzHvOs2OGNl)\n\n"
    "💬 **𝗔𝗻𝗶𝗺𝗲 𝗦𝗲𝗮𝗿𝗰𝗵 𝗮𝗻𝗱 𝗖𝗵𝗮𝘁 𝗚𝗿𝗼𝘂𝗽** 💬\n"
    "[👉 https://t.me/dkanime_group](https://t.me/dkanime_group)\n\n"
    "🍑 **𝗔𝗱𝘂𝗹𝘁 𝗔𝗻𝗶𝗺𝗲 𝗶𝗻 𝗵𝗶𝗻𝗱𝗶 [𝟭𝟴+]** 🍑\n"
    "[👉 https://t.me/+X-vfMcD-GkY3MzQ1](https://t.me/+X-vfMcD-GkY3MzQ1)"
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

    if deep_link_suffix not in channel_links:
        sent_msg = user_bot.reply_to(message, "Invalid link.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
        return

    link_data = channel_links[deep_link_suffix]

    if link_data["expiration_time"] < time.time():
        sent_msg = user_bot.reply_to(message, "The link has expired.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
        return

    current_time = time.time()
    if user.id in user_cooldowns and current_time - user_cooldowns[user.id] < 10:
        remaining = int(10 - (current_time - user_cooldowns[user.id]))
        sent_msg = user_bot.reply_to(message, f"Please wait {remaining} seconds before requesting another link.")
        threading.Timer(600, delete_message, args=[user_bot, message.chat.id, sent_msg.message_id]).start()
        return

    is_request = link_type == "request"
    channel_id = link_data["channel_id"]
    private_link = generate_private_link(channel_id, is_request)

    if private_link:
        user_cooldowns[user.id] = current_time

        users_collection.update_one(
            {"user_id": user.id},
            {"$inc": {"links_requested": 1}}
        )

        channels_collection.update_one(
            {"channel_id": channel_id},
            {"$inc": {"clicks": 1}}
        )

        try:
            # Get the actual channel name
            
            channel_title = message.chat.title 
        except Exception:
            print(f"[DEBUG] channel_id: {channel_id}")
            channel_title = "the channel"

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("Watch Now", url=private_link),
            types.InlineKeyboardButton("Get this again", url=link_data["deep_link"])
        )

        sent_msg = user_bot.reply_to(
            message,
            f"<b>⛩️ 𝐇𝐞𝐫𝐞 𝐢𝐬 𝐥𝐢𝐧𝐤 𝐟𝐨𝐫 {channel_title} ⛩️</b>\n"
            f"<b>👉 {private_link}</b>\n"
            f"<b>👉 {private_link}</b>",
            parse_mode="HTML",
            reply_markup=markup
        )

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
            "📌 About DK Links\n"
            f"‣ Made By: @MAI_HU_KIRA\n"
            f"‣ Version: 1.0\n"
            f"‣ Stats: {user_count} users | {channel_count} channels\n"
            "Ciao!!"
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(about_text, call.message.chat.id, call.message.message_id)

    elif call.data == "close":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

from telebot import types

# Replace with your actual link channel ID
LINK_CHANNEL_ID = "-1002301713536"  # or the channel's ID, e.g. -1001234567890

@bot.channel_post_handler(commands=["channelpost"])
def handle_channel_post_in_channel(message):
    """Handles the /channelpost command posted in a channel."""
    try:
        channel_id = message.chat.id

        # In channel posts, from_user is None; use sender_chat.title
        channel_title = message.chat.title or "Unnamed Channel"

        # Generate a unique deep link
        unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        bot_username = user_bot.get_me().username
        deep_link = f"https://t.me/{bot_username}?start=private_{unique_id}"

        # Save link info in memory
        link_data = {
            "channel_id": channel_id,
            "expiration_time": time.time() + 86400 * 30,  # 30 days
            "deep_link": deep_link,
            "type": "private"
        }
        channel_links[unique_id] = link_data

        # Save to MongoDB
        deep_links_collection.update_one(
            {"_id": unique_id},
            {"$set": link_data},
            upsert=True
        )

        # Save channel info if new
        if not channels_collection.find_one({"channel_id": channel_id}):
            chat_info = bot.get_chat(channel_id)
            channels_collection.insert_one({
                "channel_id": channel_id,
                "title": chat_info.title,
                "username": chat_info.username,
                "added_by": "unknown (channel post)",
                "added_at": time.time(),
                "clicks": 0,
                "joins": 0,
                "links_generated": 1
            })

            send_log(f"📌 New Channel Registered\nID: {channel_id}\nTitle: {chat_info.title}")

        # Create inline keyboard with the deep link
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔗 Watch and Download", url=deep_link))
        # Send link to link channel
        bot.send_message(
            LINK_CHANNEL_ID,
            f"✅ 𝐇𝐞𝐫𝐞 𝐢𝐬 𝐥𝐢𝐧𝐤 𝐟𝐨𝐫\n"
            f"<b>{channel_title}</b>\n"
            f"<a href='{deep_link}'>𝗪𝗔𝗥𝗖𝗛 𝗔𝗡𝗗 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗</a>",
            parse_mode="HTML",
            reply_markup=markup
        )

        # Reply in the channel
        bot.reply_to(
            message,
            f"✅ 𝐇𝐞𝐫𝐞 𝐢𝐬 𝐭𝐡𝐢𝐬 𝐜𝐡𝐚𝐧𝐧𝐞𝐥 𝐩𝐫𝐢𝐯𝐚𝐭𝐞 𝐥𝐢𝐧𝐤 \n<b>👉 {deep_link}</b>",
            parse_mode="HTML"
        )

        # Log it
        expire_time = utc_to_ist(link_data["expiration_time"])
        send_log(f"🔗 New Link Created\nChannel: {channel_title}\nExpires: {expire_time}")

        # ✅ Delete the command message
        bot.delete_message(channel_id, message.message_id)

    except Exception as e:
        print(f"[ERROR] {e}")
        bot.reply_to(message, "⚠️ Something went wrong while processing your request.")


@bot.channel_post_handler(commands=['reqpost'])
def reqpost_channel_post(message):
    """Handles the /reqpost command posted in the channel."""
    try:
        # Get channel ID from the message
        channel_id = message.chat.id
        
        # Generate a unique deep link for the channel
        unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        bot_username = user_bot.get_me().username
        deep_link = f"https://t.me/{bot_username}?start=request_{unique_id}"

        # Store the link information in memory
        link_data = {
            "channel_id": channel_id,
            "expiration_time": time.time() + 86400 * 300,  # 30 days expiration for the deep link
            "deep_link": deep_link,
            "type": "request"
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
                "added_at": time.time(),
                "clicks": 0,
                "joins": 0,
                "links_generated": 0
            })

            # Log new channel registration
            channel_title = chat_info.title
            log_msg = f"📌 New Channel Registered\nID: {channel_id}\nTitle: {channel_title}"
            send_log(log_msg)


        # Create inline keyboard with the deep link
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔗 Watch and Download", url=deep_link))
        # Send the generated link to the link channel
        bot.send_message(
            LINK_CHANNEL_ID,
            f"✅ 𝐇𝐞𝐫𝐞 𝐢𝐬 𝐥𝐢𝐧𝐤 𝐟𝐨𝐫\n"
            f"<b>{message.chat.title}</b>\n"
            f"<a href='{deep_link}'>𝗪𝗔𝗥𝗖𝗛 𝗔𝗡𝗗 𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗</a>",
            parse_mode="HTML",
            reply_markup=marku
        )

        # Acknowledge in the channel where the command was issued
        bot.reply_to(
            message,
            f"✅ 𝐇𝐞𝐫𝐞 𝐢𝐬 𝐭𝐡𝐢𝐬 𝐜𝐡𝐚𝐧𝐧𝐞𝐥 𝐑𝐞𝐪𝐮𝐞𝐬𝐭 𝐥𝐢𝐧𝐤 \n<b>👉 {deep_link}</b>",
            parse_mode="HTML"
        )

        # Log the link creation
        channel_title = bot.get_chat(channel_id).title
        expire_time = utc_to_ist(time.time() + 86400 * 30)
        log_msg = f"🔗 New Request Link Created\nChannel: {channel_title}\nExpires: {expire_time}"
        send_log(log_msg)

 # ✅ Delete the command message
        bot.delete_message(channel_id, message.message_id)

    except (ValueError, IndexError):
        bot.reply_to(message, "⚠️ Invalid command. Make sure you are using it correctly.")
    except Exception as e:
        print(f"[ERROR] {e}")
        bot.reply_to(message, "⚠️ An unexpected error occurred. Please try again later.")



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

@bot.message_handler(commands=['users'])
def users_command(message):
    """Handles the /users command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    total_users = users_collection.count_documents({})
    active_users = users_collection.count_documents({"status": "active"})
    banned_users = users_collection.count_documents({"status": "banned"})
    
    # Count new users in last 24 hours
    yesterday = time.time() - 86400
    new_users = users_collection.count_documents({"joined": {"$gte": yesterday}})
    
    user_stats = (
        "👥 User Statistics\n"
        f"Total Users: {total_users}\n"
        f"Active Users: {active_users}\n"
        f"Banned Users: {banned_users}\n"
        f"New Users (24h): {new_users}"
    )
    
    bot.reply_to(message, user_stats)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    """Handles the /stats command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    # Get daily stats
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    daily_stats = stats_collection.find_one({"date": today}) or {}
    
    total_users = users_collection.count_documents({})
    new_users = daily_stats.get("new_users", 0)
    total_channels = channels_collection.count_documents({})
    links_generated = daily_stats.get("links_generated", 0)
    
    # Calculate approval rate (successful joins / links generated)
    joins_today = daily_stats.get("successful_joins", 0)
    approval_rate = int((joins_today / links_generated * 100) if links_generated > 0 else 0)
    
    # Find top channel
    top_channel = channels_collection.find_one(
        {"clicks": {"$gt": 0}},
        sort=[("clicks", pymongo.DESCENDING)]
    )
    
    top_channel_name = "None"
    top_clicks = 0
    
    if top_channel:
        top_channel_name = top_channel.get("title", "Unknown")
        top_clicks = top_channel.get("clicks", 0)
    
    stats_msg = (
        "📊 Daily Statistics Report (Pinned)\n"
        f"👥 Total Users: {total_users}\n"
        f"📈 New Today: {new_users}\n"
        f"📢 Managed Channels: {total_channels}\n"
        f"🔗 Links Generated: {links_generated}\n"
        f"✅ Approval Rate: {approval_rate}%\n"
        f"🏆 Top Channel: {top_channel_name} ({top_clicks} clicks)"
    )
    
    bot.reply_to(message, stats_msg)
    
    # Pin stats message in log channel
    pin_log(stats_msg)

@bot.message_handler(commands=['broadcast'])
def broadcast_command(message):
    """Handles the /broadcast command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    # Extract broadcast message
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "Please provide a message to broadcast. Usage: /broadcast <message>")
        return
    
    broadcast_msg = args[1]
    sent_msg = bot.reply_to(message, "Starting broadcast...")
    
    # Log the broadcast message
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    log_msg = f"📢 Broadcast Message\nBy: {username}\nContent: {broadcast_msg}"
    send_log(log_msg)
    
    # Send broadcast
    success_count = 0
    fail_count = 0
    
    for user in users_collection.find({"status": "active"}):
        try:
            bot.send_message(user["user_id"], f"📢 Broadcast Message\n{broadcast_msg}")
            success_count += 1
        except Exception:
            fail_count += 1
    
    bot.edit_message_text(
        f"📣 Broadcast Completed\n✅ Successfully sent: {success_count}\n❌ Failed: {fail_count}",
        sent_msg.chat.id,
        sent_msg.message_id
    )

@bot.message_handler(commands=['ban'])
def ban_command(message):
    """Handles the /ban command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Invalid command. Usage: /ban <user_id or @username>")
        return
    
    target = args[1]
    
    # Check if target is a username or ID
    if target.startswith('@'):
        username = target[1:]
        user = users_collection.find_one({"username": username})
        if not user:
            bot.reply_to(message, f"User {target} not found.")
            return
        target_id = user["user_id"]
    else:
        try:
            target_id = int(target)
            user = users_collection.find_one({"user_id": target_id})
            if not user:
                bot.reply_to(message, f"User with ID {target_id} not found.")
                return
        except ValueError:
            bot.reply_to(message, "Invalid user ID. Please provide a valid ID or username with @.")
            return
    
    # Ban user
    users_collection.update_one(
        {"user_id": target_id},
        {"$set": {"status": "banned"}}
    )
    
    bot.reply_to(message, f"User {target} has been banned.")
    
    # Log ban
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    target_info = f"@{user['username']}" if user.get('username') else f"ID: {target_id}"
    log_msg = f"🚫 User Banned\nUser: {target_info}\nBy: {username}"
    send_log(log_msg)

@bot.message_handler(commands=['unban'])
def unban_command(message):
    """Handles the /unban command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Invalid command. Usage: /unban <user_id or @username>")
        return
    
    target = args[1]
    
    # Check if target is a username or ID
    if target.startswith('@'):
        username = target[1:]
        user = users_collection.find_one({"username": username})
        if not user:
            bot.reply_to(message, f"User {target} not found.")
            return
        target_id = user["user_id"]
    else:
        try:
            target_id = int(target)
            user = users_collection.find_one({"user_id": target_id})
            if not user:
                bot.reply_to(message, f"User with ID {target_id} not found.")
                return
        except ValueError:
            bot.reply_to(message, "Invalid user ID. Please provide a valid ID or username with @.")
            return
    
    # Unban user
    users_collection.update_one(
        {"user_id": target_id},
        {"$set": {"status": "active"}}
    )
    
    bot.reply_to(message, f"User {target} has been unbanned.")
    
    # Log unban
    username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
    target_info = f"@{user['username']}" if user.get('username') else f"ID: {target_id}"
    log_msg = f"✅ User Unbanned\nUser: {target_info}\nBy: {username}"
    send_log(log_msg)

@bot.message_handler(commands=['userinfo'])
def userinfo_command(message):
    """Handles the /userinfo command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Invalid command. Usage: /userinfo <user_id or @username>")
        return
    
    target = args[1]
    
    # Check if target is a username or ID
    if target.startswith('@'):
        username = target[1:]
        user = users_collection.find_one({"username": username})
        if not user:
            bot.reply_to(message, f"User {target} not found.")
            return
    else:
        try:
            target_id = int(target)
            user = users_collection.find_one({"user_id": target_id})
            if not user:
                bot.reply_to(message, f"User with ID {target_id} not found.")
                return
        except ValueError:
            bot.reply_to(message, "Invalid user ID. Please provide a valid ID or username with @.")
            return
    
    # Format user info
    joined_date = utc_to_ist(user.get("joined", 0))
    last_active = utc_to_ist(user.get("last_activity", 0))
    
    user_info = (
        f"👤 User Information\n"
        f"ID: {user['user_id']}\n"
        f"Username: @{user.get('username', 'None')}\n"
        f"Name: {user.get('first_name', '')} {user.get('last_name', '')}\n"
        f"Joined: {joined_date}\n"
        f"Last Activity: {last_active}\n"
        f"Status: {user.get('status', 'active')}\n"
        f"Links Requested: {user.get('links_requested', 0)}\n"
        f"Successful Joins: {user.get('successful_joins', 0)}"
    )
    
    bot.reply_to(message, user_info)

@bot.message_handler(commands=['cooldown'])
def cooldown_command(message):
    """Handles the /cooldown command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    args = message.text.split()
    cooldown_time = 10  # Default cooldown time
    
    if len(args) > 1:
        try:
            cooldown_time = int(args[1])
            if cooldown_time < 0:
                bot.reply_to(message, "Cooldown time must be a positive number.")
                return
        except ValueError:
            bot.reply_to(message, "Invalid cooldown time. Please provide a valid number of seconds.")
            return
    
    # Update cooldown time in settings
    settings_collection = db.settings
    settings_collection.update_one(
        {"setting": "cooldown"},
        {"$set": {"value": cooldown_time}},
        upsert=True
    )
    
    bot.reply_to(message, f"Cooldown time set to {cooldown_time} seconds.")

@bot.message_handler(commands=['list', 'channels'])
def list_channels_command(message):
    """Handles the /list channels command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    channels = list(channels_collection.find().sort("added_at", -1))
    
    if not channels:
        bot.reply_to(message, "No channels registered yet.")
        return
    
    channels_list = "📢 Managed Channels\n"
    
    for channel in channels:
        added_date = datetime.datetime.fromtimestamp(channel.get("added_at", 0)).strftime("%Y-%m-%d")
        channels_list += (
            f"• {channel.get('title', 'Unknown')} ({channel.get('channel_id', 'Unknown')})\n"
            f"  Added: {added_date}\n"
            f"  Clicks: {channel.get('clicks', 0)}, Joins: {channel.get('joins', 0)}\n"
        )
    
    bot.reply_to(message, channels_list)

@bot.message_handler(commands=['removechannel'])
def remove_channel_command(message):
    """Handles the /removechannel command."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, "You don't have permission to use this command.")
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Invalid command. Usage: /removechannel <channel_id>")
        return
    
    try:
        channel_id = int(args[1])
        
        # Find channel in the database
        channel = channels_collection.find_one({"channel_id": channel_id})
        if not channel:
            bot.reply_to(message, f"Channel with ID {channel_id} not found.")
            return
        
        # Remove channel from database
        channels_collection.delete_one({"channel_id": channel_id})
        
        # Invalidate all deep links for this channel
        for key in list(channel_links.keys()):
            if channel_links[key]["channel_id"] == channel_id:
                channel_links[key]["expiration_time"] = 0
        
        bot.reply_to(message, f"Channel {channel.get('title', channel_id)} has been removed and all links expired.")
        
        # Log channel removal
        username = f"@{message.from_user.username}" if message.from_user.username else f"ID: {message.from_user.id}"
        log_msg = f"❌ Channel Removed\nChannel: {channel.get('title', channel_id)}\nID: {channel_id}\nBy: {username}"
        send_log(log_msg)
        
    except ValueError:
        bot.reply_to(message, "Invalid channel ID. Please provide a valid ID.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        bot.reply_to(message, "An unexpected error occurred. Please try again later.")

# Schedule daily stats
def schedule_daily_stats():
    """Schedule daily statistics report."""
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    # Get daily stats
    daily_stats = stats_collection.find_one({"date": today}) or {}
    
    total_users = users_collection.count_documents({})
    new_users = daily_stats.get("new_users", 0)
    total_channels = channels_collection.count_documents({})
    links_generated = daily_stats.get("links_generated", 0)
    
    # Calculate approval rate
    joins_today = daily_stats.get("successful_joins", 0)
    approval_rate = int((joins_today / links_generated * 100) if links_generated > 0 else 0)
    
    # Find top channel
    top_channel = channels_collection.find_one(
        {"clicks": {"$gt": 0}},
        sort=[("clicks", pymongo.DESCENDING)]
    )
    
    top_channel_name = "None"
    top_clicks = 0
    
    if top_channel:
        top_channel_name = top_channel.get("title", "Unknown")
        top_clicks = top_channel.get("clicks", 0)
    
    stats_msg = (
        f"📅 Daily Report - {now.strftime('%b %d')}\n"
        f"New Users: {new_users}\n"
        f"Links Generated: {links_generated}\n"
        f"Conversion Rate: {approval_rate}%\n"
        f"Top Channel: {top_channel_name} ({top_clicks} clicks)"
    )
    
    # Pin stats message in log channel
    pin_log(stats_msg)

# Setup scheduler for daily stats
import threading
import schedule

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

# Schedule daily stats at midnight IST (6:30 PM UTC)
schedule.every().day.at("18:30").do(schedule_daily_stats)

# Start the scheduler in a separate thread
scheduler_thread = threading.Thread(target=run_schedule)
scheduler_thread.daemon = True
scheduler_thread.start()


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
