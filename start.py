import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import requests
import time
import lyricsgenius

# --------- Toggles ----------
USE_LOCAL_DEEPSEEK = True         # True = use local DeepSeek via Ollama, False = use OpenAI online
USE_GENIUS = True                 # True = use Genius for lyrics, False = skip lyrics
USE_LASTFM = True                 # True = use Last.fm for additional info, False = skip
SHOW_LLM_PROMPT_DEBUG = False      # True = show the full prompt with all fields, False = skip printing it

# ---------- Spotify API credentials ----------
CLIENT_ID = 'xxx'
CLIENT_SECRET = 'xxx'
PLAYLIST_ID = '1mZELHyKrXNyLOumaDiQwh'

# ---------- Genius API credentials ----------
GENIUS_TOKEN = 'xxx'

# ---------- Last.fm API credentials ----------
LASTFM_API_KEY = 'xxx'

# ---------- Local DeepSeek/Ollama ----------
OLLAMA_URL = 'http://localhost:11434/api/generate'
MODEL_LOCAL = 'deepseek-coder-v2'

# ---------- OpenAI Online (GPT-3.5/4/4o) ----------
OPENAI_API_URL = 'https://api.openai.com/v1/chat/completions'
OPENAI_API_KEY = 'xxx'
MODEL_ONLINE = 'gpt-4o'

# ---------- Prompt templates ----------
with open('prompt.txt', encoding='utf-8') as f:
    PROMPT_TEMPLATE = f.read()
with open('system_prompt.txt', encoding='utf-8') as f:
    SYSTEM_PROMPT = f.read()

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
)

genius = lyricsgenius.Genius(GENIUS_TOKEN, skip_non_songs=True, verbose=False, remove_section_headers=True)

def clean_track_name(name):
    import re
    name = re.sub(r"\(.*?\)", "", name)
    name = name.replace("- En Vivo", "")
    name = name.strip()
    return name

def get_lyrics(track_name, artist_name):
    if not USE_GENIUS:
        return ""
    cleaned_name = clean_track_name(track_name)
    song = genius.search_song(cleaned_name, artist_name)
    if song and getattr(song, "lyrics", None):
        return song.lyrics[:1000]
    song = genius.search_song(cleaned_name)
    if song and getattr(song, "lyrics", None):
        return song.lyrics[:1000]
    return ""

def get_lastfm_info(track_name, artist_name):
    if not USE_LASTFM:
        return ""
    try:
        url_track = (
            f"https://ws.audioscrobbler.com/2.0/?method=track.getInfo"
            f"&api_key={LASTFM_API_KEY}&artist={requests.utils.quote(artist_name)}"
            f"&track={requests.utils.quote(track_name)}&format=json"
        )
        resp_track = requests.get(url_track, timeout=10)
        info_track = resp_track.json().get("track", {})
        tags = [t["name"] for t in info_track.get("toptags", {}).get("tag", [])]
        wiki = info_track.get("wiki", {}).get("summary", "")
        url_artist = (
            f"https://ws.audioscrobbler.com/2.0/?method=artist.getInfo"
            f"&api_key={LASTFM_API_KEY}&artist={requests.utils.quote(artist_name)}&format=json"
        )
        resp_artist = requests.get(url_artist, timeout=10)
        info_artist = resp_artist.json().get("artist", {})
        artist_tags = [t["name"] for t in info_artist.get("tags", {}).get("tag", [])]
        bio = info_artist.get("bio", {}).get("summary", "")
        extra = ""
        if tags:
            extra += f"Last.fm track tags: {', '.join(tags)}. "
        if artist_tags:
            extra += f"Last.fm artist tags: {', '.join(artist_tags)}. "
        if wiki:
            extra += f"Track summary: {wiki[:300]}... "
        if bio:
            extra += f"Artist bio: {bio[:300]}... "
        return extra.strip()
    except Exception:
        return ""

def classify_track(
    track_name, artist_name, lyrics, album_name, release_date, artist_genres, lastfm_info, temperature=0.0
):
    prompt = PROMPT_TEMPLATE.format(
        track_name=track_name,
        artist_name=artist_name,
        album_name=album_name,
        release_date=release_date,
        artist_genres=artist_genres,
        lastfm_info=lastfm_info,
        lyrics=lyrics
    )
    # --- Print FULL prompt for debugging and transparency if toggle is active ---
    if SHOW_LLM_PROMPT_DEBUG:
        print("\n================= LLM PROMPT =================")
        print(f"Song: {track_name}")
        print(f"Artist: {artist_name}")
        print(f"Album: {album_name}")
        print(f"Release Date: {release_date}")
        print(f"Genres: {artist_genres}")
        print(f"Last.fm Info: {lastfm_info}")
        print(f"Lyrics: {lyrics[:400]}")
        print("==============================================\n")
    # ------------------------------------------------------
    if USE_LOCAL_DEEPSEEK:
        data = {
            "model": MODEL_LOCAL,
            "prompt": prompt,
            "stream": False
        }
        try:
            response = requests.post(OLLAMA_URL, json=data, timeout=120)
            if response.ok:
                answer = response.json().get('response', '').strip()
                if answer in ["Cubana", "Línea"]:
                    return answer
                return None
            else:
                return None
        except Exception:
            return None
    else:
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": MODEL_ONLINE,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 5,
            "temperature": temperature
        }
        try:
            response = requests.post(OPENAI_API_URL, headers=headers, json=data, timeout=120)
            if response.ok:
                answer = response.json()['choices'][0]['message']['content'].strip()
                if answer in ["Cubana", "Línea"]:
                    return answer
                return None
            else:
                return None
        except Exception:
            return None

# -- Fetch tracks --
tracks = []
offset = 0
limit = 100
while True:
    results = sp.playlist_items(PLAYLIST_ID, offset=offset, limit=limit)
    items = results.get('items', [])
    if not items:
        break
    tracks.extend(items)
    offset += len(items)

for idx, item in enumerate(tracks):
    track = item.get('track')
    if not track:
        continue
    name = track.get('name', 'Unknown Title')
    artist = ', '.join([a.get('name', 'Unknown Artist') for a in track.get('artists', [])])
    album = track.get('album', {}).get('name', 'Unknown Album')
    release_date = track.get('album', {}).get('release_date', 'Unknown Date')
    print(f"\n[{idx+1}] {name} - {artist}")
    # Last.fm info
    #print("  Fetching Last.fm info ...")
    lastfm_info = get_lastfm_info(name, artist)
    # Lyrics
    #print("  Fetching lyrics ...")
    lyrics = get_lyrics(name, artist)
    # Genres for first artist
    artist_id = track.get('artists', [{}])[0].get('id', None)
    artist_genres = []
    if artist_id:
        try:
            artist_info = sp.artist(artist_id)
            artist_genres = artist_info.get('genres', [])
        except Exception:
            artist_genres = []
    genres_str = ', '.join(artist_genres)
    # Klassifikation (zeigt Prompt im classify_track)
    style = classify_track(
        track_name=name,
        artist_name=artist,
        album_name=album,
        release_date=release_date,
        artist_genres=genres_str,
        lastfm_info=lastfm_info,
        lyrics=lyrics
    )
    if style not in ["Cubana", "Línea"]:
        style = classify_track(
            track_name=name,
            artist_name=artist,
            album_name=album,
            release_date=release_date,
            artist_genres=genres_str,
            lastfm_info=lastfm_info,
            lyrics=lyrics,
            temperature=0.3
        )
    if style not in ["Cubana", "Línea"]:
        style = "Cubana"
    print(f"  => {style}")
    time.sleep(1.5)
