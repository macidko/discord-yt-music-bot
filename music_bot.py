import nextcord
from nextcord.ext import commands
import yt_dlp
from nextcord import FFmpegPCMAudio, Embed
import asyncio
import sys
import os

intents = nextcord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Global şarkı kuyruğu (guild bazlı)
queues = {}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
    'stderr': sys.stderr
}

def get_audio_info(query):
    ydl_opts = {
        'format': 'bestaudio[ext=webm]/bestaudio',
        'quiet': True,
        'default_search': 'ytsearch'
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        return info

def play_next(guild_id, voice_client):
    queue = queues.get(guild_id, [])
    if queue:
        next_query = queue.pop(0)
        try:
            info = get_audio_info(next_query)
            stream_url = info['url']
            audio_source = FFmpegPCMAudio(stream_url, **ffmpeg_options)
            def after_playing(error):
                print("--- after_playing callback ---")
                print(f"Error: {error}")
                print(f"voice_client.is_playing(): {voice_client.is_playing()}")
                print(f"voice_client.is_paused(): {voice_client.is_paused()}")
                print(f"voice_client.is_connected(): {voice_client.is_connected()}")
                if error:
                    print(f"Şarkı oynatılırken hata oluştu: {error}")
                else:
                    print("Şarkı başarıyla bitti.")
                play_next(guild_id, voice_client)
            voice_client.play(audio_source, after=after_playing)
            print(f"Şarkı başlatıldı: {next_query}")
            # Şarkı başlarken embed mesajı gönder
            channel = voice_client.channel
            title = info.get('title', 'Bilinmiyor')
            webpage_url = info.get('webpage_url', next_query)
            thumbnail = info.get('thumbnail')
            embed = Embed(title="Şu an çalıyor", description=f"[{title}]({webpage_url})", color=0x1DB954)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            # Kanalda ilk bulduğu metin kanalına mesaj at
            text_channel = None
            for tc in channel.guild.text_channels:
                if tc.permissions_for(channel.guild.me).send_messages:
                    text_channel = tc
                    break
            if text_channel:
                asyncio.create_task(text_channel.send(embed=embed))
        except Exception as e:
            print(f"Kuyruktaki şarkı oynatılamadı: {e}")
            play_next(guild_id, voice_client)
    else:
        print("Kuyruk boş, çalacak şarkı yok.")

@bot.event
async def on_ready():
    print(f"Bot giriş yaptı: {bot.user}")

@bot.slash_command(name="play", description="Bir şarkı çal")
async def play(interaction: nextcord.Interaction, query: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        embed = Embed(title="Uyarı", description="Lütfen önce bir ses kanalına katıl.", color=0xE74C3C)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    channel = interaction.user.voice.channel
    guild_id = interaction.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    if interaction.guild.voice_client:
        voice_client = interaction.guild.voice_client
        if voice_client.channel != channel:
            await voice_client.move_to(channel)
    else:
        voice_client = await channel.connect()

    await interaction.response.defer()
    try:
        info = get_audio_info(query)
        # Playlist tespiti
        if isinstance(info, dict) and 'entries' in info and isinstance(info['entries'], list):
            entries = []
            for entry in info['entries']:
                if not entry:
                    continue
                # Sadece oynatılabilir videoları ekle
                if entry.get('webpage_url') and entry.get('title'):
                    entries.append(entry['webpage_url'])
            if not entries:
                embed = Embed(title="Playlist Hatası", description="Playlistte oynatılabilir şarkı bulunamadı.", color=0xE74C3C)
                await interaction.edit_original_message(content=None, embed=embed)
                return
            queues[guild_id].extend(entries)
            # Eğer bot çalmıyorsa kuyruğun ilkini başlat
            if not voice_client.is_playing():
                play_next(guild_id, voice_client)
            embed = Embed(title="Playlist Kuyruğa Eklendi", description=f"{len(entries)} şarkı kuyruğa eklendi.", color=0x9B59B6)
            await interaction.edit_original_message(content=None, embed=embed)
            return
        # Tek şarkı veya arama ise
        if voice_client.is_playing():
            queues[guild_id].append(query)
            embed = Embed(title="Kuyruğa Eklendi", description=f"Şarkı kuyruğa eklendi: `{query}`", color=0xF1C40F)
            await interaction.edit_original_message(content=None, embed=embed)
            return
        stream_url = info['url']
        audio_source = FFmpegPCMAudio(stream_url, **ffmpeg_options)
        def after_playing(error):
            print("--- after_playing callback ---")
            print(f"Error: {error}")
            print(f"voice_client.is_playing(): {voice_client.is_playing()}")
            print(f"voice_client.is_paused(): {voice_client.is_paused()}")
            print(f"voice_client.is_connected(): {voice_client.is_connected()}")
            if error:
                print(f"Şarkı oynatılırken hata oluştu: {error}")
            else:
                print("Şarkı başarıyla bitti.")
            play_next(guild_id, voice_client)
        voice_client.play(audio_source, after=after_playing)
        title = info.get('title', 'Bilinmiyor')
        webpage_url = info.get('webpage_url', query)
        thumbnail = info.get('thumbnail')
        embed = Embed(title="Şu an çalıyor", description=f"[{title}]({webpage_url})", color=0x1DB954)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        await interaction.edit_original_message(content=None, embed=embed)
    except Exception as e:
        hata_mesaji = str(e)
        if "Video unavailable" in hata_mesaji or "This video is not available" in hata_mesaji:
            embed = Embed(
                title="Şarkı Bulunamadı",
                description="Bu şarkı YouTube'da mevcut değil veya erişilemiyor. Lütfen başka bir şarkı deneyin.",
                color=0xE74C3C
            )
        elif "entries" in hata_mesaji and "None" in hata_mesaji:
            embed = Embed(
                title="Playlist Hatası",
                description="Playlistte oynatılabilir şarkı bulunamadı.",
                color=0xE74C3C
            )
        else:
            embed = Embed(title="Hata", description=f"Şarkı başlatılamadı: {e}", color=0xE74C3C)
        await interaction.edit_original_message(content=None, embed=embed)

@bot.slash_command(name="pause", description="Şarkıyı geçici olarak duraklatır")
async def pause(interaction: nextcord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        embed = Embed(title="Duraklatıldı", description="Şarkı duraklatıldı.", color=0xF1C40F)
        await interaction.response.send_message(embed=embed)
    else:
        embed = Embed(title="Duraklatılamadı", description="Çalan bir şarkı yok.", color=0xE74C3C)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="resume", description="Duraklatılan şarkıyı devam ettirir")
async def resume(interaction: nextcord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        embed = Embed(title="Devam Ediyor", description="Şarkı devam ediyor.", color=0x2ECC71)
        await interaction.response.send_message(embed=embed)
    else:
        embed = Embed(title="Devam Ettirilemedi", description="Duraklatılmış bir şarkı yok.", color=0xE74C3C)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="skip", description="Sıradaki şarkıya geçer")
async def skip(interaction: nextcord.Interaction):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        embed = Embed(title="Atlandı", description="Şarkı atlandı, sıradaki çalıyor.", color=0x3498DB)
        await interaction.response.send_message(embed=embed)
    else:
        embed = Embed(title="Atlanamadı", description="Çalan bir şarkı yok.", color=0xE74C3C)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.slash_command(name="stop", description="Çalmayı durdurur ve kuyruğu temizler")
async def stop(interaction: nextcord.Interaction):
    voice_client = interaction.guild.voice_client
    guild_id = interaction.guild.id
    if voice_client:
        voice_client.stop()
        queues[guild_id] = []
        embed = Embed(title="Durduruldu", description="Çalma durduruldu ve kuyruk temizlendi.", color=0xE67E22)
        await interaction.response.send_message(embed=embed)
    else:
        embed = Embed(title="Durdurulamadı", description="Bot şu anda bir ses kanalında değil.", color=0xE74C3C)
        await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN")) # TOKEN BURAYA YAZILACAK