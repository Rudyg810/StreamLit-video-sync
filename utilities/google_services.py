
import streamlit as st
import moviepy.editor as mp
from moviepy.editor import VideoFileClip, AudioFileClip
from google.cloud import speech
import os
from pydub import AudioSegment
import io
from google.oauth2 import service_account
import requests
from google.cloud import texttospeech
import json
from dotenv  import load_dotenv
load_dotenv()
# Reconstruct the credentials dictionary
google_credentials = {
    "type": os.getenv("GOOGLE_TYPE"),
    "project_id": os.getenv("GOOGLE_PROJECT_ID"),
    "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("GOOGLE_PRIVATE_KEY").replace('\\n', '\n'),  # Replacing escaped newlines
    "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
    "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
    "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_X509_CERT_URL")
}

# Use the credentials to authenticate the SpeechClient
credentials = service_account.Credentials.from_service_account_info(google_credentials)
client = speech.SpeechClient(credentials=credentials)

azure_openai_key = os.getenv("AZURE_OPENAI_KEY")
azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
class GoogleServices:
    @staticmethod
    def correct_transcription_map_with_gpt4o(transcription_map):
        """Passes the transcription map to GPT-4o model to correct grammatical mistakes minimally and remove filler words."""
        
        azure_openai_key = azure_openai_key
        azure_openai_endpoint = azure_openai_endpoint

        headers = {
            "Content-Type": "application/json",
            "api-key": azure_openai_key
        }
        
        # Create the content by converting the transcription_map to a string format.
        transcription_data = "\n".join([f"{time_range}: {transcription}" for time_range, transcription in transcription_map.items()])
        
        data = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        f"strictly without changing anything in the text. Do not increase the length of the content. Also, remove filler words like 'um,' 'ah,' etc. "
                        f"Also there will be cases where the sequence of each value in map wouldn't match when together put, So please refactor that as well, STRICTLY WITHOUT CHANGING THE LENGTH OF INPUT"
                        f"Provide the corrected output in the same format as provided: 'time_range: corrected_transcription'. "
                        f"If any transcription is mostly filler words, return an empty string for that entry.\n\nTranscriptions:\n{transcription_data}"
                    )
                }
            ],
            "max_tokens": 500
        }

        response = requests.post(azure_openai_endpoint, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()  # Parse the JSON response
            corrected_transcriptions = result["choices"][0]["message"]["content"].strip()

            # Convert the corrected response back into a dictionary format.
            corrected_map = {}
            for line in corrected_transcriptions.splitlines():
                if line.strip():
                    time_range, corrected_transcription = line.split(": ", 1)
                    corrected_map[time_range] = corrected_transcription
            
            return corrected_map
        else:
            raise Exception(f"Failed to connect or retrieve response: {response.status_code} - {response.text}")


    @staticmethod
    def text_to_speech_with_google(corrected_transcription, output_audio_file, duration):
        """Takes the corrected transcription and converts it into speech using Google Text-to-Speech,ensuring the audio duration matches the required duration from the map."""
        client = texttospeech.TextToSpeechClient(credentials=credentials)
        if corrected_transcription:
            synthesis_input = texttospeech.SynthesisInput(text=corrected_transcription)
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-IN",
                name="en-IN-Journey-F", 
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16
            )
            response = client.synthesize_speech(
                input=synthesis_input, voice=voice, audio_config=audio_config
            )
            with open(output_audio_file, "wb") as out:
                out.write(response.audio_content)
            audio = AudioSegment.from_wav(output_audio_file)
            audio_duration_ms = len(audio) 

            if audio_duration_ms < duration * 1000:
                silence_duration_ms = (duration * 1000) - audio_duration_ms
                silence = AudioSegment.silent(duration=silence_duration_ms)
                audio = audio + silence

            audio.export(output_audio_file, format="wav")

        else:
            silence = AudioSegment.silent(duration=duration * 1000)
            silence.export(output_audio_file, format="wav")
