"""Saturnite Transport Platform Adapter for Hermes Gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from gateway.platforms.base import BasePlatformAdapter, SendResult
from gateway.platforms.event import MessageEvent, MessageType
from gateway.session import SessionSource

logger = logging.getLogger(__name__)


@dataclass
class SaturniteTransportConfig:
    transport_url: str = "ws://127.0.0.1:8765"
    connect_timeout: float = 30.0
    reconnect_interval: float = 5.0
    max_reconnect_attempts: int = 10
    message_timeout: float = 60.0
    heartbeat_interval: float = 30.0


@dataclass
class HermesTransportMessage:
    message_id: str
    session_id: str
    platform: str
    content: str
    message_type: str = "text"
    timestamp: str = field(default_factory=lambda: str(time.time()))
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class HermesTransportResponse:
    message_id: str
    status: str
    content: str
class SaturnitePlatformAdapter(BasePlatformAdapter):
    PLATFORM_NAME = "saturnite"
    PLATFORM_LABEL = "Saturnite Transport"
    
    def __init__(
        self,
        config: Optional[SaturniteTransportConfig] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._transport_config = config or SaturniteTransportConfig()
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._is_shutting_down = False
        self._pending_messages: Dict[str, asyncio.Future] = {}
        self._message_counter = 0
        
    async def connect(self, *, is_reconnect: bool = False) -> bool:
        url = self._transport_config.transport_url
        logger.info("Connecting to Saturnite transport at %s", url)
        
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    ping_interval=self._transport_config.heartbeat_interval,
                    ping_timeout=10.0,
                    close_timeout=10.0,
                ),
                timeout=self._transport_config.connect_timeout,
            )
            
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._reconnect_attempts = 0
            logger.info("Connected to Saturnite transport")
            return True
            
        except asyncio.TimeoutError:
            logger.error("Connection to Saturnite transport timed out after %.1fs",
                         self._transport_config.connect_timeout)
            return False
        except (ConnectionRefusedError, WebSocketException, OSError) as e:
            logger.error("Failed to connect to Saturnite transport: %s", e)
            return False
    
    async def disconnect(self) -> None:
        logger.info("Disconnecting from Saturnite transport")
        self._is_shutting_down = True
        
        for task in (self._receive_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception as e:
                logger.warning("Error closing WebSocket: %s", e)
        
        for future in self._pending_messages.values():
            if not future.done():
                future.set_exception(ConnectionError("Transport disconnected"))
        self._pending_messages.clear()
        
        self._ws = None
        logger.info("Disconnected from Saturnite transport")
# --- Message handling ---
    
    async def _receive_loop(self) -> None:
        try:
            async for message in self._ws:
                if self._is_shutting_down:
                    break
                    
                if isinstance(message, str):
                    await self._handle_inbound_message(message)
                elif isinstance(message, bytes):
                    logger.warning("Received binary message, expected text")
                    
        except ConnectionClosed:
            logger.info("Transport connection closed")
        except WebSocketException as e:
            logger.error("WebSocket error in receive loop: %s", e)
        except Exception as e:
            logger.exception("Unexpected error in receive loop: %s", e)
        finally:
            if not self._is_shutting_down:
                asyncio.create_task(self._attempt_reconnect())
    
    async def _heartbeat_loop(self) -> None:
        while not self._is_shutting_down:
            try:
                await asyncio.sleep(self._transport_config.heartbeat_interval)
                if self._ws and not self._ws.closed:
                    await self._ws.ping()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Heartbeat error: %s", e)
    
    async def _attempt_reconnect(self) -> None:
        if self._is_shutting_down:
            return
            
        max_attempts = self._transport_config.max_reconnect_attempts
        interval = self._transport_config.reconnect_interval
        
        while self._reconnect_attempts < max_attempts and not self._is_shutting_down:
            self._reconnect_attempts += 1
            logger.info("Reconnection attempt %d/%d", self._reconnect_attempts, max_attempts)
            
            await asyncio.sleep(interval)
            
            if await self.connect(is_reconnect=True):
                logger.info("Reconnected to Saturnite transport")
                return
                
        logger.error("Failed to reconnect after %d attempts", max_attempts)
        await self._notify_fatal_error()
    
    async def _handle_inbound_message(self, raw_message: str) -> None:
        try:
            data = json.loads(raw_message)
            transport_msg = HermesTransportMessage(**data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to parse inbound message: %s", e)
            return
            
        source = self.build_source(
            chat_id=transport_msg.session_id,
            user_id=transport_msg.metadata.get("user_id"),
            user_name=transport_msg.metadata.get("user_name"),
            chat_name=transport_msg.metadata.get("chat_name"),
            chat_type=transport_msg.metadata.get("chat_type", "dm"),
        )
        
        event = MessageEvent(
            text=transport_msg.content,
            message_type=MessageType.TEXT,
            source=source,
            message_id=transport_msg.message_id,
            raw_message=data,
        )
        
        await self.handle_message(event)
    
    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SendResult:
        if not self._ws or self._ws.closed:
            logger.error("Cannot send: transport not connected")
            return SendResult(
                success=False,
                message_id=None,
                error="Transport not connected"
            )
            
        self._message_counter += 1
        message_id = f"sat-{int(time.time()*1000)}-{self._message_counter}"
        
        transport_msg = HermesTransportMessage(
            message_id=message_id,
            session_id=chat_id,
            platform=self.PLATFORM_NAME,
            content=content,
            message_type="text",
            metadata={
                "reply_to": reply_to or "",
                **(metadata or {}),
            },
        )
        
        try:
            await asyncio.wait_for(
                self._ws.send(json.dumps(transport_msg.__dict__)),
                timeout=self._transport_config.message_timeout,
            )
            
            return SendResult(
                success=True,
                message_id=message_id,
                error=None,
            )
            
        except asyncio.TimeoutError:
            logger.error("Send timeout for message %s", message_id)
            return SendResult(
                success=False,
                message_id=message_id,
                error="Send timeout"
            )
        except (ConnectionClosed, WebSocketException) as e:
            logger.error("Send failed: %s", e)
            return SendResult(
                success=False,
                message_id=message_id,
                error=f"Transport error: {e}"
            )
    
    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        return {
            "name": chat_id,
            "type": "dm",
            "platform": self.PLATFORM_NAME,
        }
    
    def build_source(
        self,
        chat_id: str,
        user_id: Optional[str] = None,
        user_name: Optional[str] = None,
        chat_name: Optional[str] = None,
        chat_type: str = "dm",
        **kwargs
    ) -> SessionSource:
        return SessionSource(
            platform=self.PLATFORM_NAME,
            chat_id=chat_id,
            chat_name=chat_name or chat_id,
            chat_type=chat_type,
            user_id=user_id,
            user_name=user_name,
            profile=self._owner_profile,
        )
    
    def is_connected(self) -> bool:
        return self._ws is not None and not self._ws.closed
def register(ctx):
    def env_enablement() -> Optional[Dict[str, str]]:
        transport_url = os.getenv("SATURNITE_TRANSPORT_URL")
        if not transport_url:
            return None
            
        extra = {"transport_url": transport_url}
        
        timeout = os.getenv("SATURNITE_TRANSPORT_TIMEOUT")
        if timeout:
            try:
                extra["connect_timeout"] = float(timeout)
            except ValueError:
                pass
                
        reconnect = os.getenv("SATURNITE_RECONNECT_INTERVAL")
        if reconnect:
            try:
                extra["reconnect_interval"] = float(reconnect)
            except ValueError:
                pass
                
        return extra
    
    def build_adapter(config, *, owner_profile: str, **kwargs) -> 'SaturnitePlatformAdapter':
        transport_config = SaturniteTransportConfig(
            transport_url=config.extra.get("transport_url", "ws://127.0.0.1:8765"),
            connect_timeout=config.extra.get("connect_timeout", 30.0),
            reconnect_interval=config.extra.get("reconnect_interval", 5.0),
        )
        
        return SaturnitePlatformAdapter(
            config=transport_config,
            owner_profile=owner_profile,
            **kwargs
        )
    
    ctx.register_platform(
        key="saturnite",
        label="Saturnite Transport",
        build_adapter=build_adapter,
        env_enablement_fn=env_enablement,
        cron_deliver_env_var="SATURNITE_HOME_CHANNEL",
    )
    error: str = ""