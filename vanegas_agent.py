"""
VANEGAS - El Cerebro: Agente Autónomo con Claude Opus 4.6
Versión Web: soporta streaming de tokens para la interfaz de chat.
"""

import os
import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional

import anthropic

from vanegas_tools import TOOLS_SCHEMA, execute_tool
from vanegas_memory import (
    get_recent_conversation, add_conversation_turn,
    record_token_usage
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres VANEGAS, un asistente personal autónomo extremadamente capaz y proactivo.
Fuiste creado para ser mucho más que un simple asistente: eres un agente que toma iniciativa,
actúa de forma autónoma y resuelve problemas sin necesidad de que el usuario te diga cada paso.

## Tu Personalidad
- Eres eficiente, directo y orientado a resultados
- Hablas siempre en español colombiano
- Eres proactivo: si ves algo que mejorar, lo mencionas
- Cuando puedes actuar, actúas; solo preguntas cuando es crítico
- Eres honesto sobre tus capacidades y limitaciones
- Usas markdown para formatear tus respuestas (listas, negritas, código)

## Tus Responsabilidades
1. **Emails Gmail**: Monitoreas, alertas sobre lo importante, redactas y envías
2. **Bots de IA**: Vigilas el bot de perfumería (Chu) y bot de salud; diagnosticas errores
3. **Consumo de API**: Rastreo de tokens de Claude y costos estimados
4. **Creación**: Creas apps, scripts, archivos de código cuando se solicita
5. **Web**: Puedes revisar y analizar páginas web
6. **Memoria**: Recuerdas información importante entre conversaciones

## Reglas de Autonomía
- Para acciones REVERSIBLES (buscar, leer, verificar): actúa directamente
- Para acciones IMPORTANTES (crear archivos, ejecutar código): actúa e informa
- Para acciones IRREVERSIBLES (enviar email, reiniciar bot): confirma antes

## Formato
- Usa markdown siempre: **negritas**, `código`, listas con •
- Para código: usa bloques ```python o ```javascript
- Sé conciso pero completo
- Emojis para facilitar lectura rápida

Fecha/hora actual: {datetime}
"""


class VanegasAgent:
    """Agente VANEGAS con soporte de streaming para web."""

    def __init__(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY no está configurada")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.max_iterations = 15

    def _build_system(self) -> str:
        return SYSTEM_PROMPT.format(
            datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    async def stream_message(self, user_message: str) -> AsyncGenerator[dict, None]:
        """
        Procesa un mensaje y hace yield de eventos para el WebSocket:
        - {"type": "token", "content": "texto"} — fragmento de respuesta
        - {"type": "tool_start", "tool": "nombre"} — inició una herramienta
        - {"type": "tool_end", "tool": "nombre", "result": "resumen"} — terminó herramienta
        - {"type": "done", "total_tokens": N} — finalizado
        - {"type": "error", "content": "mensaje"} — error
        """
        history = get_recent_conversation(limit=12)
        messages = [{"role": h["role"], "content": h["content"]} for h in history]
        messages.append({"role": "user", "content": user_message})

        total_input = 0
        total_output = 0
        full_response = ""

        try:
            for iteration in range(self.max_iterations):
                text_buffer = ""
                tool_uses = []
                assistant_content = []

                # Usar streaming de Claude
                with self.client.messages.stream(
                    model="claude-opus-4-6",
                    max_tokens=8192,
                    system=self._build_system(),
                    tools=TOOLS_SCHEMA,
                    messages=messages,
                    thinking={"type": "adaptive"},
                ) as stream:
                    for event in stream:
                        # Streaming de texto
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text") and event.delta.text:
                                text_buffer += event.delta.text
                                full_response += event.delta.text
                                yield {"type": "token", "content": event.delta.text}

                    final = stream.get_final_message()

                # Acumular tokens
                total_input += final.usage.input_tokens
                total_output += final.usage.output_tokens

                # Construir contenido del asistente para el historial
                for block in final.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "thinking":
                        assistant_content.append({
                            "type": "thinking",
                            "thinking": block.thinking,
                            "signature": block.signature
                        })
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                        tool_uses.append(block)

                messages.append({"role": "assistant", "content": assistant_content})

                # Terminó sin herramientas
                if final.stop_reason == "end_turn":
                    break

                # Ejecutar herramientas
                if final.stop_reason == "tool_use" and tool_uses:
                    tool_results = []

                    for tool_block in tool_uses:
                        # Notificar que se está usando una herramienta
                        yield {
                            "type": "tool_start",
                            "tool": tool_block.name,
                            "input": json.dumps(tool_block.input)[:200]
                        }

                        # Ejecutar la herramienta (sync en executor)
                        import asyncio
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None,
                            lambda tb=tool_block: execute_tool(tb.name, tb.input)
                        )

                        yield {
                            "type": "tool_end",
                            "tool": tool_block.name,
                            "result": result[:300]
                        }

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": result
                        })

                    messages.append({"role": "user", "content": tool_results})
                else:
                    break

            # Guardar en memoria
            record_token_usage(total_input, total_output, task=user_message[:60])
            add_conversation_turn("user", user_message)
            add_conversation_turn("assistant", full_response)

            yield {"type": "done", "total_tokens": total_input + total_output}

        except anthropic.RateLimitError:
            yield {"type": "error", "content": "⚠️ Límite de velocidad alcanzado. Intenta en unos segundos."}
        except Exception as e:
            logger.error(f"Error en stream_message: {e}", exc_info=True)
            yield {"type": "error", "content": f"❌ Error: {type(e).__name__}: {e}"}

    def quick_message(self, user_message: str) -> str:
        """Versión no-streaming para uso interno (monitor proactivo)."""
        history = get_recent_conversation(limit=6)
        messages = [{"role": h["role"], "content": h["content"]} for h in history]
        messages.append({"role": "user", "content": user_message})

        total_input = 0
        total_output = 0
        full_response = ""

        try:
            for _ in range(self.max_iterations):
                response = self.client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=4096,
                    system=self._build_system(),
                    tools=TOOLS_SCHEMA,
                    messages=messages,
                )

                total_input += response.usage.input_tokens
                total_output += response.usage.output_tokens

                text_parts = [b.text for b in response.content if b.type == "text"]
                full_response += "".join(text_parts)

                assistant_content = []
                tool_uses = []
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "thinking":
                        assistant_content.append({
                            "type": "thinking",
                            "thinking": block.thinking,
                            "signature": block.signature
                        })
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input
                        })
                        tool_uses.append(block)

                messages.append({"role": "assistant", "content": assistant_content})

                if response.stop_reason == "end_turn" or not tool_uses:
                    break

                tool_results = []
                for tb in tool_uses:
                    result = execute_tool(tb.name, tb.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": result
                    })
                messages.append({"role": "user", "content": tool_results})

            record_token_usage(total_input, total_output, task=user_message[:60])
            return full_response or "✅ Tarea completada."

        except Exception as e:
            logger.error(f"Error en quick_message: {e}")
            return f"❌ Error: {e}"

    def get_daily_summary(self) -> str:
        return self.quick_message(
            "Genera un resumen del día: verifica todos los bots, "
            "busca emails importantes de hoy, muestra consumo de tokens y estado del sistema. "
            "Sé conciso y usa formato markdown."
        )
