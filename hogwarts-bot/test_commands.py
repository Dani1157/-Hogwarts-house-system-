import asyncio
import discord
from bot import bot, data, HOUSE_DATA, QUESTS, WANDS, PETS

async def test_all_commands():
    print("="*50)
    print("?? TESTING ALL BOT COMMANDS")
    print("="*50)
    
    # Test 1: Check data structure
    print("\n?? 1. TESTING DATA STRUCTURE")
    print(f"   Houses in data: {list(data['houses'].keys())}")
    print(f"   Users in data: {len(data['users'])}")
    print(f"   QUESTS available: {len(QUESTS)}")
    print(f"   WANDS available: {len(WANDS)}")
    print(f"   PETS available: {len(PETS)}")
    
    # Test 2: Check HOUSE_DATA
    print("\n?? 2. TESTING HOUSE DATA")
    for house in HOUSE_DATA:
        print(f"   {HOUSE_DATA[house]['emoji']} {house}: {HOUSE_DATA[house]['name']}")
    
    # Test 3: Check all view classes exist
    print("\n??? 3. TESTING VIEW CLASSES")
    view_classes = ['WandView', 'PetView', 'ChestView', 'DuelChallengeView', 
                   'MaraudersMapView', 'SecretRoomsView', 'QuestView']
    for view in view_classes:
        if view in globals() or view in locals():
            print(f"   ? {view} exists")
        else:
            print(f"   ? {view} MISSING")
    
    # Test 4: Check all command decorators
    print("\n?? 4. TESTING COMMAND DECORATORS")
    commands_list = [
        'sort', 'add', 'remove', 'scores', 'pointlog', 'checkin', 'streak',
        'wand', 'pet', 'chest', 'cheststats', 'duel', 'quidditch', 'quidditchstats',
        'trivia', 'trivialeaderboard', 'map', 'buymap', 'secrets', 'roomhint',
        'secretstats', 'quests', 'startquest', 'ping'
    ]
    
    for cmd_name in commands_list:
        cmd = bot.tree.get_command(cmd_name)
        if cmd:
            print(f"   ? /{cmd_name} registered")
        else:
            print(f"   ? /{cmd_name} MISSING")
    
    print("\n" + "="*50)
    print("? TEST COMPLETE!")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(test_all_commands())
