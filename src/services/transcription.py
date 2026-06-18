"""
ReplyQ AI Agent - Voice Transcription Service (Whisper)
"""
import tempfile
import os
from typing import Optional
from pathlib import Path
import httpx
from loguru import logger

from config.settings import get_settings

settings = get_settings()


class TranscriptionService:
    """Service for transcribing audio/voice messages using Whisper."""

    def __init__(self):
        self.model_name = settings.whisper_model

    async def transcribe(self, audio_url: str) -> Optional[str]:
        """
        Transcribe an audio file from URL.
        
        Args:
            audio_url: URL to the audio file
            
        Returns:
            Transcribed text or None if transcription fails
        """
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
                # Transcribe using Whisper
                transcript = await self._transcribe_with_whisper(temp_path)
                return transcript
            finally:
                # Clean up temp file
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

    async def _transcribe_with_whisper(self, audio_path: str) -> Optional[str]:
        """
        Transcribe audio file using Whisper model.
        
        Uses OpenAI's Whisper API if API key is available,
        otherwise falls back to local model.
        """
        # Try OpenAI Whisper API first
        if settings.openai_api_key:
            return await self._transcribe_with_openai(audio_path)
        
        # Fall back to local Whisper model
        return await self._transcribe_locally(audio_path)

    async def _transcribe_with_openai(self, audio_path: str) -> Optional[str]:
        """Transcribe using OpenAI Whisper API."""
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            
            with open(audio_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="pt"  # Portuguese, can be made dynamic
                )
            
            return transcript.text
            
        except Exception as e:
            logger.error(f"OpenAI Whisper API error: {e}")
            return await self._transcribe_locally(audio_path)

    async def _transcribe_locally(self, audio_path: str) -> Optional[str]:
        """Transcribe using local Whisper model."""
        try:
            import whisper
            import torch
            
            # Load model (cached)
            model = whisper.load_model(self.model_name)
            
            # Transcribe
            result = model.transcribe(
                audio_path,
                language="pt",
                fp16=torch.cuda.is_available()
            )
            
            return result["text"].strip()
            
        except ImportError:
            logger.error("Whisper not installed. Install with: pip install whisper")
            return None
        except Exception as e:
            logger.error(f"Local Whisper error: {e}")
            return None

    async def transcribe_text_to_text(self, text: str) -> str:
        """
        Process text input (for testing or manual transcription).
        
        Args:
            text: Text content
            
        Returns:
            Same text (no transformation needed)
        """
        return text

    async def detect_language(self, audio_path: str) -> str:
        """Detect the language of an audio file."""
        try:
            import whisper
            
            model = whisper.load_model(self.model_name)
            audio = whisper.load_audio(audio_path)
            audio = whisper.pad_or_trim(audio)
            
            # Load model and detect
            mel = whisper.log_mel_spectrogram(audio).to(model.device)
            
            _, probs = model.detect_language(mel)
            detected_language = max(probs, key=probs.get)
            
            return detected_language
            
        except Exception as e:
            logger.error(f"Language detection error: {e}")
            return "unknown"
