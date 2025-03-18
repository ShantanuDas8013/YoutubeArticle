import os
import streamlit as st
import tempfile
import requests
import time
import json
from pathlib import Path
import base64
import re
import subprocess
import sys
st.set_page_config(
    page_title="YouTube to Article Converter",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="collapsed"
)

primary_color = "#FF4B4B"
secondary_color = "#4B4BFF"
success_color = "#00CC66"
info_color = "#0099FF"
warning_color = "#FFAA00"

os.environ["ASSEMBLYAI_API_KEY"] = "b89753e7fee4407f9465a712ec822716"

def download_youtube_audio(youtube_url):
    try:
        temp_dir = tempfile.mkdtemp()
        try:
            subprocess.run(["yt-dlp", "--version"], check=True, capture_output=True)
            yt_dlp_installed = True
        except (subprocess.SubprocessError, FileNotFoundError):
            yt_dlp_installed = False
        if not yt_dlp_installed:
            with st.status("Installing yt-dlp...", expanded=True) as status:
                subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp"], check=True)
                status.update(label="yt-dlp installed successfully!", state="complete")
        title_cmd = ["yt-dlp", "--get-title", youtube_url]
        video_title = subprocess.run(title_cmd, check=True, capture_output=True, text=True).stdout.strip()
        safe_title = re.sub(r'[^\w\-_\. ]', '_', video_title)
        output_template = os.path.join(temp_dir, f"{safe_title}.%(ext)s")
        with st.status("Downloading audio from YouTube...", expanded=True) as status:
            download_cmd = [
                "yt-dlp", 
                "-x", 
                "--audio-format", "mp3", 
                "-o", output_template, 
                youtube_url
            ]
            subprocess.run(download_cmd, check=True)
            status.update(label="Audio downloaded successfully!", state="complete")
        for file in os.listdir(temp_dir):
            if file.endswith(".mp3"):
                output_file = os.path.join(temp_dir, file)
                return output_file, video_title
        with st.status("Trying alternative download configuration...", expanded=True) as status:
            output_file = os.path.join(temp_dir, "audio.mp3")
            alt_download_cmd = [
                "yt-dlp", 
                "-f", "bestaudio", 
                "--extract-audio", 
                "--audio-format", "mp3", 
                "--audio-quality", "0", 
                "-o", output_file, 
                youtube_url
            ]
            subprocess.run(alt_download_cmd, check=True)
            status.update(label="Audio downloaded with alternative method!", state="complete")
        if os.path.exists(output_file):
            return output_file, video_title
        else:
            for file in os.listdir(temp_dir):
                if file.endswith(".mp3"):
                    return os.path.join(temp_dir, file), video_title
        st.error("Could not find downloaded audio file.")
        return None, None
    except Exception as e:
        st.error(f"Error downloading YouTube audio: {str(e)}")
        return None, None

def transcribe_audio(audio_file_path):
    upload_endpoint = "https://api.assemblyai.com/v2/upload"
    transcript_endpoint = "https://api.assemblyai.com/v2/transcript"
    if "ASSEMBLYAI_API_KEY" in os.environ:
        api_key = os.environ["ASSEMBLYAI_API_KEY"]
    else:
        api_key = st.session_state.get("assemblyai_api_key", "")
        if not api_key:
            api_key = st.text_input("Enter your AssemblyAI API key:", type="password")
            if api_key:
                st.session_state["assemblyai_api_key"] = api_key
            else:
                st.warning("Please enter an AssemblyAI API key to continue.")
                return None
    headers = {
        "authorization": api_key,
        "content-type": "application/json"
    }
    with st.status("Uploading audio file to AssemblyAI...", expanded=True) as status:
        with open(audio_file_path, "rb") as f:
            response = requests.post(
                upload_endpoint,
                headers=headers,
                data=f
            )
        if response.status_code != 200:
            st.error(f"Error uploading audio file: {response.text}")
            return None
        upload_url = response.json()["upload_url"]
        status.update(label="Audio file uploaded successfully!", state="complete")
    with st.status("Starting transcription process...", expanded=True) as status:
        response = requests.post(
            transcript_endpoint,
            headers=headers,
            json={
                "audio_url": upload_url,
                "language_code": "en"
            }
        )
        if response.status_code != 200:
            st.error(f"Error starting transcription: {response.text}")
            return None
        transcript_id = response.json()["id"]
        status.update(label="Transcription started! Processing audio...", state="running")
    status = "processing"
    progress_container = st.container()
    with progress_container:
        st.markdown(f"<h3 style='color:{info_color};'>Transcription Progress</h3>", unsafe_allow_html=True)
        progress_bar = st.progress(0)
        status_text = st.empty()
    while status != "completed" and status != "error":
        response = requests.get(
            f"{transcript_endpoint}/{transcript_id}",
            headers=headers
        )
        status = response.json()["status"]
        if status == "processing":
            progress = response.json().get("percent_complete", 0)
            progress_bar.progress(progress / 100)
            status_text.text(f"Processing: {progress}% complete")
            time.sleep(3)
        elif status == "completed":
            progress_bar.progress(1.0)
            status_text.text("Transcription completed!")
            return response.json()["text"]
        else:
            st.error(f"Error in transcription: {response.json()}")
            return None
    return None

def generate_article(transcription, video_title):
    try:
        sentences = [s.strip() for s in transcription.split('.') if s.strip()]
        article_title = f"Analysis and Summary: {video_title}"
        introduction = f'This comprehensive analysis provides a detailed examination of the key concepts and insights presented in the video "{video_title}". The following sections break down the main topics and provide a structured overview of the content discussed.'
        sections = []
        current_section = []
        section_count = 0
        for i, sentence in enumerate(sentences):
            current_section.append(sentence)
            if len(current_section) >= 5 and (i + 1) % 5 == 0 or i == len(sentences) - 1:
                section_count += 1
                section_title = f"Section {section_count}: Key Points"
                sections.append({"title": section_title, "content": ". ".join(current_section) + "."})
                current_section = []
        conclusion = f'This analysis has provided a structured overview of the key concepts presented in "{video_title}". The information has been organized into clear sections to facilitate understanding and reference. For the complete context and detailed discussion, we recommend viewing the original video content.'
        article = {"title": article_title, "introduction": introduction, "sections": sections, "conclusion": conclusion}
        return article
    except Exception as e:
        st.error(f"Error generating article: {str(e)}")
        return None

def get_binary_file_downloader_html(file_path, file_label):
    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    file_name = os.path.basename(file_path)
    return f'<a href="data:file/txt;base64,{b64}" download="{file_name}">{file_label}</a>'

def main():
    st.markdown(f"<h1 style='color:{primary_color};'>YouTube to Article Converter</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='font-size:18px;'>This tool helps you convert YouTube videos into well-structured articles. Simply paste a YouTube URL below to get started.</p>", unsafe_allow_html=True)
    st.divider()
    st.markdown(f"<h3 style='color:{secondary_color};'>Enter YouTube Video URL</h3>", unsafe_allow_html=True)
    youtube_url = st.text_input(
        "",
        placeholder="https://www.youtube.com/watch?v=...",
        help="Paste the full YouTube video URL here"
    )
    if st.button("Convert to Article", type="primary", use_container_width=True):
        if youtube_url:
            results_container = st.container()
            with results_container:
                audio_file_path, video_title = download_youtube_audio(youtube_url)
                if audio_file_path:
                    st.success(f"Successfully processed: {video_title}")
                    tab1, tab2, tab3 = st.tabs(["📊 Results", "🎵 Audio", "📝 Transcription"])
                    with tab1:
                        transcription = transcribe_audio(audio_file_path)
                        if transcription:
                            with st.status("Generating article from transcription...", expanded=True) as status:
                                article = generate_article(transcription, video_title)
                                status.update(label="Article generated successfully!", state="complete")
                            if article:
                                st.markdown(f"<h2 style='color:{primary_color};'>{article['title']}</h2>", unsafe_allow_html=True)
                                st.markdown(f"<p style='color:{secondary_color}; font-style:italic;'>{article['introduction']}</p>", unsafe_allow_html=True)
                                st.divider()
                                
                                for section in article['sections']:
                                    st.markdown(f"<h3 style='color:{info_color};'>{section['title']}</h3>", unsafe_allow_html=True)
                                    st.write(section['content'])
                                    st.divider()
                                
                                st.markdown(f"<p style='color:{secondary_color}; font-style:italic;'>{article['conclusion']}</p>", unsafe_allow_html=True)
                                article_file = os.path.join(os.path.dirname(audio_file_path), "article.txt")
                                with open(article_file, "w") as f:
                                    f.write(f"{article['title']}\n\n")
                                    f.write(f"{article['introduction']}\n\n")
                                    for section in article['sections']:
                                        f.write(f"{section['title']}\n")
                                        f.write(f"{section['content']}\n\n")
                                    f.write(f"{article['conclusion']}")
                                st.markdown(f"<h3 style='color:{success_color};'>Download Options</h3>", unsafe_allow_html=True)
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.download_button(
                                        label="Download Article (TXT)",
                                        data=open(article_file, "rb"),
                                        file_name=f"{os.path.basename(article_file)}",
                                        mime="text/plain"
                                    )
                                with col2:
                                    st.download_button(
                                        label="Download Audio (MP3)",
                                        data=open(audio_file_path, "rb"),
                                        file_name=f"{os.path.basename(audio_file_path)}",
                                        mime="audio/mp3"
                                    )
                    with tab2:
                        st.markdown(f"<h3 style='color:{info_color};'>Audio Player</h3>", unsafe_allow_html=True)
                        st.audio(audio_file_path, format="audio/mp3")
                        st.markdown(f"<h3 style='color:{info_color};'>Video Information</h3>", unsafe_allow_html=True)
                        st.info(f"**Title:** {video_title}")
                        st.markdown(f"**Source:** [YouTube]({youtube_url})")
                        st.download_button(
                            label="Download Audio File",
                            data=open(audio_file_path, "rb"),
                            file_name=f"{os.path.basename(audio_file_path)}",
                            mime="audio/mp3"
                        )
                    with tab3:
                        st.markdown(f"<h3 style='color:{warning_color};'>Full Transcription</h3>", unsafe_allow_html=True)
                        if 'transcription' in locals() and transcription:
                            st.text_area("", transcription, height=400)
                        else:
                            st.info("Transcription will appear here once processed.")
        else:
            st.warning("Please enter a YouTube URL to continue.")

if __name__ == "__main__":
    main()