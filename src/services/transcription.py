"""
Voice Transcription Service using Google AI Studio (Gemini API).

This service handles audio-to-text conversion for voice messages
received from Telegram, utilizing Google's Gemini models for
high-quality transcription.
"""

import io
import httpx
import asyncio
from typing import Optional
from loguru import logger

from src.config import settings
from src.models import TranscriptionResult


class TranscriptionService:
    """
    Service for transcribing voice messages using Google AI Studio.
    
    This service downloads audio files from Telegram, converts them
    to the appropriate format, and sends them to Google AI Studio's
    Gemini API for transcription.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the transcription service.
        
        Args:
            api_key: Google AI API key. If not provided, uses settings.
        """
        self.api_key = api_key or settings.GOOGLE_AI_API_KEY
        self.model = settings.GOOGLE_AI_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
    async def transcribe_audio(
        self,
        audio_data: bytes,
        filename: str = "voice.ogg",
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data: Raw audio bytes (OGG format from Telegram)
            filename: Original filename for content type detection
            language: Optional language hint (e.g., "he" for Hebrew)
            
        Returns:
            TranscriptionResult with transcribed text and metadata
            
        Raises:
            TranscriptionError: If transcription fails
        """
        if not self.api_key:
            raise TranscriptionError("Google AI API key not configured")
            
        logger.info(f"Starting transcription for {filename}, size: {len(audio_data)} bytes")
        
        try:
            # For Gemini API, we need to use the vision/multimodal endpoint
            # with audio support. As of now, Gemini supports audio input.
            result = await self._transcribe_with_gemini(audio_data, language)
            logger.info(f"Transcription completed: {len(result.text)} characters")
            return result
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise TranscriptionError(f"Failed to transcribe audio: {e}")
    
    async def _transcribe_with_gemini(
        self,
        audio_data: bytes,
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Internal method to call Gemini API for transcription.
        
        Gemini models can process audio files directly. We convert the
        audio to base64 and send it to the API.
        """
        import base64
        
        # Convert audio to base64
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
        
        # Build prompt for transcription
        prompt_parts = [
            {"text": self._build_transcription_prompt(language)},
        ]
        
        # Gemini expects inline data with mime type
        inline_data = {
            "mime_type": "audio/ogg",  # Telegram voice messages are OGG
            "data": audio_b64
        }
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt_parts[0]["text"]},
                    {"inline_data": inline_data}
                ]
            }],
            "generationConfig": {
                "temperature": 0.1,  # Low temperature for factual transcription
                "maxOutputTokens": 2048,
            }
        }
        
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            
            if response.status_code != 200:
                error_msg = response.text
                logger.error(f"Gemini API error: {response.status_code} - {error_msg}")
                raise TranscriptionError(f"Gemini API returned {response.status_code}")
            
            result = response.json()
            
            # Extract transcription from response
            if "candidates" in result and len(result["candidates"]) > 0:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    parts = candidate["content"]["parts"]
                    transcribed_text = ""
                    for part in parts:
                        if "text" in part:
                            transcribed_text += part["text"]
                    
                    return TranscriptionResult(
                        text=transcribed_text.strip(),
                        confidence=0.95,  # Gemini doesn't provide confidence, estimate
                        language=language or "auto",
                        model_used=self.model
                    )
            
            raise TranscriptionError("No transcription in Gemini response")
    
    def _build_transcription_prompt(self, language: Optional[str] = None) -> str:
        """
        Build a prompt for the transcription task.
        
        Args:
            language: Optional language code (ISO 639-1)
            
        Returns:
            Formatted prompt string
        """
        if language == "he":
            return """אתה מתמלל מקצועי. תמלל את ההודעה הקולית בדיוק מקסימלי.
החזר רק את הטקסט המתומלל ללא הערות או הסברים נוספים.
אם אינך יכול לשמוע בבירור, החזר [לא ברור]."""
        
        return f"""You are a professional transcription service. Transcribe the audio message exactly.
Return ONLY the transcribed text without any additional comments.
The audio is in language: {language or 'auto-detect'}.
If you cannot hear clearly, return [unclear]."""
    
    async def transcribe_from_url(
        self,
        file_url: str,
        language: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Download audio from URL and transcribe.
        
        Args:
            file_url: Direct URL to audio file
            language: Optional language hint
            
        Returns:
            TranscriptionResult
        """
        logger.info(f"Downloading audio from {file_url}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(file_url)
            response.raise_for_status()
            
            content_type = response.headers.get("content-type", "audio/ogg")
            filename = f"audio.{content_type.split('/')[-1]}"
            
            return await self.transcribe_audio(
                response.content,
                filename=filename,
                language=language
            )


class TranscriptionError(Exception):
    """Custom exception for transcription errors."""
    pass


# Singleton instance
_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    """Get or create the global transcription service instance."""
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service