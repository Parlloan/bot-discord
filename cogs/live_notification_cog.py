import discord
from discord.ext import commands, tasks
import logging
import requests
import json

class LiveNotificationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.is_live = False  # Variável para rastrear se já notificamos a live atual
        self.access_token = None  # Token de acesso para a Twitch API

        # Carrega as configurações do config.json
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
            self.twitch_client_id = config['twitch_client_id']
            self.twitch_client_secret = config['twitch_client_secret']
            self.twitch_channel_name = config['twitch_channel_name']
            self.live_channel_id = config['live_notification_channel_id']
        except Exception as e:
            logging.error(f"Erro ao carregar config.json: {str(e)}")
            print(f"[ERROR] Erro ao carregar config.json: {str(e)}")
            raise

        # Inicia a tarefa de verificação de live
        self.check_live_status.start()

    def cog_unload(self):
        # Para a tarefa ao descarregar o cog
        self.check_live_status.stop()

    # Função para obter o token de acesso da Twitch API
    async def get_twitch_access_token(self):
        try:
            url = "https://id.twitch.tv/oauth2/token"
            params = {
                "client_id": self.twitch_client_id,
                "client_secret": self.twitch_client_secret,
                "grant_type": "client_credentials"
            }
            response = requests.post(url, params=params)
            response.raise_for_status()
            data = response.json()
            self.access_token = data['access_token']
            logging.info("Token de acesso da Twitch obtido com sucesso")
            print("[INFO] Token de acesso da Twitch obtido com sucesso")
        except Exception as e:
            logging.error(f"Erro ao obter token de acesso da Twitch: {str(e)}")
            print(f"[ERROR] Erro ao obter token de acesso da Twitch: {str(e)}")
            self.access_token = None

    # Tarefa que verifica o status da live a cada 5 minutos
    @tasks.loop(minutes=5)
    async def check_live_status(self):
        # Etapa 1: Obter token de acesso, se ainda não temos
        if not self.access_token:
            await self.get_twitch_access_token()
            if not self.access_token:
                return  # Se não conseguimos o token, para a verificação

        # Etapa 2: Verificar se o canal está ao vivo
        try:
            url = "https://api.twitch.tv/helix/streams"
            headers = {
                "Client-ID": self.twitch_client_id,
                "Authorization": f"Bearer {self.access_token}"
            }
            params = {"user_login": self.twitch_channel_name}
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            # Verifica se há uma live ativa
            live_data = data.get('data', [])
            is_currently_live = bool(live_data)

            # Etapa 3: Enviar notificação, se necessário
            if is_currently_live and not self.is_live:
                # Canal está ao vivo e ainda não notificamos
                channel = self.bot.get_channel(self.live_channel_id)
                if not channel:
                    logging.error(f"Canal com ID {self.live_channel_id} não encontrado")
                    print(f"[ERROR] Canal com ID {self.live_channel_id} não encontrado")
                    return

                # Obtém detalhes da live
                stream = live_data[0]
                stream_title = stream.get('title', 'Sem título')
                twitch_url = f"https://twitch.tv/{self.twitch_channel_name}"

                # Envia a mensagem de notificação
                message = (
                    "@everyone\n"
                    f"🎥 **{self.twitch_channel_name} está AO VIVO na Twitch!**\n"
                    f"**Título:** {stream_title}\n"
                    f"**Assista agora:** {twitch_url}"
                )
                await channel.send(message)
                logging.info(f"Notificação de live enviada para o canal {channel.name}")
                print(f"[INFO] Notificação de live enviada para o canal {channel.name}")
                self.is_live = True  # Marca que já notificamos

            elif not is_currently_live and self.is_live:
                # Canal não está mais ao vivo, reseta o estado
                self.is_live = False
                logging.info(f"Canal {self.twitch_channel_name} não está mais ao vivo")
                print(f"[INFO] Canal {self.twitch_channel_name} não está mais ao vivo")

        except Exception as e:
            logging.error(f"Erro ao verificar status da live: {str(e)}")
            print(f"[ERROR] Erro ao verificar status da live: {str(e)}")
            # Se houver erro de autenticação (ex.: token expirado), tenta obter um novo token
            if "401" in str(e) or "403" in str(e):
                self.access_token = None

    # Aguarda o bot estar pronto antes de iniciar a tarefa
    @check_live_status.before_loop
    async def before_check_live_status(self):
        await self.bot.wait_until_ready()

# Função setup para registrar o cog
async def setup(bot):
    await bot.add_cog(LiveNotificationCog(bot))