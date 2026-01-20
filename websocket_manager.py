"""
WebSocket Manager for Real-Time Blockchain Updates
Connects to Tendermint WebSocket and broadcasts to explorer clients
"""

import asyncio
import json
import logging
from typing import Set, Dict, Any, Optional
from datetime import datetime

import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class TendermintWebSocketClient:
    """Connect to Tendermint WebSocket for real-time events"""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url.replace("http://", "ws://").replace("https://", "wss://")
        if not self.ws_url.endswith("/websocket"):
            self.ws_url += "/websocket"

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.subscriptions: Set[str] = set()
        self.handlers: Dict[str, callable] = {}

    async def connect(self):
        """Connect to Tendermint WebSocket"""
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.running = True
            logger.info(f"Connected to Tendermint WebSocket: {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Tendermint WebSocket: {e}")
            return False

    async def subscribe(self, query: str):
        """Subscribe to Tendermint events"""
        if not self.ws:
            raise RuntimeError("Not connected to WebSocket")

        subscription_id = f"sub_{len(self.subscriptions)}"
        message = {
            "jsonrpc": "2.0",
            "method": "subscribe",
            "id": subscription_id,
            "params": {"query": query},
        }

        await self.ws.send(json.dumps(message))
        self.subscriptions.add(query)
        logger.info(f"Subscribed to: {query}")

    async def listen(self):
        """Listen for WebSocket messages"""
        if not self.ws:
            raise RuntimeError("Not connected to WebSocket")

        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self.handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse WebSocket message: {e}")
                except Exception as e:
                    logger.error(f"Error handling WebSocket message: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.running = False
        except Exception as e:
            logger.error(f"WebSocket listen error: {e}")
            self.running = False

    async def handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message"""
        if "result" in data and isinstance(data["result"], dict):
            result = data["result"]

            # Extract event data
            if "data" in result:
                event_data = result["data"]
                event_type = event_data.get("type", "unknown")

                # Route to appropriate handler
                handler = self.handlers.get(event_type)
                if handler:
                    await handler(event_data)
                else:
                    logger.debug(f"No handler for event type: {event_type}")

    def register_handler(self, event_type: str, handler: callable):
        """Register event handler"""
        self.handlers[event_type] = handler

    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Disconnected from Tendermint WebSocket")


class ExplorerWebSocketServer:
    """WebSocket server for broadcasting updates to explorer clients"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8083):
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.server = None

    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register new client"""
        self.clients.add(websocket)
        logger.info(f"Client connected. Total clients: {len(self.clients)}")

        try:
            # Send initial connection message
            await websocket.send(
                json.dumps(
                    {
                        "type": "connection",
                        "status": "connected",
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )
            )

            # Keep connection alive
            async for message in websocket:
                # Handle client messages (ping/pong, subscriptions)
                try:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "pong",
                                    "timestamp": datetime.utcnow().isoformat(),
                                }
                            )
                        )
                except Exception as e:
                    logger.error(f"Error handling client message: {e}")

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.clients)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        if not self.clients:
            return

        message_str = json.dumps(message)
        disconnected = set()

        for client in self.clients:
            try:
                await client.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                disconnected.add(client)

        # Clean up disconnected clients
        self.clients -= disconnected

    async def broadcast_new_block(self, block_data: Dict[str, Any]):
        """Broadcast new block event"""
        await self.broadcast(
            {
                "type": "new_block",
                "data": block_data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    async def broadcast_new_transaction(self, tx_data: Dict[str, Any]):
        """Broadcast new transaction event"""
        await self.broadcast(
            {
                "type": "new_transaction",
                "data": tx_data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    async def broadcast_validator_update(self, validator_data: Dict[str, Any]):
        """Broadcast validator set update"""
        await self.broadcast(
            {
                "type": "validator_update",
                "data": validator_data,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    async def start(self):
        """Start WebSocket server"""
        self.server = await websockets.serve(self.register_client, self.host, self.port)
        logger.info(
            f"Explorer WebSocket server started on ws://{self.host}:{self.port}"
        )

    async def stop(self):
        """Stop WebSocket server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("Explorer WebSocket server stopped")


class WebSocketManager:
    """
    Manages WebSocket connections between Tendermint and explorer clients
    Bridges real-time blockchain events to explorer frontend
    """

    def __init__(
        self, tendermint_url: str, server_host: str = "0.0.0.0", server_port: int = 8083
    ):
        self.tm_client = TendermintWebSocketClient(tendermint_url)
        self.server = ExplorerWebSocketServer(server_host, server_port)
        self.running = False

    async def initialize(self):
        """Initialize WebSocket connections"""
        # Connect to Tendermint
        connected = await self.tm_client.connect()
        if not connected:
            raise RuntimeError("Failed to connect to Tendermint WebSocket")

        # Subscribe to events
        await self.tm_client.subscribe("tm.event='NewBlock'")
        await self.tm_client.subscribe("tm.event='Tx'")
        await self.tm_client.subscribe("tm.event='ValidatorSetUpdates'")

        # Register event handlers
        self.tm_client.register_handler("NewBlock", self.handle_new_block)
        self.tm_client.register_handler("Tx", self.handle_new_transaction)
        self.tm_client.register_handler(
            "ValidatorSetUpdates", self.handle_validator_update
        )

        # Start server
        await self.server.start()

        logger.info("WebSocket manager initialized")

    async def handle_new_block(self, event_data: Dict[str, Any]):
        """Handle new block event from Tendermint"""
        try:
            block = event_data.get("value", {}).get("block", {})
            header = block.get("header", {})

            block_info = {
                "height": int(header.get("height", 0)),
                "hash": header.get("last_block_id", {}).get("hash", ""),
                "time": header.get("time", ""),
                "proposer": header.get("proposer_address", ""),
                "num_txs": len(block.get("data", {}).get("txs", [])),
            }

            logger.info(f"New block: {block_info['height']}")
            await self.server.broadcast_new_block(block_info)

        except Exception as e:
            logger.error(f"Error handling new block: {e}")

    async def handle_new_transaction(self, event_data: Dict[str, Any]):
        """Handle new transaction event from Tendermint"""
        try:
            tx_result = event_data.get("value", {}).get("TxResult", {})

            tx_info = {
                "hash": tx_result.get("tx", ""),
                "height": int(tx_result.get("height", 0)),
                "index": tx_result.get("index", 0),
                "result": tx_result.get("result", {}),
            }

            logger.debug(f"New transaction: {tx_info['hash'][:16]}...")
            await self.server.broadcast_new_transaction(tx_info)

        except Exception as e:
            logger.error(f"Error handling new transaction: {e}")

    async def handle_validator_update(self, event_data: Dict[str, Any]):
        """Handle validator set update event"""
        try:
            updates = event_data.get("value", {}).get("ValidatorUpdates", [])

            validator_info = {"updates": updates, "num_updates": len(updates)}

            logger.info(f"Validator update: {validator_info['num_updates']} validators")
            await self.server.broadcast_validator_update(validator_info)

        except Exception as e:
            logger.error(f"Error handling validator update: {e}")

    async def run(self):
        """Main run loop"""
        self.running = True

        await self.initialize()

        # Listen for Tendermint events
        try:
            await self.tm_client.listen()
        except Exception as e:
            logger.error(f"WebSocket manager error: {e}")
        finally:
            await self.stop()

    async def stop(self):
        """Stop WebSocket manager"""
        logger.info("Stopping WebSocket manager...")
        self.running = False
        await self.tm_client.disconnect()
        await self.server.stop()
        logger.info("WebSocket manager stopped")


async def main():
    """Main entry point for standalone WebSocket manager"""
    import os

    tendermint_url = os.getenv("NODE_RPC_URL", "http://localhost:26657")
    server_host = os.getenv("WS_HOST", "0.0.0.0")
    server_port = int(os.getenv("WS_PORT", "8083"))

    manager = WebSocketManager(tendermint_url, server_host, server_port)

    try:
        await manager.run()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await manager.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
