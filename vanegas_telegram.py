"""
VANEGAS - Telegram (Solo Alertas Proactivas)
Solo envía notificaciones al usuario; toda la interacción es vía web.
"""

import os
import logging

logger = logging.getLogger(__name__)


class VanegasTelegram:
    """Envía alertas proactivas vía Telegram. No recibe comandos."""

    def __init__(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._bot = None

        if token and self.chat_id:
            try:
                # Import lazy para no fallar si la lib no está instalada
                import telegram
                self._bot = telegram.Bot(token=token)
                logger.info("Telegram bot inicializado para alertas")
            except Exception as e:
                logger.warning(f"Telegram no disponible: {e}")
        else:
            logger.warning("TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID no configurados — alertas desactivadas")

    async def send_notification(self, message: str):
        """
        Envía un mensaje de alerta al usuario.
        Llamado desde el monitor proactivo cuando hay algo importante.
        """
        if not self._bot or not self.chat_id:
            logger.debug("Telegram no configurado, alerta ignorada")
            return

        # Telegram tiene límite de 4096 chars por mensaje
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            try:
                await self._bot.send_message(
                    chat_id=self.chat_id,
                    text=chunk,
                    parse_mode="Markdown"
                )
            except Exception as e:
                # Fallback sin markdown si falla el formateo
                try:
                    await self._bot.send_message(chat_id=self.chat_id, text=chunk)
                except Exception as e2:
                    logger.error(f"Error enviando alerta Telegram: {e2}")
