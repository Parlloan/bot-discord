import discord
from discord.ext import commands
import logging
import json
import asyncio
from datetime import datetime

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Carrega as configurações do config.json
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
            self.moderator_role_id = config['moderator_role_id']
            self.mod_log_channel_id = config['mod_log_channel_id']
        except Exception as e:
            logging.error(f"Erro ao carregar config.json: {str(e)}")
            print(f"[ERROR] Erro ao carregar config.json: {str(e)}")
            raise

    # Decorador para verificar se o usuário tem o cargo de moderador
    def is_moderator():
        async def predicate(ctx):
            moderator_role = ctx.guild.get_role(int(ctx.bot.moderation_cog.moderator_role_id))
            if not moderator_role:
                await ctx.send("Cargo de moderador não encontrado. Verifique o ID no config.json.")
                return False
            if moderator_role not in ctx.author.roles:
                await ctx.send("Você não tem permissão para usar este comando. Apenas moderadores podem usá-lo.")
                return False
            return True
        return commands.check(predicate)

    @commands.command(name="ban")
    @is_moderator()
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        """Bane um usuário do servidor."""
        try:
            await member.ban(reason=reason)
            await ctx.send(f"{member.mention} foi banido por {ctx.author.mention}.")
            await self.log_action(
                ctx.guild,
                f"🚫 **Banimento**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Moderador: {ctx.author} ({ctx.author.id})\n"
                f"Motivo: {reason or 'Não especificado'}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        except Exception as e:
            await ctx.send(f"Erro ao banir {member.mention}: {str(e)}")
            logging.error(f"Erro ao banir {member}: {str(e)}")
            print(f"[ERROR] Erro ao banir {member}: {str(e)}")

    @commands.command(name="kick")
    @is_moderator()
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        """Expulsa um usuário do servidor."""
        try:
            await member.kick(reason=reason)
            await ctx.send(f"{member.mention} foi expulso por {ctx.author.mention}.")
            await self.log_action(
                ctx.guild,
                f"👢 **Expulsão**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Moderador: {ctx.author} ({ctx.author.id})\n"
                f"Motivo: {reason or 'Não especificado'}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        except Exception as e:
            await ctx.send(f"Erro ao expulsar {member.mention}: {str(e)}")
            logging.error(f"Erro ao expulsar {member}: {str(e)}")
            print(f"[ERROR] Erro ao expulsar {member}: {str(e)}")

    @commands.command(name="clear")
    @is_moderator()
    @commands.bot_has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int):
        """Deleta um número específico de mensagens no canal."""
        if amount < 1:
            await ctx.send("Por favor, especifique um número maior que 0.")
            return
        if amount > 100:
            await ctx.send("Não posso deletar mais de 100 mensagens de uma vez.")
            return

        try:
            await ctx.channel.purge(limit=amount)
            await ctx.send(f"{amount} mensagens deletadas por {ctx.author.mention}.", delete_after=5)
            await self.log_action(
                ctx.guild,
                f"🧹 **Limpeza de Mensagens**\n"
                f"Canal: {ctx.channel.name} ({ctx.channel.id})\n"
                f"Moderador: {ctx.author} ({ctx.author.id})\n"
                f"Quantidade: {amount}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        except Exception as e:
            await ctx.send(f"Erro ao deletar mensagens: {str(e)}")
            logging.error(f"Erro ao deletar mensagens: {str(e)}")
            print(f"[ERROR] Erro ao deletar mensagens: {str(e)}")

    @commands.command(name="mute")
    @is_moderator()
    @commands.bot_has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, duration: str):
        """Silencia um usuário por um período de tempo (ex.: 10m para 10 minutos)."""
        # Converte o tempo para segundos
        time_units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        try:
            unit = duration[-1].lower()
            if unit not in time_units:
                await ctx.send("Unidade de tempo inválida. Use s (segundos), m (minutos), h (horas) ou d (dias).")
                return
            time_value = int(duration[:-1])
            if time_value <= 0:
                await ctx.send("O tempo deve ser maior que 0.")
                return
            seconds = time_value * time_units[unit]
        except ValueError:
            await ctx.send("Formato de tempo inválido. Use algo como '10m' para 10 minutos.")
            return

        # Verifica ou cria o cargo "Muted"
        muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await ctx.guild.create_role(
                    name="Muted",
                    reason="Cargo criado para silenciar usuários"
                )
                # Configura permissões do cargo "Muted" em todos os canais
                for channel in ctx.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False)
            except Exception as e:
                await ctx.send(f"Erro ao criar o cargo Muted: {str(e)}")
                return

        # Aplica o cargo ao usuário
        try:
            await member.add_roles(muted_role, reason=f"Silenciado por {ctx.author}")
            await ctx.send(f"{member.mention} foi silenciado por {time_value}{unit} por {ctx.author.mention}.")
            await self.log_action(
                ctx.guild,
                f"🔇 **Silenciamento**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Moderador: {ctx.author} ({ctx.author.id})\n"
                f"Duração: {time_value}{unit}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            # Aguarda o tempo especificado e remove o cargo
            await asyncio.sleep(seconds)
            await member.remove_roles(muted_role, reason="Fim do silenciamento")
            await self.log_action(
                ctx.guild,
                f"🔊 **Fim de Silenciamento**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Moderador: {ctx.author} ({ctx.author.id})\n"
                f"Duração: {time_value}{unit}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        except Exception as e:
            await ctx.send(f"Erro ao silenciar {member.mention}: {str(e)}")
            logging.error(f"Erro ao silenciar {member}: {str(e)}")
            print(f"[ERROR] Erro ao silenciar {member}: {str(e)}")

    async def log_action(self, guild, message):
        """Registra uma ação de moderação no canal de logs e no arquivo."""
        try:
            log_channel = guild.get_channel(int(self.mod_log_channel_id))
            if log_channel:
                await log_channel.send(message)
            logging.info(message.replace('\n', ' | '))
            print(f"[INFO] {message.replace('\n', ' | ')}")
        except Exception as e:
            logging.error(f"Erro ao registrar log: {str(e)}")
            print(f"[ERROR] Erro ao registrar log: {str(e)}")

# Função setup para registrar o cog
async def setup(bot):
    cog = ModerationCog(bot)
    bot.moderation_cog = cog  # Armazena a instância do cog no bot para acesso ao moderator_role_id
    await bot.add_cog(cog)