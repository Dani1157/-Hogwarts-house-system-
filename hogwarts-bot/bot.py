from discord import app_commands
import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import Button, View, Select, Modal, TextInput
import json
import os
from datetime import datetime, timedelta
import random
import asyncio
from typing import Optional
import math
from collections import defaultdict
import aiohttp
from io import BytesIO
import time

# ==========================================
# BACKGROUND TASKS DEFINITIONS
# ==========================================
@tasks.loop(hours=1)
async def check_missed_checkins():
    """Check for missed check-ins and deduct points"""
    today = datetime.now().strftime('%Y-%m-%d')
    for user_id, check in data['checkins'].items():
        if check['last'] != today and user_id in data['users']:
            house = data['users'][user_id]['house']
            data['houses'][house]['points'] = max(0, data['houses'][house]['points'] - 5)
    save_data()

@tasks.loop(hours=24)
async def weekly_reset():
    """Reset weekly points every Monday"""
    if datetime.now().weekday() == 0:
        for house in data['houses']: 
            data['houses'][house]['weekly'] = 0
        save_data()

@tasks.loop(hours=24)
async def monthly_reset():
    """Reset monthly points on the 1st"""
    if datetime.now().day == 1:
        for house in data['houses']: 
            data['houses'][house]['monthly'] = 0
        save_data()

@tasks.loop(hours=12)
async def daily_bonus():
    """Give random bonus points sometimes"""
    if random.random() < 0.1:
        house = random.choice(list(data['houses'].keys()))
        bonus = random.randint(10, 50)
        data['houses'][house]['points'] += bonus
        data['history'].append({'timestamp': datetime.now().isoformat(), 'type': 'bonus', 'house': house, 'points': bonus})
        save_data()

@tasks.loop(hours=6)
async def pet_care_check():
    """Update pet stats periodically"""
    for user_id, user in data['users'].items():
        if user.get('pet'):
            user['pet_happiness'] = max(0, user.get('pet_happiness', 80) - random.randint(1, 3))
            user['pet_hunger'] = min(100, user.get('pet_hunger', 10) + random.randint(1, 2))
    save_data()

@tasks.loop(hours=24)
async def daily_quest_refresh():
    """Refresh daily quests at midnight"""
    pass

@tasks.loop(hours=1)
async def check_marathons():
    """Check marathon winners"""
    now = datetime.now()
    for mid, marathon in list(data.get('marathons', {}).items()):
        if datetime.fromisoformat(marathon['end_time']) < now:
            if marathon['participants']:
                winner_id = max(marathon['participants'].items(), key=lambda x: x[1]['checkins'])[0]
                house = data['users'][winner_id]['house']
                data['houses'][house]['points'] += marathon['prize']
                data['users'][winner_id]['points_contributed'] += marathon['prize']
            del data['marathons'][mid]
    save_data()

@tasks.loop(minutes=1)
async def check_brewing_potions():
    """Check for completed potions"""
    now = datetime.now()
    for user_id, user in data['users'].items():
        if 'brewing' in user:
            completed = []
            for potion_id, brew_data in user['brewing'].items():
                complete_time = datetime.fromisoformat(brew_data['complete_time'])
                if now >= complete_time:
                    completed.append(potion_id)
            
            for potion_id in completed:
                if potion_id in POTION_RECIPES:
                    potion = POTION_RECIPES[potion_id]
                    if 'inventory' not in user:
                        user['inventory'] = []
                    user['inventory'].append(potion_id)
                    user['points_contributed'] += potion['base_points']
                    user['xp'] = user.get('xp', 0) + potion['xp_reward']
                    del user['brewing'][potion_id]
    save_data()

@tasks.loop(hours=1)
async def check_quest_expiry():
    """Check for expired daily/weekly quests"""
    now = datetime.now()
    
    for user_id, user in data['users'].items():
        if 'quests' in user:
            expired = []
            for qid, progress in user['quests'].items():
                if qid in QUESTS:
                    quest = QUESTS[qid]
                    if 'time_limit' in quest:
                        started = datetime.fromisoformat(progress['started'])
                        if now - started > timedelta(hours=quest['time_limit']):
                            expired.append(qid)
            
            for qid in expired:
                del user['quests'][qid]
    
    save_data()

# ==========================================
# BOT SETUP
# ==========================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
# ==========================================
# BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print(f'📊 Connected to {len(bot.guilds)} servers')
    
    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Synced {len(synced)} slash commands!")
        for cmd in synced:
            print(f"   • /{cmd.name}")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")
    
    # Start background tasks
    try:
        # Check if these tasks exist before starting them
        if 'check_missed_checkins' in dir():
            check_missed_checkins.start()
        if 'weekly_reset' in dir():
            weekly_reset.start()
        if 'monthly_reset' in dir():
            monthly_reset.start()
        if 'daily_bonus' in dir():
            daily_bonus.start()
        if 'pet_care_check' in dir():
            pet_care_check.start()
        if 'daily_quest_refresh' in dir():
            daily_quest_refresh.start()
        if 'check_marathons' in dir():
            check_marathons.start()
        if 'check_brewing_potions' in dir():
            check_brewing_potions.start()
        if 'check_quest_expiry' in dir():
            check_quest_expiry.start()
        print("✅ Background tasks started!")
    except Exception as e:
        print(f"⚠️ Error starting tasks: {e}")
    
    # Set status
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Hogwarts | /help"
            )
        )
        print("✅ Status updated!")
    except Exception as e:
        print(f"⚠️ Error setting status: {e}")

# ==========================================
# CONSTANTS & CONFIG
# ==========================================
DATA_FILE = 'data/bot_data.json'

HOUSE_DATA = {
    'gryffindor': {
        'name': 'Gryffindor', 'color': 0x740001, 'emoji': '🦁',
        'founder': 'Godric Gryffindor', 'animal': 'Lion', 'element': 'Fire',
        'ghost': 'Nearly Headless Nick', 'common_room': 'Gryffindor Tower',
        'traits': ['Bravery', 'Courage', 'Nerve', 'Chivalry', 'Daring'],
        'mascot': '🦁', 'colors': ['Scarlet', 'Gold'],
        'welcome_message': "You might belong in Gryffindor, Where dwell the brave at heart!",
        'image_url': 'https://i.imgur.com/8lY7qUu.png',
        'password': 'courage', 'secret_passage': 'Behind the portrait of the Fat Lady',
        'house_cup_wins': 0, 'quidditch_wins': 0,
        'famous_members': ['Harry Potter', 'Hermione Granger', 'Ron Weasley', 'Albus Dumbledore']
    },
    'slytherin': {
        'name': 'Slytherin', 'color': 0x1a472a, 'emoji': '🐍',
        'founder': 'Salazar Slytherin', 'animal': 'Serpent', 'element': 'Water',
        'ghost': 'Bloody Baron', 'common_room': 'Slytherin Dungeon',
        'traits': ['Ambition', 'Cunning', 'Leadership', 'Resourcefulness', 'Determination'],
        'mascot': '🐍', 'colors': ['Green', 'Silver'],
        'welcome_message': "Or perhaps in Slytherin, You'll make your real friends!",
        'image_url': 'https://i.imgur.com/8lY7qUu.png',
        'password': 'ambition', 'secret_passage': 'Through the dungeons behind a tapestry',
        'house_cup_wins': 0, 'quidditch_wins': 0,
        'famous_members': ['Severus Snape', 'Draco Malfoy', 'Tom Riddle', 'Horace Slughorn']
    },
    'ravenclaw': {
        'name': 'Ravenclaw', 'color': 0x0e1a40, 'emoji': '🦅',
        'founder': 'Rowena Ravenclaw', 'animal': 'Eagle', 'element': 'Air',
        'ghost': 'Grey Lady', 'common_room': 'Ravenclaw Tower',
        'traits': ['Wit', 'Learning', 'Wisdom', 'Creativity', 'Intelligence'],
        'mascot': '🦅', 'colors': ['Blue', 'Bronze'],
        'welcome_message': "Or yet in wise old Ravenclaw, If you've a ready mind!",
        'image_url': 'https://i.imgur.com/8lY7qUu.png',
        'password': 'wit', 'secret_passage': 'Behind a bookshelf in the library',
        'house_cup_wins': 0, 'quidditch_wins': 0,
        'famous_members': ['Luna Lovegood', 'Cho Chang', 'Gilderoy Lockhart', 'Sybill Trelawney']
    },
    'hufflepuff': {
        'name': 'Hufflepuff', 'color': 0xecb939, 'emoji': '🦡',
        'founder': 'Helga Hufflepuff', 'animal': 'Badger', 'element': 'Earth',
        'ghost': 'Fat Friar', 'common_room': 'Hufflepuff Basement',
        'traits': ['Loyalty', 'Patience', 'Dedication', 'Fair Play', 'Hard Work'],
        'mascot': '🦡', 'colors': ['Yellow', 'Black'],
        'welcome_message': "For Hufflepuff, hard workers were Most worthy of admission!",
        'image_url': 'https://i.imgur.com/8lY7qUu.png',
        'password': 'loyalty', 'secret_passage': 'Near the kitchens behind a barrel',
        'house_cup_wins': 0, 'quidditch_wins': 0,
        'famous_members': ['Cedric Diggory', 'Nymphadora Tonks', 'Newt Scamander', 'Pomona Sprout']
    }
}

SPELL_QUOTES = [
    "Wingardium Leviosa! ✨", "Expecto Patronum! 🪄", "Lumos! 💡",
    "Nox! 🌙", "Alohomora! 🔓", "Accio! 🪄", "Stupefy! ⚡",
    "Expelliarmus! 🛡️", "Riddikulus! 😂", "Obliviate! 🌀",
    "Sectumsempra! 🔪", "Crucio! 💢", "Imperio! 👁️", "Avada Kedavra! 💀"
]

# ==========================================
# WAND DATA WITH FULL DETAILS
# ==========================================
WANDS = {
    'phoenix': {
        'name': 'Phoenix Feather Wand', 'price': 500, 'power': 50,
        'description': 'Very powerful, chooses the worthy', 'emoji': '🔥',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0xff6b6b,
        'rarity': 'legendary', 'spells': ['Expecto Patronum', 'Phoenix Song', 'Rebirth'],
        'bonus': '+20% spell power on weekends', 'core': 'Phoenix Feather',
        'wood': 'Holly', 'length': '11 inches', 'flexibility': 'Nice and supple',
        'founder': 'Godric Gryffindor', 'magic_type': 'Light', 'duel_bonus': 15
    },
    'dragon': {
        'name': 'Dragon Heartstring Wand', 'price': 400, 'power': 40,
        'description': 'Powerful and loyal', 'emoji': '🐉',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0xff4444,
        'rarity': 'rare', 'spells': ['Fiendfyre', 'Dragon Breath', 'Firestorm'],
        'bonus': '+15% power in duels', 'core': 'Dragon Heartstring',
        'wood': 'Hawthorn', 'length': '12.5 inches', 'flexibility': 'Slightly springy',
        'founder': 'Salazar Slytherin', 'magic_type': 'Dark', 'duel_bonus': 20
    },
    'unicorn': {
        'name': 'Unicorn Hair Wand', 'price': 300, 'power': 30,
        'description': 'Consistent and pure magic', 'emoji': '🦄',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0xff99cc,
        'rarity': 'rare', 'spells': ['Healing Touch', 'Purify', 'Light Shield'],
        'bonus': '+10% healing effects', 'core': 'Unicorn Hair',
        'wood': 'Cherry', 'length': '10.75 inches', 'flexibility': 'Quite flexible',
        'founder': 'Rowena Ravenclaw', 'magic_type': 'Light', 'duel_bonus': 10
    },
    'thestral': {
        'name': 'Thestral Hair Wand', 'price': 450, 'power': 45,
        'description': 'Only the worthy can wield', 'emoji': '🐴',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0x2c3e50,
        'rarity': 'legendary', 'spells': ['Death Sight', 'Shadow Walk', 'Soul Bond'],
        'bonus': '+25% stealth', 'core': 'Thestral Hair',
        'wood': 'Elder', 'length': '13 inches', 'flexibility': 'Unyielding',
        'founder': 'Helga Hufflepuff', 'magic_type': 'Neutral', 'duel_bonus': 25
    },
    'veela': {
        'name': 'Veela Hair Wand', 'price': 350, 'power': 35,
        'description': 'Temperamental but powerful', 'emoji': '💇‍♀️',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0xff69b4,
        'rarity': 'rare', 'spells': ['Charm', 'Allure', 'Emotion Control'],
        'bonus': '+15% charm spells', 'core': 'Veela Hair',
        'wood': 'Aspen', 'length': '9.5 inches', 'flexibility': 'Swishy',
        'founder': 'Fleur Delacour', 'magic_type': 'Charm', 'duel_bonus': 12
    },
    'basilisk': {
        'name': 'Basilisk Horn Wand', 'price': 600, 'power': 60,
        'description': 'Extremely rare and dangerous', 'emoji': '🐍',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0x2ecc71,
        'rarity': 'mythic', 'spells': ['Petrify', 'Venom Strike', 'Serpent Speech'],
        'bonus': '+30% dark magic', 'core': 'Basilisk Horn',
        'wood': 'Yew', 'length': '14 inches', 'flexibility': 'Very rigid',
        'founder': 'Salazar Slytherin', 'magic_type': 'Dark', 'duel_bonus': 30
    },
    'elder': {
        'name': 'Elder Wand', 'price': 10000, 'power': 100,
        'description': 'The Deathstick, most powerful wand ever', 'emoji': '👑',
        'image_url': 'https://i.imgur.com/Y6kYqUu.png', 'color': 0x000000,
        'rarity': 'mythic', 'spells': ['ALL SPELLS', 'Death Magic', 'Immortality'],
        'bonus': '+100% all magic', 'core': 'Thestral Tail Hair',
        'wood': 'Elder', 'length': '15 inches', 'flexibility': 'Legendary',
        'founder': 'Death', 'magic_type': 'Death', 'duel_bonus': 100
    }
}

# ==========================================
# PET DATA WITH FULL DETAILS
# ==========================================
PETS = {
    'owl': {
        'name': 'Snowy Owl', 'price': 200, 'bonus': '+10 daily check-in',
        'emoji': '🦉', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0xecf0f1, 'rarity': 'common', 'ability': 'Delivers mail, finds secrets',
        'hunger': 10, 'happiness': 80, 'special': 'Can find hidden items',
        'food': ['Mouse', 'Fish', 'Owl Treats'], 'max_hunger': 100,
        'favorite_food': 'Mouse', 'evolves_at': 100
    },
    'cat': {
        'name': 'Kneazle Cat', 'price': 150, 'bonus': '+5 defense',
        'emoji': '🐱', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0xf39c12, 'rarity': 'common', 'ability': 'Detects danger, loyal companion',
        'hunger': 15, 'happiness': 90, 'special': 'Warns of untrustworthy people',
        'food': ['Fish', 'Cat Food', 'Milk'], 'max_hunger': 100,
        'favorite_food': 'Fish', 'evolves_at': 150
    },
    'toad': {
        'name': 'Giant Toad', 'price': 100, 'bonus': '+5 luck',
        'emoji': '🐸', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0x27ae60, 'rarity': 'common', 'ability': 'Brings good fortune',
        'hunger': 5, 'happiness': 70, 'special': 'Can jump really high',
        'food': ['Flies', 'Worms', 'Toad Treats'], 'max_hunger': 100,
        'favorite_food': 'Flies', 'evolves_at': 80
    },
    'rat': {
        'name': 'Pettigrew\'s Rat', 'price': 50, 'bonus': '+10 stealth',
        'emoji': '🐀', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0x7f8c8d, 'rarity': 'common', 'ability': 'Sneaky, finds hidden things',
        'hunger': 20, 'happiness': 60, 'special': 'Can transform (sometimes)',
        'food': ['Cheese', 'Grains', 'Rat Treats'], 'max_hunger': 100,
        'favorite_food': 'Cheese', 'evolves_at': 120
    },
    'phoenix': {
        'name': 'Baby Phoenix', 'price': 1000, 'bonus': '+50 to everything',
        'emoji': '🔥', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0xe74c3c, 'rarity': 'mythic', 'ability': 'Rebirth, healing tears',
        'hunger': 30, 'happiness': 100, 'special': 'Can resurrect once',
        'food': ['Phoenix Tears', 'Sunlight', 'Magic Dust'], 'max_hunger': 100,
        'favorite_food': 'Phoenix Tears', 'evolves_at': 500
    },
    'dragon': {
        'name': 'Dragon Hatchling', 'price': 2000, 'bonus': '+100 power',
        'emoji': '🐉', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0xc0392b, 'rarity': 'legendary', 'ability': 'Breathes fire, flies fast',
        'hunger': 50, 'happiness': 85, 'special': 'Can be ridden in Quidditch',
        'food': ['Meat', 'Coal', 'Dragon Treats'], 'max_hunger': 100,
        'favorite_food': 'Meat', 'evolves_at': 300
    },
    'hippogriff': {
        'name': 'Hippogriff', 'price': 1500, 'bonus': '+75 flying',
        'emoji': '🦅🐴', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0xd35400, 'rarity': 'legendary', 'ability': 'Fly anywhere, proud creature',
        'hunger': 40, 'happiness': 95, 'special': 'Must bow first',
        'food': ['Insects', 'Meat', 'Hippogriff Feed'], 'max_hunger': 100,
        'favorite_food': 'Insects', 'evolves_at': 250
    },
    'house_elf': {
        'name': 'House Elf', 'price': 800, 'bonus': '+30 chores',
        'emoji': '🧦', 'image_url': 'https://i.imgur.com/Y6kYqUu.png',
        'color': 0x16a085, 'rarity': 'rare', 'ability': 'Cleans, cooks, apparates',
        'hunger': 20, 'happiness': 70, 'special': 'Can get you socks!',
        'food': ['House Elf Food', 'Socks', 'Freedom'], 'max_hunger': 100,
        'favorite_food': 'Socks', 'evolves_at': 200
    }
}
# ==========================================
# CHEST REWARDS DATA
# ==========================================
CHEST_REWARDS = {
    'common': {
        'name': '📦 Common Chest', 'price': 100, 'color': 0x95a5a6,
        'rewards': [
            {'type': 'points', 'min': 10, 'max': 50, 'chance': 50},
            {'type': 'xp', 'min': 20, 'max': 100, 'chance': 30},
            {'type': 'item', 'items': ['Potion', 'Spell Scroll', 'Magic Bean', 'Chocolate Frog'], 'chance': 20}
        ],
        'image': 'https://i.imgur.com/Y6kYqUu.png', 'min_open': 1, 'max_open': 10,
        'guaranteed': {'item': 'Chocolate Frog', 'chance': 5}
    },
    'rare': {
        'name': '🎁 Rare Chest', 'price': 250, 'color': 0x3498db,
        'rewards': [
            {'type': 'points', 'min': 50, 'max': 200, 'chance': 40},
            {'type': 'xp', 'min': 100, 'max': 500, 'chance': 35},
            {'type': 'item', 'items': ['Rare Wand Core', 'Magical Artifact', 'Ancient Tome', 'Time Turner Piece'], 'chance': 25}
        ],
        'image': 'https://i.imgur.com/Y6kYqUu.png', 'min_open': 1, 'max_open': 8,
        'guaranteed': {'item': 'Rare Core', 'chance': 10}
    },
    'legendary': {
        'name': '👑 Legendary Chest', 'price': 500, 'color': 0xf1c40f,
        'rewards': [
            {'type': 'points', 'min': 200, 'max': 500, 'chance': 30},
            {'type': 'xp', 'min': 500, 'max': 1000, 'chance': 30},
            {'type': 'item', 'items': ['Phoenix Feather', 'Dragon Egg', 'Elder Wand Piece', 'Resurrection Stone Shard'], 'chance': 40}
        ],
        'image': 'https://i.imgur.com/Y6kYqUu.png', 'min_open': 1, 'max_open': 5,
        'guaranteed': {'item': 'Legendary Shard', 'chance': 15}
    },
    'mythic': {
        'name': '✨ Mythic Chest', 'price': 1000, 'color': 0x9b59b6,
        'rewards': [
            {'type': 'points', 'min': 500, 'max': 1000, 'chance': 25},
            {'type': 'xp', 'min': 1000, 'max': 2000, 'chance': 25},
            {'type': 'item', 'items': ['Resurrection Stone', 'Invisibility Cloak', 'Elder Wand', 'Marauders Map'], 'chance': 50}
        ],
        'image': 'https://i.imgur.com/Y6kYqUu.png', 'min_open': 1, 'max_open': 3,
        'guaranteed': {'item': 'Deathly Hallow', 'chance': 1}
    }
}

# ==========================================
# QUEST DATA (EXPANDED)
# ==========================================
QUESTS = {
    # Daily Quests (repeatable)
    'daily_checkin': {
        'name': '📅 Daily Ritual',
        'description': 'Check in to Hogwarts for 3 days in a row',
        'type': 'checkin_streak',
        'target': 3,
        'reward_points': 50,
        'reward_xp': 100,
        'reward_items': ['Chocolate Frog'],
        'emoji': '📅',
        'difficulty': 'easy',
        'repeatable': True,
        'time_limit': 24,  # hours
        'category': 'daily'
    },
    'daily_duel': {
        'name': '⚔️ Daily Duelist',
        'description': 'Win 2 duels today',
        'type': 'duel_wins',
        'target': 2,
        'reward_points': 75,
        'reward_xp': 150,
        'reward_items': ['Duel Trophy'],
        'emoji': '⚔️',
        'difficulty': 'medium',
        'repeatable': True,
        'time_limit': 24,
        'category': 'daily'
    },
    'daily_quidditch': {
        'name': '🧹 Quidditch Practice',
        'description': 'Play 3 games of Quidditch',
        'type': 'quidditch_games',
        'target': 3,
        'reward_points': 60,
        'reward_xp': 120,
        'reward_items': ['Broom Polish'],
        'emoji': '🧹',
        'difficulty': 'easy',
        'repeatable': True,
        'time_limit': 24,
        'category': 'daily'
    },
    'daily_trivia': {
        'name': '📚 Trivia Master',
        'description': 'Answer 5 trivia questions correctly',
        'type': 'trivia_wins',
        'target': 5,
        'reward_points': 80,
        'reward_xp': 160,
        'reward_items': ['Spell Scroll'],
        'emoji': '📚',
        'difficulty': 'medium',
        'repeatable': True,
        'time_limit': 24,
        'category': 'daily'
    },
    'daily_points': {
        'name': '💰 Point Collector',
        'description': 'Earn 100 points for your house',
        'type': 'points_earned',
        'target': 100,
        'reward_points': 40,
        'reward_xp': 80,
        'reward_items': ['Magic Coin'],
        'emoji': '💰',
        'difficulty': 'easy',
        'repeatable': True,
        'time_limit': 24,
        'category': 'daily'
    },
    
    # Weekly Quests (repeatable weekly)
    'weekly_house_champion': {
        'name': '🏆 House Champion',
        'description': 'Earn 500 points for your house this week',
        'type': 'weekly_points',
        'target': 500,
        'reward_points': 200,
        'reward_xp': 500,
        'reward_items': ['House Trophy', 'Rare Core'],
        'emoji': '🏆',
        'difficulty': 'hard',
        'repeatable': True,
        'time_limit': 168,
        'category': 'weekly'
    },
    'weekly_duel_champion': {
        'name': '⚔️ Duel Champion',
        'description': 'Win 10 duels this week',
        'type': 'weekly_duels',
        'target': 10,
        'reward_points': 250,
        'reward_xp': 600,
        'reward_items': ['Duelist Medal', 'Rare Wand'],
        'emoji': '⚔️',
        'difficulty': 'hard',
        'repeatable': True,
        'time_limit': 168,
        'category': 'weekly'
    },
    'weekly_quidditch_star': {
        'name': '🧹 Quidditch Star',
        'description': 'Score 500 points in Quidditch',
        'type': 'weekly_quidditch',
        'target': 500,
        'reward_points': 200,
        'reward_xp': 500,
        'reward_items': ['Golden Snitch', 'Broom Upgrade'],
        'emoji': '🧹',
        'difficulty': 'hard',
        'repeatable': True,
        'time_limit': 168,
        'category': 'weekly'
    },
    'weekly_trivia_legend': {
        'name': '📚 Trivia Legend',
        'description': 'Answer 25 trivia questions correctly',
        'type': 'weekly_trivia',
        'target': 25,
        'reward_points': 225,
        'reward_xp': 550,
        'reward_items': ['Ancient Tome', 'Wisdom Scroll'],
        'emoji': '📚',
        'difficulty': 'hard',
        'repeatable': True,
        'time_limit': 168,
        'category': 'weekly'
    },
    'weekly_explorer': {
        'name': '🗺️ Master Explorer',
        'description': 'Visit 10 different locations on the Marauder\'s Map',
        'type': 'weekly_locations',
        'target': 10,
        'reward_points': 175,
        'reward_xp': 400,
        'reward_items': ['Map Piece', 'Compass'],
        'emoji': '🗺️',
        'difficulty': 'medium',
        'repeatable': True,
        'time_limit': 168,
        'category': 'weekly'
    },
    
    # Special Quests (one-time)
    'first_wand': {
        'name': '🪄 The Wand Chooses',
        'description': 'Purchase your first wand from Ollivanders',
        'type': 'first_wand',
        'target': 1,
        'reward_points': 100,
        'reward_xp': 200,
        'reward_items': ['Wand Polish', 'Spell Book'],
        'emoji': '🪄',
        'difficulty': 'easy',
        'repeatable': False,
        'category': 'special'
    },
    'first_pet': {
        'name': '🐾 Magical Companion',
        'description': 'Adopt your first pet',
        'type': 'first_pet',
        'target': 1,
        'reward_points': 100,
        'reward_xp': 200,
        'reward_items': ['Pet Treats', 'Toy'],
        'emoji': '🐾',
        'difficulty': 'easy',
        'repeatable': False,
        'category': 'special'
    },
    'first_secret': {
        'name': '🔍 Secret Seeker',
        'description': 'Find your first secret room',
        'type': 'first_secret',
        'target': 1,
        'reward_points': 150,
        'reward_xp': 300,
        'reward_items': ['Secret Map', 'Torch'],
        'emoji': '🔍',
        'difficulty': 'medium',
        'repeatable': False,
        'category': 'special'
    },
    'first_chest': {
        'name': '🎁 Treasure Hunter',
        'description': 'Open your first chest',
        'type': 'first_chest',
        'target': 1,
        'reward_points': 50,
        'reward_xp': 100,
        'reward_items': ['Chest Key'],
        'emoji': '🎁',
        'difficulty': 'easy',
        'repeatable': False,
        'category': 'special'
    },
    
    # Achievement Quests
    'wand_collector': {
        'name': '🪄 Wand Collector',
        'description': 'Own 3 different wands',
        'type': 'wands_owned',
        'target': 3,
        'reward_points': 300,
        'reward_xp': 600,
        'reward_items': ['Wand Display Case', 'Rare Core'],
        'emoji': '🪄',
        'difficulty': 'hard',
        'repeatable': False,
        'category': 'achievement'
    },
    'pet_collector': {
        'name': '🐾 Pet Collector',
        'description': 'Own 5 different pets',
        'type': 'pets_owned',
        'target': 5,
        'reward_points': 350,
        'reward_xp': 700,
        'reward_items': ['Pet Playground', 'Rare Pet Food'],
        'emoji': '🐾',
        'difficulty': 'hard',
        'repeatable': False,
        'category': 'achievement'
    },
    'secret_master': {
        'name': '🔍 Secret Master',
        'description': 'Find 10 secret rooms',
        'type': 'secrets_found',
        'target': 10,
        'reward_points': 500,
        'reward_xp': 1000,
        'reward_items': ['Master Key', 'Hidden Passage Map'],
        'emoji': '🔍',
        'difficulty': 'legendary',
        'repeatable': False,
        'category': 'achievement'
    },
    'chest_addict': {
        'name': '🎁 Chest Addict',
        'description': 'Open 50 chests',
        'type': 'chests_opened',
        'target': 50,
        'reward_points': 400,
        'reward_xp': 800,
        'reward_items': ['Golden Key', 'Loot Magnet'],
        'emoji': '🎁',
        'difficulty': 'hard',
        'repeatable': False,
        'category': 'achievement'
    },
    'duel_legend': {
        'name': '⚔️ Duel Legend',
        'description': 'Win 50 duels',
        'type': 'duels_won',
        'target': 50,
        'reward_points': 600,
        'reward_xp': 1200,
        'reward_items': ['Legendary Sword', 'Duel Arena Pass'],
        'emoji': '⚔️',
        'difficulty': 'legendary',
        'repeatable': False,
        'category': 'achievement'
    },
    'quidditch_legend': {
        'name': '🧹 Quidditch Legend',
        'description': 'Score 5000 Quidditch points',
        'type': 'quidditch_points',
        'target': 5000,
        'reward_points': 600,
        'reward_xp': 1200,
        'reward_items': ['Golden Broom', 'Quidditch Trophy'],
        'emoji': '🧹',
        'difficulty': 'legendary',
        'repeatable': False,
        'category': 'achievement'
    },
    'trivia_god': {
        'name': '📚 Trivia God',
        'description': 'Answer 100 trivia questions correctly',
        'type': 'trivia_wins_total',
        'target': 100,
        'reward_points': 500,
        'reward_xp': 1000,
        'reward_items': ['Omniscient Orb', 'Knowledge Stone'],
        'emoji': '📚',
        'difficulty': 'legendary',
        'repeatable': False,
        'category': 'achievement'
    }
}

# ==========================================
# SECRET ROOMS DATA (EXPANDED)
# ==========================================
SECRET_ROOMS = {
    'room_of_requirement': {
        'name': 'Room of Requirement',
        'password': 'need',
        'description': 'A magical room that appears when you truly need it. It transforms into whatever you require.',
        'treasure': 'Any item you desire',
        'danger': 'None - but it can be addictive',
        'found_by': 'Dobby',
        'hint': 'Think of what you need most... three times',
        'points': 300,
        'xp': 500,
        'item': 'Marauders Map Piece',
        'location': 'Seventh Floor',
        'entrance': 'Across from the tapestry of Barnabas the Barmy',
        'history': 'Helped the DA practice magic',
        'emoji': '🚪'
    },
    'chamber_of_secrets': {
        'name': 'Chamber of Secrets',
        'password': 'open',
        'description': 'Deep beneath the school, home of the Basilisk. Built by Salazar Slytherin.',
        'treasure': 'Basilisk fangs, Parseltongue ability',
        'danger': 'Basilisk (giant serpent)',
        'found_by': 'Harry Potter',
        'hint': 'Speak to the snakes... in their tongue',
        'points': 500,
        'xp': 1000,
        'item': 'Basilisk Fang',
        'location': "Girl's Bathroom, Second Floor",
        'entrance': 'Sink with a snake carving',
        'history': 'Where Ginny was taken, where Harry killed the Basilisk',
        'emoji': '🐍'
    },
    'shrieking_shack': {
        'name': 'Shrieking Shack',
        'password': 'howl',
        'description': 'The most haunted building in Britain. Actually built for Remus Lupin during his transformations.',
        'treasure': 'Werewolf secrets',
        'danger': 'Werewolf (on full moon)',
        'found_by': 'Remus Lupin',
        'hint': 'Listen for the howls... especially during the full moon',
        'points': 400,
        'xp': 800,
        'item': 'Wolfsbane Potion',
        'location': 'Hogsmeade',
        'entrance': 'Through the Whomping Willow tunnel',
        'history': 'Where Sirius Black hid, where the trio confronted Peter Pettigrew',
        'emoji': '🏚️'
    },
    'astronomy_tower': {
        'name': 'Astronomy Tower',
        'password': 'stars',
        'description': 'The tallest tower at Hogwarts, used for Astronomy classes and fateful events.',
        'treasure': 'Ancient star charts',
        'danger': 'Death Eaters',
        'found_by': 'Dumbledore',
        'hint': 'Look to the heavens... follow the brightest star',
        'points': 350,
        'xp': 600,
        'item': 'Star Chart',
        'location': 'West Tower',
        'entrance': 'Spiral staircase from the seventh floor',
        'history': 'Where Dumbledore fell, where the Death Eaters attacked',
        'emoji': '🔭'
    },
    'prefects_bathroom': {
        'name': "Prefect's Bathroom",
        'password': 'pinefresh',
        'description': 'Luxurious marble bathroom with a swimming pool-sized bath.',
        'treasure': 'Mermaid secrets',
        'danger': 'Moaning Myrtle',
        'found_by': 'Cedric Diggory',
        'hint': 'Bubbles lead the way... and follow the mermaid song',
        'points': 200,
        'xp': 300,
        'item': 'Mermaid Scale',
        'location': 'Fourth Floor',
        'entrance': 'Door with a mermaid knocker',
        'history': 'Where Harry solved the Golden Egg clue',
        'emoji': '🛁'
    },
    'divination_classroom': {
        'name': 'Divination Classroom',
        'password': 'future',
        'description': "A cramped, cozy room at the top of the North Tower, filled with crystal balls and teacups.",
        'treasure': 'Prophecy knowledge',
        'danger': 'Prophecies (some dangerous)',
        'found_by': 'Sybill Trelawney',
        'hint': 'Look into the crystal ball... what do you see?',
        'points': 250,
        'xp': 400,
        'item': 'Crystal Ball',
        'location': 'North Tower',
        'entrance': 'Trapdoor through a silver ladder',
        'history': 'Where the prophecy about Harry and Voldemort was made',
        'emoji': '🔮'
    },
    'restricted_section': {
        'name': 'Restricted Section',
        'password': 'danger',
        'description': 'The most dangerous part of the Hogwarts library, filled with dark magic books.',
        'treasure': 'Forbidden knowledge',
        'danger': 'Security spells, Madam Pince',
        'found_by': 'Hermione Granger',
        'hint': 'Some books scream when opened... follow the whispers',
        'points': 450,
        'xp': 700,
        'item': 'Ancient Tome',
        'location': 'Library',
        'entrance': 'Behind a roped-off area, guarded by chains',
        'history': 'Where Harry found the book about Horcruxes',
        'emoji': '📚'
    },
    'headmasters_office': {
        'name': "Headmaster's Office",
        'password': 'lemon drop',
        'description': "The office of the Headmaster, filled with portraits of past headmasters.",
        'treasure': 'Dumbledore\'s secrets',
        'danger': 'Fawkes the Phoenix (protective)',
        'found_by': 'Dumbledore',
        'hint': 'Lemon drops... and the password changes frequently',
        'points': 600,
        'xp': 1000,
        'item': 'Dumbledore\'s Pensieve Memory',
        'location': 'Behind the Gargoyle, Third Floor',
        'entrance': 'Stone gargoyle that requires a password',
        'history': 'Where Dumbledore trained Harry, where Snape became Headmaster',
        'emoji': '👑'
    }
}

# ==========================================
# MARAUDER'S MAP LOCATIONS (EXPANDED)
# ==========================================
MAP_LOCATIONS = [
    # Ground Floor
    {'name': 'Great Hall', 'area': 'Ground Floor', 'emoji': '🏰', 'students': 20, 'teachers': ['Dumbledore', 'McGonagall']},
    {'name': 'Entrance Hall', 'area': 'Ground Floor', 'emoji': '🚪', 'students': 5, 'teachers': ['Filch']},
    {'name': 'Staff Room', 'area': 'Ground Floor', 'emoji': '👥', 'students': 0, 'teachers': ['All Staff']},
    
    # Dungeons
    {'name': 'Slytherin Dungeon', 'area': 'Dungeons', 'emoji': '🐍', 'students': 15, 'teachers': ['Snape']},
    {'name': 'Potions Classroom', 'area': 'Dungeons', 'emoji': '⚗️', 'students': 12, 'teachers': ['Snape']},
    {'name': 'Hufflepuff Basement', 'area': 'Dungeons', 'emoji': '🦡', 'students': 14, 'teachers': ['Sprout']},
    
    # First Floor
    {'name': 'Library', 'area': 'First Floor', 'emoji': '📚', 'students': 25, 'teachers': ['Madam Pince']},
    {'name': 'Charms Classroom', 'area': 'First Floor', 'emoji': '✨', 'students': 10, 'teachers': ['Flitwick']},
    {'name': 'Infirmary', 'area': 'First Floor', 'emoji': '🏥', 'students': 2, 'teachers': ['Madam Pomfrey']},
    
    # Second Floor
    {'name': 'Ravenclaw Tower', 'area': 'Second Floor', 'emoji': '🦅', 'students': 13, 'teachers': ['Flitwick']},
    {'name': 'Gryffindor Tower', 'area': 'Second Floor', 'emoji': '🦁', 'students': 16, 'teachers': ['McGonagall']},
    {'name': 'Prefects Bathroom', 'area': 'Second Floor', 'emoji': '🛁', 'students': 1, 'teachers': []},
    
    # Third Floor
    {'name': 'Defense Against the Dark Arts', 'area': 'Third Floor', 'emoji': '⚔️', 'students': 8, 'teachers': ['Various']},
    {'name': 'Transfiguration Classroom', 'area': 'Third Floor', 'emoji': '🐱', 'students': 9, 'teachers': ['McGonagall']},
    {'name': 'Trophy Room', 'area': 'Third Floor', 'emoji': '🏆', 'students': 3, 'teachers': []},
    
    # Fourth Floor
    {'name': 'Astronomy Tower', 'area': 'Fourth Floor', 'emoji': '🔭', 'students': 6, 'teachers': ['Sinistra']},
    {'name': 'Divination Classroom', 'area': 'Fourth Floor', 'emoji': '🔮', 'students': 7, 'teachers': ['Trelawney']},
    {'name': 'Room of Requirement', 'area': 'Fourth Floor', 'emoji': '🚪', 'students': 4, 'teachers': []},
    
    # Grounds
    {'name': 'Quidditch Pitch', 'area': 'Grounds', 'emoji': '🧹', 'students': 18, 'teachers': ['Hooch']},
    {'name': 'Hagrid\'s Hut', 'area': 'Grounds', 'emoji': '🏠', 'students': 2, 'teachers': ['Hagrid']},
    {'name': 'Forbidden Forest', 'area': 'Grounds', 'emoji': '🌲', 'students': 1, 'teachers': ['Hagrid']},
    {'name': 'Greenhouses', 'area': 'Grounds', 'emoji': '🌱', 'students': 5, 'teachers': ['Sprout']},
    {'name': 'Black Lake', 'area': 'Grounds', 'emoji': '💧', 'students': 0, 'teachers': ['Squid']},
]

SECRET_PASSAGES = [
    {'from': 'Gryffindor Tower', 'to': 'Hogsmeade', 'password': 'dissendium', 'discovered': False},
    {'from': 'Fourth Floor', 'to': 'Room of Requirement', 'password': 'need', 'discovered': False},
    {'from': 'Entrance Hall', 'to': 'Dungeons', 'password': 'pureblood', 'discovered': False},
    {'from': 'Library', 'to': 'Restricted Section', 'password': 'lumos', 'discovered': False},
    {'from': 'Hagrid\'s Hut', 'to': 'Forbidden Forest', 'password': 'fang', 'discovered': False},
]

# ==========================================
# SPELL DATA (EXPANDED)
# ==========================================
SPELLS = {
    # Charms
    'wingardium_leviosa': {
        'name': 'Wingardium Leviosa',
        'emoji': '✨',
        'type': 'charm',
        'category': 'charm',
        'power': 5,
        'mana_cost': 5,
        'description': 'The levitation charm - makes objects float',
        'effect': 'Lift objects up to 100kg',
        'learn_cost': 50,
        'duel_power': 8,
        'rarity': 'common',
        'unlock_level': 1,
        'cooldown': 2,
        'requirements': [],
        'mastery_bonus': 'Can lift heavier objects, lasts longer'
    },
    'lumos': {
        'name': 'Lumos',
        'emoji': '💡',
        'type': 'charm',
        'category': 'charm',
        'power': 2,
        'mana_cost': 2,
        'description': 'Creates light at the tip of your wand',
        'effect': 'Illuminate dark areas',
        'learn_cost': 25,
        'duel_power': 5,
        'rarity': 'common',
        'unlock_level': 1,
        'cooldown': 1,
        'requirements': [],
        'mastery_bonus': 'Creates a sphere of light, reveals hidden things'
    },
    'nox': {
        'name': 'Nox',
        'emoji': '🌙',
        'type': 'charm',
        'category': 'charm',
        'power': 2,
        'mana_cost': 2,
        'description': 'Extinguishes wand light',
        'effect': 'Cancel Lumos',
        'learn_cost': 25,
        'duel_power': 3,
        'rarity': 'common',
        'unlock_level': 1,
        'cooldown': 1,
        'requirements': ['lumos'],
        'mastery_bonus': 'Can extinguish other light sources'
    },
    'alohomora': {
        'name': 'Alohomora',
        'emoji': '🔓',
        'type': 'charm',
        'category': 'charm',
        'power': 10,
        'mana_cost': 10,
        'description': 'Unlocking charm - opens locked doors',
        'effect': 'Unlock basic locks',
        'learn_cost': 75,
        'duel_power': 10,
        'rarity': 'common',
        'unlock_level': 2,
        'cooldown': 5,
        'requirements': [],
        'mastery_bonus': 'Can unlock magical locks, disarm security'
    },
    'accio': {
        'name': 'Accio',
        'emoji': '🪄',
        'type': 'charm',
        'category': 'charm',
        'power': 15,
        'mana_cost': 15,
        'description': 'Summoning charm - brings objects to you',
        'effect': 'Summon objects within sight',
        'learn_cost': 100,
        'duel_power': 15,
        'rarity': 'uncommon',
        'unlock_level': 3,
        'cooldown': 5,
        'requirements': [],
        'mastery_bonus': 'Can summon objects from other rooms'
    },
    'reparo': {
        'name': 'Reparo',
        'emoji': '🔧',
        'type': 'charm',
        'category': 'charm',
        'power': 10,
        'mana_cost': 10,
        'description': 'Repairing charm - fixes broken objects',
        'effect': 'Repair minor damage',
        'learn_cost': 75,
        'duel_power': 8,
        'rarity': 'uncommon',
        'unlock_level': 2,
        'cooldown': 10,
        'requirements': [],
        'mastery_bonus': 'Can repair magical items, restore antiques'
    },
    'scourgify': {
        'name': 'Scourgify',
        'emoji': '🧹',
        'type': 'charm',
        'category': 'charm',
        'power': 5,
        'mana_cost': 5,
        'description': 'Cleaning charm - removes dirt and grime',
        'effect': 'Clean objects and surfaces',
        'learn_cost': 40,
        'duel_power': 3,
        'rarity': 'common',
        'unlock_level': 1,
        'cooldown': 3,
        'requirements': [],
        'mastery_bonus': 'Self-cleaning clothes, permanent freshness'
    },
    'aguamenti': {
        'name': 'Aguamenti',
        'emoji': '💧',
        'type': 'charm',
        'category': 'charm',
        'power': 8,
        'mana_cost': 8,
        'description': 'Water-making charm - conjures clean water',
        'effect': 'Create water',
        'learn_cost': 60,
        'duel_power': 10,
        'rarity': 'uncommon',
        'unlock_level': 2,
        'cooldown': 5,
        'requirements': [],
        'mastery_bonus': 'Control water flow, create waves'
    },
    'incendio': {
        'name': 'Incendio',
        'emoji': '🔥',
        'type': 'charm',
        'category': 'charm',
        'power': 15,
        'mana_cost': 15,
        'description': 'Fire-making charm - creates flames',
        'effect': 'Start fires, provide warmth',
        'learn_cost': 80,
        'duel_power': 20,
        'rarity': 'uncommon',
        'unlock_level': 3,
        'cooldown': 5,
        'requirements': [],
        'mastery_bonus': 'Control fire, create fire shields'
    },
    'glacius': {
        'name': 'Glacius',
        'emoji': '❄️',
        'type': 'charm',
        'category': 'charm',
        'power': 15,
        'mana_cost': 15,
        'description': 'Freezing charm - creates ice',
        'effect': 'Freeze water, cool things',
        'learn_cost': 80,
        'duel_power': 20,
        'rarity': 'uncommon',
        'unlock_level': 3,
        'cooldown': 5,
        'requirements': ['aguamenti'],
        'mastery_bonus': 'Create ice shields, freeze opponents'
    },
    
    # Defensive Spells
    'protego': {
        'name': 'Protego',
        'emoji': '🛡️',
        'type': 'defense',
        'category': 'defense',
        'power': 20,
        'mana_cost': 20,
        'description': 'Shield charm - creates a magical barrier',
        'effect': 'Block weak spells',
        'learn_cost': 150,
        'duel_power': 25,
        'rarity': 'rare',
        'unlock_level': 4,
        'cooldown': 10,
        'requirements': [],
        'mastery_bonus': 'Reflects spells back, protects allies'
    },
    'protego_maxima': {
        'name': 'Protego Maxima',
        'emoji': '🛡️✨',
        'type': 'defense',
        'category': 'defense',
        'power': 40,
        'mana_cost': 40,
        'description': 'Powerful shield charm - creates a strong barrier',
        'effect': 'Block powerful spells',
        'learn_cost': 300,
        'duel_power': 45,
        'rarity': 'rare',
        'unlock_level': 6,
        'cooldown': 15,
        'requirements': ['protego'],
        'mastery_bonus': 'Shield lasts longer, protects a group'
    },
    'expecto_patronum': {
        'name': 'Expecto Patronum',
        'emoji': '✨🦌',
        'type': 'defense',
        'category': 'defense',
        'power': 50,
        'mana_cost': 50,
        'description': 'Patronus charm - repels Dementors',
        'effect': 'Summon a Patronus guardian',
        'learn_cost': 500,
        'duel_power': 30,
        'rarity': 'legendary',
        'unlock_level': 8,
        'cooldown': 60,
        'requirements': [],
        'mastery_bonus': 'Patronus can deliver messages, corporeal form'
    },
    'salvio_hexia': {
        'name': 'Salvio Hexia',
        'emoji': '🔮',
        'type': 'defense',
        'category': 'defense',
        'power': 30,
        'mana_cost': 30,
        'description': 'Protective enchantment - wards an area',
        'effect': 'Protect a location',
        'learn_cost': 250,
        'duel_power': 20,
        'rarity': 'rare',
        'unlock_level': 5,
        'cooldown': 30,
        'requirements': ['protego'],
        'mastery_bonus': 'Longer duration, alerts you to intruders'
    },
    
    # Offensive Spells
    'expelliarmus': {
        'name': 'Expelliarmus',
        'emoji': '⚔️',
        'type': 'offensive',
        'category': 'offensive',
        'power': 25,
        'mana_cost': 25,
        'description': 'Disarming charm - knocks weapon from opponent',
        'effect': 'Disarm opponent',
        'learn_cost': 120,
        'duel_power': 30,
        'rarity': 'uncommon',
        'unlock_level': 3,
        'cooldown': 5,
        'requirements': [],
        'mastery_bonus': 'Can disarm multiple opponents, pull wand to you'
    },
    'stupefy': {
        'name': 'Stupefy',
        'emoji': '⚡',
        'type': 'offensive',
        'category': 'offensive',
        'power': 30,
        'mana_cost': 30,
        'description': 'Stunning spell - knocks out opponent',
        'effect': 'Stun target',
        'learn_cost': 150,
        'duel_power': 35,
        'rarity': 'uncommon',
        'unlock_level': 4,
        'cooldown': 8,
        'requirements': [],
        'mastery_bonus': 'Longer stun duration, area effect'
    },
    'petrificus_totalus': {
        'name': 'Petrificus Totalus',
        'emoji': '🗿',
        'type': 'offensive',
        'category': 'offensive',
        'power': 35,
        'mana_cost': 35,
        'description': 'Full body bind - paralyzes opponent',
        'effect': 'Immobilize target',
        'learn_cost': 200,
        'duel_power': 40,
        'rarity': 'rare',
        'unlock_level': 5,
        'cooldown': 10,
        'requirements': ['stupefy'],
        'mastery_bonus': 'Longer paralysis, can target specific limbs'
    },
    'confringo': {
        'name': 'Confringo',
        'emoji': '💥',
        'type': 'offensive',
        'category': 'offensive',
        'power': 40,
        'mana_cost': 40,
        'description': 'Blasting curse - causes explosions',
        'effect': 'Blast objects, damage area',
        'learn_cost': 250,
        'duel_power': 45,
        'rarity': 'rare',
        'unlock_level': 6,
        'cooldown': 12,
        'requirements': ['incendio'],
        'mastery_bonus': 'Larger explosion, controlled demolition'
    },
    'reducto': {
        'name': 'Reducto',
        'emoji': '🧱',
        'type': 'offensive',
        'category': 'offensive',
        'power': 45,
        'mana_cost': 45,
        'description': 'Reductor curse - blasts solid objects to pieces',
        'effect': 'Destroy barriers, break walls',
        'learn_cost': 300,
        'duel_power': 50,
        'rarity': 'rare',
        'unlock_level': 7,
        'cooldown': 15,
        'requirements': ['confringo'],
        'mastery_bonus': 'Can target specific parts, precision destruction'
    },
    'sectumsempra': {
        'name': 'Sectumsempra',
        'emoji': '🔪',
        'type': 'offensive',
        'category': 'offensive',
        'power': 60,
        'mana_cost': 60,
        'description': 'Slashes opponent as if by a sword',
        'effect': 'Cause deep wounds',
        'learn_cost': 400,
        'duel_power': 65,
        'rarity': 'legendary',
        'unlock_level': 8,
        'cooldown': 20,
        'requirements': [],
        'mastery_bonus': 'Can target specific areas, healable wounds'
    },
    
    # Unforgivable Curses
    'imperio': {
        'name': 'Imperio',
        'emoji': '👁️',
        'type': 'unforgivable',
        'category': 'offensive',
        'power': 70,
        'mana_cost': 70,
        'description': 'Imperius curse - total control over victim',
        'effect': 'Control target\'s actions',
        'learn_cost': 800,
        'duel_power': 80,
        'rarity': 'legendary',
        'unlock_level': 9,
        'cooldown': 60,
        'requirements': [],
        'mastery_bonus': 'Multiple targets, longer control'
    },
    'crucio': {
        'name': 'Crucio',
        'emoji': '💢',
        'type': 'unforgivable',
        'category': 'offensive',
        'power': 80,
        'mana_cost': 80,
        'description': 'Cruciatus curse - inflicts unbearable pain',
        'effect': 'Torture target',
        'learn_cost': 900,
        'duel_power': 85,
        'rarity': 'legendary',
        'unlock_level': 9,
        'cooldown': 60,
        'requirements': [],
        'mastery_bonus': 'Lasting pain, can be sustained'
    },
    'avadakedavra': {
        'name': 'Avada Kedavra',
        'emoji': '💀',
        'type': 'unforgivable',
        'category': 'offensive',
        'power': 100,
        'mana_cost': 100,
        'description': 'Killing curse - instant death',
        'effect': 'Instant kill',
        'learn_cost': 2000,
        'duel_power': 100,
        'rarity': 'mythic',
        'unlock_level': 10,
        'cooldown': 300,
        'requirements': [],
        'mastery_bonus': 'Cannot be blocked, ignores shields'
    },
    
    # Healing Spells
    'episkey': {
        'name': 'Episkey',
        'emoji': '❤️',
        'type': 'healing',
        'category': 'healing',
        'power': 20,
        'mana_cost': 20,
        'description': 'Healing charm - mends minor injuries',
        'effect': 'Heal small wounds',
        'learn_cost': 100,
        'duel_power': 10,
        'rarity': 'uncommon',
        'unlock_level': 3,
        'cooldown': 10,
        'requirements': [],
        'mastery_bonus': 'Heal faster, more effective'
    },
    'vulnera_sanentur': {
        'name': 'Vulnera Sanentur',
        'emoji': '🩹',
        'type': 'healing',
        'category': 'healing',
        'power': 35,
        'mana_cost': 35,
        'description': 'Healing incantation - mends serious wounds',
        'effect': 'Heal deep cuts, mend bones',
        'learn_cost': 250,
        'duel_power': 15,
        'rarity': 'rare',
        'unlock_level': 5,
        'cooldown': 20,
        'requirements': ['episkey'],
        'mastery_bonus': 'Regrow tissue, faster healing'
    },
    'enervate': {
        'name': 'Enervate',
        'emoji': '⚡✨',
        'type': 'healing',
        'category': 'healing',
        'power': 15,
        'mana_cost': 15,
        'description': 'Revives stunned or unconscious victims',
        'effect': 'Wake up stunned target',
        'learn_cost': 80,
        'duel_power': 10,
        'rarity': 'uncommon',
        'unlock_level': 2,
        'cooldown': 5,
        'requirements': [],
        'mastery_bonus': 'Revive from deeper unconsciousness'
    },
    
    # Transfiguration
    'vera_verto': {
        'name': 'Vera Verto',
        'emoji': '🐦',
        'type': 'transfiguration',
        'category': 'transfiguration',
        'power': 25,
        'mana_cost': 25,
        'description': 'Animal transformation - turns objects into animals',
        'effect': 'Transform objects into living creatures',
        'learn_cost': 200,
        'duel_power': 20,
        'rarity': 'rare',
        'unlock_level': 4,
        'cooldown': 30,
        'requirements': [],
        'mastery_bonus': 'Transform into different animals, longer duration'
    },
    'avifors': {
        'name': 'Avifors',
        'emoji': '🦅',
        'type': 'transfiguration',
        'category': 'transfiguration',
        'power': 20,
        'mana_cost': 20,
        'description': 'Turns small objects into birds',
        'effect': 'Create birds from objects',
        'learn_cost': 150,
        'duel_power': 15,
        'rarity': 'rare',
        'unlock_level': 3,
        'cooldown': 25,
        'requirements': [],
        'mastery_bonus': 'Create larger birds, control their flight'
    }
}
# ==========================================
# POTION RECIPES (FULL)
# ==========================================
POTION_RECIPES = {
    'cure_for_boils': {
        'name': 'Cure for Boils',
        'emoji': '🧪',
        'difficulty': 'easy',
        'brew_time': 10,  # minutes
        'description': 'A simple potion that cures boils and skin irritations',
        'effect': 'Cures minor skin ailments',
        'ingredients': [
            {'name': 'Dried Nettles', 'emoji': '🌿', 'quantity': 3},
            {'name': 'Snake Fangs', 'emoji': '🐍', 'quantity': 2},
            {'name': 'Porcupine Quills', 'emoji': '🦔', 'quantity': 1}
        ],
        'cauldron': 'pewter',
        'stir_direction': 'clockwise',
        'stir_count': 3,
        'color': 0x27ae60,
        'base_points': 50,
        'xp_reward': 75,
        'unlock_level': 1,
        'rare_drop': False
    },
    'forgetfulness_potion': {
        'name': 'Forgetfulness Potion',
        'emoji': '🧠',
        'difficulty': 'easy',
        'brew_time': 15,
        'description': 'Causes mild memory loss and confusion',
        'effect': 'Makes target forget recent events',
        'ingredients': [
            {'name': 'Lethe Water', 'emoji': '💧', 'quantity': 2},
            {'name': 'Mistletoe Berries', 'emoji': '🫐', 'quantity': 3},
            {'name': 'Valerian Root', 'emoji': '🌱', 'quantity': 1}
        ],
        'cauldron': 'brass',
        'stir_direction': 'anticlockwise',
        'stir_count': 5,
        'color': 0x3498db,
        'base_points': 60,
        'xp_reward': 90,
        'unlock_level': 1,
        'rare_drop': False
    },
    'wiggenweld_potion': {
        'name': 'Wiggenweld Potion',
        'emoji': '❤️',
        'difficulty': 'easy',
        'brew_time': 12,
        'description': 'A healing potion that restores health',
        'effect': 'Heals minor injuries',
        'ingredients': [
            {'name': 'Dittany', 'emoji': '🌿', 'quantity': 2},
            {'name': 'Horklump Juice', 'emoji': '🧃', 'quantity': 1},
            {'name': 'Flobberworm Mucus', 'emoji': '🪱', 'quantity': 3}
        ],
        'cauldron': 'pewter',
        'stir_direction': 'clockwise',
        'stir_count': 4,
        'color': 0xe74c3c,
        'base_points': 70,
        'xp_reward': 100,
        'unlock_level': 2,
        'rare_drop': False
    },
    'draught_of_living_death': {
        'name': 'Draught of Living Death',
        'emoji': '💀',
        'difficulty': 'hard',
        'brew_time': 30,
        'description': 'Puts the drinker into a death-like slumber',
        'effect': 'Causes deep, dreamless sleep',
        'ingredients': [
            {'name': 'Powdered Moonstone', 'emoji': '🌙', 'quantity': 4},
            {'name': 'Syrup of Hellebore', 'emoji': '🍯', 'quantity': 2},
            {'name': 'Valerian Sprigs', 'emoji': '🌿', 'quantity': 3},
            {'name': 'Sopophorous Bean', 'emoji': '🫘', 'quantity': 1}
        ],
        'cauldron': 'copper',
        'stir_direction': 'anticlockwise',
        'stir_count': 7,
        'color': 0x2c3e50,
        'base_points': 200,
        'xp_reward': 300,
        'unlock_level': 4,
        'rare_drop': True
    },
    'veritaserum': {
        'name': 'Veritaserum',
        'emoji': '🔮',
        'difficulty': 'hard',
        'brew_time': 45,
        'description': 'Powerful truth serum',
        'effect': 'Forces drinker to tell the truth',
        'ingredients': [
            {'name': 'Mistletoe Berries', 'emoji': '🫐', 'quantity': 5},
            {'name': 'Valerian Root', 'emoji': '🌱', 'quantity': 4},
            {'name': 'Sopophorous Bean', 'emoji': '🫘', 'quantity': 2},
            {'name': 'Jobberknoll Feather', 'emoji': '🪶', 'quantity': 1}
        ],
        'cauldron': 'silver',
        'stir_direction': 'clockwise',
        'stir_count': 8,
        'color': 0x8e44ad,
        'base_points': 300,
        'xp_reward': 450,
        'unlock_level': 5,
        'rare_drop': True
    },
    'polyjuice_potion': {
        'name': 'Polyjuice Potion',
        'emoji': '👤',
        'difficulty': 'hard',
        'brew_time': 60,
        'description': 'Transforms drinker into someone else',
        'effect': 'Take appearance of another person',
        'ingredients': [
            {'name': 'Fluxweed', 'emoji': '🌿', 'quantity': 3},
            {'name': 'Knotgrass', 'emoji': '🌱', 'quantity': 3},
            {'name': 'Lacewing Flies', 'emoji': '🪰', 'quantity': 3},
            {'name': 'Leeches', 'emoji': '🪱', 'quantity': 2},
            {'name': 'Hair of target', 'emoji': '💇', 'quantity': 1}
        ],
        'cauldron': 'copper',
        'stir_direction': 'anticlockwise',
        'stir_count': 10,
        'color': 0xe67e22,
        'base_points': 500,
        'xp_reward': 750,
        'unlock_level': 6,
        'rare_drop': True
    },
    'felix_felicis': {
        'name': 'Felix Felicis',
        'emoji': '✨',
        'difficulty': 'legendary',
        'brew_time': 120,
        'description': 'Liquid luck - everything you try will succeed',
        'effect': 'Incredible luck for 1 hour',
        'ingredients': [
            {'name': 'Occamy Eggshell', 'emoji': '🥚', 'quantity': 1},
            {'name': 'Tincture of Thyme', 'emoji': '🧪', 'quantity': 4},
            {'name': 'Ashwinder Eggs', 'emoji': '🥚', 'quantity': 3},
            {'name': 'Powdered Unicorn Horn', 'emoji': '🦄', 'quantity': 1},
            {'name': 'Moondew', 'emoji': '🌙', 'quantity': 5}
        ],
        'cauldron': 'gold',
        'stir_direction': 'clockwise',
        'stir_count': 12,
        'color': 0xf1c40f,
        'base_points': 1000,
        'xp_reward': 1500,
        'unlock_level': 8,
        'rare_drop': True
    },
    'amortentia': {
        'name': 'Amortentia',
        'emoji': '💕',
        'difficulty': 'hard',
        'brew_time': 40,
        'description': 'The most powerful love potion',
        'effect': 'Creates strong infatuation',
        'ingredients': [
            {'name': 'Pearl Dust', 'emoji': '✨', 'quantity': 3},
            {'name': 'Rose Thorns', 'emoji': '🌹', 'quantity': 4},
            {'name': 'Peppermint', 'emoji': '🌿', 'quantity': 3},
            {'name': 'Fresh Rose Petals', 'emoji': '🌹', 'quantity': 5}
        ],
        'cauldron': 'silver',
        'stir_direction': 'anticlockwise',
        'stir_count': 7,
        'color': 0xff69b4,
        'base_points': 400,
        'xp_reward': 600,
        'unlock_level': 5,
        'rare_drop': True
    },
    'skele_gro': {
        'name': 'Skele-Gro',
        'emoji': '🦴',
        'difficulty': 'medium',
        'brew_time': 25,
        'description': 'Regrows missing or broken bones',
        'effect': 'Regenerates bone tissue',
        'ingredients': [
            {'name': 'Dragon Blood', 'emoji': '🐉', 'quantity': 2},
            {'name': 'Bone Dust', 'emoji': '🦴', 'quantity': 4},
            {'name': 'Mandrake Root', 'emoji': '🌱', 'quantity': 2},
            {'name': 'Pickled Shrake Spine', 'emoji': '🦔', 'quantity': 1}
        ],
        'cauldron': 'copper',
        'stir_direction': 'clockwise',
        'stir_count': 6,
        'color': 0xecf0f1,
        'base_points': 250,
        'xp_reward': 375,
        'unlock_level': 3,
        'rare_drop': False
    },
    'draught_of_peace': {
        'name': 'Draught of Peace',
        'emoji': '☮️',
        'difficulty': 'medium',
        'brew_time': 20,
        'description': 'Calms anxiety and agitation',
        'effect': 'Reduces stress and fear',
        'ingredients': [
            {'name': 'Lavender', 'emoji': '🌸', 'quantity': 3},
            {'name': 'Chamomile', 'emoji': '🌼', 'quantity': 3},
            {'name': 'Moonstone', 'emoji': '🌙', 'quantity': 2},
            {'name': 'Powdered Silver', 'emoji': '✨', 'quantity': 1}
        ],
        'cauldron': 'pewter',
        'stir_direction': 'clockwise',
        'stir_count': 5,
        'color': 0x3498db,
        'base_points': 150,
        'xp_reward': 225,
        'unlock_level': 2,
        'rare_drop': False
    }
}

# ==========================================
# INGREDIENT SHOP
# ==========================================
INGREDIENTS = {
    'dried_nettles': {'name': 'Dried Nettles', 'emoji': '🌿', 'price': 5, 'rarity': 'common'},
    'snake_fangs': {'name': 'Snake Fangs', 'emoji': '🐍', 'price': 8, 'rarity': 'common'},
    'porcupine_quills': {'name': 'Porcupine Quills', 'emoji': '🦔', 'price': 10, 'rarity': 'common'},
    'lethe_water': {'name': 'Lethe Water', 'emoji': '💧', 'price': 12, 'rarity': 'common'},
    'mistletoe_berries': {'name': 'Mistletoe Berries', 'emoji': '🫐', 'price': 8, 'rarity': 'common'},
    'valerian_root': {'name': 'Valerian Root', 'emoji': '🌱', 'price': 10, 'rarity': 'common'},
    'dittany': {'name': 'Dittany', 'emoji': '🌿', 'price': 15, 'rarity': 'uncommon'},
    'horklump_juice': {'name': 'Horklump Juice', 'emoji': '🧃', 'price': 12, 'rarity': 'common'},
    'flobberworm_mucus': {'name': 'Flobberworm Mucus', 'emoji': '🪱', 'price': 5, 'rarity': 'common'},
    'powdered_moonstone': {'name': 'Powdered Moonstone', 'emoji': '🌙', 'price': 25, 'rarity': 'uncommon'},
    'syrup_of_hellebore': {'name': 'Syrup of Hellebore', 'emoji': '🍯', 'price': 20, 'rarity': 'uncommon'},
    'valerian_sprigs': {'name': 'Valerian Sprigs', 'emoji': '🌿', 'price': 15, 'rarity': 'common'},
    'sopophorous_bean': {'name': 'Sopophorous Bean', 'emoji': '🫘', 'price': 30, 'rarity': 'rare'},
    'jobberknoll_feather': {'name': 'Jobberknoll Feather', 'emoji': '🪶', 'price': 40, 'rarity': 'rare'},
    'fluxweed': {'name': 'Fluxweed', 'emoji': '🌿', 'price': 25, 'rarity': 'uncommon'},
    'knotgrass': {'name': 'Knotgrass', 'emoji': '🌱', 'price': 20, 'rarity': 'uncommon'},
    'lacewing_flies': {'name': 'Lacewing Flies', 'emoji': '🪰', 'price': 15, 'rarity': 'common'},
    'leeches': {'name': 'Leeches', 'emoji': '🪱', 'price': 10, 'rarity': 'common'},
    'occamy_eggshell': {'name': 'Occamy Eggshell', 'emoji': '🥚', 'price': 100, 'rarity': 'legendary'},
    'tincture_of_thyme': {'name': 'Tincture of Thyme', 'emoji': '🧪', 'price': 30, 'rarity': 'rare'},
    'ashwinder_eggs': {'name': 'Ashwinder Eggs', 'emoji': '🥚', 'price': 50, 'rarity': 'rare'},
    'powdered_unicorn_horn': {'name': 'Powdered Unicorn Horn', 'emoji': '🦄', 'price': 150, 'rarity': 'legendary'},
    'moondew': {'name': 'Moondew', 'emoji': '🌙', 'price': 35, 'rarity': 'rare'},
    'pearl_dust': {'name': 'Pearl Dust', 'emoji': '✨', 'price': 40, 'rarity': 'rare'},
    'rose_thorns': {'name': 'Rose Thorns', 'emoji': '🌹', 'price': 10, 'rarity': 'common'},
    'peppermint': {'name': 'Peppermint', 'emoji': '🌿', 'price': 8, 'rarity': 'common'},
    'fresh_rose_petals': {'name': 'Fresh Rose Petals', 'emoji': '🌹', 'price': 12, 'rarity': 'common'},
    'dragon_blood': {'name': 'Dragon Blood', 'emoji': '🐉', 'price': 60, 'rarity': 'legendary'},
    'bone_dust': {'name': 'Bone Dust', 'emoji': '🦴', 'price': 15, 'rarity': 'common'},
    'mandrake_root': {'name': 'Mandrake Root', 'emoji': '🌱', 'price': 45, 'rarity': 'rare'},
    'pickled_shrake_spine': {'name': 'Pickled Shrake Spine', 'emoji': '🦔', 'price': 30, 'rarity': 'rare'},
    'lavender': {'name': 'Lavender', 'emoji': '🌸', 'price': 8, 'rarity': 'common'},
    'chamomile': {'name': 'Chamomile', 'emoji': '🌼', 'price': 8, 'rarity': 'common'},
    'powdered_silver': {'name': 'Powdered Silver', 'emoji': '✨', 'price': 25, 'rarity': 'uncommon'}
}

# ==========================================
# CLASS DATA (EXPANDED)
# ==========================================
CLASSES = {
    'transfiguration': {
        'name': 'Transfiguration',
        'emoji': '🐱',
        'professor': 'Minerva McGonagall',
        'description': 'The art of changing the form and appearance of objects',
        'topics': ['Match to needle', 'Teacup to turtle', 'Human transfiguration'],
        'difficulty': 'hard',
        'base_points': 30,
        'xp_reward': 50,
        'attendance_reward': 'Transfiguration Textbook',
        'schedule': ['Monday 10am', 'Wednesday 2pm', 'Friday 11am'],
        'location': 'Transfiguration Classroom, Third Floor',
        'house_points_bonus': {'gryffindor': 1.2},  # 20% bonus for Gryffindor
        'required_level': 3,
        'color': 0x740001,
        'spells_taught': ['vera_verto', 'avifors']
    },
    'potions': {
        'name': 'Potions',
        'emoji': '⚗️',
        'professor': 'Severus Snape',
        'description': 'The art of brewing magical potions',
        'topics': ['Cure for Boils', 'Draught of Living Death', 'Polyjuice Potion'],
        'difficulty': 'hard',
        'base_points': 35,
        'xp_reward': 60,
        'attendance_reward': 'Potion Ingredient',
        'schedule': ['Tuesday 9am', 'Thursday 1pm', 'Friday 3pm'],
        'location': 'Potions Dungeon',
        'house_points_bonus': {'slytherin': 1.2},
        'required_level': 3,
        'color': 0x1a472a,
        'spells_taught': []  # Potions taught separately
    },
    'dada': {
        'name': 'Defense Against the Dark Arts',
        'emoji': '⚔️',
        'professor': 'Various',
        'description': 'Learning to defend against dark creatures and spells',
        'topics': ['Red Caps', 'Grindylows', 'Boggarts', 'Dementors'],
        'difficulty': 'hard',
        'base_points': 40,
        'xp_reward': 70,
        'attendance_reward': 'Shield Charm',
        'schedule': ['Monday 1pm', 'Wednesday 10am', 'Friday 2pm'],
        'location': 'DADA Classroom, Third Floor',
        'house_points_bonus': {'gryffindor': 1.1, 'slytherin': 1.1},
        'required_level': 4,
        'color': 0x9b59b6,
        'spells_taught': ['protego', 'expelliarmus', 'expecto_patronum']
    },
    'charms': {
        'name': 'Charms',
        'emoji': '✨',
        'professor': 'Filius Flitwick',
        'description': 'Learning everyday spells and enchantments',
        'topics': ['Wingardium Leviosa', 'Lumos', 'Alohomora', 'Accio'],
        'difficulty': 'easy',
        'base_points': 20,
        'xp_reward': 30,
        'attendance_reward': 'Spell Book',
        'schedule': ['Monday 9am', 'Wednesday 11am', 'Thursday 3pm'],
        'location': 'Charms Classroom, First Floor',
        'house_points_bonus': {'ravenclaw': 1.2},
        'required_level': 1,
        'color': 0x0e1a40,
        'spells_taught': ['wingardium_leviosa', 'lumos', 'nox', 'alohomora', 'accio']
    },
    'herbology': {
        'name': 'Herbology',
        'emoji': '🌱',
        'professor': 'Pomona Sprout',
        'description': 'Study of magical plants and fungi',
        'topics': ['Mandrakes', 'Venomous Tentacula', 'Whomping Willow'],
        'difficulty': 'medium',
        'base_points': 25,
        'xp_reward': 40,
        'attendance_reward': 'Magical Plant',
        'schedule': ['Tuesday 11am', 'Wednesday 1pm', 'Friday 9am'],
        'location': 'Greenhouse Three',
        'house_points_bonus': {'hufflepuff': 1.2},
        'required_level': 2,
        'color': 0xecb939,
        'spells_taught': []
    },
    'astronomy': {
        'name': 'Astronomy',
        'emoji': '⭐',
        'professor': 'Aurora Sinistra',
        'description': 'Study of stars, planets, and celestial movements',
        'topics': ['Planetary charts', 'Moon phases', 'Star naming'],
        'difficulty': 'medium',
        'base_points': 20,
        'xp_reward': 35,
        'attendance_reward': 'Star Chart',
        'schedule': ['Monday midnight', 'Wednesday midnight', 'Friday midnight'],
        'location': 'Astronomy Tower',
        'house_points_bonus': {'ravenclaw': 1.1},
        'required_level': 2,
        'color': 0x2c3e50,
        'spells_taught': []
    },
    'history_of_magic': {
        'name': 'History of Magic',
        'emoji': '📜',
        'professor': 'Cuthbert Binns',
        'description': 'Study of wizarding history',
        'topics': ['Goblin Rebellions', 'Founding of Hogwarts', 'Wizarding Wars'],
        'difficulty': 'easy',
        'base_points': 15,
        'xp_reward': 25,
        'attendance_reward': 'History Book',
        'schedule': ['Tuesday 10am', 'Thursday 11am', 'Friday 1pm'],
        'location': 'History Classroom, First Floor',
        'house_points_bonus': {},
        'required_level': 1,
        'color': 0x95a5a6,
        'spells_taught': []
    },
    'flying': {
        'name': 'Flying',
        'emoji': '🧹',
        'professor': 'Rolanda Hooch',
        'description': 'Learning to fly on broomsticks',
        'topics': ['Broom mounting', 'Basic flight', 'Sharp turns', 'Landing'],
        'difficulty': 'medium',
        'base_points': 25,
        'xp_reward': 45,
        'attendance_reward': 'Broom Polish',
        'schedule': ['Tuesday 2pm', 'Thursday 10am', 'Saturday 10am'],
        'location': 'Quidditch Pitch',
        'house_points_bonus': {'gryffindor': 1.1},
        'required_level': 2,
        'color': 0x27ae60,
        'spells_taught': []
    },
    'ancient_runes': {
        'name': 'Ancient Runes',
        'emoji': '🔤',
        'professor': 'Bathsheda Babbling',
        'description': 'Study of ancient magical symbols and languages',
        'topics': ['Elder Futhark', 'Runic translations', 'Enchantment symbols'],
        'difficulty': 'hard',
        'base_points': 30,
        'xp_reward': 55,
        'attendance_reward': 'Rune Dictionary',
        'schedule': ['Monday 2pm', 'Wednesday 3pm', 'Thursday 9am'],
        'location': 'Runes Classroom, Second Floor',
        'house_points_bonus': {'ravenclaw': 1.1},
        'required_level': 4,
        'color': 0xd35400,
        'spells_taught': []
    },
    'divination': {
        'name': 'Divination',
        'emoji': '🔮',
        'professor': 'Sybill Trelawney',
        'description': 'Art of predicting the future',
        'topics': ['Tea leaves', 'Crystal balls', 'Dream interpretation', 'Palmistry'],
        'difficulty': 'medium',
        'base_points': 20,
        'xp_reward': 35,
        'attendance_reward': 'Crystal Ball',
        'schedule': ['Monday 3pm', 'Wednesday 9am', 'Friday 10am'],
        'location': 'Divination Classroom, North Tower',
        'house_points_bonus': {},
        'required_level': 3,
        'color': 0x8e44ad,
        'spells_taught': []
    },
    'care_of_magical_creatures': {
        'name': 'Care of Magical Creatures',
        'emoji': '🦄',
        'professor': 'Rubeus Hagrid',
        'description': 'Learning to care for magical beasts',
        'topics': ['Hippogriffs', 'Dragons', 'Nifflers', 'Thestrals'],
        'difficulty': 'medium',
        'base_points': 30,
        'xp_reward': 50,
        'attendance_reward': 'Creature Treat',
        'schedule': ['Tuesday 1pm', 'Thursday 2pm', 'Saturday 11am'],
        'location': 'Hagrid\'s Hut',
        'house_points_bonus': {'hufflepuff': 1.1},
        'required_level': 3,
        'color': 0xe67e22,
        'spells_taught': []
    },
    'alchemy': {
        'name': 'Alchemy',
        'emoji': '⚜️',
        'professor': 'Unknown',
        'description': 'The study of transmutation and the Philosopher\'s Stone',
        'topics': ['Lead to gold', 'Elixir of Life', 'Philosopher\'s Stone'],
        'difficulty': 'legendary',
        'base_points': 100,
        'xp_reward': 200,
        'attendance_reward': 'Philosopher\'s Stone Shard',
        'schedule': ['Saturday 2pm', 'Sunday 11am'],
        'location': 'Alchemy Chamber',
        'house_points_bonus': {},
        'required_level': 10,
        'color': 0xf1c40f,
        'spells_taught': []
    }
}

# ==========================================
# BATTLE PASS SYSTEM
# ==========================================
BATTLE_PASS_TIERS = {
    1: {
        'name': 'Novice Wizard',
        'points_required': 0,
        'free_rewards': [
            {'type': 'points', 'amount': 100, 'emoji': '💰'},
            {'type': 'item', 'item': 'Chocolate Frog', 'emoji': '🐸'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 200, 'emoji': '💰'},
            {'type': 'item', 'item': 'Rare Core', 'emoji': '✨'},
            {'type': 'badge', 'name': 'Novice Wizard', 'emoji': '🎓'}
        ],
        'color': 0x95a5a6,
        'emoji': '🎓'
    },
    2: {
        'name': 'Apprentice',
        'points_required': 500,
        'free_rewards': [
            {'type': 'points', 'amount': 150, 'emoji': '💰'},
            {'type': 'item', 'item': 'Spell Scroll', 'emoji': '📜'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 300, 'emoji': '💰'},
            {'type': 'item', 'item': 'Wand Polish', 'emoji': '✨'},
            {'type': 'consumable', 'item': 'Butterbeer x3', 'emoji': '🍺'}
        ],
        'color': 0x3498db,
        'emoji': '📚'
    },
    3: {
        'name': 'Journeyman',
        'points_required': 1000,
        'free_rewards': [
            {'type': 'points', 'amount': 200, 'emoji': '💰'},
            {'type': 'item', 'item': 'Potion Ingredient Pack', 'emoji': '🧪'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 400, 'emoji': '💰'},
            {'type': 'item', 'item': 'Rare Wand Core', 'emoji': '🪄'},
            {'type': 'key', 'name': 'Common Chest Key', 'emoji': '🔑'}
        ],
        'color': 0x2ecc71,
        'emoji': '⚔️'
    },
    4: {
        'name': 'Adept',
        'points_required': 2000,
        'free_rewards': [
            {'type': 'points', 'amount': 250, 'emoji': '💰'},
            {'type': 'item', 'item': 'Ancient Tome Page', 'emoji': '📖'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 500, 'emoji': '💰'},
            {'type': 'item', 'item': 'Dragon Egg Fragment', 'emoji': '🥚'},
            {'type': 'consumable', 'item': 'Felix Felicis (1 use)', 'emoji': '✨'}
        ],
        'color': 0xe67e22,
        'emoji': '🔮'
    },
    5: {
        'name': 'Expert',
        'points_required': 3500,
        'free_rewards': [
            {'type': 'points', 'amount': 300, 'emoji': '💰'},
            {'type': 'item', 'item': 'Magical Compass', 'emoji': '🧭'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 600, 'emoji': '💰'},
            {'type': 'item', 'item': 'Phoenix Feather', 'emoji': '🪶'},
            {'type': 'badge', 'name': 'Expert Wizard', 'emoji': '🌟'}
        ],
        'color': 0xf1c40f,
        'emoji': '🏆'
    },
    6: {
        'name': 'Master',
        'points_required': 5000,
        'free_rewards': [
            {'type': 'points', 'amount': 350, 'emoji': '💰'},
            {'type': 'item', 'item': 'Enchanted Map', 'emoji': '🗺️'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 700, 'emoji': '💰'},
            {'type': 'item', 'item': 'Basilisk Fang', 'emoji': '🐍'},
            {'type': 'key', 'name': 'Rare Chest Key', 'emoji': '🔑'}
        ],
        'color': 0x9b59b6,
        'emoji': '👑'
    },
    7: {
        'name': 'Grandmaster',
        'points_required': 7500,
        'free_rewards': [
            {'type': 'points', 'amount': 400, 'emoji': '💰'},
            {'type': 'item', 'item': 'Time Turner Shard', 'emoji': '⏳'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 800, 'emoji': '💰'},
            {'type': 'item', 'item': 'Thestral Hair', 'emoji': '🐴'},
            {'type': 'consumable', 'item': 'Polyjuice Potion', 'emoji': '👤'}
        ],
        'color': 0xe74c3c,
        'emoji': '⚡'
    },
    8: {
        'name': 'Legend',
        'points_required': 10000,
        'free_rewards': [
            {'type': 'points', 'amount': 500, 'emoji': '💰'},
            {'type': 'item', 'item': 'Marauders Map Piece', 'emoji': '🗺️'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 1000, 'emoji': '💰'},
            {'type': 'item', 'item': 'Elder Wand Piece', 'emoji': '👑'},
            {'type': 'badge', 'name': 'Legendary Wizard', 'emoji': '✨'}
        ],
        'color': 0xc0392b,
        'emoji': '🏅'
    },
    9: {
        'name': 'Mythic',
        'points_required': 15000,
        'free_rewards': [
            {'type': 'points', 'amount': 750, 'emoji': '💰'},
            {'type': 'item', 'item': 'Resurrection Stone Shard', 'emoji': '💎'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 1500, 'emoji': '💰'},
            {'type': 'item', 'item': 'Invisibility Cloak Fragment', 'emoji': '👻'},
            {'type': 'key', 'name': 'Legendary Chest Key', 'emoji': '🔑'}
        ],
        'color': 0x8e44ad,
        'emoji': '🌌'
    },
    10: {
        'name': 'Headmaster',
        'points_required': 20000,
        'free_rewards': [
            {'type': 'points', 'amount': 1000, 'emoji': '💰'},
            {'type': 'item', 'item': 'House Cup', 'emoji': '🏆'}
        ],
        'premium_rewards': [
            {'type': 'points', 'amount': 2000, 'emoji': '💰'},
            {'type': 'item', 'item': 'Complete Elder Wand', 'emoji': '👑'},
            {'type': 'item', 'item': 'Complete Resurrection Stone', 'emoji': '💎'},
            {'type': 'item', 'item': 'Complete Invisibility Cloak', 'emoji': '👻'},
            {'type': 'badge', 'name': 'Headmaster', 'emoji': '🏰'},
            {'type': 'role', 'name': 'Headmaster', 'emoji': '👑'}
        ],
        'color': 0x000000,
        'emoji': '🏰'
    }
}

PREMIUM_COST = 1000  # Points to unlock premium

# ==========================================
# INVENTORY ITEMS (SPECIAL ITEMS)
# ==========================================
ITEM_CATEGORIES = {
    'wand': {'name': 'Wands', 'emoji': '🪄', 'color': 0xff6b6b},
    'pet': {'name': 'Pets', 'emoji': '🐾', 'color': 0x3498db},
    'potion': {'name': 'Potions', 'emoji': '🧪', 'color': 0x2ecc71},
    'spell': {'name': 'Spells', 'emoji': '✨', 'color': 0x9b59b6},
    'treasure': {'name': 'Treasures', 'emoji': '💎', 'color': 0xf1c40f},
    'consumable': {'name': 'Consumables', 'emoji': '🍫', 'color': 0xe67e22},
    'quest': {'name': 'Quest Items', 'emoji': '📜', 'color': 0x1abc9c},
    'key': {'name': 'Keys', 'emoji': '🔑', 'color': 0xe74c3c},
    'artifact': {'name': 'Artifacts', 'emoji': '🏺', 'color': 0x8e44ad}
}

SPECIAL_ITEMS = {
    # Wands
    'phoenix_feather_wand': {
        'name': 'Phoenix Feather Wand',
        'emoji': '🪄',
        'category': 'wand',
        'rarity': 'legendary',
        'value': 500,
        'description': 'A wand with a phoenix feather core - very powerful and loyal',
        'effects': ['+20% spell power', 'Can cast Phoenix Song'],
        'obtained_from': ['Wand Shop', 'Legendary Chest'],
        'stackable': False,
        'tradeable': True
    },
    'dragon_heartstring_wand': {
        'name': 'Dragon Heartstring Wand',
        'emoji': '🐉',
        'category': 'wand',
        'rarity': 'rare',
        'value': 400,
        'description': 'A wand with a dragon heartstring core - powerful but temperamental',
        'effects': ['+15% duel power', 'Fire resistance'],
        'obtained_from': ['Wand Shop', 'Rare Chest'],
        'stackable': False,
        'tradeable': True
    },
    'unicorn_hair_wand': {
        'name': 'Unicorn Hair Wand',
        'emoji': '🦄',
        'category': 'wand',
        'rarity': 'rare',
        'value': 300,
        'description': 'A wand with a unicorn hair core - pure and consistent magic',
        'effects': ['+10% healing', '+5% spell accuracy'],
        'obtained_from': ['Wand Shop', 'Rare Chest'],
        'stackable': False,
        'tradeable': True
    },
    'thestral_hair_wand': {
        'name': 'Thestral Hair Wand',
        'emoji': '🐴',
        'category': 'wand',
        'rarity': 'legendary',
        'value': 450,
        'description': 'A wand with a thestral hair core - mysterious and powerful',
        'effects': ['+25% stealth', 'Can see thestrals'],
        'obtained_from': ['Wand Shop', 'Legendary Chest'],
        'stackable': False,
        'tradeable': True
    },
    'elder_wand': {
        'name': 'Elder Wand',
        'emoji': '👑',
        'category': 'wand',
        'rarity': 'mythic',
        'value': 10000,
        'description': 'The Deathstick - the most powerful wand in existence',
        'effects': ['+100% all magic', 'Unbeatable in duels', 'Can cast any spell'],
        'obtained_from': ['Mythic Chest (1% chance)', 'Legendary Quest'],
        'stackable': False,
        'tradeable': False
    },
    
    # Potions
    'felix_felicis': {
        'name': 'Felix Felicis',
        'emoji': '✨',
        'category': 'potion',
        'rarity': 'legendary',
        'value': 500,
        'description': 'Liquid luck - everything you try will succeed for a limited time',
        'effects': ['100% success rate for 1 hour', 'Find rare items'],
        'obtained_from': ['Potions Class', 'Legendary Chest'],
        'stackable': True,
        'max_stack': 3,
        'tradeable': True
    },
    'polyjuice_potion': {
        'name': 'Polyjuice Potion',
        'emoji': '🧪',
        'category': 'potion',
        'rarity': 'rare',
        'value': 300,
        'description': 'Transform into someone else for 1 hour',
        'effects': ['Disguise yourself', 'Access restricted areas'],
        'obtained_from': ['Potions Class', 'Rare Chest'],
        'stackable': True,
        'max_stack': 5,
        'tradeable': True
    },
    'veritaserum': {
        'name': 'Veritaserum',
        'emoji': '🔮',
        'category': 'potion',
        'rarity': 'rare',
        'value': 400,
        'description': 'Truth serum - forces the drinker to tell the truth',
        'effects': ['Win any argument', 'Solve mysteries'],
        'obtained_from': ['Potions Class', 'Rare Chest'],
        'stackable': True,
        'max_stack': 3,
        'tradeable': False
    },
    'amortentia': {
        'name': 'Amortentia',
        'emoji': '💕',
        'category': 'potion',
        'rarity': 'rare',
        'value': 350,
        'description': 'The most powerful love potion in existence',
        'effects': ['Make anyone fall for you', 'Special interactions'],
        'obtained_from': ['Potions Class', 'Rare Chest'],
        'stackable': True,
        'max_stack': 3,
        'tradeable': True
    },
    'skele_gro': {
        'name': 'Skele-Gro',
        'emoji': '🦴',
        'category': 'potion',
        'rarity': 'uncommon',
        'value': 200,
        'description': 'Regrows bones - painful but effective',
        'effects': ['Heal broken bones', 'Survive falls'],
        'obtained_from': ['Infirmary', 'Common Chest'],
        'stackable': True,
        'max_stack': 10,
        'tradeable': True
    },
    
    # Treasure Items
    'golden_snitch': {
        'name': 'Golden Snitch',
        'emoji': '✨',
        'category': 'treasure',
        'rarity': 'legendary',
        'value': 1000,
        'description': 'A tiny golden ball with silver wings - catches the light beautifully',
        'effects': ['+150 Quidditch points', 'Shows memories'],
        'obtained_from': ['Quidditch Victory', 'Legendary Chest'],
        'stackable': False,
        'tradeable': True
    },
    'house_cup': {
        'name': 'House Cup',
        'emoji': '🏆',
        'category': 'treasure',
        'rarity': 'legendary',
        'value': 2000,
        'description': 'The coveted House Cup - proof of your house superiority',
        'effects': ['Double points for 1 week', 'House pride'],
        'obtained_from': ['Winning House Cup'],
        'stackable': False,
        'tradeable': False
    },
    'gringotts_key': {
        'name': 'Gringotts Vault Key',
        'emoji': '🔑',
        'category': 'key',
        'rarity': 'rare',
        'value': 500,
        'description': 'A key to a personal vault at Gringotts',
        'effects': ['Weekly interest', 'Safe storage'],
        'obtained_from': ['Mythic Chest', 'Special Quest'],
        'stackable': False,
        'tradeable': False
    },
    
    # Consumables
    'chocolate_frog': {
        'name': 'Chocolate Frog',
        'emoji': '🐸',
        'category': 'consumable',
        'rarity': 'common',
        'value': 10,
        'description': 'A magical chocolate frog that tries to hop away',
        'effects': ['Restore 10 energy', 'Collect wizard cards'],
        'obtained_from': ['Honeydukes', 'Common Chest'],
        'stackable': True,
        'max_stack': 99,
        'tradeable': True
    },
    'butterbeer': {
        'name': 'Butterbeer',
        'emoji': '🍺',
        'category': 'consumable',
        'rarity': 'common',
        'value': 15,
        'description': 'A delicious butterscotch drink - slightly warming',
        'effects': ['Restore 15 energy', 'Warmth buff'],
        'obtained_from': ['Three Broomsticks', 'Common Chest'],
        'stackable': True,
        'max_stack': 99,
        'tradeable': True
    },
    'pumpkin_juice': {
        'name': 'Pumpkin Juice',
        'emoji': '🧃',
        'category': 'consumable',
        'rarity': 'common',
        'value': 5,
        'description': 'Fresh pumpkin juice - a Hogwarts favorite',
        'effects': ['Restore 5 energy'],
        'obtained_from': ['Great Hall', 'Common Chest'],
        'stackable': True,
        'max_stack': 99,
        'tradeable': True
    },
    
    # Quest Items
    'marauders_map': {
        'name': "Marauder's Map",
        'emoji': '🗺️',
        'category': 'quest',
        'rarity': 'legendary',
        'value': 1000,
        'description': 'A magical map showing everyone in Hogwarts',
        'effects': ['See all locations', 'Find secret passages'],
        'obtained_from': ['Mythic Chest', 'Secret Room'],
        'stackable': False,
        'tradeable': False
    },
    'resurrection_stone': {
        'name': 'Resurrection Stone',
        'emoji': '💎',
        'category': 'artifact',
        'rarity': 'mythic',
        'value': 5000,
        'description': 'One of the Deathly Hallows - can talk to the dead',
        'effects': ['Summon memories', 'Talk to departed'],
        'obtained_from': ['Mythic Chest (0.5% chance)', 'Legendary Quest'],
        'stackable': False,
        'tradeable': False
    },
    'invisibility_cloak': {
        'name': 'Invisibility Cloak',
        'emoji': '👻',
        'category': 'artifact',
        'rarity': 'mythic',
        'value': 5000,
        'description': 'One of the Deathly Hallows - true invisibility',
        'effects': ['Completely invisible', 'Avoid all detection'],
        'obtained_from': ['Mythic Chest (0.5% chance)', 'Legendary Quest'],
        'stackable': False,
        'tradeable': False
    }
}
# ==========================================
# DATA MANAGEMENT
# ==========================================
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            'houses': {h: {'points': 0, 'weekly': 0, 'monthly': 0, 'house_cup_wins': 0, 'quidditch_wins': 0, **HOUSE_DATA[h]} for h in HOUSE_DATA},
            'users': {},
            'checkins': {},
            'history': [],
            'duels': {},
            'achievements': {},
            'inventory': {},
            'chests_opened': {},
            'quests': {},
            'secrets_found': {},
            'map_access': {},
            'spells_learned': {},
            'potions_made': {},
            'classes_attended': {},
            'battle_pass': {},
            'tournaments': {},
            'marathons': {},
            'wands': {},
            'pets': {},
            'active_games': {},
            'market': {},
            'guilds': {}
        }

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

data = load_data()

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_house_emoji(house):
    return data['houses'][house]['emoji']

def get_house_color(house):
    return data['houses'][house]['color']

def get_random_spell_quote():
    return random.choice(SPELL_QUOTES)

def format_points(points):
    if points >= 1000000:
        return f"{points/1000000:.1f}M"
    elif points >= 1000:
        return f"{points/1000:.1f}K"
    return str(points)

def get_level_from_points(points):
    return math.floor(math.sqrt(points / 10)) + 1

def get_next_level_points(level):
    return (level ** 2) * 10

def get_level_progress(current_xp, current_level):
    next_xp = get_next_level_points(current_level)
    prev_xp = get_next_level_points(current_level - 1) if current_level > 1 else 0
    xp_for_level = current_xp - prev_xp
    xp_needed = next_xp - prev_xp
    progress = (xp_for_level / xp_needed) * 100 if xp_needed > 0 else 0
    return min(100, max(0, progress))

def create_progress_bar(percentage, length=20):
    filled = int((percentage / 100) * length)
    return "█" * filled + "░" * (length - filled)

def time_until_next_checkin(last_checkin):
    if not last_checkin:
        return "Now!"
    next_checkin = datetime.fromisoformat(last_checkin) + timedelta(days=1)
    time_left = next_checkin - datetime.now()
    hours = time_left.seconds // 3600
    minutes = (time_left.seconds % 3600) // 60
    return f"{hours}h {minutes}m"

def calculate_streak_bonus(streak):
    bonuses = {
        7: 50,
        30: 200,
        100: 500,
        365: 1000,
        500: 2000,
        1000: 5000,
        1825: 10000  # 5 years!
    }
    for days, bonus in sorted(bonuses.items()):
        if streak >= days:
            return bonus
    return 0

def get_achievement_emoji(achievement_id):
    achievements = {
        'first_checkin': '👣', 'streak_7': '🔥', 'streak_30': '🌙',
        'streak_100': '💯', 'streak_365': '👑', 'streak_500': '⚡',
        'streak_1000': '🌟', 'points_1000': '💰', 'points_10000': '💎',
        'duel_winner': '⚔️', 'quidditch_star': '🧹', 'secret_finder': '🔍',
        'pet_collector': '🐾', 'wand_master': '🪄', 'potion_brewer': '⚗️',
        'class_attendance': '📚', 'tournament_champ': '🏆', 'marathon_runner': '🏃'
    }
    return achievements.get(achievement_id, '🏅')

def get_rarity_color(rarity):
    colors = {
        'common': 0x95a5a6,
        'rare': 0x3498db,
        'legendary': 0xf1c40f,
        'mythic': 0x9b59b6
    }
    return colors.get(rarity, 0x95a5a6)

# ==========================================
# PERMISSION CHECKS FOR SLASH COMMANDS
# ==========================================
async def slash_is_staff(interaction: discord.Interaction):
    staff_roles = ['Headmaster', 'Professor', 'Prefect', 'Moderator', 'Admin', 'Staff', 'House Leader']
    return any(role.name in staff_roles for role in interaction.user.roles) or interaction.user.guild_permissions.administrator

async def slash_is_sorted(interaction: discord.Interaction):
    return str(interaction.user.id) in data['users']

async def slash_has_wand(interaction: discord.Interaction):
    return data['users'][str(interaction.user.id)].get('wand') is not None

async def slash_has_pet(interaction: discord.Interaction):
    return data['users'][str(interaction.user.id)].get('pet') is not None

async def slash_not_in_duel(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if 'duels' in data and user_id in data['duels']:
        return False
    return True

# ==========================================
# ACHIEVEMENT SYSTEM
# ==========================================
async def award_achievement(user_id, achievement_id):
    achievements = {
        'first_checkin': {
            'name': 'First Check-in',
            'emoji': '👣',
            'description': 'Checked in for the first time',
            'points': 50
        },
        'streak_7': {
            'name': 'Weekly Warrior',
            'emoji': '🔥',
            'description': '7-day check-in streak',
            'points': 100
        },
        'streak_30': {
            'name': 'Monthly Master',
            'emoji': '🌙',
            'description': '30-day check-in streak',
            'points': 300
        },
        'streak_100': {
            'name': 'Century Champion',
            'emoji': '💯',
            'description': '100-day check-in streak',
            'points': 1000
        },
        'streak_365': {
            'name': 'Yearly Legend',
            'emoji': '👑',
            'description': '365-day check-in streak',
            'points': 5000
        },
        'duel_winner': {
            'name': 'Duelist',
            'emoji': '⚔️',
            'description': 'Won first duel',
            'points': 100
        },
        'duel_master': {
            'name': 'Duel Master',
            'emoji': '⚔️✨',
            'description': 'Won 10 duels',
            'points': 500
        },
        'quidditch_star': {
            'name': 'Quidditch Star',
            'emoji': '🧹',
            'description': 'Played first Quidditch match',
            'points': 50
        },
        'secret_hunter': {
            'name': 'Secret Hunter',
            'emoji': '🔍',
            'description': 'Found 5 secret rooms',
            'points': 200
        },
        'master_explorer': {
            'name': 'Master Explorer',
            'emoji': '🗺️',
            'description': 'Found 10 secret rooms',
            'points': 500
        },
        'hogwarts_legend': {
            'name': 'Hogwarts Legend',
            'emoji': '🏰',
            'description': 'Found all secret rooms',
            'points': 1000
        },
        'pet_collector': {
            'name': 'Animal Friend',
            'emoji': '🐾',
            'description': 'Adopted first pet',
            'points': 100
        },
        'wand_master': {
            'name': 'Wand Master',
            'emoji': '🪄',
            'description': 'Purchased first wand',
            'points': 100
        },
        'potion_brewer': {
            'name': 'Potion Brewer',
            'emoji': '⚗️',
            'description': 'Brewed first potion',
            'points': 150
        },
        'class_attendance': {
            'name': 'Diligent Student',
            'emoji': '📚',
            'description': 'Attended first class',
            'points': 50
        },
        'tournament_champ': {
            'name': 'Tournament Champion',
            'emoji': '🏆',
            'description': 'Won a tournament',
            'points': 500
        },
        'marathon_runner': {
            'name': 'Marathon Runner',
            'emoji': '🏃',
            'description': 'Completed a marathon',
            'points': 300
        },
        'bp_veteran': {
            'name': 'Battle Pass Veteran',
            'emoji': '🎖️',
            'description': 'Reached tier 5',
            'points': 200
        },
        'bp_champion': {
            'name': 'Battle Pass Champion',
            'emoji': '🏆',
            'description': 'Reached tier 10',
            'points': 500
        },
        'bp_legend': {
            'name': 'Battle Pass Legend',
            'emoji': '👑',
            'description': 'Completed premium battle pass',
            'points': 1000
        }
    }
    
    if achievement_id not in achievements:
        return
    
    ach = achievements[achievement_id]
    
    if user_id not in data['users']:
        return
    
    user = data['users'][user_id]
    
    if 'achievements' not in user:
        user['achievements'] = []
    
    # Check if already has achievement
    if any(a['id'] == achievement_id for a in user['achievements']):
        return
    
    # Award achievement
    user['achievements'].append({
        'id': achievement_id,
        'name': ach['name'],
        'emoji': ach['emoji'],
        'earned': datetime.now().isoformat()
    })
    
    # Award bonus points
    user['points_contributed'] += ach['points']
    data['houses'][user['house']]['points'] += ach['points']
    
    save_data()
    
    return ach

# ==========================================
# QUEST PROGRESS TRACKING
# ==========================================
async def start_quest(user_id, quest_id):
    if quest_id not in QUESTS:
        return False
    
    user = data['users'][user_id]
    
    if 'quests' not in user:
        user['quests'] = {}
    
    if quest_id in user['quests']:
        return False
    
    if quest_id in user.get('completed_quests', []):
        return False
    
    quest = QUESTS[quest_id]
    
    user['quests'][quest_id] = {
        'current': 0,
        'target': quest['target'],
        'started': datetime.now().isoformat()
    }
    
    save_data()
    return True

async def update_quest_progress(user_id, quest_type, amount=1):
    if user_id not in data['users']:
        return
    
    user = data['users'][user_id]
    
    if 'quests' not in user:
        return
    
    updated = False
    for qid, progress in user['quests'].items():
        if qid in QUESTS and QUESTS[qid]['type'] == quest_type:
            progress['current'] += amount
            if progress['current'] > progress['target']:
                progress['current'] = progress['target']
            updated = True
    
    if updated:
        save_data()

# ==========================================
# BATTLE PASS FUNCTIONS
# ==========================================
async def give_reward(user_id, reward):
    user = data['users'][user_id]
    
    if reward['type'] == 'points':
        user['points_contributed'] += reward['amount']
        data['houses'][user['house']]['points'] += reward['amount']
    
    elif reward['type'] == 'item':
        if 'inventory' not in user:
            user['inventory'] = []
        # Find item ID
        for item_id, item_data in SPECIAL_ITEMS.items():
            if item_data['name'] == reward['item']:
                user['inventory'].append(item_id)
                break
    
    elif reward['type'] == 'consumable':
        if 'inventory' not in user:
            user['inventory'] = []
        # Add multiple if specified
        if 'x' in reward['item']:
            item_name = reward['item'].split(' x')[0]
            count = int(reward['item'].split('x')[-1])
            for item_id, item_data in SPECIAL_ITEMS.items():
                if item_data['name'] == item_name:
                    for _ in range(count):
                        user['inventory'].append(item_id)
                    break
        else:
            for item_id, item_data in SPECIAL_ITEMS.items():
                if item_data['name'] == reward['item']:
                    user['inventory'].append(item_id)
                    break
    
    elif reward['type'] == 'key':
        if 'keys' not in user:
            user['keys'] = []
        user['keys'].append(reward['name'])
    
    elif reward['type'] == 'badge':
        if 'badges' not in user:
            user['badges'] = []
        user['badges'].append({
            'name': reward['name'],
            'emoji': reward['emoji'],
            'earned': datetime.now().isoformat()
        })
    
    elif reward['type'] == 'role':
        # Role will be assigned by server
        pass

async def update_battle_pass_points(user_id, points_earned):
    """Update battle pass progress when user earns points"""
    user = data['users'][user_id]
    
    if 'battle_pass' not in user:
        user['battle_pass'] = {
            'tier': 1,
            'points': 0,
            'premium': False,
            'claimed_free': [],
            'claimed_premium': []
        }
    
    # Check for tier ups
    old_tier = user['battle_pass']['tier']
    current_points = user.get('points_contributed', 0)
    
    for tier_num, tier_data in BATTLE_PASS_TIERS.items():
        if current_points >= tier_data['points_required'] and tier_num > old_tier:
            user['battle_pass']['tier'] = tier_num
    
    if user['battle_pass']['tier'] > old_tier:
        await award_achievement(user_id, 'bp_veteran' if user['battle_pass']['tier'] >= 5 else None)
        if user['battle_pass']['tier'] >= 10:
            await award_achievement(user_id, 'bp_champion')
        if user['battle_pass'].get('premium', False) and user['battle_pass']['tier'] >= 10:
            await award_achievement(user_id, 'bp_legend')
    
    save_data()

# ==========================================
# CLASS ACHIEVEMENTS
# ==========================================
async def check_class_achievements(user_id):
    user = data['users'][user_id]
    attendance = user.get('class_attendance', {})
    total = sum(attendance.values())
    
    if total >= 10:
        await award_achievement(user_id, 'class_attendance')
    
    if total >= 50:
        # Could add more achievements here
        pass

# ==========================================
# POINT REASON MODAL
# ==========================================
class PointReasonModal(Modal):
    def __init__(self, member, points, action):
        super().__init__(title=f"{action.title()} Points")
        self.member = member
        self.points = points
        self.action = action
        
        self.reason = discord.ui.TextInput(
            label="Reason",
            placeholder=f"Reason for {action}ing points...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=100
        )
        self.add_item(self.reason)
    
    async def callback(self, interaction: discord.Interaction):
        if self.action == "add":
            await process_add_points(interaction, self.member, self.points, self.reason.value)
        else:
            await process_remove_points(interaction, self.member, self.points, self.reason.value)

# ==========================================
# POINT PROCESSING FUNCTIONS
# ==========================================
async def process_add_points(interaction, member, points, reason=""):
    if points <= 0:
        await interaction.response.send_message("❌ Points must be positive!", ephemeral=True)
        return
    
    user_id = str(member.id)
    if user_id not in data['users']:
        await interaction.response.send_message("❌ User hasn't been sorted yet!", ephemeral=True)
        return
    
    house = data['users'][user_id]['house']
    house_info = data['houses'][house]
    
    # Random multiplier
    multiplier = 1
    if random.random() < 0.05:  # 5% chance
        multiplier = 2
        bonus_msg = "🎉 **DOUBLE POINTS!** 🎉"
    elif random.random() < 0.01:  # 1% chance
        multiplier = 3
        bonus_msg = "⚡ **TRIPLE POINTS!** ⚡"
    else:
        bonus_msg = ""
    
    actual_points = points * multiplier
    
    # Add points
    data['houses'][house]['points'] += actual_points
    data['houses'][house]['weekly'] += actual_points
    data['houses'][house]['monthly'] += actual_points
    data['users'][user_id]['points_contributed'] += actual_points
    data['users'][user_id]['xp'] = data['users'][user_id].get('xp', 0) + actual_points
    
    # Check level up
    old_level = data['users'][user_id].get('level', 1)
    new_level = get_level_from_points(data['users'][user_id]['xp'])
    if new_level > old_level:
        data['users'][user_id]['level'] = new_level
        level_msg = f"\n🌟 **LEVEL UP!** Now level {new_level}! 🌟"
    else:
        level_msg = ""
    
    # Log it
    data['history'].append({
        'timestamp': datetime.now().isoformat(),
        'type': 'add',
        'user': user_id,
        'mod': interaction.user.id,
        'house': house,
        'points': actual_points,
        'multiplier': multiplier,
        'reason': reason
    })
    
    # Dramatic announcement
    quality = random.choice(house_info['traits'])
    
    embed = discord.Embed(
        title="✨ POINTS AWARDED! ✨",
        description=f"{bonus_msg}\n\n**{actual_points} points** to **{house_info['name']}** for {quality}!{level_msg}",
        color=house_info['color']
    )
    embed.add_field(name="Recipient", value=member.mention)
    embed.add_field(name="Awarded by", value=interaction.user.mention)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    save_data()

async def process_remove_points(interaction, member, points, reason=""):
    if points <= 0:
        await interaction.response.send_message("❌ Points must be positive!", ephemeral=True)
        return
    
    user_id = str(member.id)
    if user_id not in data['users']:
        await interaction.response.send_message("❌ User hasn't been sorted yet!", ephemeral=True)
        return
    
    house = data['users'][user_id]['house']
    house_info = data['houses'][house]
    
    data['houses'][house]['points'] = max(0, data['houses'][house]['points'] - points)
    data['houses'][house]['weekly'] = max(0, data['houses'][house]['weekly'] - points)
    data['houses'][house]['monthly'] = max(0, data['houses'][house]['monthly'] - points)
    
    data['history'].append({
        'timestamp': datetime.now().isoformat(),
        'type': 'remove',
        'user': user_id,
        'mod': interaction.user.id,
        'house': house,
        'points': points,
        'reason': reason
    })
    
    embed = discord.Embed(
        title="⚠️ POINTS DEDUCTED",
        description=f"**{points} points** from **{house_info['name']}**!",
        color=0x808080
    )
    embed.add_field(name="Recipient", value=member.mention)
    embed.add_field(name="Deducted by", value=interaction.user.mention)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    save_data()

# ==========================================
# TRIVIA GAME CLASS
# ==========================================
class TriviaGame:
    def __init__(self):
        self.questions = {
            'easy': [
                {"q": "What is Harry Potter's owl's name?", "a": "hedwig", "points": 10},
                {"q": "Which house is Harry Potter in?", "a": "gryffindor", "points": 10},
                {"q": "Who is the headmaster of Hogwarts?", "a": "dumbledore", "points": 10},
                {"q": "What is the name of the Hogwarts game?", "a": "quidditch", "points": 10},
                {"q": "What is Ron's last name?", "a": "weasley", "points": 10}
            ],
            'medium': [
                {"q": "What spell is used to disarm an opponent?", "a": "expelliarmus", "points": 20},
                {"q": "What is the core of Harry's first wand?", "a": "phoenix feather", "points": 20},
                {"q": "Who killed Dobby?", "a": "bellatrix", "points": 20},
                {"q": "What is Voldemort's real name?", "a": "tom riddle", "points": 20},
                {"q": "What potion gives luck?", "a": "felix felicis", "points": 20}
            ],
            'hard': [
                {"q": "What are the three Unforgivable Curses?", "a": "imperio crucio avada kedavra", "points": 50},
                {"q": "Who was the master of the Elder Wand before Dumbledore?", "a": "grindelwald", "points": 40},
                {"q": "How many staircases are there at Hogwarts?", "a": "142", "points": 50},
                {"q": "What is the exact incantation for the Patronus Charm?", "a": "expecto patronum", "points": 30},
                {"q": "What is the name of the Room of Requirement when it's hiding things?", "a": "room of hidden things", "points": 40}
            ]
        }
        self.active_games = {}
        self.scores = defaultdict(int)
    
    def get_question(self, difficulty):
        return random.choice(self.questions.get(difficulty, self.questions['easy']))

trivia = TriviaGame()
# ==========================================
# SLASH COMMANDS - SORTING HAT
# ==========================================
class SortingHatView(View):
    def __init__(self, user_id, member):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.member = member
        self.add_item(HouseSelect(user_id, member))
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class HouseSelect(Select):
    def __init__(self, user_id, member):
        self.user_id = user_id
        self.member = member
        options = []
        for house_id, house in HOUSE_DATA.items():
            options.append(discord.SelectOption(
                label=f"{house['emoji']} {house['name']}",
                description=house['welcome_message'][:50],
                emoji=house['emoji'],
                value=house_id
            ))
        super().__init__(placeholder="Choose a house for the sorting...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Only the staff member who started this can sort!", ephemeral=True)
            return
        
        house = self.values[0]
        await perform_sorting(interaction, self.member, house)

async def perform_sorting(interaction, member, house):
    user_id = str(member.id)
    
    # Dramatic sorting ceremony
    embed = discord.Embed(
        title="🎓 THE SORTING HAT CEREMONY",
        description=f"{member.mention} approaches the stool...\n\nThe Sorting Hat considers...",
        color=HOUSE_DATA[house]['color']
    )
    await interaction.response.edit_message(embed=embed, view=None)
    await asyncio.sleep(2)
    
    # Check if user already exists
    old_house = None
    if user_id in data['users']:
        old_house = data['users'][user_id]['house']
    
    # Create or update user
    data['users'][user_id] = {
        'name': member.name,
        'display_name': member.display_name,
        'house': house,
        'points_contributed': data['users'].get(user_id, {}).get('points_contributed', 0),
        'checkins': data['users'].get(user_id, {}).get('checkins', 0),
        'joined': data['users'].get(user_id, {}).get('joined', datetime.now().isoformat()),
        'level': get_level_from_points(data['users'].get(user_id, {}).get('xp', 0)),
        'xp': data['users'].get(user_id, {}).get('xp', 0),
        'title': data['users'].get(user_id, {}).get('title', 'Student'),
        'bio': data['users'].get(user_id, {}).get('bio', ''),
        'favorite_spell': data['users'].get(user_id, {}).get('favorite_spell', ''),
        'pet': data['users'].get(user_id, {}).get('pet', None),
        'wand': data['users'].get(user_id, {}).get('wand', None),
        'achievements': data['users'].get(user_id, {}).get('achievements', []),
        'badges': data['users'].get(user_id, {}).get('badges', []),
        'duels_won': data['users'].get(user_id, {}).get('duels_won', 0),
        'duels_lost': data['users'].get(user_id, {}).get('duels_lost', 0),
        'quidditch_points': data['users'].get(user_id, {}).get('quidditch_points', 0),
        'inventory': data['users'].get(user_id, {}).get('inventory', []),
        'spells_learned': data['users'].get(user_id, {}).get('spells_learned', []),
        'secrets_found': data['users'].get(user_id, {}).get('secrets_found', []),
        'quests': data['users'].get(user_id, {}).get('quests', {}),
        'chests_opened': data['users'].get(user_id, {}).get('chests_opened', {}),
        'last_class': data['users'].get(user_id, {}).get('last_class', {}),
        'battle_pass': data['users'].get(user_id, {}).get('battle_pass', {'tier': 1, 'points': 0, 'claimed': []})
    }
    
    # Assign house role
    guild = interaction.guild
    house_role = discord.utils.get(guild.roles, name=house.title())
    if not house_role:
        house_role = await guild.create_role(
            name=house.title(),
            color=discord.Color(HOUSE_DATA[house]['color']),
            hoist=True,
            mentionable=True
        )
    await member.add_roles(house_role)
    
    # Remove old house role if exists
    if old_house:
        old_role = discord.utils.get(guild.roles, name=old_house.title())
        if old_role:
            await member.remove_roles(old_role)
    
    # Award welcome points
    welcome_points = 100
    data['houses'][house]['points'] += welcome_points
    data['houses'][house]['weekly'] += welcome_points
    data['houses'][house]['monthly'] += welcome_points
    data['users'][user_id]['points_contributed'] += welcome_points
    data['users'][user_id]['xp'] = data['users'][user_id].get('xp', 0) + welcome_points
    
    # Final announcement
    house_info = HOUSE_DATA[house]
    embed = discord.Embed(
        title="🏰 THE SORTING HAT HAS SPOKEN! 🏰",
        description=f"{get_random_spell_quote()}\n\n**{member.mention}** is now a member of...\n\n# {house_info['emoji']} **{house_info['name']}!**\n\n*{house_info['welcome_message']}*",
        color=house_info['color']
    )
    embed.add_field(name="Founder", value=house_info['founder'], inline=True)
    embed.add_field(name="Animal", value=house_info['animal'], inline=True)
    embed.add_field(name="Element", value=house_info['element'], inline=True)
    embed.add_field(name="Ghost", value=house_info['ghost'], inline=True)
    embed.add_field(name="Common Room", value=house_info['common_room'], inline=True)
    embed.add_field(name="Welcome Points", value=f"+{welcome_points}", inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    
    await interaction.channel.send(embed=embed)
    save_data()

@bot.tree.command(name="sort", description="Sort a user into a house (Staff only)")
@app_commands.describe(member="The user to sort", house="Choose a house (optional - interactive if not chosen)")
@app_commands.choices(house=[
    app_commands.Choice(name="🦁 Gryffindor", value="gryffindor"),
    app_commands.Choice(name="🐍 Slytherin", value="slytherin"),
    app_commands.Choice(name="🦅 Ravenclaw", value="ravenclaw"),
    app_commands.Choice(name="🦡 Hufflepuff", value="hufflepuff"),
    app_commands.Choice(name="🎲 Random House", value="random")
])
async def slash_sort(interaction: discord.Interaction, member: discord.Member, house: str = None):
    if not await slash_is_staff(interaction):
        await interaction.response.send_message("❌ You need staff permissions!", ephemeral=True)
        return
    
    if house == "random":
        house = random.choice(list(HOUSE_DATA.keys()))
        await perform_sorting(interaction, member, house)
    elif house:
        if house not in HOUSE_DATA:
            await interaction.response.send_message("❌ Invalid house!", ephemeral=True)
            return
        await perform_sorting(interaction, member, house)
    else:
        view = SortingHatView(str(interaction.user.id), member)
        embed = discord.Embed(
            title="🎓 SORTING CEREMONY",
            description=f"Choose a house for {member.mention}:",
            color=0x9b59b6
        )
        await interaction.response.send_message(embed=embed, view=view)

# ==========================================
# SLASH COMMANDS - POINTS
# ==========================================
@bot.tree.command(name="add", description="Add points to a user (Staff only)")
@app_commands.describe(member="The user to award", points="Number of points", reason="Reason for awarding")
async def slash_add(interaction: discord.Interaction, member: discord.Member, points: int, reason: str = ""):
    if not await slash_is_staff(interaction):
        await interaction.response.send_message("❌ You need staff permissions!", ephemeral=True)
        return
    
    if points <= 0:
        await interaction.response.send_message("❌ Points must be positive!", ephemeral=True)
        return
    
    user_id = str(member.id)
    if user_id not in data['users']:
        await interaction.response.send_message("❌ User hasn't been sorted yet!", ephemeral=True)
        return
    
    house = data['users'][user_id]['house']
    house_info = data['houses'][house]
    
    # Add points
    data['houses'][house]['points'] += points
    data['houses'][house]['weekly'] += points
    data['houses'][house]['monthly'] += points
    data['users'][user_id]['points_contributed'] += points
    data['users'][user_id]['xp'] = data['users'][user_id].get('xp', 0) + points
    
    # Log it
    if 'history' not in data:
        data['history'] = []
    data['history'].append({
        'timestamp': datetime.now().isoformat(),
        'type': 'add',
        'user': user_id,
        'mod': interaction.user.id,
        'house': house,
        'points': points,
        'reason': reason
    })
    
    embed = discord.Embed(
        title="✨ POINTS AWARDED! ✨",
        description=f"**{points} points** to **{HOUSE_DATA[house]['name']}**!",
        color=HOUSE_DATA[house]['color']
    )
    embed.add_field(name="Recipient", value=member.mention)
    embed.add_field(name="Awarded by", value=interaction.user.mention)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    save_data()

@bot.tree.command(name="remove", description="Remove points from a user (Staff only)")
@app_commands.describe(member="The user", points="Number of points", reason="Reason for removal")
async def slash_remove(interaction: discord.Interaction, member: discord.Member, points: int, reason: str = ""):
    if not await slash_is_staff(interaction):
        await interaction.response.send_message("❌ You need staff permissions!", ephemeral=True)
        return
    
    if points <= 0:
        await interaction.response.send_message("❌ Points must be positive!", ephemeral=True)
        return
    
    user_id = str(member.id)
    if user_id not in data['users']:
        await interaction.response.send_message("❌ User hasn't been sorted yet!", ephemeral=True)
        return
    
    house = data['users'][user_id]['house']
    house_info = data['houses'][house]
    
    data['houses'][house]['points'] = max(0, data['houses'][house]['points'] - points)
    data['houses'][house]['weekly'] = max(0, data['houses'][house]['weekly'] - points)
    data['houses'][house]['monthly'] = max(0, data['houses'][house]['monthly'] - points)
    
    if 'history' not in data:
        data['history'] = []
    data['history'].append({
        'timestamp': datetime.now().isoformat(),
        'type': 'remove',
        'user': user_id,
        'mod': interaction.user.id,
        'house': house,
        'points': points,
        'reason': reason
    })
    
    embed = discord.Embed(
        title="⚠️ POINTS DEDUCTED",
        description=f"**{points} points** from **{house_info['name']}**!",
        color=0x808080
    )
    embed.add_field(name="Recipient", value=member.mention)
    embed.add_field(name="Deducted by", value=interaction.user.mention)
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed)
    save_data()
# ==========================================
# SLASH COMMANDS - SCOREBOARD
# ==========================================
@bot.tree.command(name="scores", description="View house points standings")
@app_commands.describe(period="Time period to view")
@app_commands.choices(period=[
    app_commands.Choice(name="🏆 All Time", value="all"),
    app_commands.Choice(name="📅 This Week", value="weekly"),
    app_commands.Choice(name="📆 This Month", value="monthly")
])
async def slash_scores(interaction: discord.Interaction, period: str = "all"):
    embed = discord.Embed(
        title="🏆 THE HOUSE CUP STANDINGS 🏆",
        color=0x9b59b6,
        timestamp=datetime.now()
    )
    
    points_key = 'weekly' if period == 'weekly' else 'monthly' if period == 'monthly' else 'points'
    period_name = "This Week" if period == 'weekly' else "This Month" if period == 'monthly' else "All Time"
    
    sorted_houses = sorted(
        data['houses'].items(),
        key=lambda x: x[1][points_key],
        reverse=True
    )
    
    max_points = max(h[1][points_key] for h in sorted_houses) if sorted_houses else 1
    
    for house, info in sorted_houses:
        points = info[points_key]
        
        # Create progress bar
        bar_length = 20
        filled = int((points / max(1, max_points)) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        # Get member count
        member_count = len([u for u in data['users'].values() if u['house'] == house])
        
        # Calculate percentage
        total_points = sum(h[points_key] for h in data['houses'].values())
        percentage = (points / total_points * 100) if total_points > 0 else 0
        
        embed.add_field(
            name=f"{info['emoji']} **{info['name']}**",
            value=f"```\n{bar}\n```**{format_points(points)}** points | {member_count} members | {percentage:.1f}%",
            inline=False
        )
    
    # Add footer with stats
    total = sum(h[points_key] for h in data['houses'].values())
    embed.add_field(
        name="📊 STATISTICS",
        value=f"**Total Points:** {format_points(total)}\n**Period:** {period_name}",
        inline=False
    )
    
    # Add house cup wins
    cup_wins = "\n".join([f"{data['houses'][h]['emoji']} {data['houses'][h]['name']}: {data['houses'][h].get('house_cup_wins', 0)} wins" for h in data['houses']])
    embed.add_field(name="🏆 HOUSE CUP HISTORY", value=cup_wins, inline=False)
    
    await interaction.response.send_message(embed=embed)

# ==========================================
# SLASH COMMANDS - POINT LOG
# ==========================================
@bot.tree.command(name="pointlog", description="View recent point transactions")
@app_commands.describe(limit="Number of entries to show (default 10)")
async def slash_pointlog(interaction: discord.Interaction, limit: int = 10):
    history = data['history'][-limit:]
    
    if not history:
        await interaction.response.send_message("No point history yet!")
        return
    
    embed = discord.Embed(
        title="📜 RECENT POINT TRANSACTIONS",
        color=0x9b59b6,
        timestamp=datetime.now()
    )
    
    for entry in reversed(history):
        timestamp = datetime.fromisoformat(entry['timestamp']).strftime('%H:%M %b %d')
        
        user = interaction.guild.get_member(int(entry['user']))
        user_name = user.display_name if user else "Unknown"
        
        mod = interaction.guild.get_member(int(entry['mod'])) if 'mod' in entry else None
        mod_name = mod.display_name if mod else "System"
        
        emoji = "➕" if entry['type'] == 'add' else "➖" if entry['type'] == 'remove' else "🔄"
        house_emoji = data['houses'][entry['house']]['emoji'] if entry['house'] in data['houses'] else ""
        
        value = f"{house_emoji} **{entry['points']}** points by {mod_name}"
        if entry.get('reason'):
            value += f"\n*{entry['reason']}*"
        
        embed.add_field(
            name=f"{emoji} {user_name} - {timestamp}",
            value=value,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

# ==========================================
# SLASH COMMANDS - CHECK-IN
# ==========================================
@bot.tree.command(name="checkin", description="Daily check-in to earn points")
async def slash_checkin(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first! Use `/sort`", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    today = datetime.now().strftime('%Y-%m-%d')
    user = data['users'][user_id]
    house = user['house']
    
    if user_id not in data['checkins']:
        data['checkins'][user_id] = {'last': None, 'streak': 0, 'total': 0, 'longest': 0}
    
    check = data['checkins'][user_id]
    if check['last'] == today:
        await interaction.response.send_message(f"❌ {interaction.user.mention}, you've already checked in today!", ephemeral=True)
        return
    
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    check['streak'] = check['streak'] + 1 if check['last'] == yesterday else 1
    check['longest'] = max(check['longest'], check['streak'])
    check['last'] = today
    check['total'] += 1
    
    base_points = 10
    streak_bonus = calculate_streak_bonus(check['streak'])
    total_points = base_points + streak_bonus
    
    data['houses'][house]['points'] += total_points
    data['houses'][house]['weekly'] += total_points
    data['houses'][house]['monthly'] += total_points
    user['points_contributed'] += total_points
    user['checkins'] = user.get('checkins', 0) + 1
    user['xp'] = user.get('xp', 0) + total_points
    
    # Check level up
    old_level = user.get('level', 1)
    new_level = get_level_from_points(user['xp'])
    if new_level > old_level:
        user['level'] = new_level
        level_msg = f"\n🌟 **LEVEL UP!** Now level {new_level}! 🌟"
    else:
        level_msg = ""
    
    # Check for achievements
    if check['total'] == 1:
        await award_achievement(user_id, 'first_checkin')
    if check['streak'] >= 7:
        await award_achievement(user_id, 'streak_7')
    if check['streak'] >= 30:
        await award_achievement(user_id, 'streak_30')
    if check['streak'] >= 100:
        await award_achievement(user_id, 'streak_100')
    if check['streak'] >= 365:
        await award_achievement(user_id, 'streak_365')
    
    embed = discord.Embed(
        title="✨ DAILY CHECK-IN ✨",
        description=f"{get_random_spell_quote()}\n\n{interaction.user.mention} checked in for **{data['houses'][house]['name']}**!{level_msg}",
        color=data['houses'][house]['color']
    )
    embed.add_field(name="Points", value=f"**{total_points}**", inline=True)
    embed.add_field(name="Streak", value=f"**{check['streak']}** days", inline=True)
    if streak_bonus > 0:
        embed.add_field(name="Streak Bonus", value=f"+{streak_bonus}", inline=True)
    
    await interaction.response.send_message(embed=embed)
    save_data()

@bot.tree.command(name="streak", description="Check your check-in streak")
@app_commands.describe(member="User to check (optional)")
async def slash_streak(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    user_id = str(target.id)
    
    if user_id not in data['users']:
        await interaction.response.send_message(f"❌ {target.display_name} hasn't been sorted yet!", ephemeral=True)
        return
    
    house = data['users'][user_id]['house']
    check = data['checkins'].get(user_id, {'streak': 0, 'longest': 0, 'total': 0})
    
    embed = discord.Embed(title=f"📊 Check-in Stats: {target.display_name}", color=data['houses'][house]['color'])
    embed.add_field(name="House", value=f"{data['houses'][house]['emoji']} {data['houses'][house]['name']}")
    embed.add_field(name="Current Streak", value=f"**{check['streak']}** days")
    embed.add_field(name="Longest Streak", value=f"**{check['longest']}** days")
    embed.add_field(name="Total Check-ins", value=f"**{check['total']}**")
    await interaction.response.send_message(embed=embed)
    # ==========================================
# SLASH COMMANDS - WAND SHOP
# ==========================================
class WandView(View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.add_item(WandSelect(user_id))
        self.add_item(WandInfoButton(user_id))
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class WandSelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = []
        for wid, wand in WANDS.items():
            options.append(discord.SelectOption(
                label=f"{wand['name']} - {wand['price']} pts",
                description=f"Power: {wand['power']} | {wand['rarity'].title()}",
                emoji=wand['emoji'],
                value=wid
            ))
        super().__init__(placeholder="🔮 Choose a wand to view details...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This shop isn't for you!", ephemeral=True)
            return
        
        wand_id = self.values[0]
        wand = WANDS[wand_id]
        user = data['users'][self.user_id]
        
        embed = discord.Embed(
            title=f"{wand['emoji']} {wand['name']}",
            description=f"*{wand['description']}*",
            color=wand['color']
        )
        embed.set_image(url=wand['image_url'])
        embed.add_field(name="💰 Price", value=f"{wand['price']} points", inline=True)
        embed.add_field(name="⚡ Power", value=str(wand['power']), inline=True)
        embed.add_field(name="✨ Rarity", value=wand['rarity'].title(), inline=True)
        embed.add_field(name="🪄 Core", value=wand['core'], inline=True)
        embed.add_field(name="🌳 Wood", value=wand['wood'], inline=True)
        embed.add_field(name="📏 Length", value=wand['length'], inline=True)
        embed.add_field(name="🎯 Flexibility", value=wand['flexibility'], inline=True)
        embed.add_field(name="🔮 Magic Type", value=wand['magic_type'], inline=True)
        embed.add_field(name="⚔️ Duel Bonus", value=f"+{wand['duel_bonus']}%", inline=True)
        embed.add_field(name="✨ Special Spells", value=", ".join(wand['spells']), inline=False)
        embed.add_field(name="🎁 Bonus", value=wand['bonus'], inline=False)
        embed.add_field(name="💰 Your Points", value=f"**{user['points_contributed']}**", inline=False)
        
        view = View()
        view.add_item(WandBuyButton(wand_id, wand, self.user_id))
        view.add_item(BackToWandsButton(self.user_id))
        
        await interaction.response.edit_message(embed=embed, view=view)

class WandBuyButton(Button):
    def __init__(self, wand_id, wand_data, user_id):
        super().__init__(
            label=f"Buy for {wand_data['price']} points",
            style=discord.ButtonStyle.success,
            emoji="💰",
            custom_id=f"buy_wand_{wand_id}"
        )
        self.wand_id = wand_id
        self.wand_data = wand_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This isn't your shop!", ephemeral=True)
            return
        
        user = data['users'][self.user_id]
        
        if user['points_contributed'] < self.wand_data['price']:
            embed = discord.Embed(
                title="❌ Not Enough Points!",
                description=f"You need **{self.wand_data['price']}** points but you only have **{user['points_contributed']}**!\n\nEarn more points by:\n• Daily check-ins (`/checkin`)\n• Playing Quidditch (`/quidditch`)\n• Winning duels (`/duel`)\n• Opening chests (`/chest`)",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check if already owns a wand
        if user.get('wand'):
            confirm_view = View()
            confirm_view.add_item(ConfirmWandReplaceButton(self.wand_id, self.wand_data, self.user_id))
            confirm_view.add_item(CancelButton())
            
            embed = discord.Embed(
                title="⚠️ Replace Wand?",
                description=f"You already own **{user['wand']}**. Are you sure you want to replace it with **{self.wand_data['name']}**?\n\nYour old wand will be lost forever!",
                color=0xffaa00
            )
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
            return
        
        await complete_wand_purchase(interaction, self.wand_id, self.wand_data, self.user_id)

class ConfirmWandReplaceButton(Button):
    def __init__(self, wand_id, wand_data, user_id):
        super().__init__(
            label="Yes, replace my wand",
            style=discord.ButtonStyle.danger,
            emoji="⚠️"
        )
        self.wand_id = wand_id
        self.wand_data = wand_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await complete_wand_purchase(interaction, self.wand_id, self.wand_data, self.user_id)

class CancelButton(Button):
    def __init__(self):
        super().__init__(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Purchase cancelled.", embed=None, view=None)

class WandInfoButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Your Wand",
            style=discord.ButtonStyle.secondary,
            emoji="🪄",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        user = data['users'][self.user_id]
        if not user.get('wand'):
            embed = discord.Embed(
                title="❌ No Wand",
                description="You don't have a wand yet! Buy one from the shop above.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Find wand data
        wand_data = None
        for wand in WANDS.values():
            if wand['name'] == user['wand']:
                wand_data = wand
                break
        
        if wand_data:
            embed = discord.Embed(
                title=f"🪄 Your Wand: {wand_data['name']}",
                color=wand_data['color']
            )
            embed.add_field(name="Power", value=str(wand_data['power']))
            embed.add_field(name="Core", value=wand_data['core'])
            embed.add_field(name="Wood", value=wand_data['wood'])
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(f"🪄 Your wand: {user['wand']}", ephemeral=True)

class BackToWandsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Back to Wands",
            style=discord.ButtonStyle.primary,
            emoji="🔙"
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await show_wand_shop(interaction, self.user_id)

async def complete_wand_purchase(interaction, wand_id, wand_data, user_id):
    user = data['users'][user_id]
    
    # Deduct points
    user['points_contributed'] -= wand_data['price']
    user['wand'] = wand_data['name']
    user['wand_power'] = wand_data['power']
    user['wand_id'] = wand_id
    
    # Award achievement if first wand
    await award_achievement(user_id, 'wand_master')
    
    embed = discord.Embed(
        title="🪄 WAND PURCHASED!",
        description=f"{interaction.user.mention} now wields the **{wand_data['name']}**!\n\nThe wand chooses the wizard, and this wand has chosen you!",
        color=wand_data['color']
    )
    embed.set_image(url=wand_data['image_url'])
    embed.add_field(name="Power", value=str(wand_data['power']))
    embed.add_field(name="Rarity", value=wand_data['rarity'].title())
    embed.add_field(name="Core", value=wand_data['core'])
    embed.add_field(name="Wood", value=wand_data['wood'])
    embed.add_field(name="Length", value=wand_data['length'])
    embed.add_field(name="Flexibility", value=wand_data['flexibility'])
    embed.add_field(name="Special Spells", value=", ".join(wand_data['spells'][:3]), inline=False)
    
    await interaction.response.edit_message(embed=embed, view=None)
    save_data()

async def show_wand_shop(interaction, user_id):
    user = data['users'][user_id]
    
    embed = discord.Embed(
        title="🪄 OLLIVANDERS: Makers of Fine Wands since 382 BC",
        description="*The wand chooses the wizard, remember...*",
        color=0x9b59b6
    )
    
    # Show owned wand
    if user.get('wand'):
        embed.add_field(name="✨ Your Current Wand", value=user['wand'], inline=False)
    
    embed.add_field(name="💰 Your Points", value=f"**{user['points_contributed']}**", inline=False)
    embed.set_footer(text="Select a wand from the dropdown to see details!")
    
    view = WandView(user_id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="wand", description="Visit Ollivanders wand shop")
async def slash_wand(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first! Use `/sort`", ephemeral=True)
        return
    
    await show_wand_shop(interaction, str(interaction.user.id))

# ==========================================
# SLASH COMMANDS - PET SHOP
# ==========================================
class PetView(View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.add_item(PetSelect(user_id))
        self.add_item(PetInfoButton(user_id))
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class PetSelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = []
        for pid, pet in PETS.items():
            options.append(discord.SelectOption(
                label=f"{pet['name']} - {pet['price']} pts",
                description=f"{pet['bonus']} | {pet['rarity'].title()}",
                emoji=pet['emoji'],
                value=pid
            ))
        super().__init__(placeholder="🐾 Choose a magical pet...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This shop isn't for you!", ephemeral=True)
            return
        
        pet_id = self.values[0]
        pet = PETS[pet_id]
        user = data['users'][self.user_id]
        
        embed = discord.Embed(
            title=f"{pet['emoji']} {pet['name']}",
            description=f"*{pet['ability']}*",
            color=pet['color']
        )
        embed.set_image(url=pet['image_url'])
        embed.add_field(name="💰 Price", value=f"{pet['price']} points", inline=True)
        embed.add_field(name="✨ Rarity", value=pet['rarity'].title(), inline=True)
        embed.add_field(name="🎁 Bonus", value=pet['bonus'], inline=True)
        embed.add_field(name="🌟 Special Ability", value=pet['special'], inline=False)
        embed.add_field(name="❤️ Base Happiness", value=f"{pet['happiness']}%", inline=True)
        embed.add_field(name="🍖 Base Hunger", value=f"{pet['hunger']}/100", inline=True)
        embed.add_field(name="⭐ Favorite Food", value=pet['favorite_food'], inline=True)
        embed.add_field(name="💰 Your Points", value=f"**{user['points_contributed']}**", inline=False)
        
        view = View()
        view.add_item(PetBuyButton(pet_id, pet, self.user_id))
        view.add_item(BackToPetsButton(self.user_id))
        
        await interaction.response.edit_message(embed=embed, view=view)

class PetBuyButton(Button):
    def __init__(self, pet_id, pet_data, user_id):
        super().__init__(
            label=f"Adopt for {pet_data['price']} points",
            style=discord.ButtonStyle.success,
            emoji="🐾",
            custom_id=f"buy_pet_{pet_id}"
        )
        self.pet_id = pet_id
        self.pet_data = pet_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This isn't your shop!", ephemeral=True)
            return
        
        user = data['users'][self.user_id]
        
        if user['points_contributed'] < self.pet_data['price']:
            embed = discord.Embed(
                title="❌ Not Enough Points!",
                description=f"You need **{self.pet_data['price']}** points but you only have **{user['points_contributed']}**!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check if already has a pet
        if user.get('pet'):
            confirm_view = View()
            confirm_view.add_item(ConfirmPetReplaceButton(self.pet_id, self.pet_data, self.user_id))
            confirm_view.add_item(CancelButton())
            
            embed = discord.Embed(
                title="⚠️ Replace Pet?",
                description=f"You already have **{user['pet']}**. Are you sure you want to replace it with **{self.pet_data['name']}**?\n\nYour current pet will be released back into the wild!",
                color=0xffaa00
            )
            await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)
            return
        
        await complete_pet_purchase(interaction, self.pet_id, self.pet_data, self.user_id)

class ConfirmPetReplaceButton(Button):
    def __init__(self, pet_id, pet_data, user_id):
        super().__init__(
            label="Yes, release my current pet",
            style=discord.ButtonStyle.danger,
            emoji="⚠️"
        )
        self.pet_id = pet_id
        self.pet_data = pet_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await complete_pet_purchase(interaction, self.pet_id, self.pet_data, self.user_id)

class PetInfoButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Your Pet",
            style=discord.ButtonStyle.secondary,
            emoji="🐾",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        user = data['users'][self.user_id]
        if not user.get('pet'):
            embed = discord.Embed(
                title="❌ No Pet",
                description="You don't have a pet yet! Adopt one from the shop above.",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"🐾 Your Pet: {user['pet']}",
            color=0x9b59b6
        )
        embed.add_field(name="❤️ Happiness", value=f"{user.get('pet_happiness', 80)}%")
        embed.add_field(name="🍖 Hunger", value=f"{user.get('pet_hunger', 10)}/100")
        embed.add_field(name="✨ Special", value=user.get('pet_special', 'None'))
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class BackToPetsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Back to Pets",
            style=discord.ButtonStyle.primary,
            emoji="🔙"
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await show_pet_shop(interaction, self.user_id)

async def complete_pet_purchase(interaction, pet_id, pet_data, user_id):
    user = data['users'][user_id]
    
    # Deduct points
    user['points_contributed'] -= pet_data['price']
    user['pet'] = pet_data['name']
    user['pet_id'] = pet_id
    user['pet_happiness'] = pet_data['happiness']
    user['pet_hunger'] = pet_data['hunger']
    user['pet_ability'] = pet_data['ability']
    user['pet_special'] = pet_data['special']
    user['pet_favorite_food'] = pet_data['favorite_food']
    
    # Award achievement if first pet
    await award_achievement(user_id, 'pet_collector')
    
    embed = discord.Embed(
        title=f"{pet_data['emoji']} NEW COMPANION!",
        description=f"{interaction.user.mention} adopts a **{pet_data['name']}**!\n\n*{pet_data['ability']}*",
        color=pet_data['color']
    )
    embed.set_image(url=pet_data['image_url'])
    embed.add_field(name="Bonus", value=pet_data['bonus'])
    embed.add_field(name="Special", value=pet_data['special'])
    embed.add_field(name="Happiness", value=f"{pet_data['happiness']}%")
    embed.add_field(name="Care Tips", value=f"Feed them {pet_data['favorite_food']} for best results!", inline=False)
    
    await interaction.response.edit_message(embed=embed, view=None)
    save_data()

async def show_pet_shop(interaction, user_id):
    user = data['users'][user_id]
    
    embed = discord.Embed(
        title="🐾 MAGICAL MENAGERIE",
        description="*Find your perfect magical companion!*",
        color=0x9b59b6
    )
    
    # Show owned pet
    if user.get('pet'):
        embed.add_field(
            name="✨ Your Current Pet",
            value=f"{user['pet']}\n❤️ {user.get('pet_happiness', 80)}% | 🍖 {user.get('pet_hunger', 10)}/100",
            inline=False
        )
    
    embed.add_field(name="💰 Your Points", value=f"**{user['points_contributed']}**", inline=False)
    embed.set_footer(text="Select a pet from the dropdown to see details!")
    
    view = PetView(user_id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="pet", description="Visit the Magical Menagerie pet shop")
async def slash_pet(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first! Use `/sort`", ephemeral=True)
        return
    
    await show_pet_shop(interaction, str(interaction.user.id))

# ==========================================
# SLASH COMMANDS - CHEST SYSTEM
# ==========================================
class ChestView(View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        
        for cid, chest in CHEST_REWARDS.items():
            self.add_item(ChestButton(cid, chest, user_id))
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class ChestButton(Button):
    def __init__(self, chest_id, chest_data, user_id):
        super().__init__(
            label=f"{chest_data['name']} ({chest_data['price']} pts)",
            style=discord.ButtonStyle.secondary,
            emoji="🎁",
            custom_id=f"chest_{chest_id}"
        )
        self.chest_id = chest_id
        self.chest_data = chest_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This isn't your chest game!", ephemeral=True)
            return
        
        user = data['users'][self.user_id]
        
        if user['points_contributed'] < self.chest_data['price']:
            embed = discord.Embed(
                title="❌ Not Enough Points!",
                description=f"You need **{self.chest_data['price']}** points but you only have **{user['points_contributed']}**!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Show opening animation
        embed = discord.Embed(
            title="🎁 Opening Chest...",
            description="✨ *Magic swirls around the chest...*",
            color=self.chest_data['color']
        )
        await interaction.response.edit_message(embed=embed, view=None)
        await asyncio.sleep(2)
        
        # Deduct points
        user['points_contributed'] -= self.chest_data['price']
        
        # Determine reward
        roll = random.randint(1, 100)
        cumulative = 0
        reward = None
        
        for reward_option in self.chest_data['rewards']:
            cumulative += reward_option['chance']
            if roll <= cumulative:
                reward = reward_option
                break
        
        if not reward:
            reward = self.chest_data['rewards'][0]
        
        # Generate reward
        reward_text = ""
        reward_value = 0
        item_name = ""
        
        if reward['type'] == 'points':
            amount = random.randint(reward['min'], reward['max'])
            user['points_contributed'] += amount
            reward_text = f"**{amount}** points"
            reward_value = amount
            emoji = "💰"
            
        elif reward['type'] == 'xp':
            amount = random.randint(reward['min'], reward['max'])
            user['xp'] = user.get('xp', 0) + amount
            reward_text = f"**{amount}** XP"
            reward_value = amount
            emoji = "✨"
            
        else:  # item
            item_name = random.choice(reward['items'])
            if 'inventory' not in user:
                user['inventory'] = []
            user['inventory'].append(item_name)
            reward_text = f"**{item_name}**"
            emoji = "📦"
            
            # Check for special items
            if item_name in ['Resurrection Stone', 'Invisibility Cloak', 'Elder Wand', 'Marauders Map']:
                if item_name == 'Marauders Map':
                    user['map_access'] = user.get('map_access', 0) + 5
        
        # Track chest opens
        if 'chests_opened' not in user:
            user['chests_opened'] = {}
        user['chests_opened'][self.chest_id] = user['chests_opened'].get(self.chest_id, 0) + 1
        
        # Check for guaranteed item chance
        if 'guaranteed' in self.chest_data and random.random() * 100 < self.chest_data['guaranteed']['chance']:
            bonus_item = self.chest_data['guaranteed']['item']
            user['inventory'].append(bonus_item)
            bonus_text = f"\n\n🎉 **BONUS!** You also found a **{bonus_item}**!"
        else:
            bonus_text = ""
        
        # Create result embed
        embed = discord.Embed(
            title=f"✨ {self.chest_data['name']} OPENED! ✨",
            description=f"{interaction.user.mention} opened a {self.chest_data['name']}!{bonus_text}",
            color=self.chest_data['color']
        )
        embed.set_image(url=self.chest_data['image'])
        embed.add_field(name="You found:", value=f"{emoji} {reward_text}", inline=True)
        embed.add_field(name="Points remaining", value=f"💰 **{user['points_contributed']}**", inline=True)
        
        # Add stats
        total_chests = sum(user['chests_opened'].values())
        embed.set_footer(text=f"Total chests opened: {total_chests}")
        
        # Offer to open another
        view = View()
        view.add_item(OpenAnotherChestButton(self.user_id))
        view.add_item(LeaveChestButton())
        
        await interaction.channel.send(embed=embed, view=view)
        save_data()

class OpenAnotherChestButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Open Another Chest",
            style=discord.ButtonStyle.primary,
            emoji="🎁"
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        await show_chest_shop(interaction, self.user_id)

class LeaveChestButton(Button):
    def __init__(self):
        super().__init__(
            label="Leave",
            style=discord.ButtonStyle.secondary,
            emoji="👋"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=None)

async def show_chest_shop(interaction, user_id):
    user = data['users'][user_id]
    
    embed = discord.Embed(
        title="🎁 MAGICAL CHESTS",
        description="Choose a chest to open! Each chest contains random rewards.",
        color=0x9b59b6
    )
    
    for cid, chest in CHEST_REWARDS.items():
        opened = user.get('chests_opened', {}).get(cid, 0)
        embed.add_field(
            name=f"{chest['name']} - {chest['price']} pts",
            value=f"Opened: {opened} times\nChance of rare items!",
            inline=False
        )
    
    embed.add_field(name="💰 Your Points", value=f"**{user['points_contributed']}**", inline=False)
    embed.add_field(name="📊 Total Chests", value=f"**{sum(user.get('chests_opened', {}).values())}**", inline=True)
    
    view = ChestView(user_id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="chest", description="Open magical chests for rewards!")
async def slash_chest(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first! Use `/sort`", ephemeral=True)
        return
    
    await show_chest_shop(interaction, str(interaction.user.id))

@bot.tree.command(name="cheststats", description="View your chest opening statistics")
async def slash_chest_stats(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    user = data['users'][user_id]
    
    chests = user.get('chests_opened', {})
    total = sum(chests.values())
    
    embed = discord.Embed(
        title=f"📊 {interaction.user.display_name}'s Chest Statistics",
        color=0x9b59b6
    )
    
    for cid, chest in CHEST_REWARDS.items():
        opened = chests.get(cid, 0)
        if opened > 0:
            embed.add_field(
                name=chest['name'],
                value=f"Opened: **{opened}** times",
                inline=True
            )
    
    embed.add_field(name="📦 Total Chests", value=f"**{total}**", inline=False)
    
    await interaction.response.send_message(embed=embed)
    # ==========================================
# SLASH COMMANDS - DUEL SYSTEM
# ==========================================
class DuelChallengeView(View):
    def __init__(self, challenger_id, opponent_id):
        super().__init__(timeout=60)
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.add_item(AcceptDuelButton(challenger_id, opponent_id))
        self.add_item(DeclineDuelButton())
    
    async def on_timeout(self):
        challenger = self.challenger_id
        opponent = self.opponent_id
        if 'duels' in data and challenger in data['duels']:
            del data['duels'][challenger]
        for item in self.children:
            item.disabled = True
        await self.message.edit(content="⏰ Duel challenge expired.", view=self)

class AcceptDuelButton(Button):
    def __init__(self, challenger_id, opponent_id):
        super().__init__(
            label="Accept Duel",
            style=discord.ButtonStyle.success,
            emoji="⚔️"
        )
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message("❌ This challenge isn't for you!", ephemeral=True)
            return
        
        challenger = interaction.guild.get_member(int(self.challenger_id))
        opponent = interaction.user
        
        # Check if both have wands
        if not data['users'][self.challenger_id].get('wand'):
            await interaction.response.send_message(f"❌ {challenger.display_name} doesn't have a wand!", ephemeral=True)
            return
        
        if not data['users'][self.opponent_id].get('wand'):
            await interaction.response.send_message("❌ You need a wand to duel! Visit the wand shop with `/wand`", ephemeral=True)
            return
        
        # Initialize duel
        data['duels'][self.challenger_id] = {
            'opponent': self.opponent_id,
            'challenger_score': 0,
            'opponent_score': 0,
            'round': 0,
            'total_rounds': 5,
            'questions': [],
            'start_time': datetime.now().isoformat()
        }
        
        embed = discord.Embed(
            title="⚔️ DUEL ACCEPTED! ⚔️",
            description=f"{challenger.mention} vs {opponent.mention}\n\nThe duel will begin shortly...",
            color=0xffd700
        )
        await interaction.response.edit_message(embed=embed, view=None)
        await asyncio.sleep(3)
        
        await start_duel(interaction, self.challenger_id)

class DeclineDuelButton(Button):
    def __init__(self):
        super().__init__(
            label="Decline",
            style=discord.ButtonStyle.danger,
            emoji="❌"
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Duel declined.", embed=None, view=None)

async def start_duel(interaction, duel_id):
    duel = data['duels'][duel_id]
    challenger = interaction.guild.get_member(int(duel_id))
    opponent = interaction.guild.get_member(int(duel['opponent']))
    
    # Generate questions based on spells known
    all_questions = [
        {"q": "What spell disarms your opponent?", "a": "expelliarmus", "points": 10},
        {"q": "What is the Killing Curse?", "a": "avadakedavra", "points": 20},
        {"q": "What spell creates a Patronus?", "a": "expecto patronum", "points": 15},
        {"q": "What spell unlocks doors?", "a": "alohomora", "points": 10},
        {"q": "What spell lights your wand?", "a": "lumos", "points": 5},
        {"q": "What spell extinguishes light?", "a": "nox", "points": 5},
        {"q": "What spell stuns your opponent?", "a": "stupefy", "points": 15},
        {"q": "What spell creates a shield?", "a": "protego", "points": 15},
        {"q": "What summons objects?", "a": "accio", "points": 10},
        {"q": "What is the Cruciatus Curse?", "a": "crucio", "points": 20},
        {"q": "What is the Imperius Curse?", "a": "imperio", "points": 20},
        {"q": "What spell causes pain?", "a": "sectumsempra", "points": 15}
    ]
    
    # Select random questions
    duel['questions'] = random.sample(all_questions, 5)
    
    embed = discord.Embed(
        title="⚔️ THE DUEL BEGINS! ⚔️",
        description=f"{challenger.mention} vs {opponent.mention}\n\nFirst to win 3 rounds wins the duel!",
        color=0xffd700
    )
    await interaction.channel.send(embed=embed)
    await asyncio.sleep(2)
    
    await run_duel_round(interaction, duel_id, 0)

async def run_duel_round(interaction, duel_id, round_num):
    duel = data['duels'][duel_id]
    
    if round_num >= 5 or duel['challenger_score'] >= 3 or duel['opponent_score'] >= 3:
        await end_duel(interaction, duel_id)
        return
    
    challenger = interaction.guild.get_member(int(duel_id))
    opponent = interaction.guild.get_member(int(duel['opponent']))
    question = duel['questions'][round_num]
    
    embed = discord.Embed(
        title=f"⚔️ ROUND {round_num + 1}/5",
        description=f"**{question['q']}**\n\nFirst to answer correctly wins this round!",
        color=0x9b59b6
    )
    embed.set_footer(text="Type your answer in chat!")
    await interaction.channel.send(embed=embed)
    
    def check(m):
        return m.author in [challenger, opponent] and m.channel == interaction.channel
    
    try:
        # Wait for answer
        answer_msg = await bot.wait_for('message', timeout=30.0, check=check)
        
        # Check if answer is correct
        is_correct = answer_msg.content.lower().replace(' ', '') == question['a'].lower().replace(' ', '')
        
        if is_correct:
            if answer_msg.author == challenger:
                duel['challenger_score'] += 1
                winner_mention = challenger.mention
            else:
                duel['opponent_score'] += 1
                winner_mention = opponent.mention
            
            # Speed bonus
            time_taken = (datetime.now() - answer_msg.created_at).seconds
            speed_bonus = max(0, 10 - time_taken)
            
            embed = discord.Embed(
                title="✅ CORRECT!",
                description=f"{winner_mention} wins the round!",
                color=0x00ff00
            )
            embed.add_field(name="Score", value=f"{duel['challenger_score']} - {duel['opponent_score']}")
            if speed_bonus > 0:
                embed.add_field(name="Speed Bonus", value=f"+{speed_bonus}% power next round")
            await interaction.channel.send(embed=embed)
        else:
            # Wrong answer - other person gets a chance?
            embed = discord.Embed(
                title="❌ INCORRECT!",
                description=f"{answer_msg.author.mention} got it wrong!",
                color=0xff0000
            )
            await interaction.channel.send(embed=embed)
        
        # Next round
        await asyncio.sleep(2)
        duel['round'] = round_num + 1
        await run_duel_round(interaction, duel_id, round_num + 1)
        
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="⏰ TIME'S UP!",
            description="No one answered in time. Moving to next round...",
            color=0xffaa00
        )
        await interaction.channel.send(embed=embed)
        await asyncio.sleep(2)
        duel['round'] = round_num + 1
        await run_duel_round(interaction, duel_id, round_num + 1)

async def end_duel(interaction, duel_id):
    duel = data['duels'][duel_id]
    challenger = interaction.guild.get_member(int(duel_id))
    opponent = interaction.guild.get_member(int(duel['opponent']))
    
    challenger_score = duel['challenger_score']
    opponent_score = duel['opponent_score']
    
    # Calculate winner
    if challenger_score > opponent_score:
        winner = challenger
        loser = opponent
        winner_score = challenger_score
        loser_score = opponent_score
    elif opponent_score > challenger_score:
        winner = opponent
        loser = challenger
        winner_score = opponent_score
        loser_score = challenger_score
    else:
        # Tie
        embed = discord.Embed(
            title="🤝 IT'S A TIE!",
            description=f"{challenger.mention} and {opponent.mention} are equally matched!",
            color=0x808080
        )
        embed.add_field(name="Final Score", value=f"{challenger_score} - {opponent_score}")
        
        # Award tie points
        tie_points = 50
        winner_house = data['users'][str(challenger.id)]['house']
        loser_house = data['users'][str(opponent.id)]['house']
        
        data['houses'][winner_house]['points'] += tie_points
        data['houses'][loser_house]['points'] += tie_points
        
        data['users'][str(challenger.id)]['points_contributed'] += tie_points
        data['users'][str(opponent.id)]['points_contributed'] += tie_points
        
        embed.add_field(name="Reward", value=f"Both earn **{tie_points}** points!")
        
        await interaction.channel.send(embed=embed)
        
        del data['duels'][duel_id]
        save_data()
        return
    
    # Calculate points
    base_points = 100
    score_diff = winner_score - loser_score
    bonus = score_diff * 20
    
    total_points = base_points + bonus
    
    winner_house = data['users'][str(winner.id)]['house']
    data['houses'][winner_house]['points'] += total_points
    data['users'][str(winner.id)]['points_contributed'] += total_points
    data['users'][str(winner.id)]['xp'] = data['users'][str(winner.id)].get('xp', 0) + total_points
    data['users'][str(winner.id)]['duels_won'] = data['users'][str(winner.id)].get('duels_won', 0) + 1
    data['users'][str(loser.id)]['duels_lost'] = data['users'][str(loser.id)].get('duels_lost', 0) + 1
    
    # Check for achievements
    if data['users'][str(winner.id)]['duels_won'] >= 10:
        await award_achievement(str(winner.id), 'duel_master')
    
    embed = discord.Embed(
        title="🏆 DUEL VICTORY! 🏆",
        description=f"{winner.mention} wins the duel {winner_score}-{loser_score}!",
        color=0xffd700
    )
    embed.add_field(name="Prize", value=f"**{total_points}** points for {data['houses'][winner_house]['name']}!")
    embed.add_field(name="Final Score", value=f"{winner_score} - {loser_score}")
    
    await interaction.channel.send(embed=embed)
    
    del data['duels'][duel_id]
    save_data()

@bot.tree.command(name="duel", description="Challenge someone to a magical duel")
@app_commands.describe(opponent="The user to challenge")
async def slash_duel(interaction: discord.Interaction, opponent: discord.Member):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    if opponent == interaction.user:
        await interaction.response.send_message("❌ You can't duel yourself!", ephemeral=True)
        return
    
    if opponent.bot:
        await interaction.response.send_message("❌ You can't duel a bot!", ephemeral=True)
        return
    
    opponent_id = str(opponent.id)
    if opponent_id not in data['users']:
        await interaction.response.send_message(f"❌ {opponent.display_name} hasn't been sorted yet!", ephemeral=True)
        return
    
    challenger_id = str(interaction.user.id)
    
    if challenger_id in data.get('duels', {}):
        await interaction.response.send_message("❌ You're already in a duel!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⚔️ DUEL CHALLENGE ⚔️",
        description=f"{interaction.user.mention} challenges {opponent.mention} to a wizard's duel!\n\n{opponent.mention}, click below to accept!",
        color=0xff0000
    )
    
    view = DuelChallengeView(challenger_id, opponent_id)
    await interaction.response.send_message(embed=embed, view=view)
    
    data['duels'][challenger_id] = {
        'opponent': opponent_id,
        'status': 'pending'
    }
    save_data()

# ==========================================
# SLASH COMMANDS - QUIDDITCH
# ==========================================
class QuidditchView(View):
    def __init__(self, user_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        
        positions = [
            ("Chaser", "🎯", discord.ButtonStyle.primary),
            ("Beater", "🏏", discord.ButtonStyle.success),
            ("Keeper", "🥅", discord.ButtonStyle.secondary),
            ("Seeker", "✨", discord.ButtonStyle.danger)
        ]
        
        for position, emoji, style in positions:
            self.add_item(QuidditchPositionButton(position, emoji, style, user_id))
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class QuidditchPositionButton(Button):
    def __init__(self, position, emoji, style, user_id):
        super().__init__(
            label=position,
            style=style,
            emoji=emoji,
            custom_id=f"quid_{position.lower()}"
        )
        self.position = position
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This isn't your game!", ephemeral=True)
            return
        
        await play_quidditch_position(interaction, self.position, self.user_id)

async def play_quidditch_position(interaction, position, user_id):
    user = data['users'][user_id]
    house = user['house']
    
    # Check cooldown
    last_quidditch = user.get('last_quidditch')
    if last_quidditch:
        last_time = datetime.fromisoformat(last_quidditch)
        if datetime.now() - last_time < timedelta(hours=1):
            time_left = timedelta(hours=1) - (datetime.now() - last_time)
            minutes = int(time_left.total_seconds() / 60)
            embed = discord.Embed(
                title="❌ Cooldown",
                description=f"You need to wait {minutes} minutes before playing Quidditch again!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    
    # Position-based outcomes
    outcomes = {
        'Chaser': {
            'success': ['SCORES! +50', 'GOAL! +40', 'QUAFFLE THROUGH! +45'],
            'fail': ['Misses!', 'Blocked!', 'Fumbles!'],
            'success_rate': 0.7,
            'points_range': (30, 50)
        },
        'Beater': {
            'success': ['HITS BLUDGER! +30', 'SMASH! +35', 'CRACK! +25'],
            'fail': ['Gets hit! -10', 'Dodges! 0', 'Misses! 0'],
            'success_rate': 0.6,
            'points_range': (20, 35)
        },
        'Keeper': {
            'success': ['SAVES! +40', 'BLOCKS! +35', 'CATCHES! +45'],
            'fail': ['Goal conceded! -15', 'Misses! -10', 'Scored on! -20'],
            'success_rate': 0.8,
            'points_range': (30, 45)
        },
        'Seeker': {
            'success': ['CATCHES THE SNITCH! +150', 'SNITCH SIGHTED! +100', 'GRABS IT! +125'],
            'fail': ['Snitch escapes! -20', 'Lost it! -15', 'Falls! -25'],
            'success_rate': 0.2,
            'points_range': (100, 150)
        }
    }
    
    pos_data = outcomes[position]
    success = random.random() < pos_data['success_rate']
    
    if success:
        points = random.randint(pos_data['points_range'][0], pos_data['points_range'][1])
        result = random.choice(pos_data['success'])
    else:
        points = random.randint(-25, 0)
        result = random.choice(pos_data['fail'])
    
    # Apply bonuses
    if user.get('pet') == 'Dragon Hatchling':
        points = int(points * 1.5)
        bonus_msg = " (Dragon bonus!)"
    elif user.get('wand'):
        points = int(points * 1.1)
        bonus_msg = " (Wand bonus!)"
    else:
        bonus_msg = ""
    
    # Award points
    data['houses'][house]['points'] += points
    data['houses'][house]['weekly'] += points
    data['houses'][house]['monthly'] += points
    user['points_contributed'] += points
    user['quidditch_points'] = user.get('quidditch_points', 0) + max(0, points)
    user['xp'] = user.get('xp', 0) + max(0, points)
    user['last_quidditch'] = datetime.now().isoformat()
    
    if points > 0:
        data['houses'][house]['quidditch_wins'] = data['houses'][house].get('quidditch_wins', 0) + 1
        await update_quest_progress(user_id, 'quidditch_win')
    
    # Create embed
    embed = discord.Embed(
        title="🧹 QUIDDITCH MATCH",
        description=f"{interaction.user.mention} plays as **{position}**!",
        color=data['houses'][house]['color']
    )
    
    if points > 0:
        embed.add_field(name="✨ Result", value=f"**{result}** +{points} points{bonus_msg}")
    else:
        embed.add_field(name="❌ Result", value=f"**{result}** {points} points{bonus_msg}")
    
    embed.add_field(name="🏆 Total Quidditch Points", value=str(user.get('quidditch_points', 0)))
    
    await interaction.response.edit_message(embed=embed, view=None)
    save_data()

@bot.tree.command(name="quidditch", description="Play a game of Quidditch")
async def slash_quidditch(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    view = QuidditchView(str(interaction.user.id))
    embed = discord.Embed(
        title="🧹 QUIDDITCH PITCH",
        description="Choose your position!",
        color=0x9b59b6
    )
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="quidditchstats", description="View your Quidditch statistics")
async def slash_quidditch_stats(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    user = data['users'][user_id]
    
    embed = discord.Embed(
        title=f"🧹 {interaction.user.display_name}'s Quidditch Stats",
        color=data['houses'][user['house']]['color']
    )
    embed.add_field(name="Total Points", value=str(user.get('quidditch_points', 0)))
    embed.add_field(name="Games Played", value="Coming soon!")
    embed.add_field(name="Win Rate", value="Coming soon!")
    
    await interaction.response.send_message(embed=embed)

# ==========================================
# SLASH COMMANDS - TRIVIA
# ==========================================
class TriviaDifficultySelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = [
            discord.SelectOption(label="Easy", value="easy", emoji="🟢", description="10-15 points"),
            discord.SelectOption(label="Medium", value="medium", emoji="🟡", description="15-25 points"),
            discord.SelectOption(label="Hard", value="hard", emoji="🟠", description="25-50 points"),
            discord.SelectOption(label="Extreme", value="extreme", emoji="🔴", description="50-200 points"),
            discord.SelectOption(label="Random", value="random", emoji="🎲", description="Random difficulty")
        ]
        super().__init__(placeholder="Choose difficulty...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not your trivia game!", ephemeral=True)
            return
        
        difficulty = self.values[0]
        if difficulty == "random":
            difficulty = random.choice(['easy', 'medium', 'hard', 'extreme'])
        
        question = trivia.get_question(difficulty)
        
        embed = discord.Embed(
            title=f"🎮 TRIVIA - {difficulty.upper()}",
            description=f"**{question['q']}**",
            color=0x9b59b6
        )
        embed.add_field(name="Prize", value=f"**{question['points']}** points for your house!")
        embed.add_field(name="Time", value="30 seconds")
        embed.set_footer(text="Type your answer in chat!")
        
        # Store question for answer checking
        trivia.active_games[str(interaction.user.id)] = {
            'question': question,
            'start_time': datetime.now()
        }
        
        await interaction.response.edit_message(embed=embed, view=None)

@bot.tree.command(name="trivia", description="Test your Harry Potter knowledge!")
@app_commands.describe(difficulty="Choose difficulty level")
@app_commands.choices(difficulty=[
    app_commands.Choice(name="🟢 Easy", value="easy"),
    app_commands.Choice(name="🟡 Medium", value="medium"),
    app_commands.Choice(name="🟠 Hard", value="hard"),
    app_commands.Choice(name="🔴 Extreme", value="extreme"),
    app_commands.Choice(name="🎲 Random", value="random")
])
async def slash_trivia(interaction: discord.Interaction, difficulty: str = "random"):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    if difficulty == "random":
        difficulty = random.choice(['easy', 'medium', 'hard', 'extreme'])
    
    question = trivia.get_question(difficulty)
    
    embed = discord.Embed(
        title=f"🎮 TRIVIA - {difficulty.upper()}",
        description=f"**{question['q']}**",
        color=0x9b59b6
    )
    embed.add_field(name="Prize", value=f"**{question['points']}** points for your house!")
    embed.add_field(name="Time", value="30 seconds")
    embed.set_footer(text="Type your answer in chat!")
    
    await interaction.response.send_message(embed=embed)
    
    # Store question for answer checking
    trivia.active_games[str(interaction.user.id)] = {
        'question': question,
        'start_time': datetime.now()
    }
    
    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel
    
    try:
        answer_msg = await bot.wait_for('message', timeout=30.0, check=check)
        
        # Check answer
        user_answer = answer_msg.content.lower().strip()
        correct_answer = question['a'].lower()
        
        # Handle multiple word answers
        if ' ' in correct_answer:
            is_correct = all(word in user_answer for word in correct_answer.split())
        else:
            is_correct = user_answer == correct_answer
        
        if is_correct:
            user_id = str(interaction.user.id)
            house = data['users'][user_id]['house']
            
            # Calculate speed bonus
            time_taken = (datetime.now() - trivia.active_games[user_id]['start_time']).seconds
            speed_bonus = max(0, int((30 - time_taken) / 2))
            
            total_points = question['points'] + speed_bonus
            
            # Award points
            data['houses'][house]['points'] += total_points
            data['houses'][house]['weekly'] += total_points
            data['houses'][house]['monthly'] += total_points
            data['users'][user_id]['points_contributed'] += total_points
            data['users'][user_id]['xp'] = data['users'][user_id].get('xp', 0) + total_points
            
            # Track trivia wins
            if 'trivia_wins' not in data['users'][user_id]:
                data['users'][user_id]['trivia_wins'] = 0
            data['users'][user_id]['trivia_wins'] += 1
            
            # Check for trivia master achievement
            if data['users'][user_id]['trivia_wins'] >= 10:
                await award_achievement(user_id, 'trivia_master')
            
            embed = discord.Embed(
                title="🎉 CORRECT!",
                description=f"{interaction.user.mention} got it right in {time_taken} seconds!",
                color=0x00ff00
            )
            embed.add_field(name="Base Points", value=str(question['points']))
            embed.add_field(name="Speed Bonus", value=f"+{speed_bonus}")
            embed.add_field(name="Total Earned", value=f"**{total_points}** for {data['houses'][house]['name']}!")
            
            await interaction.channel.send(embed=embed)
            save_data()
        else:
            await interaction.channel.send(f"❌ Sorry {interaction.user.mention}, that's incorrect. The answer was: **{question['a']}**")
        
        del trivia.active_games[str(interaction.user.id)]
        
    except asyncio.TimeoutError:
        if str(interaction.user.id) in trivia.active_games:
            del trivia.active_games[str(interaction.user.id)]
        await interaction.channel.send(f"⏰ Time's up {interaction.user.mention}! The answer was: **{question['a']}**")

@bot.tree.command(name="trivialeaderboard", description="View the top trivia players")
async def slash_trivia_leaderboard(interaction: discord.Interaction):
    users = []
    for user_id, user_data in data['users'].items():
        wins = user_data.get('trivia_wins', 0)
        if wins > 0:
            member = interaction.guild.get_member(int(user_id))
            if member:
                users.append((member.display_name, wins, user_data['house']))
    
    users.sort(key=lambda x: x[1], reverse=True)
    
    embed = discord.Embed(
        title="🎮 TRIVIA LEADERBOARD",
        description="Top trivia masters of Hogwarts!",
        color=0x9b59b6
    )
    
    if not users:
        embed.description = "No trivia wins yet! Play `/trivia` to get started!"
    else:
        for i, (name, wins, house) in enumerate(users[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
            embed.add_field(
                name=f"{medal} {i}. {name}",
                value=f"{HOUSE_DATA[house]['emoji']} **{wins}** wins",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)
    # ==========================================
# SLASH COMMANDS - MARAUDER'S MAP
# ==========================================
class MaraudersMapView(View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        
        # Location selection dropdown
        self.add_item(LocationSelect(user_id))
        
        # Secret passages button
        self.add_item(SecretPassagesButton(user_id))
        
        # Find friends button
        self.add_item(FindFriendsButton(user_id))
        
        # Area filter dropdown
        self.add_item(AreaFilterSelect(user_id))
    
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(content="🗺️ *Mischief Managed*", view=self)

class LocationSelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = []
        for loc in random.sample(MAP_LOCATIONS, 10):  # Show 10 random locations
            options.append(discord.SelectOption(
                label=loc['name'],
                description=f"{loc['area']} | {loc['emoji']}",
                emoji=loc['emoji'],
                value=loc['name']
            ))
        super().__init__(placeholder="🔍 Where would you like to look?", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This map isn't for you!", ephemeral=True)
            return
        
        location_name = self.values[0]
        location = next((loc for loc in MAP_LOCATIONS if loc['name'] == location_name), None)
        
        if not location:
            await interaction.response.send_message("❌ Location not found!", ephemeral=True)
            return
        
        await show_location_details(interaction, location, self.user_id)

class AreaFilterSelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        areas = list(set(loc['area'] for loc in MAP_LOCATIONS))
        options = [discord.SelectOption(label="All Areas", value="all", emoji="🗺️")]
        for area in sorted(areas):
            options.append(discord.SelectOption(label=area, value=area))
        super().__init__(placeholder="📌 Filter by area...", options=options[:5], row=1)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        area = self.values[0]
        await show_filtered_locations(interaction, area, self.user_id)

class SecretPassagesButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Secret Passages",
            style=discord.ButtonStyle.secondary,
            emoji="🚪",
            row=2
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        await show_secret_passages(interaction, self.user_id)

class FindFriendsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Find Friends",
            style=discord.ButtonStyle.primary,
            emoji="👥",
            row=2
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        await find_friends(interaction, self.user_id)

async def show_location_details(interaction, location, user_id):
    # Get online members in this location (simulated)
    online_count = random.randint(0, location['students'])
    
    # Find which online members might be there
    guild = interaction.guild
    online_members = []
    if online_count > 0:
        # Get random online members
        potential_members = [m for m in guild.members if not m.bot and m.status != discord.Status.offline]
        online_members = random.sample(potential_members, min(online_count, len(potential_members)))
    
    # Create embed
    embed = discord.Embed(
        title=f"{location['emoji']} {location['name']}",
        description=f"*Located in the {location['area']}*",
        color=0x2ecc71
    )
    
    # Show who's there
    if online_members:
        member_list = []
        for member in online_members[:5]:  # Show up to 5
            if str(member.id) in data['users']:
                house = data['users'][str(member.id)]['house']
                member_list.append(f"{HOUSE_DATA[house]['emoji']} {member.display_name}")
            else:
                member_list.append(f"👤 {member.display_name}")
        
        embed.add_field(
            name="👥 Currently here:",
            value="\n".join(member_list),
            inline=False
        )
    else:
        embed.add_field(name="👥 Currently here:", value="No one...", inline=False)
    
    # Show teachers
    if location['teachers']:
        embed.add_field(
            name="👨‍🏫 Teachers:",
            value=", ".join(location['teachers']),
            inline=False
        )
    
    # Activity
    activities = [
        "Studying quietly",
        "Talking in groups",
        "Walking through",
        "Casting spells",
        "Eating snacks",
        "Reading books",
        "Playing chess",
        "Sleeping (tsk tsk)"
    ]
    embed.add_field(name="📋 Activity", value=random.choice(activities), inline=True)
    
    # Atmosphere
    atmospheres = [
        "Peaceful and quiet",
        "Bustling with students",
        "Mysteriously empty",
        "Filled with chatter",
        "Eerily silent",
        "Magical energy flowing"
    ]
    embed.add_field(name="✨ Atmosphere", value=random.choice(atmospheres), inline=True)
    
    embed.set_footer(text=f"Map last updated: {datetime.now().strftime('%H:%M:%S')}")
    
    view = View()
    view.add_item(BackToMapButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def show_filtered_locations(interaction, area, user_id):
    if area == "all":
        locations = MAP_LOCATIONS
    else:
        locations = [loc for loc in MAP_LOCATIONS if loc['area'] == area]
    
    embed = discord.Embed(
        title=f"🗺️ {area if area != 'all' else 'All'} Locations",
        description=f"Found **{len(locations)}** locations",
        color=0x2ecc71
    )
    
    # Group by area
    for loc in sorted(locations, key=lambda x: x['name'])[:10]:  # Show up to 10
        embed.add_field(
            name=f"{loc['emoji']} {loc['name']}",
            value=f"Students: {loc['students']} | {loc['area']}",
            inline=True
        )
    
    view = View()
    view.add_item(BackToMapButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def show_secret_passages(interaction, user_id):
    user = data['users'][user_id]
    discovered = user.get('secret_passages', [])
    
    embed = discord.Embed(
        title="🚪 SECRET PASSAGES",
        description="*I solemnly swear that I am up to no good...*",
        color=0x9b59b6
    )
    
    for passage in SECRET_PASSAGES:
        if passage['from'] in discovered:
            embed.add_field(
                name=f"✅ {passage['from']} → {passage['to']}",
                value=f"Password: ||{passage['password']}||",
                inline=False
            )
        else:
            embed.add_field(
                name=f"❓ {passage['from']} → ???",
                value="Undiscovered",
                inline=False
            )
    
    embed.add_field(
        name="🔍 To discover passages",
        value="Explore different locations using the map!",
        inline=False
    )
    
    view = View()
    view.add_item(BackToMapButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def find_friends(interaction, user_id):
    guild = interaction.guild
    online_friends = []
    
    for member in guild.members:
        if not member.bot and member.status != discord.Status.offline:
            if str(member.id) in data['users']:
                online_friends.append(member)
    
    embed = discord.Embed(
        title="👥 ONLINE FRIENDS",
        description=f"**{len(online_friends)}** wizards currently online",
        color=0x2ecc71
    )
    
    if online_friends:
        # Group by house
        for house in HOUSE_DATA.keys():
            house_members = [m for m in online_friends if str(m.id) in data['users'] and data['users'][str(m.id)]['house'] == house]
            if house_members:
                member_names = "\n".join([f"• {m.display_name}" for m in house_members[:5]])
                if len(house_members) > 5:
                    member_names += f"\n• ...and {len(house_members)-5} more"
                embed.add_field(
                    name=f"{HOUSE_DATA[house]['emoji']} {HOUSE_DATA[house]['name']}",
                    value=member_names,
                    inline=False
                )
        
        # Show unsorted members
        unsorted = [m for m in online_friends if str(m.id) not in data['users']]
        if unsorted:
            embed.add_field(
                name="👤 Unsorted",
                value=", ".join([m.display_name for m in unsorted[:5]]),
                inline=False
            )
    else:
        embed.description = "No friends online right now..."
    
    view = View()
    view.add_item(BackToMapButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

class BackToMapButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Back to Map",
            style=discord.ButtonStyle.primary,
            emoji="🗺️"
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await show_marauders_map(interaction, self.user_id)

async def show_marauders_map(interaction, user_id):
    user = data['users'][user_id]
    
    # Check if user has map access
    if user.get('map_access', 0) <= 0:
        embed = discord.Embed(
            title="❌ No Map Access",
            description="You don't have the Marauder's Map! Find it in:\n• Mythic Chests\n• Secret Rooms\n• Special Quests",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    # Decrease map uses
    user['map_access'] = user.get('map_access', 1) - 1
    
    embed = discord.Embed(
        title="🗺️ MARAUDER'S MAP",
        description="*I solemnly swear that I am up to no good...*",
        color=0x2ecc71
    )
    
    # Show map stats
    total_locations = len(MAP_LOCATIONS)
    discovered = len(user.get('secret_passages', []))
    
    embed.add_field(name="📍 Locations", value=str(total_locations), inline=True)
    embed.add_field(name="🔍 Passages Found", value=str(discovered), inline=True)
    embed.add_field(name="🎫 Uses Left", value=str(user.get('map_access', 0)), inline=True)
    
    # Show random locations preview
    preview = random.sample(MAP_LOCATIONS, 3)
    preview_text = "\n".join([f"{loc['emoji']} {loc['name']} ({loc['area']})" for loc in preview])
    embed.add_field(name="📌 Recent Activity", value=preview_text, inline=False)
    
    embed.set_footer(text="Select a location from the dropdown to explore!")
    
    view = MaraudersMapView(user_id)
    await interaction.response.send_message(embed=embed, view=view)
    save_data()

@bot.tree.command(name="map", description="Use the Marauder's Map to explore Hogwarts")
async def slash_map(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    await show_marauders_map(interaction, str(interaction.user.id))

@bot.tree.command(name="buymap", description="Buy a Marauder's Map (500 points)")
async def slash_buy_map(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    user = data['users'][user_id]
    
    map_price = 500
    
    if user['points_contributed'] < map_price:
        await interaction.response.send_message(f"❌ You need {map_price} points! You have {user['points_contributed']}", ephemeral=True)
        return
    
    user['points_contributed'] -= map_price
    user['map_access'] = user.get('map_access', 0) + 3
    
    embed = discord.Embed(
        title="🗺️ MAP PURCHASED!",
        description=f"{interaction.user.mention} bought a Marauder's Map!\nYou now have **{user['map_access']}** uses.",
        color=0x2ecc71
    )
    
    await interaction.response.send_message(embed=embed)
    save_data()

# ==========================================
# SLASH COMMANDS - SECRET ROOMS
# ==========================================
class SecretRoomsView(View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        
        # Room selection dropdown
        self.add_item(SecretRoomSelect(user_id))
        
        # Found secrets button
        self.add_item(FoundSecretsButton(user_id))
        
        # Room hints button
        self.add_item(RoomHintsButton(user_id))

class SecretRoomSelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = []
        for room_id, room in SECRET_ROOMS.items():
            options.append(discord.SelectOption(
                label=room['name'],
                description=f"{room['location']} | {room['emoji']}",
                emoji=room['emoji'],
                value=room_id
            ))
        super().__init__(placeholder="🔍 Choose a secret room to explore...", options=options[:10])
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ This isn't your exploration!", ephemeral=True)
            return
        
        room_id = self.values[0]
        room = SECRET_ROOMS[room_id]
        
        await show_room_details(interaction, room_id, room, self.user_id)

class FoundSecretsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="My Discoveries",
            style=discord.ButtonStyle.primary,
            emoji="🏆",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        await show_discovered_rooms(interaction, self.user_id)

class RoomHintsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Get a Hint",
            style=discord.ButtonStyle.secondary,
            emoji="💡",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        await give_random_hint(interaction, self.user_id)

async def show_room_details(interaction, room_id, room, user_id):
    user = data['users'][user_id]
    discovered = user.get('secrets_found', [])
    
    embed = discord.Embed(
        title=f"{room['emoji']} {room['name']}",
        description=room['description'],
        color=0x9b59b6
    )
    
    embed.add_field(name="📍 Location", value=room['location'], inline=True)
    embed.add_field(name="🚪 Entrance", value=room['entrance'], inline=True)
    embed.add_field(name="⚠️ Danger", value=room['danger'], inline=True)
    
    if room_id in discovered:
        embed.add_field(name="✅ Discovered!", value=f"You found this room!\nTreasure: {room['treasure']}", inline=False)
        embed.add_field(name="📜 History", value=room['history'], inline=False)
    else:
        embed.add_field(name="❓ Undiscovered", value=f"Hint: {room['hint']}", inline=False)
        
        # Add attempt button
        view = View()
        view.add_item(AttemptRoomButton(room_id, room, user_id))
        view.add_item(BackToRoomsButton(user_id))
        
        await interaction.response.edit_message(embed=embed, view=view)
        return
    
    view = View()
    view.add_item(BackToRoomsButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

class AttemptRoomButton(Button):
    def __init__(self, room_id, room_data, user_id):
        super().__init__(
            label="Attempt to Enter",
            style=discord.ButtonStyle.danger,
            emoji="🚪"
        )
        self.room_id = room_id
        self.room_data = room_data
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not for you!", ephemeral=True)
            return
        
        # Create password modal
        modal = SecretRoomModal(self.room_id, self.room_data, self.user_id)
        await interaction.response.send_modal(modal)

class SecretRoomModal(Modal):
    def __init__(self, room_id, room_data, user_id):
        super().__init__(title=f"Enter {room_data['name']}")
        self.room_id = room_id
        self.room_data = room_data
        self.user_id = user_id
        
        self.password = discord.ui.TextInput(
            label="Password/Hint",
            placeholder=room_data['hint'],
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.add_item(self.password)
    
    async def callback(self, interaction: discord.Interaction):
        answer = self.password.value.lower().strip()
        correct = self.room_data['password'].lower()
        
        if answer == correct or answer in correct or correct in answer:
            # Success!
            user = data['users'][self.user_id]
            
            if 'secrets_found' not in user:
                user['secrets_found'] = []
            
            if self.room_id in user['secrets_found']:
                await interaction.response.send_message("❌ You already found this secret!", ephemeral=True)
                return
            
            user['secrets_found'].append(self.room_id)
            
            # Award rewards
            points = self.room_data['points']
            xp = self.room_data['xp']
            
            user['points_contributed'] += points
            user['xp'] = user.get('xp', 0) + xp
            data['houses'][user['house']]['points'] += points
            
            # Give item
            if 'inventory' not in user:
                user['inventory'] = []
            user['inventory'].append(self.room_data['item'])
            
            # Check for achievement
            if len(user['secrets_found']) >= 5:
                await award_achievement(self.user_id, 'secret_hunter')
            
            embed = discord.Embed(
                title=f"✨ SECRET FOUND: {self.room_data['name']} ✨",
                description=self.room_data['description'],
                color=0x00ff00
            )
            embed.add_field(name="📍 Location", value=self.room_data['location'], inline=True)
            embed.add_field(name="📜 History", value=self.room_data['history'], inline=False)
            embed.add_field(name="💰 Rewards", value=f"**{points}** points\n**{xp}** XP\n📦 **{self.room_data['item']}**", inline=False)
            
            await interaction.response.send_message(embed=embed)
            save_data()
        else:
            # Wrong password
            await interaction.response.send_message(f"❌ Wrong password! Hint: {self.room_data['hint']}", ephemeral=True)

async def show_discovered_rooms(interaction, user_id):
    user = data['users'][user_id]
    discovered = user.get('secrets_found', [])
    
    embed = discord.Embed(
        title=f"🏆 {interaction.user.display_name}'s Discoveries",
        description=f"You have found **{len(discovered)}** out of **{len(SECRET_ROOMS)}** secret rooms!",
        color=0xffd700
    )
    
    if discovered:
        for room_id in discovered:
            if room_id in SECRET_ROOMS:
                room = SECRET_ROOMS[room_id]
                embed.add_field(
                    name=f"✅ {room['emoji']} {room['name']}",
                    value=f"*{room['location']}*",
                    inline=True
                )
    else:
        embed.description = "You haven't found any secret rooms yet! Use the map to explore!"
    
    view = View()
    view.add_item(BackToRoomsButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def give_random_hint(interaction, user_id):
    user = data['users'][user_id]
    discovered = user.get('secrets_found', [])
    
    # Find undiscovered rooms
    undiscovered = [room for room_id, room in SECRET_ROOMS.items() if room_id not in discovered]
    
    if not undiscovered:
        await interaction.response.send_message("🎉 You've found all the secrets! You're a true Hogwarts explorer!", ephemeral=True)
        return
    
    room = random.choice(undiscovered)
    
    embed = discord.Embed(
        title="💡 SECRET ROOM HINT",
        description=f"**{room['name']}**\n\nHint: {room['hint']}",
        color=0xffaa00
    )
    embed.add_field(name="Location Area", value=room['location'].split(',')[0], inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

class BackToRoomsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Back to Rooms",
            style=discord.ButtonStyle.primary,
            emoji="🔙"
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await show_secret_rooms_menu(interaction, self.user_id)

async def show_secret_rooms_menu(interaction, user_id):
    user = data['users'][user_id]
    discovered = len(user.get('secrets_found', []))
    
    embed = discord.Embed(
        title="🔍 SECRET ROOMS OF HOGWARTS",
        description=f"*Legends speak of hidden chambers throughout the castle...*\n\nYou have discovered **{discovered}** out of **{len(SECRET_ROOMS)}** secret rooms!",
        color=0x9b59b6
    )
    
    # Show progress
    progress = int((discovered / len(SECRET_ROOMS)) * 20)
    bar = "█" * progress + "░" * (20 - progress)
    embed.add_field(name="📊 Discovery Progress", value=f"`{bar}`", inline=False)
    
    # Show some room previews
    preview = random.sample(list(SECRET_ROOMS.items()), min(3, len(SECRET_ROOMS)))
    preview_text = ""
    for room_id, room in preview:
        status = "✅" if room_id in user.get('secrets_found', []) else "❓"
        preview_text += f"{status} {room['emoji']} **{room['name']}** - {room['location']}\n"
    embed.add_field(name="📌 Featured Rooms", value=preview_text, inline=False)
    
    embed.set_footer(text="Select a room from the dropdown to explore!")
    
    view = SecretRoomsView(user_id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="secrets", description="Search for hidden rooms and secrets")
async def slash_secrets(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    await show_secret_rooms_menu(interaction, str(interaction.user.id))

@bot.tree.command(name="roomhint", description="Get a hint for an undiscovered secret room")
async def slash_room_hint(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    await give_random_hint(interaction, str(interaction.user.id))

@bot.tree.command(name="secretstats", description="View your secret room discovery progress")
async def slash_secret_stats(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    user = data['users'][user_id]
    discovered = user.get('secrets_found', [])
    
    embed = discord.Embed(
        title=f"🔍 {interaction.user.display_name}'s Secret Discovery Progress",
        color=0x9b59b6
    )
    
    total = len(SECRET_ROOMS)
    found = len(discovered)
    percentage = (found / total) * 100
    
    embed.add_field(name="📊 Total Found", value=f"**{found}/{total}** ({percentage:.1f}%)", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ==========================================
# SLASH COMMANDS - QUESTS
# ==========================================
class QuestView(View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.user_id = user_id
        
        # Quest category selector
        self.add_item(QuestCategorySelect(user_id))
        
        # Active quests button
        self.add_item(ActiveQuestsButton(user_id))
        
        # Completed quests button
        self.add_item(CompletedQuestsButton(user_id))
        
        # Claim rewards button
        self.add_item(ClaimRewardsButton(user_id))

class QuestCategorySelect(Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = [
            discord.SelectOption(label="Daily Quests", value="daily", emoji="📅", description="Repeat daily"),
            discord.SelectOption(label="Weekly Quests", value="weekly", emoji="📆", description="Repeat weekly"),
            discord.SelectOption(label="Special Quests", value="special", emoji="✨", description="One-time only"),
            discord.SelectOption(label="Achievement Quests", value="achievement", emoji="🏆", description="Long-term goals")
        ]
        super().__init__(placeholder="📋 Select quest category...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not your quest log!", ephemeral=True)
            return
        
        category = self.values[0]
        await show_quest_category(interaction, self.user_id, category)

class ActiveQuestsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Active Quests",
            style=discord.ButtonStyle.primary,
            emoji="📋",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not your quest log!", ephemeral=True)
            return
        
        await show_active_quests(interaction, self.user_id)

class CompletedQuestsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Completed",
            style=discord.ButtonStyle.success,
            emoji="✅",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not your quest log!", ephemeral=True)
            return
        
        await show_completed_quests(interaction, self.user_id)

class ClaimRewardsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Claim Rewards",
            style=discord.ButtonStyle.danger,
            emoji="💰",
            row=1
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Not your quest log!", ephemeral=True)
            return
        
        await claim_quest_rewards(interaction, self.user_id)

async def show_quest_category(interaction, user_id, category):
    user = data['users'][user_id]
    quests_data = user.get('quests', {})
    
    embed = discord.Embed(
        title=f"📋 {category.title()} Quests",
        color=0x9b59b6
    )
    
    category_quests = {qid: q for qid, q in QUESTS.items() if q['category'] == category}
    
    for qid, quest in category_quests.items():
        if qid in quests_data:
            # Quest is active
            progress = quests_data[qid]
            percent = int((progress['current'] / progress['target']) * 100)
            bar = "█" * int(percent/5) + "░" * (20 - int(percent/5))
            
            embed.add_field(
                name=f"{quest['emoji']} {quest['name']} (In Progress)",
                value=f"Progress: {progress['current']}/{progress['target']}\n`{bar}` {percent}%\nReward: {quest['reward_points']} pts",
                inline=False
            )
        elif qid not in user.get('completed_quests', []):
            # Quest is available
            embed.add_field(
                name=f"{quest['emoji']} {quest['name']}",
                value=f"**Goal:** {quest['description']}\n**Reward:** {quest['reward_points']} pts, {quest['reward_xp']} XP\n{quest.get('reward_items', ['Item'])[0]}",
                inline=False
            )
    
    view = View()
    view.add_item(BackToQuestsButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def show_active_quests(interaction, user_id):
    user = data['users'][user_id]
    quests_data = user.get('quests', {})
    
    embed = discord.Embed(
        title=f"📋 {interaction.user.display_name}'s Active Quests",
        color=0x9b59b6
    )
    
    if not quests_data:
        embed.description = "No active quests! Browse categories to start some!"
    else:
        for qid, progress in quests_data.items():
            if qid in QUESTS:
                quest = QUESTS[qid]
                percent = int((progress['current'] / progress['target']) * 100)
                bar = "█" * int(percent/5) + "░" * (20 - int(percent/5))
                
                embed.add_field(
                    name=f"{quest['emoji']} {quest['name']}",
                    value=f"Progress: {progress['current']}/{progress['target']}\n`{bar}` {percent}%\nReward: {quest['reward_points']} pts",
                    inline=False
                )
    
    view = View()
    view.add_item(BackToQuestsButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def show_completed_quests(interaction, user_id):
    user = data['users'][user_id]
    completed = user.get('completed_quests', [])
    
    embed = discord.Embed(
        title=f"✅ {interaction.user.display_name}'s Completed Quests",
        description=f"Total: **{len(completed)}** quests completed",
        color=0x00ff00
    )
    
    if completed:
        # Show last 10 completed
        for qid in completed[-10:]:
            if qid in QUESTS:
                quest = QUESTS[qid]
                embed.add_field(
                    name=f"{quest['emoji']} {quest['name']}",
                    value=f"Completed!",
                    inline=True
                )
    else:
        embed.description = "No completed quests yet!"
    
    view = View()
    view.add_item(BackToQuestsButton(user_id))
    
    await interaction.response.edit_message(embed=embed, view=view)

async def claim_quest_rewards(interaction, user_id):
    user = data['users'][user_id]
    quests_data = user.get('quests', {})
    
    completed = []
    for qid, progress in list(quests_data.items()):
        if progress['current'] >= progress['target']:
            completed.append(qid)
    
    if not completed:
        await interaction.response.send_message("❌ No quests ready to claim!", ephemeral=True)
        return
    
    total_points = 0
    total_xp = 0
    items = []
    
    for qid in completed:
        quest = QUESTS[qid]
        total_points += quest['reward_points']
        total_xp += quest['reward_xp']
        
        # Add items
        if 'reward_items' in quest:
            for item in quest['reward_items']:
                if 'inventory' not in user:
                    user['inventory'] = []
                user['inventory'].append(item)
                items.append(item)
        
        # Move to completed
        if 'completed_quests' not in user:
            user['completed_quests'] = []
        user['completed_quests'].append(qid)
        
        # Remove from active
        del quests_data[qid]
    
    # Award points and XP
    user['points_contributed'] += total_points
    user['xp'] = user.get('xp', 0) + total_xp
    data['houses'][user['house']]['points'] += total_points
    
    embed = discord.Embed(
        title="💰 REWARDS CLAIMED!",
        description=f"Claimed **{len(completed)}** quest rewards!",
        color=0x00ff00
    )
    embed.add_field(name="Points", value=f"+{total_points}", inline=True)
    embed.add_field(name="XP", value=f"+{total_xp}", inline=True)
    
    if items:
        embed.add_field(name="Items", value=", ".join(items), inline=False)
    
    await interaction.response.send_message(embed=embed)
    save_data()

async def show_quests_menu(interaction, user_id):
    user = data['users'][user_id]
    active = len(user.get('quests', {}))
    completed = len(user.get('completed_quests', []))
    
    embed = discord.Embed(
        title="📜 QUEST LOG",
        description=f"*Adventure awaits, brave wizard!*",
        color=0x9b59b6
    )
    
    embed.add_field(name="📋 Active Quests", value=str(active), inline=True)
    embed.add_field(name="✅ Completed Quests", value=str(completed), inline=True)
    embed.add_field(name="🏆 Total Available", value=str(len(QUESTS)), inline=True)
    
    # Show daily reset timer
    next_reset = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
    time_until = next_reset - datetime.now()
    hours = int(time_until.total_seconds() / 3600)
    minutes = int((time_until.total_seconds() % 3600) / 60)
    
    embed.add_field(
        name="⏰ Daily Reset",
        value=f"New daily quests in {hours}h {minutes}m",
        inline=False
    )
    
    view = QuestView(user_id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="quests", description="View your quest log")
async def slash_quests(interaction: discord.Interaction):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    await show_quests_menu(interaction, str(interaction.user.id))
async def quest_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete function for quest names"""
    print(f"🔍 Autocomplete called with: '{current}'")  # Debug print
    print(f"👤 User: {interaction.user.name}")  # Debug print
    
    quests = []
    user_id = str(interaction.user.id)
    
    # Get user's active and completed quests
    user = data['users'].get(user_id, {})
    active_quests = user.get('quests', {})
    completed_quests = user.get('completed_quests', [])
    
    print(f"📊 Active quests: {len(active_quests)}")  # Debug print
    print(f"✅ Completed quests: {len(completed_quests)}")  # Debug print
    
    for qid, quest in QUESTS.items():
        # Skip if quest is already active or completed
        if qid in active_quests or qid in completed_quests:
            continue
            
        if current.lower() in quest['name'].lower():
            # Create a nice display name with emoji and difficulty
            display_name = f"{quest['emoji']} {quest['name']} ({quest['difficulty'].title()})"
            print(f"➕ Adding quest: {display_name}")  # Debug print
            quests.append(
                app_commands.Choice(
                    name=display_name[:100],  # Discord has a 100 char limit
                    value=quest['name']  # Use the actual name as the value
                )
            )
    
    print(f"📤 Returning {len(quests)} quests")  # Debug print
    return quests[:25]

@bot.tree.command(name="startquest", description="Start a new quest")
@app_commands.describe(quest="The name of the quest to start")
@app_commands.autocomplete(quest=quest_autocomplete)
async def slash_start_quest(interaction: discord.Interaction, quest: str):
    if not await slash_is_sorted(interaction):
        await interaction.response.send_message("❌ You need to be sorted first!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    
    # Find quest
    found_quest = None
    found_id = None
    for qid, q in QUESTS.items():
        if quest.lower() in q['name'].lower():
            found_quest = q
            found_id = qid
            break
    
    if not found_quest:
        await interaction.response.send_message("❌ Quest not found!", ephemeral=True)
        return
    
    # Check if quest is already active
    user = data['users'].get(user_id, {})
    if found_id in user.get('quests', {}):
        await interaction.response.send_message("❌ You already have this quest active!", ephemeral=True)
        return
    
    # Check if quest is already completed
    if found_id in user.get('completed_quests', []):
        await interaction.response.send_message("❌ You've already completed this quest!", ephemeral=True)
        return
    
    if await start_quest(user_id, found_id):
        embed = discord.Embed(
            title=f"{found_quest['emoji']} QUEST STARTED!",
            description=f"**{found_quest['name']}**\n\n{found_quest['description']}",
            color=0x00ff00
        )
        embed.add_field(name="Goal", value=str(found_quest['target']))
        embed.add_field(name="Reward", value=f"{found_quest['reward_points']} points")
        if found_quest.get('reward_items'):
            embed.add_field(name="Items", value=", ".join(found_quest['reward_items']), inline=False)
        
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("❌ Couldn't start quest!", ephemeral=True)


class BackToQuestsButton(Button):
    def __init__(self, user_id):
        super().__init__(
            label="Back to Quests",
            style=discord.ButtonStyle.primary,
            emoji="🔙"
        )
        self.user_id = user_id
    
    async def callback(self, interaction: discord.Interaction):
        await show_quests_menu(interaction, self.user_id)
       
       # ==========================================
# RUN THE BOT
# ==========================================
if __name__ == "__main__":
    # Use environment variable for token (safer for hosting)
    import os
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        # Fallback to manual input if no env var (for local testing)
        token = input("Enter your Discord bot token: ").strip()
    
    if token:
        try:
            bot.run(token)
        except discord.errors.PrivilegedIntentsRequired:
            print("❌ Error: Privileged Intents not enabled!")
            print("Go to: https://discord.com/developers/applications/")
            print("Click your bot → Bot → Enable ALL Privileged Gateway Intents")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("❌ No token provided!")