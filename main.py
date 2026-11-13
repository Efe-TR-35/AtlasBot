import os
import time
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands

# Bot Ayarları ve İzinler
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Hafıza Verileri (Küfür sayacı, spam takibi, engelliler, taranan kanallar)
kufur_sayaci = {}      # {(guild_id, user_id, tarih): sayi}
engelliler = {}        # {guild_id: set(user_id)}
spam_takip = {}        # {(guild_id, user_id): [zamanlar]}
aktif_kanallar = {}    # {guild_id: set(channel_id)}

# Yasaklı Kelimeler Listesi (İstediğin kelimeleri buraya ekleyebilirsin)
KUFURLER = ["küfür1", "küfür2", "aq", "amk", "sg", "oç", "piç", "yavşak", "mal", "salak", "gerizekalı"]

# Ekran görüntüsündeki sunucu şablonu (Kategoriler ve Kanallar)
SUNUCU_SABLONU = [
    ("📌 BİLGİLENDİRME", [
        ("text", "📌-kurallar"),
        ("text", "📣-duyurular"),
        ("text", "📥-gelen-giden")
    ]),
    ("🎬 İÇERİK & YAYIN", [
        ("text", "📢-video-duyuru"),
        ("text", "📺-canli-yayin"),
        ("text", "💡-video-fikirleri"),
        ("text", "💬-chat-ve-fan")
    ]),
    ("💬 GENEL TOPLULUK", [
        ("text", "💬-sohbet"),
        ("text", "🤖-bot-komut"),
        ("text", "🖼️-gorsel-paylasim")
    ]),
    ("🛡️ YÖNETİM", [
        ("text", "🗣️-yetkili-chat"),
        ("text", "📜-mod-log"),
        ("text", "🤖-albe-bot-log")
    ]),
    ("🔊 SES KANALLARI", [
        ("voice", "🎬 Yayın Ekibi"),
        ("voice", "🔊 Sohbet 1"),
        ("voice", "🔒 Yetkili Odası"),
        ("voice", "💤 AFK")
    ]),
    ("🎟️ DESTEK", [
        ("text", "📜-destek-kurallari"),
        ("text", "🎟️-destek-talebi")
    ]),
    ("🎭 ROL SEÇİMİ", [
        ("text", "📋-rol-bilgi")
    ]),
    ("Kayıt", [
        ("text", "kayit-sorulari")
    ])
]

@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı! Kanallar otomatik taranıyor...")
    # Açılışta tüm sunuculardaki kanalları sessizce hafızaya alır
    for guild in bot.guilds:
        aktif_kanallar[guild.id] = {ch.id for ch in guild.text_channels}
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)} komut grubu senkronize edildi.")
    except Exception as e:
        print(f"Senkronizasyon hatası: {e}")

# Geliş - Gidiş Kontrolü
@bot.event
async def on_member_join(member):
    kanal = discord.utils.find(lambda c: "gelen-giden" in c.name, member.guild.text_channels)
    if kanal:
        await kanal.send(f"📥 **Hoş geldin {member.mention}!** Sunucumuza katıldın. Seninle birlikte **{member.guild.member_count}** kişiyiz!")

@bot.event
async def on_member_remove(member):
    kanal = discord.utils.find(lambda c: "gelen-giden" in c.name, member.guild.text_channels)
    if kanal:
        await kanal.send(f"📤 **{member.name}** aramızdan ayrıldı. Kalan üye: **{member.guild.member_count}**")

# Mesaj Kontrolü (Engel, Küfür ve Spam Koruması)
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    # Kanal taranmamışsa otomatik listeye dahil et
    if guild_id not in aktif_kanallar:
        aktif_kanallar[guild_id] = {ch.id for ch in message.guild.text_channels}
    if message.channel.id not in aktif_kanallar[guild_id]:
        return

    # 1. Engel Kontrolü (/a engelle ile engellenenler hiçbir yere yazamaz)
    if guild_id in engelliler and user_id in engelliler[guild_id]:
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        return

    # Yöneticiler küfür/spam filtresine takılmasın istiyorsan bu satırı bırakabilirsin
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    # 2. Spam Kontrolü (5 saniyede 5 mesaj atarsa siler ve uyarır)
    simdi = time.time()
    anahtar_spam = (guild_id, user_id)
    spam_takip.setdefault(anahtar_spam, [])
    spam_takip[anahtar_spam] = [t for t in spam_takip[anahtar_spam] if simdi - t < 5]
    spam_takip[anahtar_spam].append(simdi)

    if len(spam_takip[anahtar_spam]) >= 5:
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, spam yapmayı durdur!", delete_after=4)
        except discord.Forbidden:
            pass
        return

    # 3. Küfür Kontrolü ve Günde 5 Küfürde Susturma
    icerik = message.content.lower()
    if any(kelime in icerik.split() or kelime in icerik for kelime in KUFURLER):
        try:
            await message.delete()
        except discord.Forbidden:
            pass

        bugun = datetime.now().strftime("%Y-%m-%d")
        anahtar_kufur = (guild_id, user_id, bugun)
        kufur_sayaci[anahtar_kufur] = kufur_sayaci.get(anahtar_kufur, 0) + 1
        sayi = kufur_sayaci[anahtar_kufur]

        if sayi >= 5:
            try:
                # 1 saatlik susturma (Timeout)
                await message.author.timeout(timedelta(hours=1), reason="Günde 5 kez küfür sınırı aşıldı.")
                await message.channel.send(f"🔇 {message.author.mention} bugün **5 kez** küfür ettiği için 1 saat susturuldu!")
                kufur_sayaci[anahtar_kufur] = 0
            except discord.Forbidden:
                await message.channel.send(f"⚠️ {message.author.mention} 5 küfür sınırını aştı ama yetkim yetmediği için susturamadım.")
        else:
            await message.channel.send(f"🚫 {message.author.mention}, küfür yasak! Mesajın silindi. (Günlük uyarı: **{sayi}/5**)", delete_after=5)
        return

    await bot.process_commands(message)

# --- /a KOMUT GRUBU ---
class AtlasKomutlari(app_commands.Group):
    def __init__(self):
        super().__init__(name="a", description="AtlasBot yönetim ve koruma komutları")

    @app_commands.command(name="help", description="AtlasBot'un tüm komutlarını gösterir.")
    async def help_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 AtlasBot Komut Listesi",
            description="Tüm komutlar `/a` ön eki ile çalışır:",
            color=discord.Color.blue()
        )
        embed.add_field(name="/a sunucu-kur", value="Ekran görüntüsündeki tüm kategorileri ve kanalları otomatik kurar.", inline=False)
        embed.add_field(name="/a otomatik-kanal-tarama", value="Sunucudaki tüm kanalları sessizce tarar ve koruma sistemine bağlar.", inline=False)
        embed.add_field(name="/a engelle [kullanıcı]", value="Kullanıcının sunucuda mesaj yazmasını tamamen engeller.", inline=False)
        embed.add_field(name="/a engelikaldir [kullanıcı]", value="Engellenen kullanıcının mesaj engelini kaldırır.", inline=False)
        embed.add_field(name="/a kanal-olustur [isim]", value="Bulunduğun yerden yeni bir metin kanalı oluşturur.", inline=False)
        embed.add_field(name="/a temizle [miktar]", value="Belirtilen sayıda mesajı kanaldan siler.", inline=False)
        embed.add_field(name="/a kick [kullanıcı] / ban [kullanıcı]", value="Kullanıcıyı sunucudan atar veya yasaklar.", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sunucu-kur", description="Şablondaki tüm kategori ve kanalları otomatik oluşturur.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sunucu_kur(self, interaction: discord.Interaction):
        await interaction.response.send_message("⚙️ **Sunucu kurulumu başlatıldı!** Kanallar oluşturuluyor, lütfen bekleyin...")
        guild = interaction.guild

        # İstatistik kanalları (Üstteki kilitli ses kanalları)
        try:
            await guild.create_voice_channel(f"👥 Toplam Üye: {guild.member_count}")
            bot_sayisi = sum(1 for m in guild.members if m.bot)
            await guild.create_voice_channel(f"🤖 Botlar: {bot_sayisi}")
        except Exception:
            pass

        for kategori_adi, kanallar in SUNUCU_SABLONU:
            kategori = await guild.create_category(kategori_adi)
            for tur, kanal_adi in kanallar:
                if tur == "text":
                    yeni_kanal = await guild.create_text_channel(kanal_adi, category=kategori)
                    aktif_kanallar.setdefault(guild.id, set()).add(yeni_kanal.id)
                elif tur == "voice":
                    await guild.create_voice_channel(kanal_adi, category=kategori)

        await interaction.followup.send("✅ **Kurulum tamamlandı!** Tüm kategori ve kanallar oluşturuldu ve korumaya alındı.")

    @app_commands.command(name="otomatik-kanal-tarama", description="Sunucudaki tüm kanalları sessizce tarar ve yönetime bağlar.")
    @app_commands.checks.has_permissions(administrator=True)
    async def otomatik_kanal_tarama(self, interaction: discord.Interaction):
        guild = interaction.guild
        tarananlar = set()
        for kanal in guild.text_channels:
            tarananlar.add(kanal.id)
        aktif_kanallar[guild.id] = tarananlar
        # Sadece komutu yazan kişiye (ephemeral=True) görünür, kanallara mesaj atmaz
        await interaction.response.send_message(
            f"✅ Tarama tamamlandı! Toplam **{len(tarananlar)}** metin kanalı sessizce AtlasBot korumasına (küfür/spam/engel) bağlandı.",
            ephemeral=True
        )

    @app_commands.command(name="engelle", description="Seçilen kullanıcının sunucuda mesaj yazmasını tamamen engeller.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def engelle(self, interaction: discord.Interaction, kullanici: discord.Member):
        if kullanici.guild_permissions.administrator:
            await interaction.response.send_message("❌ Yöneticileri engelleyemezsin.", ephemeral=True)
            return
        engelliler.setdefault(interaction.guild.id, set()).add(kullanici.id)
        await interaction.response.send_message(f"🚫 **{kullanici.display_name}** engellenmiştir. Artık sunucudaki hiçbir kanala mesaj yazamayacak.")

    @app_commands.command(name="engelikaldir", description="Engellenen kullanıcının mesaj engelini kaldırır.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def engeli_kaldir(self, interaction: discord.Interaction, kullanici: discord.Member):
        guild_engelleri = engelliler.get(interaction.guild.id, set())
        if kullanici.id in guild_engelleri:
            guild_engelleri.remove(kullanici.id)
            await interaction.response.send_message(f"✅ **{kullanici.display_name}** kullanıcısının engeli kaldırıldı, tekrar mesaj yazabilir.")
        else:
            await interaction.response.send_message(f"ℹ️ **{kullanici.display_name}** zaten engelli değil.", ephemeral=True)

    @app_commands.command(name="kanal-olustur", description="Yeni bir metin kanalı oluşturur.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def kanal_olustur(self, interaction: discord.Interaction, isim: str):
        yeni_kanal = await interaction.guild.create_text_channel(isim)
        aktif_kanallar.setdefault(interaction.guild.id, set()).add(yeni_kanal.id)
        await interaction.response.send_message(f"✅ {yeni_kanal.mention} kanalı oluşturuldu ve korumaya bağlandı!")

    @app_commands.command(name="temizle", description="Belirtilen sayıda mesajı siler.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def temizle(self, interaction: discord.Interaction, miktar: int):
        await interaction.response.defer(ephemeral=True)
        silinen = await interaction.channel.purge(limit=miktar)
        await interaction.followup.send(f"🧹 **{len(silinen)}** mesaj temizlendi.", ephemeral=True)

    @app_commands.command(name="kick", description="Kullanıcıyı sunucudan atar.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, kullanici: discord.Member, sebep: str = "Sebep belirtilmedi"):
        await kullanici.kick(reason=sebep)
        await interaction.response.send_message(f"👢 **{kullanici.display_name}** sunucudan atıldı. (Sebep: {sebep})")

    @app_commands.command(name="ban", description="Kullanıcıyı sunucudan yasaklar.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, kullanici: discord.Member, sebep: str = "Sebep belirtilmedi"):
        await kullanici.ban(reason=sebep)
        await interaction.response.send_message(f"🔨 **{kullanici.display_name}** sunucudan yasaklandı. (Sebep: {sebep})")

bot.tree.add_command(AtlasKomutlari())

# Botu Başlat
TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("HATA: Replit Secrets kısmına DISCORD_TOKEN eklenmemiş!")
import os
from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "AtlasBot aktif!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

keep_alive()
