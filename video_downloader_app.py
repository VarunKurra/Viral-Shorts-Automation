import os
import streamlit as st
from pathlib import Path
import yt_dlp
import pickle
import random
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from streamlit_autorefresh import st_autorefresh
from groq import Groq

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloaded_videos"
DOWNLOAD_DIR.mkdir(exist_ok=True)

HISTORY_FILE = BASE_DIR / "downloaded_titles.txt"
HISTORY_FILE.touch(exist_ok=True)

CLIENT_SECRETS_FILE = BASE_DIR / "client_secrets.json"
TOKEN_PATH = BASE_DIR / "token.pickle"
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

GROQ_API_KEY = "" # Replace with your Groq API key
groq = Groq(api_key=GROQ_API_KEY)

SUGGESTIONS = [
    "AI ASMR", "Weird Tech Inventions", "Viral Street Interviews", "Mind-Blowing Facts",
    "Tiny Cooking", "Oddly Satisfying", "Fitness Hacks", "Crazy Optical Illusions",
    "Top AI Tools 2025", "Gadget Unboxings", "Insane Productivity Hacks", "AI vs Human Challenges"
]
# Authentication and YouTube API
def get_authenticated_service():
    creds = None
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, 'wb') as token:
            pickle.dump(creds, token)
    return build('youtube', 'v3', credentials=creds)

# Groq AI Enhancements
def generate_title(old_title, topic):
    prompt = (
        f"Rewrite this YouTube Shorts title to be more clickable but similar, and add 5 relevant hashtags.\n"
        f"Topic: {topic}\nOld title: {old_title}\n\nNew title:"
    )
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content.strip() or "Untitled Short"

def generate_description(old_desc, topic):
    prompt = (
        f"Rewrite this YouTube Shorts description to improve SEO and engagement, keeping the original tone.\n"
        f"Include relevant hashtags and align it with the topic '{topic}'.\n"
        f"Old description: {old_desc}\n\nNew description:"
    )
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content.strip() or "#shorts"

# YouTube Upload
def upload_video(youtube, file_path, title, description):
    body = {
        'snippet': {
            'title': title[:100] if title else "Untitled Short",
            'description': description,
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'public',
            'madeForKids': False
        }
    }
    media = MediaFileUpload(str(file_path), chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    bar = st.progress(0)
    while response is None:
        status, response = request.next_chunk()
        if status:
            bar.progress(int(status.progress() * 100))
    bar.progress(100)
    return response.get("id")

# Video Downloading
def load_download_history():
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_to_download_history(title):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(title.strip() + "\n")

def search_youtube_shorts(topic, max_results=5):
    query = f"ytsearch{max_results}:{topic} shorts"
    opts = {'quiet': True, 'nocheckcertificate': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            return info.get('entries', [])
    except Exception as e:
        st.error(f"❌ Error: {e}")
        return []

def download_video(entry):
    url = entry['webpage_url']
    opts = {
        'outtmpl': str(DOWNLOAD_DIR / '%(title).70s.%(ext)s'),
        'format': 'bestvideo[height<=720]+bestaudio/best/best',
        'merge_output_format': 'mp4',
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        st.warning(f"⚠️ Failed to download {url}: {e}")
        return False

# Streamlit UI and Workflow
st.set_page_config(page_title="Viral Shorts Automation", layout="centered")

st.title("📥 Viral YouTube Shorts Downloader & ⬆️ Reuploader")

if "upload_done" not in st.session_state:
    st.session_state.upload_done = False

if "refreshed_once" not in st.session_state:
    st.session_state.refreshed_once = False

youtube = get_authenticated_service()

downloaded_titles = load_download_history()

if st.session_state.upload_done and not st.session_state.refreshed_once:
    st_autorefresh(interval=1500, limit=1, key="refresh_after_upload")
    st.session_state.refreshed_once = True
    st.stop()

topic = st.text_input("Enter a topic (e.g., AI ASMR)", key="topic", placeholder="AI ASMR")

if st.button("Suggest a Topic"):
    st.info(f"Try this one: **{random.choice(SUGGESTIONS)}**")

if st.button("Download and Upload"):
    if not topic.strip():
        st.error("⚠️ Please enter a topic first.")
    else:
        with st.spinner("🔍 Searching YouTube Shorts..."):
            entries = search_youtube_shorts(topic.strip(), max_results=5)

        if not entries:
            st.error("❌ No videos found.")
        else:
            st.success(f"Found {len(entries)} videos. Downloading now...")
            downloaded = []
            skipped = []

            for entry in entries:
                title = entry.get('title', '').strip()
                if not title:
                    continue
                if title in downloaded_titles:
                    skipped.append(title)
                    continue
                if entry.get('duration', 0) <= 180 and download_video(entry):
                    save_to_download_history(title)
                    files = sorted(DOWNLOAD_DIR.glob("*.mp4"), key=os.path.getmtime, reverse=True)
                    if files:
                        downloaded.append((files[0], entry))

            st.info(f"⏩ Skipped {len(skipped)} video(s) already downloaded.")
            if skipped:
                with st.expander("📄 Skipped Titles"):
                    for t in skipped:
                        st.markdown(f"- {t}")

            st.success(f"✅ Downloaded {len(downloaded)} new video(s). Now uploading to YouTube...")
            uploaded = 0
            for file_path, entry in downloaded:
                try:
                    old_title = entry.get('title', '')
                    old_desc = entry.get('description', '')
                    new_title = generate_title(old_title, topic)
                    new_desc = generate_description(old_desc, topic)
                    upload_video(youtube, file_path, new_title, new_desc)
                    os.remove(file_path)
                    uploaded += 1
                except Exception as e:
                    st.warning(f"⚠️ Upload failed for {file_path.name}: {e}")

            st.success(f"✅ Uploaded {uploaded} video(s) to YouTube!")
            st.session_state.upload_done = True
            st.session_state.refreshed_once = False
            st.experimental_rerun()
            st.session_state.upload_done = True