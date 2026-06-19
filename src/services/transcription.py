"""
ReplyQ AI Agent - Transcription Service (Google AI Studio)
Open Hands Agent | Tal HaTil Empire
"""
import tempfile
import os
import base64
from typing import Optional
import httpx
from loguru import logger

from config.settings import get_settings

settings = get_settings()


class TranscriptionService:
    """Service for transcribing audio using Google AI Studio."""

    def __init__(self):
        self.api_key = settings.google_ai_api_key or settings.google_speech_api_key
        self.model_name = settings.ai_model

    async def transcribe(self, audio_url: str) -> Optional[str]:
        """Transcribe an audio file from URL."""
        try:
            # Download audio file
            audio_data = await self._download_audio(audio_url)
            if not audio_data:
                return None
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
                f.write(audio_data)
                temp_path = f.name
            
            try:
                # Transcribe using Google AI
                transcript = await self.transcribe_with_google(temp_path)
                return transcript
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return None

    async def _download_audio(self, url: str) -> Optional[bytes]:
        """Download audio file from URL."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                if response.status_code == 200:
                    return response.content
                logger.warning(f"Failed to download audio: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            return None

    async def transcribe_with_google(self, audio_path: str, language: str = "he-IL") -> Optional[str]:
        """
        Transcribe audio using Google Cloud Speech-to-Text API.
        
        Args:
            audio_path: Path to the audio file
            language: Language code (default: Hebrew - he-IL)
            
        Returns:
            Transcribed text or None if transcription fails
        """
        if not self.api_key:
            logger.warning("Google AI API key not configured, using fallback")
            return await self._fallback_transcribe(audio_path)
        
        try:
            # Read and encode audio file
            with open(audio_path, "rb") as audio_file:
                audio_content = base64.b64encode(audio_file.read()).decode("utf-8")
            
            # Determine audio encoding based on file extension
            if audio_path.endswith(".ogg"):
                encoding = "OGG_OPUS"
            elif audio_path.endswith(".mp3"):
                encoding = "MP3"
            elif audio_path.endswith(".wav"):
                encoding = "LINEAR16"
            else:
                encoding = "OGG_OPUS"
            
            # Call Google Cloud Speech-to-Text API
            url = "https://speech.googleapis.com/v1/speech:recognize"
            params = {"key": self.api_key}
            
            payload = {
                "config": {
                    "encoding": encoding,
                    "languageCode": language,
                    "enableAutomaticPunctuation": True,
                    "model": "default",
                    "audioChannelCount": 1
                },
                "audio": {
                    "content": audio_content
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    result = response.json()
                    if "results" in result and len(result["results"]) > 0:
                        transcription = result["results"][0].get("alternatives", [{}])[0].get("transcript", "")
                        return transcription.strip()
                else:
                    logger.error(f"Google Speech API error: {response.text}")
            
            return await self._fallback_transcribe(audio_path)
            
        except Exception as e:
            logger.error(f"Error with Google Speech API: {e}")
            return await self._fallback_transcribe(audio_path)

    async def _fallback_transcribe(self, audio_path: str) -> Optional[str]:
        """Fallback transcription using basic audio processing."""
        # This is a placeholder for when API is not available
        # In production, you could use a local model or return None
        logger.warning("Using fallback transcription - API not configured")
        return "[הודעה קולית - יש לבדוק תמלול ידני]"

    async def detect_language(self, audio_path: str) -> str:
        """Detect the language of an audio file."""
        # Simple implementation - can be extended with Google Cloud API
        return "he-IL"  # Default to Hebrew

    async def process_voice_message(self, audio_data: bytes, format: str = "ogg") -> Optional[str]:
        """
        Process voice message from Telegram directly.
        
        Args:
            audio_data: Raw audio bytes
            format: Audio format (ogg, mp3, etc.)
            
        Returns:
            Transcribed text
        """
        if not self.api_key:
            return "[הודעה קולית]"
        
        try:
            # Encode audio
            audio_content = base64.b64encode(audio_data).decode("utf-8")
            
            # Determine encoding
            encoding_map = {
                "ogg": "OGG_OPUS",
                "mp3": "MP3",
                "wav": "LINEAR16",
                "m4a": "MP3"
            }
            encoding = encoding_map.get(format.lower(), "OGG_OPUS")
            
            url = "https://speech.googleapis.com/v1/speech:recognize"
            params = {"key": self.api_key}
            
            payload = {
                "config": {
                    "encoding": encoding,
                    "languageCode": "he-IL",
                    "enableAutomaticPunctuation": True
                },
                "audio": {
                    "content": audio_content
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    result = response.json()
                    if "results" in result and len(result["results"]) > 0:
                        return result["results"][0].get("alternatives", [{}])[0].get("transcript", "")
            
            return "[שגיאת תמלול]"
            
        except Exception as e:
            logger.error(f"Error processing voice message: {e}")
            return "[הודעה קולית - יש לבדוק תמלול ידני]"
