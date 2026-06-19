"""
ReplyQ AI Agent - Telegram Channel Integration
Open Hands Agent | Tal HaTil Empire
"""
import hashlib
import json
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from loguru import logger
import httpx

from config.settings import get_settings
from src.agents.core import get_agent
from src.services.transcription import TranscriptionService
from src.services.payment import get_payment_service
from src.database.connection import get_db_context
from src.database.models import Customer, Conversation, Message, MessageDirection, MessageType, CustomerSegment, BlackoutStatus

settings = get_settings()
router = APIRouter(prefix="/webhook/telegram", tags=["Telegram"])


# Tal HaTil Empire Brand Constants
BRAND_NAME = "Tal HaTil Empire"
BOOK_TITLE = "Manifesting Reality"
BOOK_PRICE_USD = 47.00
TALHATIL_URL = "https://talhatil.com"
PAYPAL_LINK = "https://paypal.me/talhatil"


class TelegramUpdate(BaseModel):
    """Telegram webhook update model."""
    update_id: int
    message: Optional[Dict[str, Any]] = None
    edited_message: Optional[Dict[str, Any]] = None
    channel_post: Optional[Dict[str, Any]] = None


async def get_or_create_customer(telegram_id: int, username: str = None, first_name: str = None) -> Customer:
    """Get existing customer or create new one from Telegram."""
    async with get_db_context() as session:
        from sqlalchemy import select
        
        stmt = select(Customer).where(Customer.telegram_id == str(telegram_id))
        result = await session.execute(stmt)
        customer = result.scalar_one_or_none()
        
        if not customer:
            customer = Customer(
                id=f"tg_{hashlib.md5(str(telegram_id).encode()).hexdigest()[:12]}",
                telegram_id=str(telegram_id),
                telegram_username=username,
                name=first_name,
                segment=CustomerSegment.B2C,
                lead_score=settings.initial_lead_score
            )
            session.add(customer)
            await session.commit()
            await session.refresh(customer)
        
        return customer


async def get_or_create_conversation(customer: Customer, chat_id: int) -> Conversation:
    """Get active conversation or create new one."""
    async with get_db_context() as session:
        from sqlalchemy import select
        
        stmt = select(Conversation).where(
            Conversation.customer_id == customer.id,
            Conversation.channel == "telegram",
            Conversation.is_active == True
        )
        result = await session.execute(stmt)
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            conversation = Conversation(
                id=f"conv_tg_{hashlib.md5(str(chat_id).encode()).hexdigest()[:12]}",
                customer_id=customer.id,
                channel="telegram",
                channel_id=str(chat_id)
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
        
        return conversation


async def store_message(
    conversation_id: str,
    direction: MessageDirection,
    message_type: MessageType,
    content: str,
    media_url: Optional[str] = None,
    transcription: Optional[str] = None,
    intent: Optional[str] = None,
    confidence: Optional[float] = None,
    ai_response: Optional[str] = None
) -> Message:
    """Store a message in the database."""
    async with get_db_context() as session:
        message = Message(
            id=f"msg_tg_{hashlib.md5(content[:50].encode()).hexdigest()[:12]}",
            conversation_id=conversation_id,
            direction=direction,
            message_type=message_type,
            content=content,
            media_url=media_url,
            transcription=transcription,
            intent_detected=intent,
            confidence=confidence,
            ai_response=ai_response
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message


async def send_telegram_message(chat_id: int, text: str, parse_mode: str = "Markdown") -> bool:
    """Send message via Telegram Bot API."""
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured")
        return False
    
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Telegram message sent to {chat_id}")
                return True
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
                return False
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")
        return False


async def process_voice_note(file_id: str, transcription_service: TranscriptionService) -> Optional[str]:
    """Download and transcribe voice note using Google AI Studio."""
    if not settings.telegram_bot_token:
        return None
    
    try:
        # Get file path
        file_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            response = await client.get(file_url)
            if response.status_code != 200:
                return None
            file_path = response.json().get("result", {}).get("file_path")
        
        if not file_path:
            return None
        
        # Download the audio file
        download_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file_path}"
        audio_response = await httpx.AsyncClient().get(download_url)
        
        if audio_response.status_code != 200:
            return None
        
        # Save temporarily and transcribe
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(audio_response.content)
            temp_path = f.name
        
        try:
            transcript = await transcription_service.transcribe_with_google(temp_path)
            return transcript
        finally:
            import os
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    except Exception as e:
        logger.error(f"Error processing voice note: {e}")
        return None


def format_book_promotion() -> str:
    """Format the book promotion message."""
    return f"""
📖 *{BOOK_TITLE}*

הספר הדיגיטלי שישנה את המציאות שלך.

✅ מדריך מעשי להגשמת מטרות
✅ טכניקות מוכחות שעובדות
✅ כלים פרקטיים ליישום מיידי

💰 *מחיר מבצע: ${BOOK_PRICE_USD}*

🎯 [רכוש עכשיו ב-PayPal]({PAYPAL_LINK})

🌐 [או בקר באתר שלנו]({TALHATIL_URL})
"""


def format_welcome_message(first_name: str = None) -> str:
    """Format welcome message."""
    name = first_name or "אורח"
    return f"""
👋 שלום {name}!

*ברוך הבא ל{BRAND_NAME}*

אני כאן כדי לעזור לך. 

מה תרצה לדעת?
"""


def format_fallback_message() -> str:
    """Format fallback message when AI is unsure."""
    return """
🤔 לא בטוח שהבנתי נכון.

נסה לשאול אותי על:
• הספר "Manifesting Reality"
• שירותי האימפריה
• איך לרכוש

או פנה ישירות: /help
"""


@router.get("/webhook")
async def telegram_webhook_verify(request: Request):
    """Webhook verification endpoint for Telegram."""
    return {"status": "ok"}


@router.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Main webhook endpoint for Telegram messages.
    Open Hands Agent processing incoming messages.
    """
    try:
        body = await request.json()
        logger.info(f"Telegram update received: {body.get('update_id')}")
        
        # Extract message data
        message = body.get("message") or body.get("edited_message")
        
        if not message:
            return {"status": "ok", "processed": False}
        
        # Skip group messages unless configured
        chat = message.get("chat", {})
        chat_type = chat.get("type", "private")
        
        if chat_type in ["group", "supergroup"] and not settings.telegram_allow_groups:
            return {"status": "ok", "processed": False, "reason": "group_not_allowed"}
        
        # Extract user info
        user = message.get("from", {})
        telegram_id = user.get("id")
        username = user.get("username")
        first_name = user.get("first_name", "")
        chat_id = chat.get("id")
        
        # Get message content
        text = message.get("text", "")
        voice = message.get("voice")
        audio = message.get("audio")
        photo = message.get("photo")
        document = message.get("document")
        
        # Handle commands
        if text and text.startswith("/"):
            await handle_telegram_command(chat_id, text, telegram_id, username, first_name)
            return {"status": "ok", "processed": True, "type": "command"}
        
        # Get or create customer and conversation
        customer = await get_or_create_customer(telegram_id, username, first_name)
        conversation = await get_or_create_conversation(customer, chat_id)
        
        # Process content
        processed_content = text
        message_type = MessageType.TEXT
        media_url = None
        
        # Handle voice message
        transcription_service = TranscriptionService()
        if voice:
            message_type = MessageType.VOICE
            transcript = await process_voice_note(voice.get("file_id"), transcription_service)
            processed_content = transcript or "[הודעה קולית]"
            logger.info(f"Voice transcribed: {processed_content[:50]}")
        
        # Handle other media
        elif audio:
            message_type = MessageType.VOICE
            processed_content = f"[הודעת שמע] {text or ''}"
        elif photo:
            message_type = MessageType.IMAGE
            processed_content = f"[תמונה] {text or 'תמונה מצורפת'}"
        elif document:
            message_type = MessageType.DOCUMENT
            processed_content = f"[מסמך] {text or 'מסמך מצורף'}"
        
        # Store incoming message
        await store_message(
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            message_type=message_type,
            content=processed_content,
            media_url=media_url
        )
        
        # Update customer interaction time
        async with get_db_context() as session:
            from sqlalchemy import select
            stmt = select(Customer).where(Customer.id == customer.id)
            result = await session.execute(stmt)
            cust = result.scalar_one_or_none()
            if cust:
                cust.last_interaction = datetime.utcnow()
                cust.blackout_count = 0
                cust.blackout_status = BlackoutStatus.NORMAL
                await session.commit()
        
        # Get AI response
        agent = get_agent()
        context = {
            "customer_name": first_name or username or str(telegram_id),
            "customer_id": customer.id,
            "segment": customer.segment.value,
            "lead_score": customer.lead_score,
            "channel": "telegram",
            "brand": BRAND_NAME,
            "book_title": BOOK_TITLE
        }
        
        ai_result = await agent.get_ai_response(
            message=processed_content,
            customer_id=customer.id,
            context=context
        )
        
        response_text = ai_result.get("message", "")
        
        # Check for blackout mode
        if ai_result.get("blackout_suspected"):
            response_text = format_fallback_message()
        
        # Store AI response
        await store_message(
            conversation_id=conversation.id,
            direction=MessageDirection.OUTBOUND,
            message_type=MessageType.TEXT,
            content=response_text,
            intent=ai_result.get("intent"),
            confidence=ai_result.get("confidence"),
            ai_response=response_text
        )
        
        # Update conversation
        async with get_db_context() as session:
            from sqlalchemy import select
            stmt = select(Conversation).where(Conversation.id == conversation.id)
            result = await session.execute(stmt)
            conv = result.scalar_one_or_none()
            if conv:
                conv.last_ai_response = response_text
                if ai_result.get("escalation"):
                    conv.is_escalated = True
                await session.commit()
        
        # Update lead score
        if ai_result.get("lead_score_impact"):
            async with get_db_context() as session:
                from sqlalchemy import select
                stmt = select(Customer).where(Customer.id == customer.id)
                result = await session.execute(stmt)
                cust = result.scalar_one_or_none()
                if cust:
                    new_score = cust.lead_score + ai_result["lead_score_impact"]
                    cust.lead_score = max(0, min(settings.max_lead_score, new_score))
                    await session.commit()
        
        # Send response via Telegram
        await send_telegram_message(chat_id, response_text)
        
        # Handle escalation if needed
        if ai_result.get("escalation") and settings.human_escalation_webhook_url:
            background_tasks.add_task(
                trigger_escalation,
                customer,
                conversation,
                ai_result
            )
        
        return {"status": "ok", "processed": True}
        
    except Exception as e:
        logger.error(f"Error processing Telegram message: {e}")
        return {"status": "error", "message": str(e)}


async def handle_telegram_command(chat_id: int, command: str, telegram_id: int, username: str, first_name: str):
    """Handle Telegram bot commands."""
    command = command.lower().strip()
    
    if command in ["/start", "/hello", "/shalom"]:
        message = format_welcome_message(first_name)
        await send_telegram_message(chat_id, message)
    
    elif command in ["/book", "/manifesting", "/ספר"]:
        message = format_book_promotion()
        await send_telegram_message(chat_id, message)
    
    elif command in ["/buy", "/purchase", "/קנה", "/רכוש"]:
        payment_service = get_payment_service()
        customer = await get_or_create_customer(telegram_id, username, first_name)
        
        result = await payment_service.create_paypal_link(
            customer_id=customer.id,
            amount=BOOK_PRICE_USD,
            currency="USD",
            description=f"רכישת הספר {BOOK_TITLE}"
        )
        
        if result.get("success"):
            payment_url = result.get("payment_url", PAYPAL_LINK)
            message = f"""
✅ *מוכן לרכישה!*

📖 *{BOOK_TITLE}*
💰 *מחיר: ${BOOK_PRICE_USD}*

[לחץ כאן לרכישה בטוחה ב-PayPal]({payment_url})

או בקר באתר: {TALHATIL_URL}
"""
        else:
            message = f"""
⚠️ נתקלנו בבעיה טכנית.

רכוש ישירות: {PAYPAL_LINK}

או פנה לתמיכה באתר.
"""
        await send_telegram_message(chat_id, message)
    
    elif command in ["/website", "/site", "/אתר", "/talhatil"]:
        message = f"""
🌐 *אתר האימפריה*

[TALHATIL]({TALHATIL_URL})

כל המידע והשירותים במקום אחד.
"""
        await send_telegram_message(chat_id, message)
    
    elif command in ["/help", "/support", "/עזרה"]:
        message = """
📋 *פקודות זמינות:*

/start - התחל שיחה
/book - מידע על הספר
/buy - רכישת הספר
/website - אתר האימפריה
/help - עזרה

או פשוט שאל אותי שאלה 💬
"""
        await send_telegram_message(chat_id, message)
    
    else:
        message = f"""
❓ לא הכרתי את הפקודה: {command}

נסה:
/help לרשימת פקודות
או שאל שאלה ישירות
"""
        await send_telegram_message(chat_id, message)


async def trigger_escalation(customer: Customer, conversation: Conversation, ai_result: Dict[str, Any]):
    """Trigger human escalation via webhook."""
    if not settings.human_escalation_webhook_url:
        return
    
    payload = {
        "source": "telegram",
        "customer_id": customer.id,
        "telegram_id": customer.telegram_id,
        "telegram_username": customer.telegram_username,
        "conversation_id": conversation.id,
        "reason": "ai_blackout_or_escalation",
        "ai_result": ai_result,
        "priority": "high",
        "brand": BRAND_NAME
    }
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                settings.human_escalation_webhook_url,
                json=payload,
                timeout=10.0
            )
        logger.info(f"Escalation triggered for customer {customer.id}")
    except Exception as e:
        logger.error(f"Failed to trigger escalation: {e}")


@router.post("/set-webhook")
async def set_webhook(url: str):
    """Set the Telegram webhook URL."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")
    
    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, json={"url": url})
            result = response.json()
            
            if result.get("ok"):
                return {"status": "ok", "webhook_url": url}
            else:
                raise HTTPException(status_code=400, detail=result.get("description"))
                
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook-info")
async def get_webhook_info():
    """Get current webhook info."""
    if not settings.telegram_bot_token:
        raise HTTPException(status_code=400, detail="Telegram bot token not configured")
    
    api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getWebhookInfo"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)
            return response.json()
    except Exception as e:
        logger.error(f"Error getting webhook info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/broadcast")
async def broadcast_message(message: str, parse_mode: str = "Markdown"):
    """Broadcast message to all Telegram users (admin only)."""
    # This would typically require admin authentication
    async with get_db_context() as session:
        from sqlalchemy import select
        from src.database.models import Customer
        
        stmt = select(Customer).where(Customer.telegram_id.isnot(None))
        result = await session.execute(stmt)
        customers = result.scalars().all()
        
        sent_count = 0
        for customer in customers:
            try:
                if await send_telegram_message(int(customer.telegram_id), message, parse_mode):
                    sent_count += 1
            except:
                pass
        
        return {"status": "ok", "sent": sent_count, "total": len(customers)}
