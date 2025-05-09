import discord
from discord.ext import commands, tasks
import logging
import json
from datetime import datetime, timedelta
import asyncio
import os
import random

class EconomyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}  # Controle de cooldown para mensagens
        self.voice_cooldowns = {}  # Controle de cooldown para tempo em voz
        self.message_history = {}  # Histórico de mensagens para detectar spam
        self.economy_file = "economy.json"
        self.users = self.load_economy()
        self.daily_limits = {}  # Controle de limites diários
        self.message_cooldown = 60  # Cooldown de 60 segundos para mensagens
        self.voice_cooldown = 300  # 5 minutos para recompensa por voz
        self.daily_message_limit = 10  # Limite diário de Rupias por mensagens
        self.daily_voice_limit = 20  # Limite diário de Rupias por tempo em voz
        self.voice_time_tracking = {}  # Rastreia o tempo total em voz por usuário (para conquistas)
        self.private_channels = {}  # Armazena canais de voz privados temporários

        # Carrega as configurações do config.json
        try:
            with open('config.json', 'r') as config_file:
                config = json.load(config_file)
            self.log_channel_id = config['economy_log_channel_id']
            self.items = config['economy_items']
        except Exception as e:
            logging.error(f"Erro ao carregar config.json: {str(e)}")
            print(f"[ERROR] Erro ao carregar config.json: {str(e)}")
            raise

        # Inicia a tarefa de verificação de tempo em voz
        self.check_voice_time.start()

    def load_economy(self):
        """Carrega os dados da economia do arquivo JSON."""
        try:
            if not os.path.exists(self.economy_file) or os.path.getsize(self.economy_file) == 0:
                logging.info("Arquivo economy.json não existe ou está vazio. Criando novo dicionário vazio.")
                print("[INFO] Arquivo economy.json não existe ou está vazio. Criando novo dicionário vazio.")
                return {}
            with open(self.economy_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.info("Arquivo economy.json não encontrado. Criando novo dicionário vazio.")
            print("[INFO] Arquivo economy.json não encontrado. Criando novo dicionário vazio.")
            return {}
        except json.JSONDecodeError as e:
            logging.error(f"Erro ao decodificar economy.json (formato inválido): {str(e)}. Retornando dicionário vazio.")
            print(f"[ERROR] Erro ao decodificar economy.json (formato inválido): {str(e)}. Retornando dicionário vazio.")
            return {}
        except Exception as e:
            logging.error(f"Erro ao carregar economy.json: {str(e)}")
            print(f"[ERROR] Erro ao carregar economy.json: {str(e)}")
            return {}

    def save_economy(self):
        """Salva os dados da economia no arquivo JSON."""
        try:
            with open(self.economy_file, 'w') as f:
                json.dump(self.users, f, indent=4)
        except Exception as e:
            logging.error(f"Erro ao salvar economy.json: {str(e)}")
            print(f"[ERROR] Erro ao salvar economy.json: {str(e)}")

    def check_daily_limit(self, user_id, limit_type):
        """Verifica e atualiza o limite diário do usuário."""
        user_id = str(user_id)
        current_date = datetime.utcnow().date()
        
        if user_id not in self.daily_limits:
            self.daily_limits[user_id] = {}
        
        if limit_type not in self.daily_limits[user_id]:
            self.daily_limits[user_id][limit_type] = {"date": current_date, "count": 0}
        
        # Reseta o contador se for um novo dia
        if self.daily_limits[user_id][limit_type]["date"] != current_date:
            self.daily_limits[user_id][limit_type] = {"date": current_date, "count": 0}
        
        return self.daily_limits[user_id][limit_type]["count"]

    def increment_daily_limit(self, user_id, limit_type, max_limit):
        """Incrementa o contador de limite diário."""
        user_id = str(user_id)
        count = self.check_daily_limit(user_id, limit_type)
        if count >= max_limit:
            return False
        self.daily_limits[user_id][limit_type]["count"] += 1
        return True

    def initialize_user_achievements(self, user_id):
        """Inicializa as conquistas de um usuário, se não existirem."""
        user_id = str(user_id)
        if "achievements" not in self.users[user_id]:
            self.users[user_id]["achievements"] = {
                "mensageiro": {"completed": False, "progress": 0},  # 100 mensagens
                "voz_ativa": {"completed": False, "progress": 0},  # 10 horas (36.000 segundos)
                "comprador": {"completed": False, "progress": 0}  # 5 compras
            }
            self.save_economy()

    async def check_achievement(self, user_id, achievement, progress_increment, target, reward, user, guild):
        """Verifica e atualiza o progresso de uma conquista."""
        user_id = str(user_id)
        self.initialize_user_achievements(user_id)
        
        achievement_data = self.users[user_id]["achievements"][achievement]
        if achievement_data["completed"]:
            return

        achievement_data["progress"] += progress_increment
        self.save_economy()

        if achievement_data["progress"] >= target and not achievement_data["completed"]:
            achievement_data["completed"] = True
            self.users[user_id]["coins"] += reward
            self.save_economy()

            await user.send(f"🎉 **Conquista Desbloqueada!** Você completou a conquista '{achievement}' e ganhou {reward} Rupias!")
            await self.log_action(
                guild,
                f"🏆 **Conquista Desbloqueada**\n"
                f"Usuário: {user} ({user.id})\n"
                f"Conquista: {achievement}\n"
                f"Recompensa: {reward} Rupias\n"
                f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

    @commands.Cog.listener()
    async def on_message(self, message):
        """Dá Rupias aos usuários por mensagens enviadas, com cooldown e limite diário."""
        if message.author.bot:
            return

        user_id = str(message.author.id)
        current_time = datetime.utcnow().timestamp()

        # Verifica cooldown (60 segundos entre ganhos)
        if user_id in self.cooldowns:
            last_time = self.cooldowns[user_id]
            if current_time - last_time < self.message_cooldown:
                return

        # Verifica limite diário de Rupias por mensagens
        if not self.increment_daily_limit(user_id, "message", self.daily_message_limit):
            if self.check_daily_limit(user_id, "message") == self.daily_message_limit:
                await self.log_action(
                    message.guild,
                    f"⚠️ **Limite Diário Atingido (Mensagens)**\n"
                    f"Usuário: {message.author} ({message.author.id})\n"
                    f"Limite: {self.daily_message_limit} Rupias por dia\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
            return

        # Verifica mensagens repetidas (spam)
        if user_id not in self.message_history:
            self.message_history[user_id] = []
        
        recent_messages = self.message_history[user_id][-3:]  # Últimas 3 mensagens
        if len(recent_messages) >= 3 and all(msg == message.content for msg in recent_messages):
            await self.log_action(
                message.guild,
                f"🚨 **Possível Spam Detectado**\n"
                f"Usuário: {message.author} ({message.author.id})\n"
                f"Mensagem: {message.content}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
            return

        self.message_history[user_id].append(message.content)
        if len(self.message_history[user_id]) > 3:
            self.message_history[user_id].pop(0)

        # Inicializa o usuário no sistema, se não existir
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": message.author.name}

        # Dá 1 Rupia ao usuário
        self.users[user_id]["coins"] += 1
        self.users[user_id]["name"] = message.author.name  # Atualiza o nome
        self.cooldowns[user_id] = current_time
        self.save_economy()

        # Verifica a conquista "Mensageiro"
        await self.check_achievement(user_id, "mensageiro", 1, 100, 200, message.author, message.guild)

        # Log da ação
        await self.log_action(
            message.guild,
            f"💰 **Ganho de Rupias (Mensagem)**\n"
            f"Usuário: {message.author} ({message.author.id})\n"
            f"Quantidade: 1 Rupia\n"
            f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
            f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

    @tasks.loop(seconds=60)  # Verifica a cada 60 segundos
    async def check_voice_time(self):
        """Dá Rupias aos usuários por tempo em canais de voz, com limite diário."""
        for guild in self.bot.guilds:
            for voice_channel in guild.voice_channels:
                for member in voice_channel.members:
                    if member.bot:
                        continue

                    user_id = str(member.id)
                    current_time = datetime.utcnow().timestamp()

                    # Verifica cooldown para recompensa por voz (5 minutos)
                    if user_id in self.voice_cooldowns:
                        last_time = self.voice_cooldowns[user_id]
                        if current_time - last_time < self.voice_cooldown:
                            # Incrementa o tempo em voz para a conquista "Voz Ativa"
                            if user_id not in self.voice_time_tracking:
                                self.voice_time_tracking[user_id] = 0
                            self.voice_time_tracking[user_id] += 60  # 60 segundos
                            await self.check_achievement(user_id, "voz_ativa", 60, 36000, 300, member, guild)
                            continue

                    # Verifica limite diário de Rupias por voz
                    if not self.increment_daily_limit(user_id, "voice", self.daily_voice_limit):
                        if self.check_daily_limit(user_id, "voice") == self.daily_voice_limit:
                            await self.log_action(
                                guild,
                                f"⚠️ **Limite Diário Atingido (Voz)**\n"
                                f"Usuário: {member} ({member.id})\n"
                                f"Limite: {self.daily_voice_limit} Rupias por dia\n"
                                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                            )
                        continue

                    # Inicializa o usuário no sistema, se não existir
                    if user_id not in self.users:
                        self.users[user_id] = {"coins": 0, "name": member.name}

                    # Dá 1 Rupia ao usuário
                    self.users[user_id]["coins"] += 1
                    self.users[user_id]["name"] = member.name
                    self.voice_cooldowns[user_id] = current_time
                    self.save_economy()

                    # Incrementa o tempo em voz para a conquista "Voz Ativa"
                    if user_id not in self.voice_time_tracking:
                        self.voice_time_tracking[user_id] = 0
                    self.voice_time_tracking[user_id] += 60  # 60 segundos
                    await self.check_achievement(user_id, "voz_ativa", 60, 36000, 300, member, guild)

                    # Log da ação
                    await self.log_action(
                        guild,
                        f"🎙️ **Ganho de Rupias (Voz)**\n"
                        f"Usuário: {member} ({member.id})\n"
                        f"Quantidade: 1 Rupia\n"
                        f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
                        f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )

    @check_voice_time.before_loop
    async def before_check_voice_time(self):
        await self.bot.wait_until_ready()

    def is_owner():
        async def predicate(ctx):
            if ctx.author.id != ctx.guild.owner_id:
                await ctx.send("Você não tem permissão para usar este comando. Apenas o dono do servidor pode usá-lo.")
                return False
            return True
        return commands.check(predicate)

    @commands.command(name="dar_rupias")
    @is_owner()
    async def dar_rupias(self, ctx, member: discord.Member, amount: int):
        """Dá Rupias a um usuário específico (apenas o dono do servidor)."""
        if amount <= 0:
            await ctx.send("A quantidade de Rupias deve ser maior que 0.")
            return

        user_id = str(member.id)
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": member.name}

        self.users[user_id]["coins"] += amount
        self.users[user_id]["name"] = member.name
        self.save_economy()

        await ctx.send(f"✅ **Rupias Adicionadas!** {amount} Rupias foram adicionadas ao saldo de {member.mention}. Novo saldo: {self.users[user_id]['coins']} Rupias.")
        await self.log_action(
            ctx.guild,
            f"💸 **Rupias Adicionadas (Manual)**\n"
            f"Moderador: {ctx.author} ({ctx.author.id})\n"
            f"Usuário: {member} ({member.id})\n"
            f"Quantidade: {amount} Rupias\n"
            f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
            f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        # Notifica o usuário por DM
        try:
            await member.send(f"💸 Você recebeu {amount} Rupias do dono do servidor! Seu novo saldo é {self.users[user_id]['coins']} Rupias.")
        except discord.Forbidden:
            await self.log_action(
                ctx.guild,
                f"⚠️ **Falha ao Enviar DM**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Motivo: Usuário bloqueou DMs ou não permite mensagens de bots\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

    @commands.command(name="remover_rupias")
    @is_owner()
    async def remover_rupias(self, ctx, member: discord.Member, amount: int):
        """Remove Rupias de um usuário específico (apenas o dono do servidor)."""
        if amount <= 0:
            await ctx.send("A quantidade de Rupias deve ser maior que 0.")
            return

        user_id = str(member.id)
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": member.name}

        # Verifica se o usuário tem Rupias suficientes para remover
        if self.users[user_id]["coins"] < amount:
            await ctx.send(f"{member.mention} não tem Rupias suficientes para remover. Saldo atual: {self.users[user_id]['coins']} Rupias.")
            return

        self.users[user_id]["coins"] -= amount
        self.users[user_id]["name"] = member.name
        self.save_economy()

        await ctx.send(f"✅ **Rupias Removidas!** {amount} Rupias foram removidas do saldo de {member.mention}. Novo saldo: {self.users[user_id]['coins']} Rupias.")
        await self.log_action(
            ctx.guild,
            f"💸 **Rupias Removidas (Manual)**\n"
            f"Moderador: {ctx.author} ({ctx.author.id})\n"
            f"Usuário: {member} ({member.id})\n"
            f"Quantidade: {amount} Rupias\n"
            f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
            f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        # Notifica o usuário por DM
        try:
            await member.send(f"💸 Foram removidas {amount} Rupias do seu saldo pelo dono do servidor. Seu novo saldo é {self.users[user_id]['coins']} Rupias.")
        except discord.Forbidden:
            await self.log_action(
                ctx.guild,
                f"⚠️ **Falha ao Enviar DM**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Motivo: Usuário bloqueou DMs ou não permite mensagens de bots\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

    @commands.command(name="bonus")
    @is_owner()
    async def bonus(self, ctx, amount: int):
        """Dá Rupias a todos os usuários em canais de voz (apenas o dono do servidor)."""
        if amount <= 0:
            await ctx.send("A quantidade de Rupias deve ser maior que 0.")
            return

        # Coleta usuários em canais de voz
        voice_members = []
        for voice_channel in ctx.guild.voice_channels:
            for member in voice_channel.members:
                if not member.bot and member not in voice_members:  # Evita duplicatas
                    voice_members.append(member)

        if not voice_members:
            await ctx.send("Nenhum usuário em canais de voz no momento.")
            return

        # Distribui as Rupias e notifica os usuários
        for member in voice_members:
            user_id = str(member.id)
            if user_id not in self.users:
                self.users[user_id] = {"coins": 0, "name": member.name}
            self.users[user_id]["coins"] += amount
            self.users[user_id]["name"] = member.name

            # Envia uma DM para o usuário
            try:
                await member.send(f"🎉 Você recebeu {amount} Rupias de bônus por participar de um evento no servidor!")
            except discord.Forbidden:
                await self.log_action(
                    ctx.guild,
                    f"⚠️ **Falha ao Enviar DM**\n"
                    f"Usuário: {member} ({member.id})\n"
                    f"Motivo: Usuário bloqueou DMs ou não permite mensagens de bots\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )

        self.save_economy()
        await ctx.send(f"🎉 **Bônus Distribuído!** {amount} Rupias foram dadas a {len(voice_members)} usuários em canais de voz.")
        await self.log_action(
            ctx.guild,
            f"🎁 **Bônus de Rupias Distribuído (Canais de Voz)**\n"
            f"Moderador: {ctx.author} ({ctx.author.id})\n"
            f"Quantidade: {amount} Rupias\n"
            f"Usuários Agraciados: {len(voice_members)}\n"
            f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

    @commands.command(name="saldo")
    async def saldo(self, ctx):
        """Mostra o saldo de Rupias do usuário."""
        user_id = str(ctx.author.id)
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": ctx.author.name}
            self.save_economy()

        rupias = self.users[user_id]["coins"]
        await ctx.send(f"{ctx.author.mention}, você tem **{rupias} Rupias**! 💰")

    @commands.command(name="top_rupias")
    async def top_rupias(self, ctx):
        """Mostra os 10 usuários com mais Rupias."""
        if not self.users:
            await ctx.send("Nenhum usuário tem Rupias ainda. Comece a interagir no servidor! 💬")
            return

        sorted_users = sorted(
            self.users.items(),
            key=lambda x: x[1]["coins"],
            reverse=True
        )[:10]

        ranking = "🏆 **Ranking de Rupias (Top 10)** 🏆\n\n"
        for i, (user_id, data) in enumerate(sorted_users, 1):
            user = self.bot.get_user(int(user_id))
            name = user.name if user else data["name"]
            rupias = data["coins"]
            ranking += f"**{i}.** {name} - {rupias} Rupias\n"

        await ctx.send(ranking)

    @commands.command(name="loja")
    async def loja(self, ctx):
        """Mostra os itens disponíveis na loja."""
        if not self.items:
            await ctx.send("A loja está vazia no momento. Volte mais tarde! 🏪")
            return

        loja = "🏪 **Loja de Rupias** 🏪\n\n"
        for item_id, item_data in self.items.items():
            loja += f"**{item_id}**\n"
            loja += f"Descrição: {item_data['description']}\n"
            loja += f"Preço: {item_data['price']} Rupias\n\n"

        await ctx.send(loja)

    @commands.command(name="conquistas")
    async def conquistas(self, ctx):
        """Mostra as conquistas do usuário e seu progresso."""
        user_id = str(ctx.author.id)
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": ctx.author.name}
            self.save_economy()

        self.initialize_user_achievements(user_id)
        achievements = self.users[user_id]["achievements"]

        embed = discord.Embed(title=f"🏆 Conquistas de {ctx.author.name}", color=discord.Color.gold())
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)

        # Mensageiro: Envie 100 mensagens
        mensageiro = achievements["mensageiro"]
        embed.add_field(
            name="📩 Mensageiro",
            value=f"Envie 100 mensagens\n**Progresso**: {mensageiro['progress']}/100\n**Status**: {'✅ Concluído' if mensageiro['completed'] else '⏳ Em andamento'}\n**Recompensa**: 200 Rupias",
            inline=False
        )

        # Voz Ativa: Passe 10 horas em voz
        voz_ativa = achievements["voz_ativa"]
        hours_progress = voz_ativa['progress'] // 3600
        hours_target = 36000 // 3600  # 10 horas
        embed.add_field(
            name="🎙️ Voz Ativa",
            value=f"Passe 10 horas em canais de voz\n**Progresso**: {hours_progress}/{hours_target} horas\n**Status**: {'✅ Concluído' if voz_ativa['completed'] else '⏳ Em andamento'}\n**Recompensa**: 300 Rupias",
            inline=False
        )

        # Comprador: Compre 5 itens
        comprador = achievements["comprador"]
        embed.add_field(
            name="🛒 Comprador",
            value=f"Compre 5 itens na loja\n**Progresso**: {comprador['progress']}/5\n**Status**: {'✅ Concluído' if comprador['completed'] else '⏳ Em andamento'}\n**Recompensa**: 500 Rupias",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.command(name="doar")
    async def doar(self, ctx, member: discord.Member, amount: int):
        """Permite ao usuário doar Rupias para outro usuário."""
        if member == ctx.author:
            await ctx.send("Você não pode doar Rupias para si mesmo!")
            return

        if amount <= 0:
            await ctx.send("A quantidade de Rupias deve ser maior que 0.")
            return

        donor_id = str(ctx.author.id)
        receiver_id = str(member.id)

        # Inicializa os usuários, se necessário
        if donor_id not in self.users:
            self.users[donor_id] = {"coins": 0, "name": ctx.author.name}
        if receiver_id not in self.users:
            self.users[receiver_id] = {"coins": 0, "name": member.name}

        # Verifica se o doador tem Rupias suficientes
        if self.users[donor_id]["coins"] < amount:
            await ctx.send(f"{ctx.author.mention}, você não tem Rupias suficientes! Você precisa de {amount} Rupias, mas tem apenas {self.users[donor_id]['coins']} Rupias.")
            return

        # Transfere as Rupias
        self.users[donor_id]["coins"] -= amount
        self.users[receiver_id]["coins"] += amount
        self.users[donor_id]["name"] = ctx.author.name
        self.users[receiver_id]["name"] = member.name
        self.save_economy()

        await ctx.send(f"{ctx.author.mention}, você doou {amount} Rupias para {member.mention}!")
        try:
            await member.send(f"💸 Você recebeu {amount} Rupias de {ctx.author.mention}! Seu novo saldo é {self.users[receiver_id]['coins']} Rupias.")
        except discord.Forbidden:
            await self.log_action(
                ctx.guild,
                f"⚠️ **Falha ao Enviar DM**\n"
                f"Usuário: {member} ({member.id})\n"
                f"Motivo: Usuário bloqueou DMs ou não permite mensagens de bots\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

        await self.log_action(
            ctx.guild,
            f"💸 **Doação de Rupias**\n"
            f"Doador: {ctx.author} ({ctx.author.id})\n"
            f"Recebedor: {member} ({member.id})\n"
            f"Quantidade: {amount} Rupias\n"
            f"Novo Saldo do Doador: {self.users[donor_id]['coins']} Rupias\n"
            f"Novo Saldo do Recebedor: {self.users[receiver_id]['coins']} Rupias\n"
            f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

    @commands.command(name="comprar")
    async def comprar(self, ctx, item_id: str):
        """Permite ao usuário comprar um item da loja."""
        if item_id not in self.items:
            await ctx.send(f"O item '{item_id}' não existe na loja. Use `!loja` para ver os itens disponíveis.")
            return

        user_id = str(ctx.author.id)
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": ctx.author.name}
            self.save_economy()

        item = self.items[item_id]
        price = item["price"]
        rupias = self.users[user_id]["coins"]

        if rupias < price:
            await ctx.send(f"{ctx.author.mention}, você não tem Rupias suficientes! Você precisa de {price} Rupias, mas tem apenas {rupias} Rupias.")
            return

        # Verifica permissões do bot manualmente
        bot_member = ctx.guild.me
        required_perms = {
            "manage_roles": False,  # Para cargo_vip e cargo_personalizado
            "manage_channels": False,  # Para mute_texto e canal_voz_privado
            "mute_members": False,  # Para mute_voz
            "move_members": False,  # Para kick_voz
        }

        if item_id in ["cargo_vip", "cargo_personalizado"]:
            required_perms["manage_roles"] = True
        elif item_id == "kick_voz":
            required_perms["move_members"] = True
        elif item_id == "mute_voz":
            required_perms["mute_members"] = True
        elif item_id in ["mute_texto", "canal_voz_privado"]:
            required_perms["manage_channels"] = True

        missing_perms = []
        for perm, needed in required_perms.items():
            if needed and not getattr(bot_member.guild_permissions, perm):
                missing_perms.append(perm.replace("_", " ").title())

        if missing_perms:
            await ctx.send(f"O bot não tem as permissões necessárias para executar esta ação. Permissões faltando: {', '.join(missing_perms)}. Por favor, peça a um administrador para conceder essas permissões.")
            return

        self.users[user_id]["coins"] -= price
        self.save_economy()

        # Incrementa a conquista "Comprador"
        await self.check_achievement(user_id, "comprador", 1, 5, 500, ctx.author, ctx.guild)

        # Encontra o canal #geral para anúncios públicos
        geral_channel = discord.utils.get(ctx.guild.channels, name="geral")
        if not geral_channel:
            await ctx.send("Canal #geral não encontrado. As ações serão realizadas, mas o anúncio público não será enviado.")
            # Prossegue com a ação mesmo que o canal #geral não exista

        if item_id == "cargo_vip":
            role = discord.utils.get(ctx.guild.roles, name="VIP")
            if not role:
                role = await ctx.guild.create_role(name="VIP", reason="Cargo para compradores da loja")
            try:
                await ctx.author.add_roles(role)
                await ctx.send(f"{ctx.author.mention}, você comprou o **{item_id}**! O cargo VIP foi adicionado por 30 dias. 🎉")
                await self.log_action(
                    ctx.guild,
                    f"🛒 **Compra Realizada**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Item: {item_id}\n"
                    f"Preço: {price} Rupias\n"
                    f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                await asyncio.sleep(30 * 24 * 60 * 60)  # 30 dias em segundos
                await ctx.author.remove_roles(role)
                await self.log_action(
                    ctx.guild,
                    f"⏰ **Fim do Cargo VIP**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Item: {item_id}\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
            except Exception as e:
                await ctx.send(f"Erro ao adicionar o cargo VIP: {str(e)}")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

        elif item_id == "mensagem_personalizada":
            if not geral_channel:
                await ctx.send("Canal #geral não encontrado. Peça a um administrador para criá-lo.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return
            try:
                await ctx.send(f"{ctx.author.mention}, você comprou uma **mensagem personalizada**! Envie a mensagem que deseja no canal #geral (você tem 60 segundos).")
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                message = await self.bot.wait_for("message", check=check, timeout=60)
                await geral_channel.send(f"📢 Mensagem personalizada de {ctx.author.mention}: {message.content}")
                await self.log_action(
                    ctx.guild,
                    f"🛒 **Compra Realizada**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Item: {item_id}\n"
                    f"Preço: {price} Rupias\n"
                    f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
            except asyncio.TimeoutError:
                await ctx.send(f"{ctx.author.mention}, o tempo para enviar a mensagem expirou. Suas Rupias foram reembolsadas.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

        elif item_id == "kick_voz":
            # Coleta usuários em canais de voz (excluindo o comprador)
            voice_members = []
            for voice_channel in ctx.guild.voice_channels:
                for member in voice_channel.members:
                    if member != ctx.author and not member.bot:
                        voice_members.append(member)

            if not voice_members:
                await ctx.send("Nenhum outro usuário em canais de voz no momento.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

            # Mostra a lista de usuários disponíveis para kick
            member_list = "\n".join([f"{i+1}. {member.name}" for i, member in enumerate(voice_members)])
            await ctx.send(f"Escolha um usuário para expulsar do canal de voz (digite o número correspondente, você tem 30 segundos):\n{member_list}")

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

            try:
                response = await self.bot.wait_for("message", check=check, timeout=30)
                choice = int(response.content) - 1
                if choice < 0 or choice >= len(voice_members):
                    await ctx.send("Número inválido. A compra foi cancelada.")
                    self.users[user_id]["coins"] += price  # Reembolsa o usuário
                    self.save_economy()
                    return

                target = voice_members[choice]

                # Pergunta se o usuário quer ser anônimo
                anonymous = False
                await ctx.send("Deseja pagar 50 Rupias extras para que esta ação seja anônima? (Responda 'sim' ou 'não' em 15 segundos)")
                def check_anonymous(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["sim", "não"]

                try:
                    anon_response = await self.bot.wait_for("message", check=check_anonymous, timeout=15)
                    if anon_response.content.lower() == "sim":
                        if self.users[user_id]["coins"] >= 50:
                            self.users[user_id]["coins"] -= 50
                            self.save_economy()
                            anonymous = True
                            await ctx.send("Ação será realizada anonimamente.")
                        else:
                            await ctx.send("Você não tem Rupias suficientes para ser anônimo (50 Rupias necessárias). A ação será realizada normalmente.")
                except asyncio.TimeoutError:
                    await ctx.send("Tempo esgotado. A ação será realizada normalmente.")

                try:
                    await target.move_to(None)  # Expulsa do canal de voz
                    # Anuncia no canal #geral, se existir
                    if geral_channel:
                        if anonymous:
                            await geral_channel.send(f"{target.mention} foi expulso de um canal de voz por um usuário anônimo!")
                            await target.send("👢 Você foi expulso de um canal de voz por um usuário anônimo!")
                        else:
                            await geral_channel.send(f"{target.mention} foi expulso de um canal de voz por {ctx.author.mention}!")
                            await target.send(f"👢 Você foi expulso de um canal de voz por {ctx.author.mention}!")
                    else:
                        if anonymous:
                            await target.send("👢 Você foi expulso de um canal de voz por um usuário anônimo!")
                        else:
                            await target.send(f"👢 Você foi expulso de um canal de voz por {ctx.author.mention}!")

                    await self.log_action(
                        ctx.guild,
                        f"👢 **Kick em Canal de Voz (Compra)**\n"
                        f"Autor: {'Anônimo' if anonymous else f'{ctx.author} ({ctx.author.id})'}\n"
                        f"Alvo: {target} ({target.id})\n"
                        f"Preço: {price + (50 if anonymous else 0)} Rupias\n"
                        f"Novo Saldo do Autor: {self.users[user_id]['coins']} Rupias\n"
                        f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                except Exception as e:
                    await ctx.send(f"Erro ao expulsar o usuário do canal de voz: {str(e)}")
                    self.users[user_id]["coins"] += price + (50 if anonymous else 0)  # Reembolsa o usuário
                    self.save_economy()
                    return

            except asyncio.TimeoutError:
                await ctx.send(f"{ctx.author.mention}, o tempo para escolher um usuário expirou. Suas Rupias foram reembolsadas.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

        elif item_id == "mute_voz":
            # Coleta usuários em canais de voz (excluindo o comprador)
            voice_members = []
            for voice_channel in ctx.guild.voice_channels:
                for member in voice_channel.members:
                    if member != ctx.author and not member.bot:
                        voice_members.append(member)

            if not voice_members:
                await ctx.send("Nenhum outro usuário em canais de voz no momento.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

            # Mostra a lista de usuários disponíveis para mute
            member_list = "\n".join([f"{i+1}. {member.name}" for i, member in enumerate(voice_members)])
            await ctx.send(f"Escolha um usuário para mutar no canal de voz por 5 minutos (digite o número correspondente, você tem 30 segundos):\n{member_list}")

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

            try:
                response = await self.bot.wait_for("message", check=check, timeout=30)
                choice = int(response.content) - 1
                if choice < 0 or choice >= len(voice_members):
                    await ctx.send("Número inválido. A compra foi cancelada.")
                    self.users[user_id]["coins"] += price  # Reembolsa o usuário
                    self.save_economy()
                    return

                target = voice_members[choice]

                # Pergunta se o usuário quer ser anônimo
                anonymous = False
                await ctx.send("Deseja pagar 50 Rupias extras para que esta ação seja anônima? (Responda 'sim' ou 'não' em 15 segundos)")
                def check_anonymous(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["sim", "não"]

                try:
                    anon_response = await self.bot.wait_for("message", check=check_anonymous, timeout=15)
                    if anon_response.content.lower() == "sim":
                        if self.users[user_id]["coins"] >= 50:
                            self.users[user_id]["coins"] -= 50
                            self.save_economy()
                            anonymous = True
                            await ctx.send("Ação será realizada anonimamente.")
                        else:
                            await ctx.send("Você não tem Rupias suficientes para ser anônimo (50 Rupias necessárias). A ação será realizada normalmente.")
                except asyncio.TimeoutError:
                    await ctx.send("Tempo esgotado. A ação será realizada normalmente.")

                try:
                    await target.edit(mute=True)
                    # Anuncia no canal #geral, se existir
                    if geral_channel:
                        if anonymous:
                            await geral_channel.send(f"{target.mention} foi mutado em um canal de voz por um usuário anônimo por 5 minutos!")
                            await target.send("🔇 Você foi mutado em um canal de voz por um usuário anônimo por 5 minutos!")
                        else:
                            await geral_channel.send(f"{target.mention} foi mutado em um canal de voz por {ctx.author.mention} por 5 minutos!")
                            await target.send(f"🔇 Você foi mutado em um canal de voz por {ctx.author.mention} por 5 minutos!")
                    else:
                        if anonymous:
                            await target.send("🔇 Você foi mutado em um canal de voz por um usuário anônimo por 5 minutos!")
                        else:
                            await target.send(f"🔇 Você foi mutado em um canal de voz por {ctx.author.mention} por 5 minutos!")

                    await self.log_action(
                        ctx.guild,
                        f"🔇 **Mute em Canal de Voz (Compra)**\n"
                        f"Autor: {'Anônimo' if anonymous else f'{ctx.author} ({ctx.author.id})'}\n"
                        f"Alvo: {target} ({target.id})\n"
                        f"Preço: {price + (50 if anonymous else 0)} Rupias\n"
                        f"Novo Saldo do Autor: {self.users[user_id]['coins']} Rupias\n"
                        f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                    await asyncio.sleep(5 * 60)  # 5 minutos
                    await target.edit(mute=False)
                    await self.log_action(
                        ctx.guild,
                        f"🔊 **Fim do Mute em Canal de Voz**\n"
                        f"Usuário: {target} ({target.id})\n"
                        f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                except Exception as e:
                    await ctx.send(f"Erro ao mutar o usuário no canal de voz: {str(e)}")
                    self.users[user_id]["coins"] += price + (50 if anonymous else 0)  # Reembolsa o usuário
                    self.save_economy()
                    return

            except asyncio.TimeoutError:
                await ctx.send(f"{ctx.author.mention}, o tempo para escolher um usuário expirou. Suas Rupias foram reembolsadas.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

        elif item_id == "mute_texto":
            # Coleta usuários no servidor (excluindo o comprador)
            members = [member for member in ctx.guild.members if member != ctx.author and not member.bot]
            if not members:
                await ctx.send("Nenhum outro usuário disponível no servidor.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

            # Mostra a lista de usuários disponíveis para mute
            member_list = "\n".join([f"{i+1}. {member.name}" for i, member in enumerate(members)])
            await ctx.send(f"Escolha um usuário para mutar nos canais de texto por 5 minutos (digite o número correspondente, você tem 30 segundos):\n{member_list}")

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

            try:
                response = await self.bot.wait_for("message", check=check, timeout=30)
                choice = int(response.content) - 1
                if choice < 0 or choice >= len(members):
                    await ctx.send("Número inválido. A compra foi cancelada.")
                    self.users[user_id]["coins"] += price  # Reembolsa o usuário
                    self.save_economy()
                    return

                target = members[choice]

                # Pergunta se o usuário quer ser anônimo
                anonymous = False
                await ctx.send("Deseja pagar 50 Rupias extras para que esta ação seja anônima? (Responda 'sim' ou 'não' em 15 segundos)")
                def check_anonymous(m):
                    return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["sim", "não"]

                try:
                    anon_response = await self.bot.wait_for("message", check=check_anonymous, timeout=15)
                    if anon_response.content.lower() == "sim":
                        if self.users[user_id]["coins"] >= 50:
                            self.users[user_id]["coins"] -= 50
                            self.save_economy()
                            anonymous = True
                            await ctx.send("Ação será realizada anonimamente.")
                        else:
                            await ctx.send("Você não tem Rupias suficientes para ser anônimo (50 Rupias necessárias). A ação será realizada normalmente.")
                except asyncio.TimeoutError:
                    await ctx.send("Tempo esgotado. A ação será realizada normalmente.")

                try:
                    # Aplica o mute nos canais de texto (nega permissões de envio de mensagens)
                    for channel in ctx.guild.text_channels:
                        await channel.set_permissions(target, send_messages=False)
                    # Anuncia no canal #geral, se existir
                    if geral_channel:
                        if anonymous:
                            await geral_channel.send(f"{target.mention} foi mutado nos canais de texto por um usuário anônimo por 5 minutos!")
                            await target.send("🔇 Você foi mutado nos canais de texto por um usuário anônimo por 5 minutos!")
                        else:
                            await geral_channel.send(f"{target.mention} foi mutado nos canais de texto por {ctx.author.mention} por 5 minutos!")
                            await target.send(f"🔇 Você foi mutado nos canais de texto por {ctx.author.mention} por 5 minutos!")
                    else:
                        if anonymous:
                            await target.send("🔇 Você foi mutado nos canais de texto por um usuário anônimo por 5 minutos!")
                        else:
                            await target.send(f"🔇 Você foi mutado nos canais de texto por {ctx.author.mention} por 5 minutos!")

                    await self.log_action(
                        ctx.guild,
                        f"🔇 **Mute em Canais de Texto (Compra)**\n"
                        f"Autor: {'Anônimo' if anonymous else f'{ctx.author} ({ctx.author.id})'}\n"
                        f"Alvo: {target} ({target.id})\n"
                        f"Preço: {price + (50 if anonymous else 0)} Rupias\n"
                        f"Novo Saldo do Autor: {self.users[user_id]['coins']} Rupias\n"
                        f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                    await asyncio.sleep(5 * 60)  # 5 minutos
                    for channel in ctx.guild.text_channels:
                        await channel.set_permissions(target, send_messages=None)  # Remove a restrição
                    await self.log_action(
                        ctx.guild,
                        f"🔊 **Fim do Mute em Canais de Texto**\n"
                        f"Usuário: {target} ({target.id})\n"
                        f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                except Exception as e:
                    await ctx.send(f"Erro ao mutar o usuário nos canais de texto: {str(e)}")
                    self.users[user_id]["coins"] += price + (50 if anonymous else 0)  # Reembolsa o usuário
                    self.save_economy()
                    return

            except asyncio.TimeoutError:
                await ctx.send(f"{ctx.author.mention}, o tempo para escolher um usuário expirou. Suas Rupias foram reembolsadas.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

        elif item_id == "cargo_personalizado":
            try:
                await ctx.send(f"{ctx.author.mention}, você comprou um **cargo personalizado**! Digite o nome do cargo que deseja (máximo 50 caracteres, você tem 60 segundos).")
                def check(m):
                    return m.author == ctx.author and m.channel == ctx.channel
                message = await self.bot.wait_for("message", check=check, timeout=60)
                role_name = message.content[:50]  # Limita o nome a 50 caracteres
                role = await ctx.guild.create_role(name=role_name, reason=f"Cargo personalizado para {ctx.author.name}")
                await ctx.author.add_roles(role)
                await ctx.send(f"{ctx.author.mention}, seu cargo personalizado '{role_name}' foi criado e adicionado por 7 dias! 🎉")
                await self.log_action(
                    ctx.guild,
                    f"🛒 **Compra Realizada**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Item: {item_id}\n"
                    f"Preço: {price} Rupias\n"
                    f"Cargo Criado: {role_name}\n"
                    f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                await asyncio.sleep(7 * 24 * 60 * 60)  # 7 dias em segundos
                await ctx.author.remove_roles(role)
                await role.delete(reason="Fim do período do cargo personalizado")
                await self.log_action(
                    ctx.guild,
                    f"⏰ **Fim do Cargo Personalizado**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Cargo: {role_name}\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
            except asyncio.TimeoutError:
                await ctx.send(f"{ctx.author.mention}, o tempo para enviar o nome do cargo expirou. Suas Rupias foram reembolsadas.")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return
            except Exception as e:
                await ctx.send(f"Erro ao criar o cargo personalizado: {str(e)}")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

        elif item_id == "canal_voz_privado":
            try:
                # Busca a categoria pelo ID
                category_id = 627874145085947957
                category = discord.utils.get(ctx.guild.categories, id=category_id)
                if not category:
                    await ctx.send("Erro: A categoria de canais de voz (ID: 627874145085947957) não foi encontrada. Por favor, verifique o ID ou peça a um administrador para recriar a categoria.")
                    self.users[user_id]["coins"] += price  # Reembolsa o usuário
                    self.save_economy()
                    return

                channel_name = f"Privado-{ctx.author.name}"
                overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    ctx.author: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True),
                    ctx.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)
                }
                channel = await ctx.guild.create_voice_channel(
                    name=channel_name,
                    overwrites=overwrites,
                    category=category,  # Define a categoria
                    reason=f"Canal de voz privado para {ctx.author.name}"
                )
                self.private_channels[channel.id] = {"owner": ctx.author.id, "invited": []}
                await ctx.send(
                    f"{ctx.author.mention}, seu canal de voz privado '{channel_name}' foi criado por 24 horas! 🎉\n"
                    f"Use o comando `!convidar @usuário` para convidar outros usuários para o canal.\n"
                    f"Nota: Este canal é privado e só pode ser gerenciado com o comando `!convidar`."
                )
                await self.log_action(
                    ctx.guild,
                    f"🛒 **Compra Realizada**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Item: {item_id}\n"
                    f"Preço: {price} Rupias\n"
                    f"Canal Criado: {channel_name}\n"
                    f"Novo Saldo: {self.users[user_id]['coins']} Rupias\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
                await asyncio.sleep(24 * 60 * 60)  # 24 horas em segundos
                await channel.delete(reason="Fim do período do canal de voz privado")
                del self.private_channels[channel.id]
                await self.log_action(
                    ctx.guild,
                    f"⏰ **Fim do Canal de Voz Privado**\n"
                    f"Usuário: {ctx.author} ({ctx.author.id})\n"
                    f"Canal: {channel_name}\n"
                    f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                )
            except Exception as e:
                await ctx.send(f"Erro ao criar o canal de voz privado: {str(e)}")
                self.users[user_id]["coins"] += price  # Reembolsa o usuário
                self.save_economy()
                return

    @commands.command(name="convidar")
    async def convidar(self, ctx, member: discord.Member):
        """Permite ao dono de um canal de voz privado convidar outros usuários."""
        user_id = str(ctx.author.id)
        if user_id not in self.users:
            self.users[user_id] = {"coins": 0, "name": ctx.author.name}
            self.save_economy()

        # Verifica se o autor é o dono de algum canal privado
        channel_id = None
        for chan_id, data in self.private_channels.items():
            if data["owner"] == ctx.author.id:
                channel_id = chan_id
                break

        if not channel_id:
            await ctx.send("Você não possui um canal de voz privado ativo. Compre um com `!comprar canal_voz_privado`.")
            return

        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send("O canal de voz privado não existe mais.")
            del self.private_channels[channel_id]
            return

        if member.id in self.private_channels[channel_id]["invited"]:
            await ctx.send(f"{member.mention} já foi convidado para o canal de voz privado!")
            return

        try:
            await channel.set_permissions(member, view_channel=True, connect=True, speak=True)
            self.private_channels[channel_id]["invited"].append(member.id)
            await ctx.send(f"{member.mention} foi convidado para o seu canal de voz privado '{channel.name}'!")
            await member.send(f"🎉 Você foi convidado por {ctx.author.mention} para o canal de voz privado '{channel.name}'! Junte-se a ele!")
            await self.log_action(
                ctx.guild,
                f"📩 **Convite para Canal de Voz Privado**\n"
                f"Autor: {ctx.author} ({ctx.author.id})\n"
                f"Convidado: {member} ({member.id})\n"
                f"Canal: {channel.name}\n"
                f"Data: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
        except Exception as e:
            await ctx.send(f"Erro ao convidar o usuário: {str(e)}")

    async def log_action(self, guild, message):
        """Registra uma ação da economia no canal de logs e no arquivo."""
        try:
            log_channel = guild.get_channel(int(self.log_channel_id))
            if log_channel:
                await log_channel.send(message)
            logging.info(message.replace('\n', ' | '))
            print(f"[INFO] {message.replace('\n', ' | ')}")
        except Exception as e:
            logging.error(f"Erro ao registrar log: {str(e)}")
            print(f"[ERROR] Erro ao registrar log: {str(e)}")

# Função setup para registrar o cog
async def setup(bot):
    await bot.add_cog(EconomyCog(bot))