import os
import time
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread

# 1. Flask Web Sunucusu (Render ve Koyeb'in botu kapatmaması için Keep-Alive mekanizması)
app = Flask('')

@app.route('/')
def home():
    return "AtlasBot aktif ve çalışıyor!"

def run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Bot Ayarları ve İzinler
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# Hafıza Verileri (Küfür sayacı, spam takibi, engelliler, taranan kanallar)
kufur_sayaci = {}      # {(guild_id, user_id, tarih): sayi}
engelliler = {}        # {guild_id: set(user_id)}
spam_takip = {}        # {(guild_id, user_id): [zamanlar]}
aktif_kanallar = {}    # {guild_id: set(channel_id)}

# Yasaklı Kelimeler Listesi
KUFURLER = ["küfür1", "küfür2", "aq", "amk", "sg", "oç", "piç", "yavşak", "mal", "salak", "gerizekalı"]

# İstediğin Rollerin Listesi (İsim ve Renkleri ile birlikte)
SUNUCU_ROLLERI = [
    ("Admin", discord.Color.red()),
    ("Mod", discord.Color.blue()),
    ("Alt Mod", discord.Color.green()),
    ("Rehber Mod", discord.Color.purple()),
    ("YouTuber / Yayıncı", discord.Color.dark_red()),
    ("Geliştirici / Yazılımcı", discord.Color.blurple()),
    ("Minecraft Oyuncusu", discord.Color.teal()),
    ("Botlar", discord.Color.light_grey()),
    ("VIP / Sponsor", discord.Color.magenta()),
    ("Üye", discord.Color.default()),
    ("Kayıtsız", discord.Color.dark_grey())
]

# Sunucu Şablonu (Kategoriler ve Kanallar)
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

# Log Gönderme Yardımcı Fonksiyonu
async def log_gonder(guild: discord.Guild, baslik: str, aciklama: str, renk: discord.Color = discord.Color.blue()):
    # Önce mod-log, bulamazsa log kanalını arar
    log_kanali = discord.utils.get(guild.text_channels, name="📜-mod-log")
    if not log_kanali:
        log_kanali = discord.utils.get(guild.text_channels, name="mod-log")
    if not log_kanali:
        log_kanali = discord.utils.get(guild.text_channels, name="log")
    
    if log_kanali:
        embed = discord.Embed(title=baslik, description=aciklama, color=renk, timestamp=discord.utils.utcnow())
        try:
            await log_kanali.send(embed=embed)
        except Exception:
            pass

# Yetki Kontrolü: Yönetici veya sunucuda "Admin" / "Mod" rolü olanlar komut çalıştırabilir
def yonetici_veya_yetkili():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator:
            return True
        izinli_roller = ["Admin", "Mod"]
        if any(rol.name in izinli_roller for rol in interaction.user.roles):
            return True
        raise app_commands.CheckFailure("Bu komutu kullanmak için Admin veya Mod rolüne sahip olmalısın!")
    return app.check(predicate)

@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı! Kanallar otomatik taranıyor...")
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

# Silinen Mesajları Loglama
@bot.event
async def on_message_delete(message):
    if message.author.bot or not message.guild:
        return
    log_icerik = f"**Kanal:** {message.channel.mention}\n**Yazan:** {message.author.mention}\n**Silinen Mesaj:** {message.content or '[Medya/Ekran Görüntüsü]'}"
    await log_gonder(message.guild, "🗑️ Mesaj Silindi", log_icerik, discord.Color.light_gray())

# Mesaj Kontrolü (Engel, Küfür ve Spam Koruması)
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    if guild_id not in aktif_kanallar:
        aktif_kanallar[guild_id] = {ch.id for ch in message.guild.text_channels}
    if message.channel.id not in aktif_kanallar[guild_id]:
        return

    if guild_id in engelliler and user_id in engelliler[guild_id]:
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        return

    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    # Spam Kontrolü
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

    # Küfür Kontrolü
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
                await message.author.timeout(timedelta(hours=1), reason="Günde 5 kez küfür sınırı aşıldı.")
                await message.channel.send(f"🔇 {message.author.mention} bugün **5 kez** küfür ettiği için 1 saat susturuldu!")
                await log_gonder(message.guild, "🔇 Otomatik Susturma (Timeout)", f"**Kullanıcı:** {message.author.mention}\n**Sebep:** Günde 5 kez küfür sınırı aşıldı.", discord.Color.orange())
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
        embed.add_field(name="/a sunucu-kur", value="Rolleri, kategorileri ve kanalları otomatik kurar.", inline=False)
        embed.add_field(name="/a otomatik-kanal-tarama", value="Sunucudaki tüm kanalları tarar ve korumaya bağlar.", inline=False)
        embed.add_field(name="/a engelle [kullanıcı]", value="Kullanıcının mesaj yazmasını engeller.", inline=False)
        embed.add_field(name="/a engelikaldir [kullanıcı]", value="Kullanıcının engelini kaldırır.", inline=False)
        embed.add_field(name="/a kanal-olustur [isim]", value="Yeni bir metin kanalı oluşturur.", inline=False)
        embed.add_field(name="/a temizle [miktar]", value="Belirtilen sayıda mesajı siler ve log tutar.", inline=False)
        embed.add_field(name="/a kick / ban", value="Kullanıcıyı atar/yasaklar ve log tutar.", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sunucu-kur", description="İstediğin rolleri, kategori ve kanalları otomatik oluşturur.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sunucu_kur(self, interaction: discord.Interaction):
        # 3 saniye aşımını önlemek için defer kullanıyoruz
        await interaction.response.defer(thinking=True)
        guild = interaction.guild

        # 1. İstediğin Rolleri Oluşturma
        for rol_adi, renk in SUNUCU_ROLLERI:
            if not discord.utils.get(guild.roles, name=rol_adi):
                try:
                    await guild.create_role(name=rol_adi, color=renk)
                except Exception:
                    pass

        # 2. İstatistik Ses Kanalları
        try:
            await guild.create_voice_channel(f"👥 Toplam Üye: {guild.member_count}")
            bot_sayisi = sum(1 for m in guild.members if m.bot)
            await guild.create_voice_channel(f"🤖 Botlar: {bot_sayisi}")
        except Exception:
            pass

        # 3. Kategori ve Kanalları Oluşturma
        for kategori_adi, kanallar in SUNUCU_SABLONU:
            kategori = await guild.create_category(kategori_adi)
            for tur, kanal_adi in kanallar:
                if tur == "text":
                    yeni_kanal = await guild.create_text_channel(kanal_adi, category=kategori)
                    aktif_kanallar.setdefault(guild.id, set()).add(yeni_kanal.id)
                elif tur == "voice":
                    await guild.create_voice_channel(kanal_adi, category=kategori)

        await log_gonder(guild, "🛠️ Sunucu Kuruldu", f"Tüm roller, kategoriler ve kanallar {interaction.user.mention} tarafından başarıyla kuruldu.", discord.Color.green())
        await interaction.followup.send("✅ **Kurulum tamamlandı!** Roller, tüm kategori/kanallar oluşturuldu ve log sistemi aktif edildi.")

    @app_commands.command(name="otomatik-kanal-tarama", description="Sunucudaki tüm kanalları sessizce tarar ve yönetime bağlar.")
    @app_commands.checks.has_permissions(administrator=True)
    async def otomatik_kanal_tarama(self, interaction: discord.Interaction):
        guild = interaction.guild
        tarananlar = set()
        for kanal in guild.text_channels:
            tarananlar.add(kanal.id)
        aktif_kanallar[guild.id] = tarananlar
        await interaction.response.send_message(
            f"✅ Tarama tamamlandı! Toplam **{len(tarananlar)}** metin kanalı AtlasBot korumasına bağlandı.",
            ephemeral=True
        )

    @app_commands.command(name="engelle", description="Seçilen kullanıcının sunucuda mesaj yazmasını tamamen engeller.")
    @yonetici_veya_yetkili()
    async def engelle(self, interaction: discord.Interaction, kullanici: discord.Member):
        if kullanici.guild_permissions.administrator:
            await interaction.response.send_message("❌ Yöneticileri engelleyemezsin.", ephemeral=True)
            return
        engelliler.setdefault(interaction.guild.id, set()).add(kullanici.id)
        await log_gonder(interaction.guild, "🚫 Kullanıcı Engellendi", f"**Hedef:** {kullanici.mention}\n**Yetkili:** {interaction.user.mention}", discord.Color.red())
        await interaction.response.send_message(f"🚫 **{kullanici.display_name}** engellenmiştir. Artık sunucudaki hiçbir kanala mesaj yazamayacak.")

    @app_commands.command(name="engelikaldir", description="Engellenen kullanıcının mesaj engelini kaldırır.")
    @yonetici_veya_yetkili()
    async def engeli_kaldir(self, interaction: discord.Interaction, kullanici: discord.Member):
        guild_engelleri = engelliler.get(interaction.guild.id, set())
        if kullanici.id in guild_engelleri:
            guild_engelleri.remove(kullanici.id)
            await log_gonder(interaction.guild, "✅ Engel Kaldırıldı", f"**Hedef:** {kullanici.mention}\n**Yetkili:** {interaction.user.mention}", discord.Color.green())
            await interaction.response.send_message(f"✅ **{kullanici.display_name}** kullanıcısının engeli kaldırıldı.")
        else:
            await interaction.response.send_message(f"ℹ️ **{kullanici.display_name}** zaten engelli değil.", ephemeral=True)

    @app_commands.command(name="kanal-olustur", description="Yeni bir metin kanalı oluşturur.")
    @yonetici_veya_yetkili()
    async def kanal_olustur(self, interaction: discord.Interaction, isim: str):
        yeni_kanal = await interaction.guild.create_text_channel(isim)
        aktif_kanallar.setdefault(interaction.guild.id, set()).add(yeni_kanal.id)
        await log_gonder(interaction.guild, " Kanal Oluşturuldu", f"**Kanal:** {yeni_kanal.mention}\n**Yetkili:** {interaction.user.mention}", discord.Color.blue())
        await interaction.response.send_message(f"✅ {yeni_kanal.mention} kanalı oluşturuldu ve korumaya bağlandı!")

    @app_commands.command(name="temizle", description="Belirtilen sayıda mesajı siler.")
    @yonetici_veya_yetkili()
    async def temizle(self, interaction: discord.Interaction, miktar: int):
        await interaction.response.defer(ephemeral=True)
        silinen = await interaction.channel.purge(limit=miktar)
        await log_gonder(interaction.guild, "🧹 Mesajlar Temizlendi", f"**Kanal:** {interaction.channel.mention}\n**Silinen Miktar:** {len(silinen)}\n**Yetkili:** {interaction.user.mention}", discord.Color.orange())
        await interaction.followup.send(f"🧹 **{len(silinen)}** mesaj temizlendi.", ephemeral=True)

    @app_commands.command(name="kick", description="Kullanıcıyı sunucudan atar.")
    @yonetici_veya_yetkili()
    async def kick(self, interaction: discord.Interaction, kullanici: discord.Member, sebep: str = "Sebep belirtilmedi"):
        await kullanici.kick(reason=sebep)
        await log_gonder(interaction.guild, "👢 Kullanıcı Atıldı (Kick)", f"**Hedef:** {kullanici.mention}\n**Sebep:** {sebep}\n**Yetkili:** {interaction.user.mention}", discord.Color.red())
        await interaction.response.send_message(f"👢 **{kullanici.display_name}** sunucudan atıldı. (Sebep: {sebep})")

    @app_commands.command(name="ban", description="Kullanıcıyı sunucudan yasaklar.")
    @yonetici_veya_yetkili()
    async def ban(self, interaction: discord.Interaction, kullanici: discord.Member, sebep: str = "Sebep belirtilmedi"):
        await kullanici.ban(reason=sebep)
        await log_gonder(interaction.guild, "🔨 Kullanıcı Yasaklandı (Ban)", f"**Hedef:** {kullanici.mention}\n**Sebep:** {sebep}\n**Yetkili:** {interaction.user.mention}", discord.Color.dark_red())
        await interaction.response.send_message(f"🔨 **{kullanici.display_name}** sunucudan yasaklandı. (Sebep: {sebep})")

bot.tree.add_command(AtlasKomutlari())

# Flask Sunucusunu Başlat ve Botu Çalıştır
keep_alive()
TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("HATA: DISCORD_TOKEN bulunamadı!")
               
