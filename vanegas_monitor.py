"""
VANEGAS - Módulo de Monitoreo Proactivo
Tareas programadas que VANEGAS ejecuta automáticamente.
"""

import asyncio
import logging
import os
from datetime import datetime

from vanegas_memory import (
    is_email_processed, mark_email_processed,
    get_token_stats, get_bot_status
)
from vanegas_gmail import search_emails, is_gmail_configured

logger = logging.getLogger(__name__)


class VanegasMonitor:
    """Gestiona todas las tareas proactivas de monitoreo."""

    def __init__(self, agent, send_notification):
        """
        agent: instancia de VanegasAgent
        send_notification: función async(message: str) para enviar notificación a Telegram
        """
        self.agent = agent
        self.send = send_notification
        self.email_interval = int(os.getenv("EMAIL_CHECK_INTERVAL", "15"))
        self.bot_interval = int(os.getenv("BOT_CHECK_INTERVAL", "10"))
        self.token_threshold = int(os.getenv("TOKEN_ALERT_THRESHOLD_DAILY", "1000000"))
        self._tasks = []

    async def start_all(self):
        """Inicia todas las tareas de monitoreo en background."""
        self._tasks = [
            asyncio.create_task(self._email_monitor_loop()),
            asyncio.create_task(self._bot_monitor_loop()),
            asyncio.create_task(self._token_monitor_loop()),
            asyncio.create_task(self._daily_summary_loop()),
        ]
        logger.info("✅ Monitoreo proactivo iniciado")

    async def stop_all(self):
        """Detiene todas las tareas de monitoreo."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("⛔ Monitoreo proactivo detenido")

    # ─────────────────────────────────────────────
    # MONITOR DE EMAILS
    # ─────────────────────────────────────────────

    async def _email_monitor_loop(self):
        """Revisa emails nuevos cada X minutos."""
        logger.info(f"📧 Monitor de emails iniciado (cada {self.email_interval} min)")

        while True:
            try:
                await self._check_new_emails()
            except Exception as e:
                logger.error(f"Error en monitor de emails: {e}")

            await asyncio.sleep(self.email_interval * 60)

    async def _check_new_emails(self):
        """Verifica si hay emails nuevos importantes."""
        if not is_gmail_configured():
            return

        try:
            emails = await asyncio.get_event_loop().run_in_executor(
                None, lambda: search_emails("is:unread", max_results=5)
            )

            if not emails or ("error" in emails[0]):
                return

            new_emails = []
            for email in emails:
                if not is_email_processed(email["id"]):
                    new_emails.append(email)
                    mark_email_processed(email["id"], email["asunto"], email["de"])

            if new_emails:
                msg = f"📧 *{len(new_emails)} email(s) nuevo(s)*\n\n"
                for e in new_emails[:3]:
                    msg += f"• *{e['asunto'][:60]}*\n"
                    msg += f"  De: {e['de'][:50]}\n"
                    msg += f"  {e['preview'][:100]}\n\n"

                if len(new_emails) > 3:
                    msg += f"_...y {len(new_emails) - 3} más_"

                await self.send(msg)
                logger.info(f"📧 Alertados {len(new_emails)} emails nuevos")

        except Exception as e:
            logger.error(f"Error chequeando emails: {e}")

    # ─────────────────────────────────────────────
    # MONITOR DE BOTS
    # ─────────────────────────────────────────────

    async def _bot_monitor_loop(self):
        """Verifica el estado de los bots cada X minutos."""
        logger.info(f"🤖 Monitor de bots iniciado (cada {self.bot_interval} min)")

        await asyncio.sleep(30)  # Esperar 30s al inicio antes del primer chequeo

        while True:
            try:
                await self._check_bots()
            except Exception as e:
                logger.error(f"Error en monitor de bots: {e}")

            await asyncio.sleep(self.bot_interval * 60)

    async def _check_bots(self):
        """Verifica si los bots están corriendo correctamente."""
        import psutil
        from pathlib import Path

        bots = [
            {
                "nombre": "perfumeria",
                "display": os.getenv("BOT_PERFUMERIA_NAME", "Chu (Perfumería)"),
                "path": os.getenv("BOT_PERFUMERIA_PATH", "../perfumeria-bot"),
                "script": os.getenv("BOT_PERFUMERIA_SCRIPT", "bot.js"),
            },
            {
                "nombre": "salud",
                "display": os.getenv("BOT_SALUD_NAME", "Bot Salud"),
                "path": os.getenv("BOT_SALUD_PATH", "../bot-salud"),
                "script": os.getenv("BOT_SALUD_SCRIPT", "index.js"),
            }
        ]

        for bot in bots:
            try:
                bot_path = Path(bot["path"])
                if not bot_path.exists():
                    continue  # Bot no configurado, omitir

                # Verificar si el proceso está corriendo
                proceso_activo = False
                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        cmdline = " ".join(proc.info.get("cmdline") or [])
                        if bot["script"] in cmdline:
                            proceso_activo = True
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                # Obtener estado previo para detectar cambios
                prev_status = get_bot_status(bot["display"])
                prev_running = prev_status and prev_status[0]["estado"] == "activo"

                if not proceso_activo:
                    if prev_running or not prev_status:
                        # Cambio de estado: estaba corriendo o es el primer chequeo
                        await self.send(
                            f"🚨 *ALERTA: {bot['display']} NO ESTÁ CORRIENDO*\n\n"
                            f"El bot `{bot['script']}` no se detecta como proceso activo.\n"
                            f"Usa: `/verificar_bot {bot['nombre']}` para diagnóstico completo."
                        )

                # Verificar errores en logs
                log_files = (
                    list(bot_path.glob("*.log")) +
                    list(bot_path.glob("logs/*.log"))
                )
                if log_files:
                    log_file = sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]
                    try:
                        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                            recent = f.readlines()[-10:]
                        errors = [l.strip() for l in recent
                                  if "error" in l.lower() and "favicon" not in l.lower()]
                        if len(errors) >= 3:
                            await self.send(
                                f"⚠️ *{bot['display']}: Errores detectados en logs*\n\n"
                                f"```\n{errors[-1][:300]}\n```\n"
                                f"Usa `/ver_logs {bot['nombre']}` para más detalles."
                            )
                    except Exception:
                        pass

            except Exception as e:
                logger.error(f"Error chequeando bot {bot['nombre']}: {e}")

    # ─────────────────────────────────────────────
    # MONITOR DE TOKENS
    # ─────────────────────────────────────────────

    async def _token_monitor_loop(self):
        """Verifica el consumo de tokens cada 2 horas."""
        logger.info("📊 Monitor de tokens iniciado")

        while True:
            await asyncio.sleep(2 * 3600)  # Cada 2 horas
            try:
                await self._check_token_usage()
            except Exception as e:
                logger.error(f"Error en monitor de tokens: {e}")

    async def _check_token_usage(self):
        """Alerta si el consumo de tokens supera el umbral diario."""
        stats = get_token_stats(days=1)
        total = stats["total_tokens"]

        if total > self.token_threshold:
            costo = stats["costo_estimado_usd"]
            await self.send(
                f"💸 *Alerta de consumo de tokens*\n\n"
                f"Has usado {total:,} tokens hoy (umbral: {self.token_threshold:,})\n"
                f"Costo estimado: ${costo:.4f} USD\n\n"
                f"Usa `/tokens` para ver el detalle."
            )

    # ─────────────────────────────────────────────
    # RESUMEN DIARIO
    # ─────────────────────────────────────────────

    async def _daily_summary_loop(self):
        """Envía resumen diario a las 8 AM."""
        logger.info("📅 Resumen diario programado para las 8:00 AM")

        while True:
            now = datetime.now()
            # Calcular segundos hasta las 8 AM del siguiente día
            target = now.replace(hour=8, minute=0, second=0, microsecond=0)
            if now.hour >= 8:
                from datetime import timedelta
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)

            try:
                await self.send("📅 *Generando resumen diario...*")
                summary = await asyncio.get_event_loop().run_in_executor(
                    None, self.agent.get_daily_summary
                )
                await self.send(f"📅 *Resumen del Día - {datetime.now().strftime('%d/%m/%Y')}*\n\n{summary}")
            except Exception as e:
                logger.error(f"Error en resumen diario: {e}")
                await self.send(f"❌ Error generando resumen diario: {e}")
