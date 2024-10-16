import streamlit as st
import moviepy.editor as mp
from moviepy.editor import VideoFileClip, AudioFileClip
from google.cloud import speech
import os
from pydub import AudioSegment
import io
import requests
from google.cloud import texttospeech
import json
from utilities.google_services import GoogleServices
import time

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"
client = speech.SpeechClient()

class Utilities:
    def __init__(self):
        """Initialize the Utilities class and create necessary directories for input and output."""
        self.input_folder = "input_audio"
        self.output_folder = "output_audio"
        os.makedirs("input_audio", exist_ok=True)
        os.makedirs("output_audio", exist_ok=True)

    @staticmethod
    def extract_audio_segment(video, start_time, duration=1):
        """Extracts a segment of audio from the video starting at `start_time` with a given `duration`, converts it to mono, and resamples to 16kHz."""
        segment = video.subclip(start_time, start_time + duration)
        segment_audio_path = f"input_audio/temp_audio_{start_time}_{start_time + duration}.wav"
        segment.audio.write_audiofile(segment_audio_path)

        audio = AudioSegment.from_wav(segment_audio_path)
        audio = audio.set_channels(1) 
        audio = audio.set_frame_rate(16000) 
        resampled_audio_path = f"resampled_audio_{start_time}_{start_time + duration}.wav"
        audio.export(resampled_audio_path, format="wav")

        return resampled_audio_path

    @staticmethod
    def transcribe_audio_segment(audio_path):
        """Transcribes a given audio segment using Google Cloud Speech-to-Text."""
        with io.open(audio_path, "rb") as audio_file:
            content = audio_file.read()
        
        audio = speech.RecognitionAudio(content=content)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,  
            language_code="en-US"
        )

        response = client.recognize(config=config, audio=audio)

        transcription = ""
        for result in response.results:
            transcription += result.alternatives[0].transcript

        return transcription

    @staticmethod
    def create_audio_transcription_map(video_path, segment_duration=1):
        """Creates a map with 10-second segments of audio and the respective transcription."""
        # Load the video file
        video = mp.VideoFileClip(video_path)
        total_duration = int(video.duration)
        transcription_map = {}

        try:
            for start_time in range(0, total_duration, segment_duration):
                end_time = min(start_time + segment_duration, total_duration)
                
                if start_time < total_duration:
                    audio_path = Utilities.extract_audio_segment(video, start_time, end_time - start_time)
                    transcription = Utilities.transcribe_audio_segment(audio_path)

                    time_range = f"{start_time}-{end_time}"
                    transcription_map[time_range] = transcription
                    os.remove(audio_path)
        finally:
            video.close()

        return transcription_map

    @staticmethod
    def correct_transcription_map(transcription_map, delay=2):
        """Loops through the transcription map, corrects each transcription using GPT-4o, 
        introduces a delay after each request, and returns a corrected map."""
        
        corrected_map = GoogleServices.correct_transcription_map_with_gpt4o(transcription_map)
        return corrected_map
    @staticmethod
    def join_audio_files_from_map(transcription_map, output_file="final_output.wav"):
        """Joins all the generated audio files (temp_audio_output_start_end.wav) into a single file."""
        combined_audio = AudioSegment.silent(duration=0) 

        for time_range in transcription_map.keys():
            start, end = map(int, time_range.split('-'))
            audio_file = f"output_audio/temp_audio_output_{start}_{end}.wav"
            if os.path.exists(audio_file):
                audio_segment = AudioSegment.from_wav(audio_file)
                combined_audio += audio_segment

        combined_audio.export(output_file, format="wav")
        print(f"Combined audio exported to {output_file}")
    @staticmethod
    def generate_audio_files_from_map(transcription_map):
        """Loops through the corrected transcription map, generates audio for each time range, and saves them as separate audio files."""
        
        for time_range, corrected_transcription in transcription_map.items():
            start, end = map(int, time_range.split('-'))
            duration = end - start  
            output_audio_file = f"output_audio/temp_audio_output_{start}_{end}.wav"
            GoogleServices.text_to_speech_with_google(corrected_transcription, output_audio_file, duration)

    @staticmethod
    def attach_audio_to_video(video_path, audio_path, output_video_path):
        """Attaches the combined audio to the original video and saves it as a new file."""
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)
        video_with_audio = video.set_audio(audio)
        video_with_audio.write_videofile(output_video_path, codec="libx264", audio_codec="aac")
        video.close()
        audio.close()
