import discord
from discord.ext import commands

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'? Test bot is working!')

if __name__ == '__main__':
    print('Test successful - no import errors')
