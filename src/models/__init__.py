from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MessageType(str, Enum):
    """Types of messages supported by the bot."""
    TEXT = "text"
    VOICE = "voice"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    PHOTO = "photo"
    STICKER = "sticker"


class TranscriptionResult(BaseModel):
    """Result of voice message transcription."""
    text: str = Field(..., description="Transcribed text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    language: Optional[str] = Field(None, description="Detected language")
    duration_seconds: Optional[float] = Field(None, description="Audio duration")
    model_used: str = Field(..., description="Model used for transcription")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class UserContext(BaseModel):
    """User session context."""
    user_id: int
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    language: str = "he"  # Default to Hebrew
    preferences: dict = Field(default_factory=dict)
    message_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BotResponse(BaseModel):
    """Standardized bot response."""
    success: bool
    message: str
    data: Optional[dict] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)