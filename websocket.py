"""
WebSocket support for real-time block explorer updates
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from flask import Flask
from flask_sock import Sock

logger = logging.getLogger(__name__)


class WSMessageType(Enum):
    """WebSocket message types"""
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    NEW_BLOCK = "new_block"
    NEW_TX = "new_transaction"
    ADDRESS_ACTIVITY = "address_activity"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


@dataclass
class WSMessage:
    """WebSocket message structure"""
    type: str
    data: Dict
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().timestamp()

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class SubscriptionManager:
    """Manages WebSocket subscriptions"""

    def __init__(self):
        self.subscriptions: Dict[str, Set] = {
            "blocks": set(),
            "transactions": set(),
            "addresses": {},  # address -> set of websockets
        }
        self._lock = asyncio.Lock()

    async def subscribe_blocks(self, ws) -> None:
        """Subscribe to new block notifications"""
        async with self._lock:
            self.subscriptions["blocks"].add(ws)
            logger.info(f"Client subscribed to blocks. Total: {len(self.subscriptions['blocks'])}")

    async def unsubscribe_blocks(self, ws) -> None:
        """Unsubscribe from block notifications"""
        async with self._lock:
            self.subscriptions["blocks"].discard(ws)
            logger.info(f"Client unsubscribed from blocks")

    async def subscribe_transactions(self, ws) -> None:
        """Subscribe to new transaction notifications"""
        async with self._lock:
            self.subscriptions["transactions"].add(ws)
            logger.info(f"Client subscribed to transactions. Total: {len(self.subscriptions['transactions'])}")

    async def unsubscribe_transactions(self, ws) -> None:
        """Unsubscribe from transaction notifications"""
        async with self._lock:
            self.subscriptions["transactions"].discard(ws)

    async def subscribe_address(self, ws, address: str) -> None:
        """Subscribe to address activity"""
        async with self._lock:
            if address not in self.subscriptions["addresses"]:
                self.subscriptions["addresses"][address] = set()
            self.subscriptions["addresses"][address].add(ws)
            logger.info(f"Client subscribed to address {address}")

    async def unsubscribe_address(self, ws, address: str) -> None:
        """Unsubscribe from address activity"""
        async with self._lock:
            if address in self.subscriptions["addresses"]:
                self.subscriptions["addresses"][address].discard(ws)
                if not self.subscriptions["addresses"][address]:
                    del self.subscriptions["addresses"][address]

    async def unsubscribe_all(self, ws) -> None:
        """Unsubscribe from all notifications"""
        async with self._lock:
            self.subscriptions["blocks"].discard(ws)
            self.subscriptions["transactions"].discard(ws)

            # Remove from all address subscriptions
            addresses_to_remove = []
            for address, subscribers in self.subscriptions["addresses"].items():
                subscribers.discard(ws)
                if not subscribers:
                    addresses_to_remove.append(address)

            for address in addresses_to_remove:
                del self.subscriptions["addresses"][address]

    def get_block_subscribers(self) -> Set:
        """Get all block subscribers"""
        return self.subscriptions["blocks"].copy()

    def get_transaction_subscribers(self) -> Set:
        """Get all transaction subscribers"""
        return self.subscriptions["transactions"].copy()

    def get_address_subscribers(self, address: str) -> Set:
        """Get subscribers for a specific address"""
        return self.subscriptions["addresses"].get(address, set()).copy()


class WebSocketHandler:
    """Handles WebSocket connections and broadcasts"""

    def __init__(self, app: Flask):
        self.sock = Sock(app)
        self.subscription_manager = SubscriptionManager()
        self.active_connections: Set = set()

        # Register WebSocket endpoint
        @self.sock.route('/ws')
        def websocket(ws):
            return self.handle_connection(ws)

    def handle_connection(self, ws):
        """Handle WebSocket connection"""
        self.active_connections.add(ws)
        logger.info(f"New WebSocket connection. Total: {len(self.active_connections)}")

        try:
            while True:
                message = ws.receive()
                if message is None:
                    break

                # Handle message
                asyncio.run(self.handle_message(ws, message))

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Clean up
            asyncio.run(self.subscription_manager.unsubscribe_all(ws))
            self.active_connections.discard(ws)
            logger.info(f"WebSocket disconnected. Remaining: {len(self.active_connections)}")

    async def handle_message(self, ws, raw_message: str) -> None:
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type")
            payload = data.get("data", {})

            if msg_type == WSMessageType.SUBSCRIBE.value:
                await self.handle_subscribe(ws, payload)
            elif msg_type == WSMessageType.UNSUBSCRIBE.value:
                await self.handle_unsubscribe(ws, payload)
            elif msg_type == WSMessageType.PING.value:
                await self.send_message(ws, WSMessage(
                    type=WSMessageType.PONG.value,
                    data={}
                ))
            else:
                await self.send_error(ws, f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            await self.send_error(ws, "Invalid JSON")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.send_error(ws, str(e))

    async def handle_subscribe(self, ws, payload: Dict) -> None:
        """Handle subscription request"""
        channel = payload.get("channel")

        if channel == "blocks":
            await self.subscription_manager.subscribe_blocks(ws)
            await self.send_message(ws, WSMessage(
                type="subscribed",
                data={"channel": "blocks"}
            ))
        elif channel == "transactions":
            await self.subscription_manager.subscribe_transactions(ws)
            await self.send_message(ws, WSMessage(
                type="subscribed",
                data={"channel": "transactions"}
            ))
        elif channel == "address":
            address = payload.get("address")
            if not address:
                await self.send_error(ws, "Address required for address subscription")
                return
            await self.subscription_manager.subscribe_address(ws, address)
            await self.send_message(ws, WSMessage(
                type="subscribed",
                data={"channel": "address", "address": address}
            ))
        else:
            await self.send_error(ws, f"Unknown channel: {channel}")

    async def handle_unsubscribe(self, ws, payload: Dict) -> None:
        """Handle unsubscribe request"""
        channel = payload.get("channel")

        if channel == "blocks":
            await self.subscription_manager.unsubscribe_blocks(ws)
        elif channel == "transactions":
            await self.subscription_manager.unsubscribe_transactions(ws)
        elif channel == "address":
            address = payload.get("address")
            if address:
                await self.subscription_manager.unsubscribe_address(ws, address)

        await self.send_message(ws, WSMessage(
            type="unsubscribed",
            data={"channel": channel}
        ))

    async def send_message(self, ws, message: WSMessage) -> None:
        """Send message to WebSocket"""
        try:
            ws.send(message.to_json())
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def send_error(self, ws, error: str) -> None:
        """Send error message to WebSocket"""
        await self.send_message(ws, WSMessage(
            type=WSMessageType.ERROR.value,
            data={"error": error}
        ))

    async def broadcast_new_block(self, block_data: Dict) -> None:
        """Broadcast new block to all subscribers"""
        message = WSMessage(
            type=WSMessageType.NEW_BLOCK.value,
            data=block_data
        )

        subscribers = self.subscription_manager.get_block_subscribers()
        logger.info(f"Broadcasting block to {len(subscribers)} subscribers")

        for ws in subscribers:
            try:
                ws.send(message.to_json())
            except Exception as e:
                logger.error(f"Error broadcasting to subscriber: {e}")
                self.active_connections.discard(ws)

    async def broadcast_new_transaction(self, tx_data: Dict) -> None:
        """Broadcast new transaction to all subscribers"""
        message = WSMessage(
            type=WSMessageType.NEW_TX.value,
            data=tx_data
        )

        subscribers = self.subscription_manager.get_transaction_subscribers()

        for ws in subscribers:
            try:
                ws.send(message.to_json())
            except Exception as e:
                logger.error(f"Error broadcasting to subscriber: {e}")

        # Also notify address subscribers if involved
        if "from" in tx_data:
            await self.notify_address_activity(tx_data["from"], tx_data)
        if "to" in tx_data:
            await self.notify_address_activity(tx_data["to"], tx_data)

    async def notify_address_activity(self, address: str, activity_data: Dict) -> None:
        """Notify subscribers of address activity"""
        message = WSMessage(
            type=WSMessageType.ADDRESS_ACTIVITY.value,
            data={"address": address, "activity": activity_data}
        )

        subscribers = self.subscription_manager.get_address_subscribers(address)

        for ws in subscribers:
            try:
                ws.send(message.to_json())
            except Exception as e:
                logger.error(f"Error notifying address subscriber: {e}")

    def get_stats(self) -> Dict:
        """Get WebSocket statistics"""
        return {
            "active_connections": len(self.active_connections),
            "block_subscribers": len(self.subscription_manager.subscriptions["blocks"]),
            "tx_subscribers": len(self.subscription_manager.subscriptions["transactions"]),
            "address_subscriptions": len(self.subscription_manager.subscriptions["addresses"]),
        }
