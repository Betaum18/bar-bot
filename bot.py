import asyncio
import base64
import json
import os
from datetime import datetime

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN            = os.getenv("DISCORD_TOKEN")
CANAL_PAINEL_ID  = int(os.getenv("CANAL_PAINEL_ID", "1504517445954703554"))
CANAL_POSTS_ID   = int(os.getenv("CANAL_POSTS_ID",  "1504491774150705152"))
IMGBB_API_KEY    = os.getenv("IMGBB_API_KEY", "")
APPS_SCRIPT_URL  = os.getenv("APPS_SCRIPT_URL", "")

DATA_FILE  = "data.json"
PANEL_FILE = "panel_id.json"

COMBOS      = ["Aurora", "Delfos", "Estradeiro", "Estradeiro Verde", "Sunset", "Midnight"]
PELUCIAS    = ["Aegis", "Raposo"]
TODOS_ITENS = COMBOS + PELUCIAS

DRACMAS = {**{c: 10 for c in COMBOS}, **{p: 250 for p in PELUCIAS}}

EMOJI = {
    "Aurora":           "🌅",
    "Delfos":           "🌊",
    "Estradeiro":       "🛣️",
    "Estradeiro Verde": "🌿",
    "Sunset":           "🌇",
    "Midnight":         "🌙",
    "Aegis":            "🛡️",
    "Raposo":           "🦊",
}

# user_id -> sale info (waiting for chest photo)
pending_sales: dict[int, dict] = {}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ── Local data ────────────────────────────────────────────────────────────────

def default_data() -> dict:
    return {
        "estoque": {item: 0 for item in TODOS_ITENS},
        "total_dracmas_depositados": 0,
        "historico": [],
    }


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        data = default_data()
        save_data(data)
        return data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "estoque_atual" in data:  # migrate old structure
        new = default_data()
        new["total_dracmas_depositados"] = data.get("total_dracmas_depositados", 0)
        new["historico"] = data.get("historico", [])
        save_data(new)
        return new
    for item in TODOS_ITENS:
        data["estoque"].setdefault(item, 0)
    return data


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


# ── Apps Script ───────────────────────────────────────────────────────────────

async def sheets_append(payload: dict) -> None:
    """POST a row to the Google Apps Script Web App."""
    if not APPS_SCRIPT_URL:
        return
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(APPS_SCRIPT_URL, json=payload, allow_redirects=True) as r:
                if r.status not in (200, 302):
                    print(f"⚠️  Apps Script: status {r.status}")
    except Exception as e:
        print(f"⚠️  Apps Script: {e}")


# ── imgbb ─────────────────────────────────────────────────────────────────────

async def imgbb_upload(discord_url: str) -> str:
    """Upload image to imgbb, return permanent URL. Falls back to Discord URL on error."""
    if not IMGBB_API_KEY:
        return discord_url
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(discord_url) as r:
                image_bytes = await r.read()
            encoded = base64.b64encode(image_bytes).decode()
            async with session.post(
                "https://api.imgbb.com/1/upload",
                data={"key": IMGBB_API_KEY, "image": encoded},
            ) as r:
                result = await r.json()
        return result["data"]["url"]
    except Exception as e:
        print(f"⚠️  imgbb: {e}")
        return discord_url


# ── Select options ────────────────────────────────────────────────────────────

SELECT_OPTIONS = [
    discord.SelectOption(label="Aurora",           emoji="🌅", description="Combo • 10 Ð"),
    discord.SelectOption(label="Delfos",           emoji="🌊", description="Combo • 10 Ð"),
    discord.SelectOption(label="Estradeiro",       emoji="🛣️", description="Combo • 10 Ð"),
    discord.SelectOption(label="Estradeiro Verde", emoji="🌿", description="Combo • 10 Ð"),
    discord.SelectOption(label="Sunset",           emoji="🌇", description="Combo • 10 Ð"),
    discord.SelectOption(label="Midnight",         emoji="🌙", description="Combo • 10 Ð"),
    discord.SelectOption(label="Aegis",            emoji="🛡️", description="Pelúcia • 250 Ð"),
    discord.SelectOption(label="Raposo",           emoji="🦊", description="Pelúcia • 250 Ð"),
]


# ── Modals ────────────────────────────────────────────────────────────────────

class AdicionarEstoqueModal(discord.ui.Modal):
    def __init__(self, item: str):
        super().__init__(title=f"📦 Adicionar {item}")
        self.item = item
        self.quantidade = discord.ui.TextInput(
            label=f"Quantos(as) {item} adicionar?",
            placeholder="Ex: 5",
            min_length=1,
            max_length=6,
        )
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value.strip())
            if qtd <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Digite um número inteiro positivo.", ephemeral=True)
            return

        data = load_data()
        data["estoque"][self.item] += qtd
        save_data(data)

        tipo = "Pelúcia" if self.item in PELUCIAS else "Combo"
        now  = datetime.now()

        embed = discord.Embed(title="📦 Estoque Atualizado", color=discord.Color.blue())
        embed.add_field(name="Item",         value=f"{EMOJI[self.item]} {self.item} ({tipo})", inline=False)
        embed.add_field(name="Adicionados",  value=f"+{qtd}",                                  inline=True)
        embed.add_field(name="Estoque Atual",value=str(data["estoque"][self.item]),             inline=True)
        embed.set_footer(text=f"{interaction.user.display_name} • {now.strftime('%d/%m/%Y %H:%M')}")

        await interaction.response.send_message("✅ Estoque atualizado!", ephemeral=True)

        canal_posts = bot.get_channel(CANAL_POSTS_ID) or await bot.fetch_channel(CANAL_POSTS_ID)
        payload = {
            "timestamp":       now.strftime("%d/%m/%Y %H:%M"),
            "tipo":            "Estoque",
            "usuario":         interaction.user.display_name,
            "item":            self.item,
            "quantidade":      qtd,
            "dracmas":         "",
            "foto":            "",
            "estoque_restante": data["estoque"][self.item],
        }
        await asyncio.gather(
            canal_posts.send(embed=embed),
            sheets_append(payload),
        )


class RegistrarVendaModal(discord.ui.Modal):
    def __init__(self, item: str):
        super().__init__(title=f"💰 Venda — {item}")
        self.item = item
        self.quantidade = discord.ui.TextInput(
            label=f"Quantos(as) {item} foram vendidos(as)?",
            placeholder="Ex: 2",
            min_length=1,
            max_length=6,
        )
        self.add_item(self.quantidade)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value.strip())
            if qtd <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Digite um número inteiro positivo.", ephemeral=True)
            return

        data = load_data()
        estoque_item = data["estoque"].get(self.item, 0)
        if estoque_item < qtd:
            await interaction.response.send_message(
                f"❌ Estoque insuficiente de **{self.item}**! Disponível: **{estoque_item}**.",
                ephemeral=True,
            )
            return

        dracmas = DRACMAS[self.item] * qtd
        pending_sales[interaction.user.id] = {
            "item":         self.item,
            "quantidade":   qtd,
            "dracmas":      dracmas,
            "channel_id":   CANAL_PAINEL_ID,
            "display_name": interaction.user.display_name,
            "mention":      interaction.user.mention,
        }

        await interaction.response.send_message(
            f"📸 **Envie a foto do baú agora** neste canal (Ctrl+V para colar a imagem).\n"
            f"> {EMOJI[self.item]} **{self.item}**: {qtd} unid. • **{dracmas} Ð** a depositar",
            ephemeral=True,
        )


# ── Select menus ──────────────────────────────────────────────────────────────

class SelecionarItemEstoqueView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(placeholder="Selecione o item...", options=SELECT_OPTIONS)
    async def select_item(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_modal(AdicionarEstoqueModal(select.values[0]))


class SelecionarItemVendaView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.select(placeholder="Selecione o item vendido...", options=SELECT_OPTIONS)
    async def select_item(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_modal(RegistrarVendaModal(select.values[0]))


# ── Persistent panel view ─────────────────────────────────────────────────────

class PainelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Adicionar Estoque", emoji="📦", style=discord.ButtonStyle.primary,   custom_id="bar:add_stock")
    async def add_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📦 **Selecione o item para adicionar ao estoque:**",
            view=SelecionarItemEstoqueView(),
            ephemeral=True,
        )

    @discord.ui.button(label="Registrar Venda",   emoji="💰", style=discord.ButtonStyle.success,   custom_id="bar:register_sale")
    async def register_sale(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "💰 **Selecione o item vendido:**",
            view=SelecionarItemVendaView(),
            ephemeral=True,
        )

    @discord.ui.button(label="Ver Resumo",        emoji="📊", style=discord.ButtonStyle.secondary, custom_id="bar:summary")
    async def summary(self, interaction: discord.Interaction, button: discord.ui.Button):
        data     = load_data()
        estoque  = data["estoque"]
        historico = data["historico"]

        total_combos   = sum(r["quantidade"] for r in historico if r.get("item") in COMBOS)
        total_pelucias = sum(r["quantidade"] for r in historico if r.get("item") in PELUCIAS)

        combos_lines   = "\n".join(f"{EMOJI[c]} **{c}**: {estoque.get(c, 0)}" for c in COMBOS)
        pelucias_lines = "\n".join(f"{EMOJI[p]} **{p}**: {estoque.get(p, 0)}" for p in PELUCIAS)

        embed = discord.Embed(title="📊 Resumo do Bar", color=discord.Color.gold())
        embed.add_field(name="🍹 Estoque — Combos",    value=combos_lines,   inline=True)
        embed.add_field(name="🧸 Estoque — Pelúcias",  value=pelucias_lines, inline=True)
        embed.add_field(name="​", value="​", inline=False)
        embed.add_field(name="💰 Combos Vendidos",     value=str(total_combos),                        inline=True)
        embed.add_field(name="🧸 Pelúcias Vendidas",   value=str(total_pelucias),                      inline=True)
        embed.add_field(name="🪙 Dracmas Depositados", value=f"{data['total_dracmas_depositados']} Ð", inline=True)
        embed.set_footer(text=f"Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")

        await interaction.response.send_message("📊 Resumo gerado!", ephemeral=True)
        canal_posts = bot.get_channel(CANAL_POSTS_ID) or await bot.fetch_channel(CANAL_POSTS_ID)
        await canal_posts.send(embed=embed)


# ── Panel embed ───────────────────────────────────────────────────────────────

def make_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🍺 Gerenciamento do Bar — GTA RP",
        description=(
            "Use os botões abaixo para gerenciar o bar.\n\n"
            "**📦 Adicionar Estoque** — Registra itens no estoque\n"
            "**💰 Registrar Venda** — Registra venda com foto obrigatória do baú\n"
            "**📊 Ver Resumo** — Exibe estoque e totais acumulados\n\n"
            "🍹 **Combos** (10 Ð/unid): Aurora, Delfos, Estradeiro, Estradeiro Verde, Sunset, Midnight\n"
            "🧸 **Pelúcias** (250 Ð/unid): Aegis, Raposo"
        ),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Bar Bot • GTA RP")
    return embed


# ── Events ────────────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user} (ID: {bot.user.id})")
    print(f"🔍 Servidores: {[g.name for g in bot.guilds]}")

    bot.add_view(PainelView())

    try:
        canal = await bot.fetch_channel(CANAL_PAINEL_ID)
    except discord.NotFound:
        print(f"❌ Canal do painel {CANAL_PAINEL_ID} não encontrado.")
        return
    except discord.Forbidden:
        print(f"❌ Sem permissão para acessar o canal {CANAL_PAINEL_ID}.")
        return
    except Exception as e:
        print(f"❌ Erro ao buscar canal do painel: {e}")
        return

    print(f"✅ Canal do painel: #{canal.name}")

    embed    = make_panel_embed()
    view     = PainelView()
    panel_id = load_panel_id()

    if panel_id:
        try:
            msg = await canal.fetch_message(panel_id)
            await msg.edit(embed=embed, view=view)
            print(f"♻️  Painel atualizado (msg ID: {panel_id})")
            return
        except discord.NotFound:
            print("⚠️  Mensagem do painel não encontrada, criando nova...")

    try:
        msg = await canal.send(embed=embed, view=view)
        save_panel_id(msg.id)
        print(f"📌 Painel criado (msg ID: {msg.id})")
    except discord.Forbidden:
        print(f"❌ Sem permissão para enviar no canal #{canal.name}.")
    except Exception as e:
        print(f"❌ Erro ao criar painel: {e}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    sale = pending_sales.get(message.author.id)

    if sale is None or message.channel.id != sale["channel_id"]:
        await bot.process_commands(message)
        return

    image = next(
        (a for a in message.attachments if a.content_type and a.content_type.startswith("image/")),
        None,
    )

    if image is None:
        await message.reply(
            "❌ Nenhuma imagem detectada. Envie a **foto do baú** (Ctrl+V para colar).",
            delete_after=10,
        )
        return

    item      = sale["item"]
    quantidade = sale["quantidade"]
    dracmas   = sale["dracmas"]
    now       = datetime.now()

    # Upload to imgbb and delete photo concurrently
    async def _delete():
        try:
            await message.delete()
        except discord.Forbidden:
            pass

    imgbb_url, _ = await asyncio.gather(imgbb_upload(image.url), _delete())

    data = load_data()
    data["estoque"][item] = max(0, data["estoque"].get(item, 0) - quantidade)
    data["total_dracmas_depositados"] += dracmas
    data["historico"].append({
        "usuario":    sale["display_name"],
        "usuario_id": message.author.id,
        "item":       item,
        "quantidade": quantidade,
        "dracmas":    dracmas,
        "data":       now.isoformat(),
        "foto_url":   imgbb_url,
    })
    save_data(data)
    del pending_sales[message.author.id]

    tipo = "Pelúcia" if item in PELUCIAS else "Combo"
    embed = discord.Embed(title="✅ Venda Registrada!", color=discord.Color.green())
    embed.add_field(name="👤 Vendedor",            value=sale["mention"],                    inline=True)
    embed.add_field(name="🛍️ Item",               value=f"{EMOJI[item]} {item} ({tipo})",  inline=True)
    embed.add_field(name="📦 Quantidade",          value=str(quantidade),                   inline=True)
    embed.add_field(name="🪙 Dracmas Depositados", value=f"{dracmas} Ð",                    inline=True)
    embed.add_field(name="📦 Estoque Restante",    value=str(data["estoque"][item]),         inline=True)
    embed.set_image(url=imgbb_url)
    embed.set_footer(text=now.strftime("%d/%m/%Y %H:%M"))

    canal_posts = bot.get_channel(CANAL_POSTS_ID) or await bot.fetch_channel(CANAL_POSTS_ID)
    payload = {
        "timestamp":        now.strftime("%d/%m/%Y %H:%M"),
        "tipo":             "Venda",
        "usuario":          sale["display_name"],
        "item":             item,
        "quantidade":       quantidade,
        "dracmas":          dracmas,
        "foto":             imgbb_url,
        "estoque_restante": data["estoque"][item],
    }
    await asyncio.gather(
        canal_posts.send(embed=embed),
        sheets_append(payload),
    )


bot.run(TOKEN)
