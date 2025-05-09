import discord
from discord.ext import commands
import logging
from PIL import Image, ImageDraw, ImageFont
import io
import json

class WelcomeCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Carrega o ID do canal do config.json
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
            self.channel_id = config['welcome_channel_id']
        except Exception as e:
            logging.error(f"Erro ao carregar config.json: {str(e)}")
            print(f"[ERROR] Erro ao carregar config.json: {str(e)}")
            raise

        self.template_path = "template.png"  # Caminho do template do banner
        self.font_path = "ArchivoBlack-Regular.ttf"  # Nova fonte personalizada
        self.font_size = 40  # Tamanho inicial da fonte
        self.min_font_size = 20  # Tamanho mínimo da fonte
        self.text_position = (50, 50)  # Posição do texto no banner (x, y)
        self.text_color = "white"  # Cor do texto

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Log temporário para confirmar que o evento foi disparado
        logging.info(f"Evento on_member_join disparado para {member.name}#{member.discriminator}")
        print(f"[DEBUG] Evento on_member_join disparado para {member.name}#{member.discriminator}")

        # Etapa 1: Detectar novo membro
        logging.info(f"Novo membro detectado: {member.name}#{member.discriminator}")
        print(f"[INFO] Etapa 1: Novo membro detectado: {member.name}#{member.discriminator}")

        # Etapa 2: Verificar se o canal existe
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            logging.error(f"Canal com ID {self.channel_id} não encontrado")
            print(f"[ERROR] Etapa 2: Canal com ID {self.channel_id} não encontrado")
            return

        logging.info(f"Canal encontrado: {channel.name}")
        print(f"[INFO] Etapa 2: Canal encontrado: {channel.name}")

        # Etapa 3: Gerar o banner
        try:
            banner_file = self.generate_banner(member.name)
            logging.info(f"Banner gerado para {member.name}")
            print(f"[INFO] Etapa 3: Banner gerado para {member.name}")
        except Exception as e:
            logging.error(f"Erro ao gerar banner: {str(e)}")
            print(f"[ERROR] Etapa 3: Erro ao gerar banner: {str(e)}")
            return

        # Etapa 4: Enviar a mensagem de boas-vindas com o banner
        try:
            banner_file.seek(0)  # Volta ao início do buffer
            file = discord.File(banner_file, filename="welcome.png")
            await channel.send(
                f"Bem-vindo(a), {member.mention}! Leia as regras em #regras e se apresente no #geral! 🎉",
                file=file
            )
            logging.info(f"Mensagem de boas-vindas enviada para {member.name}")
            print(f"[INFO] Etapa 4: Mensagem de boas-vindas enviada para {member.name}")
        except Exception as e:
            logging.error(f"Erro ao enviar mensagem: {str(e)}")
            print(f"[ERROR] Etapa 4: Erro ao enviar mensagem: {str(e)}")
            return
        finally:
            banner_file.close()  # Fecha o buffer

    def generate_banner(self, member_name):
        # Carrega o template do banner
        banner = Image.open(self.template_path).convert("RGBA")
        draw = ImageDraw.Draw(banner)

        # Carrega a fonte (use uma fonte padrão ou especifique o caminho de uma fonte baixada)
        font_size = self.font_size
        try:
            font = ImageFont.truetype(self.font_path, font_size)
        except Exception:
            font = ImageFont.load_default()
            logging.warning("Fonte padrão usada, pois a fonte especificada não foi encontrada")
            print("[WARNING] Fonte padrão usada")

        # Ajusta o tamanho da fonte para nomes longos
        text = f"Bem-vindo, {member_name}!"
        while font_size > self.min_font_size:
            font = ImageFont.truetype(self.font_path, font_size)
            text_width = draw.textlength(text, font=font)
            if text_width <= banner.width - 100:  # Ajusta para caber no banner
                break
            font_size -= 2

        # Corta o nome se ainda for muito longo
        if draw.textlength(text, font=font) > banner.width - 100:
            text = f"Bem-vindo, {member_name[:10]}..."

        # Desenha o texto no banner
        draw.text(self.text_position, text, fill=self.text_color, font=font)

        # Salva o banner em memória (em vez de um arquivo temporário)
        buffer = io.BytesIO()
        banner.save(buffer, format="PNG")
        buffer.seek(0)  # Volta ao início do buffer
        return buffer

# Função setup para registrar o cog
async def setup(bot):
    await bot.add_cog(WelcomeCog(bot))