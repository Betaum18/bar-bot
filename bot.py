import discord
from discord.ext import commands
import json
import os
from datetime import datetime

TOKEN = os.environ["DISCORD_TOKEN"]
CANAL_ID = int(os.environ.get("CANAL_ID", "1504491774150705152"))

DATA_FILE = "data.json"
PANEL_FILE = "panel_id.json"

# Tracks users waiting to send a chest photo: user_id -> sale info
pending_sales: dict[int, dict] = {}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ── Data helpers ──────────────────────────────────────────────────────────────

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        data = {
            "estoque_atual": 0,
            "total_combos_vendidos": 0,
            "total_dracmas_depositados": 0,
            "historico": [],
        }
        save_data(data)
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_panel_id() -> int | None:
    if not os.path.exists(PANEL_FILE):
        return None
    with open(PANEL_FILE, "r") as f:
        return json.load(f).get("message_id")


def save_panel_id(message_id: int) -> None:
    with open(PANEL_FILE, "w") as f:
        json.dump({"message_id": message_id}, f)


# ── Modals ────────────────────────────────────────────────────────────────────

class AdicionarEstoqueModal(discord.ui.Modal, title="📦 Adicionar Estoque"):
    quantidade = discord.ui.TextInput(
        label="Quantos combos foram adicionados?",
        placeholder="Ex: 10",
        min_length=1,
        max_length=6,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value.strip())
            if qtd <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Digite um número inteiro positivo.", ephemeral=True
            )
            return

        data = load_data()
        data["estoque_atual"] += qtd
        save_data(data)

        embed = discord.Embed(title="📦 Estoque Atualizado", color=discord.Color.blue())
        embed.add_field(name="Combos Adicionados", value=f"+{qtd}", inline=True)
        embed.add_field(name="Estoque Atual", value=str(data["estoque_atual"]), inline=True)
        embed.set_footer(
            text=f"{interaction.user.display_name} • {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        await interaction.response.send_message(embed=embed)


class RegistrarVendaModal(discord.ui.Modal, title="💰 Registrar Venda"):
    quantidade = discord.ui.TextInput(
        label="Quantos combos foram vendidos?",
        placeholder="Ex: 5",
        min_length=1,
        max_length=6,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value.strip())
            if qtd <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "❌ Digite um número inteiro positivo.", ephemeral=True
            )
            return

        data = load_data()
        if data["estoque_atual"] < qtd:
            await interaction.response.send_message(
                f"❌ Estoque insuficiente! Disponível: **{data['estoque_atual']}** combos.",
                ephemeral=True,
            )
            return

        pending_sales[interaction.user.id] = {
            "combos": qtd,
            "channel_id": interaction.channel_id,
            "display_name": interaction.user.display_name,
            "mention": interaction.user.mention,
        }

        await interaction.response.send_message(
            f"📸 **Envie a foto do baú agora** (Ctrl+V para colar a imagem).\n"
            f"> Combos: **{qtd}** • Dracmas a depositar: **{qtd * 10} Ð**",
            ephemeral=True,
        )


# ── Persistent panel view ─────────────────────────────────────────────────────

class PainelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Adicionar Estoque",
        emoji="📦",
        style=discord.ButtonStyle.primary,
        custom_id="bar:add_stock",
    )
    async def add_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdicionarEstoqueModal())

    @discord.ui.button(
        label="Registrar Venda",
        emoji="💰",
        style=discord.ButtonStyle.success,
        custom_id="bar:register_sale",
    )
    async def register_sale(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrarVendaModal())

    @discord.ui.button(
        label="Ver Resumo",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id="bar:summary",
    )
    async def summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        embed = discord.Embed(title="📊 Resumo do Bar", color=discord.Color.gold())
        embed.add_field(
            name="📦 Estoque Atual",
            value=f"{data['estoque_atual']} combos",
            inline=False,
        )
        embed.add_field(
            name="💰 Total Vendido",
            value=f"{data['total_combos_vendidos']} combos",
            inline=True,
        )
        embed.add_field(
            name="🪙 Dracmas Depositados",
            value=f"{data['total_dracmas_depositados']} Ð",
            inline=True,
        )
        embed.set_footer(text=f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        await interaction.response.send_message(embed=embed)


# ── Events ────────────────────────────────────────────────────────────────────

def make_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🍺 Gerenciamento do Bar — GTA RP",
        description=(
            "Use os botões abaixo para gerenciar o bar.\n\n"
            "**📦 Adicionar Estoque** — Registra combos adicionados ao estoque\n"
            "**💰 Registrar Venda** — Registra venda com foto obrigatória do baú\n"
            "**📊 Ver Resumo** — Exibe estoque atual e totais acumulados"
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Bar Bot • GTA RP")
    return embed


@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user} (ID: {bot.user.id})")

    # Register persistent view so buttons survive bot restarts
    bot.add_view(PainelView())

    canal = bot.get_channel(CANAL_ID)
    if canal is None:
        print(f"❌ Canal {CANAL_ID} não encontrado. Verifique CANAL_ID no .env")
        return

    embed = make_panel_embed()
    view = PainelView()
    panel_id = load_panel_id()

    if panel_id:
        try:
            msg = await canal.fetch_message(panel_id)
            await msg.edit(embed=embed, view=view)
            print(f"♻️  Painel atualizado (msg ID: {panel_id})")
            return
        except discord.NotFound:
            print("⚠️  Mensagem do painel não encontrada, criando nova...")

    msg = await canal.send(embed=embed, view=view)
    save_panel_id(msg.id)
    print(f"📌 Painel criado (msg ID: {msg.id})")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    sale = pending_sales.get(message.author.id)

    # Not waiting for a photo from this user, or wrong channel
    if sale is None or message.channel.id != sale["channel_id"]:
        await bot.process_commands(message)
        return

    # Find first image attachment
    image = next(
        (
            a
            for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ),
        None,
    )

    if image is None:
        await message.reply(
            "❌ Nenhuma imagem detectada. Envie a **foto do baú** (Ctrl+V para colar).",
            delete_after=10,
        )
        return

    combos = sale["combos"]
    dracmas = combos * 10
    now = datetime.now()

    data = load_data()
    data["estoque_atual"] = max(0, data["estoque_atual"] - combos)
    data["total_combos_vendidos"] += combos
    data["total_dracmas_depositados"] += dracmas
    data["historico"].append(
        {
            "usuario": sale["display_name"],
            "usuario_id": message.author.id,
            "combos": combos,
            "dracmas": dracmas,
            "data": now.isoformat(),
            "foto_url": image.url,
        }
    )
    save_data(data)
    del pending_sales[message.author.id]

    embed = discord.Embed(title="✅ Venda Registrada!", color=discord.Color.green())
    embed.add_field(name="👤 Vendedor", value=sale["mention"], inline=True)
    embed.add_field(name="📦 Combos Vendidos", value=str(combos), inline=True)
    embed.add_field(name="🪙 Dracmas Depositados", value=f"{dracmas} Ð", inline=True)
    embed.add_field(
        name="📦 Estoque Restante",
        value=f"{data['estoque_atual']} combos",
        inline=True,
    )
    embed.set_image(url=image.url)
    embed.set_footer(text=now.strftime("%d/%m/%Y %H:%M"))

    await message.reply(embed=embed)


bot.run(TOKEN)
