import discord
from discord.ext import commands
import logging
import json
import asyncio

# Configuração do logging para console e arquivo
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('welcome_bot.log'),  # Logs em arquivo
        logging.StreamHandler()  # Logs no console
    ]
)

# Carrega as configurações do config.json
try:
    with open('config.json', 'r') as config_file:
        config = json.load(config_file)
    TOKEN = config['token']
except Exception as e:
    logging.error(f"Erro ao carregar config.json: {str(e)}")
    print(f"[ERROR] Erro ao carregar config.json: {str(e)}")
    exit(1)

# Configuração do bot com intents
intents = discord.Intents.default()
intents.members = True  # Para detectar novos membros
intents.message_content = True  # Para comandos baseados em prefixo
bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    max_messages=None  # Evita problemas com cache de mensagens
)

# Evento para indicar que o bot está online e carregar os cogs
@bot.event
async def on_ready():
    logging.info(f"Bot conectado como {bot.user.name} (ID: {bot.user.id})")
    print(f"[INFO] Bot conectado como {bot.user.name} (ID: {bot.user.id})")
    
    # Lista de cogs para carregar
    cogs = ["cogs.welcome_cog", "cogs.live_notification_cog", "cogs.moderation_cog", "cogs.economy_cog"]
    
    # Carrega os cogs de forma assíncrona
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logging.info(f"Cog {cog} carregado com sucesso")
            print(f"[INFO] Cog {cog} carregado com sucesso")
        except Exception as e:
            logging.error(f"Erro ao carregar o cog {cog}: {str(e)}")
            print(f"[ERROR] Erro ao carregar o cog {cog}: {str(e)}")
            return

# Adiciona um pequeno atraso para evitar atingir limites de taxa ao iniciar
async def start_bot():
    try:
        await asyncio.sleep(2)  # Atraso de 2 segundos para evitar limites de taxa
        await bot.start(TOKEN, reconnect=True)
    except Exception as e:
        logging.error(f"Erro ao iniciar o bot: {str(e)}")
        print(f"[ERROR] Erro ao iniciar o bot: {str(e)}")

# Inicia o bot
if __name__ == "__main__":
    asyncio.run(start_bot())