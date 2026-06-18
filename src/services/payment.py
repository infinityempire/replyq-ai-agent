"""
ReplyQ AI Agent - Payment Service (Stripe Integration)
"""
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from loguru import logger
from stripe import StripeClient
from stripe.models import Price, PaymentLink, PaymentIntent

from config.settings import get_settings
from src.database.connection import get_db_context
from src.database.models import PaymentLink as PaymentLinkModel, Customer

settings = get_settings()


class PaymentService:
    """Service for handling payment operations with Stripe."""

    def __init__(self):
        if settings.stripe_api_key:
            self.stripe = StripeClient(settings.stripe_api_key)
        else:
            self.stripe = None
            logger.warning("Stripe API key not configured")

    async def create_payment_link(
        self,
        customer_id: str,
        amount: float,
        currency: str,
        description: str,
        expires_in_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Create a Stripe payment link for a customer.
        
        Args:
            customer_id: Customer ID in database
            amount: Amount in smallest currency unit (e.g., cents)
            currency: Currency code (e.g., 'USD', 'BRL')
            description: Description of the payment
            expires_in_hours: Hours until link expires
            
        Returns:
            Dict with payment link details
        """
        if not self.stripe:
            return {
                "success": False,
                "error": "Stripe not configured"
            }

        try:
            # Get customer from database
            async with get_db_context() as session:
                from sqlalchemy import select
                stmt = select(Customer).where(Customer.id == customer_id)
                result = await session.execute(stmt)
                customer = result.scalar_one_or_none()
                
                if not customer:
                    return {
                        "success": False,
                        "error": "Customer not found"
                    }
            
            # Create Stripe Payment Link
            # Convert to cents for Stripe
            amount_cents = int(amount * 100)
            
            # Create a price/product inline
            product = self.stripe.products.create(
                name=description[:100],  # Stripe product name limit
                metadata={"customer_id": customer_id}
            )
            
            price = self.stripe.prices.create(
                product=product.id,
                unit_amount=amount_cents,
                currency=currency.lower()
            )
            
            payment_link = self.stripe.payment_links.payment_link_create(
                line_items=[{"price": price.id, "quantity": 1}],
                metadata={"customer_id": customer_id},
                after_completion={"type": "hosted_confirmation", "custom_message": "Obrigado pelo pagamento!"}
            )
            
            # Calculate expiration
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
            
            # Store in database
            async with get_db_context() as session:
                db_payment = PaymentLinkModel(
                    id=f"pay_{hashlib.md5(payment_link.id.encode()).hexdigest()[:12]}",
                    customer_id=customer_id,
                    amount=amount,
                    currency=currency.upper(),
                    description=description,
                    stripe_payment_intent_id=payment_link.id,
                    payment_link_url=payment_link.url,
                    status="pending",
                    expires_at=expires_at
                )
                session.add(db_payment)
                await session.commit()
            
            logger.info(f"Payment link created for customer {customer_id}: {payment_link.url}")
            
            return {
                "success": True,
                "payment_link_id": db_payment.id,
                "payment_link_url": payment_link.url,
                "expires_at": expires_at.isoformat(),
                "message": f"Link de pagamento criado: {payment_link.url}"
            }
            
        except Exception as e:
            logger.error(f"Error creating payment link: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def create_payment_intent(
        self,
        customer_id: str,
        amount: float,
        currency: str,
        description: str
    ) -> Dict[str, Any]:
        """
        Create a Stripe PaymentIntent for more control.
        
        Args:
            customer_id: Customer ID
            amount: Amount in currency units (not cents)
            currency: Currency code
            
        Returns:
            Dict with PaymentIntent details
        """
        if not self.stripe:
            return {
                "success": False,
                "error": "Stripe not configured"
            }

        try:
            # Get customer from database
            async with get_db_context() as session:
                from sqlalchemy import select
                stmt = select(Customer).where(Customer.id == customer_id)
                result = await session.execute(stmt)
                customer = result.scalar_one_or_none()
            
            # Convert to cents
            amount_cents = int(amount * 100)
            
            # Create PaymentIntent
            intent = self.stripe.payment_intents.payment_intent_create(
                amount=amount_cents,
                currency=currency.lower(),
                metadata={
                    "customer_id": customer_id,
                    "description": description
                },
                automatic_payment_methods={"enabled": True}
            )
            
            # Store in database
            async with get_db_context() as session:
                db_payment = PaymentLinkModel(
                    id=f"pi_{hashlib.md5(intent.id.encode()).hexdigest()[:12]}",
                    customer_id=customer_id,
                    amount=amount,
                    currency=currency.upper(),
                    description=description,
                    stripe_payment_intent_id=intent.id,
                    status="pending"
                )
                session.add(db_payment)
                await session.commit()
            
            return {
                "success": True,
                "payment_intent_id": intent.id,
                "client_secret": intent.client_secret,
                "message": "PaymentIntent criado com sucesso"
            }
            
        except Exception as e:
            logger.error(f"Error creating PaymentIntent: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def check_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """Check the status of a payment."""
        async with get_db_context() as session:
            from sqlalchemy import select
            stmt = select(PaymentLinkModel).where(PaymentLinkModel.id == payment_id)
            result = await session.execute(stmt)
            payment = result.scalar_one_or_none()
            
            if not payment:
                return {"success": False, "error": "Payment not found"}
            
            return {
                "success": True,
                "payment_id": payment.id,
                "status": payment.status,
                "amount": payment.amount,
                "currency": payment.currency,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
                "paid_at": payment.paid_at.isoformat() if payment.paid_at else None
            }

    async def handle_payment_webhook(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle Stripe webhook events.
        
        Args:
            event_data: Stripe webhook event data
            
        Returns:
            Result of webhook processing
        """
        try:
            event_type = event_data.get("type")
            data = event_data.get("data", {}).get("object", {})
            
            payment_intent_id = data.get("id")
            
            # Find payment in database
            async with get_db_context() as session:
                from sqlalchemy import select
                stmt = select(PaymentLinkModel).where(
                    PaymentLinkModel.stripe_payment_intent_id == payment_intent_id
                )
                result = await session.execute(stmt)
                payment = result.scalar_one_or_none()
                
                if not payment:
                    return {"success": False, "error": "Payment not found in database"}
                
                if event_type == "payment_intent.succeeded":
                    payment.status = "paid"
                    payment.paid_at = datetime.utcnow()
                    logger.info(f"Payment succeeded: {payment_intent_id}")
                    
                elif event_type == "payment_intent.payment_failed":
                    payment.status = "failed"
                    logger.warning(f"Payment failed: {payment_intent_id}")
                    
                elif event_type == "payment_intent.canceled":
                    payment.status = "cancelled"
                    logger.info(f"Payment cancelled: {payment_intent_id}")
                
                await session.commit()
                
                return {
                    "success": True,
                    "event_type": event_type,
                    "payment_id": payment.id,
                    "new_status": payment.status
                }
                
        except Exception as e:
            logger.error(f"Error handling payment webhook: {e}")
            return {"success": False, "error": str(e)}

    async def get_customer_payments(self, customer_id: str) -> List[Dict[str, Any]]:
        """Get all payments for a customer."""
        async with get_db_context() as session:
            from sqlalchemy import select
            stmt = select(PaymentLinkModel).where(
                PaymentLinkModel.customer_id == customer_id
            ).order_by(PaymentLinkModel.created_at.desc())
            result = await session.execute(stmt)
            payments = result.scalars().all()
            
            return [
                {
                    "id": p.id,
                    "amount": p.amount,
                    "currency": p.currency,
                    "description": p.description,
                    "status": p.status,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "paid_at": p.paid_at.isoformat() if p.paid_at else None
                }
                for p in payments
            ]

    async def cancel_payment_link(self, payment_id: str) -> Dict[str, Any]:
        """Cancel a pending payment link."""
        if not self.stripe:
            return {"success": False, "error": "Stripe not configured"}

        try:
            async with get_db_context() as session:
                from sqlalchemy import select
                stmt = select(PaymentLinkModel).where(PaymentLinkModel.id == payment_id)
                result = await session.execute(stmt)
                payment = result.scalar_one_or_none()
                
                if not payment:
                    return {"success": False, "error": "Payment not found"}
                
                if payment.status != "pending":
                    return {"success": False, "error": f"Cannot cancel payment with status: {payment.status}"}
                
                # If it's a payment link, we can't really cancel it, just mark as cancelled
                payment.status = "cancelled"
                await session.commit()
                
                return {
                    "success": True,
                    "payment_id": payment_id,
                    "message": "Pagamento cancelado"
                }
                
        except Exception as e:
            logger.error(f"Error cancelling payment: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
_payment_service: Optional[PaymentService] = None


def get_payment_service() -> PaymentService:
    """Get the singleton payment service instance."""
    global _payment_service
    if _payment_service is None:
        _payment_service = PaymentService()
    return _payment_service
