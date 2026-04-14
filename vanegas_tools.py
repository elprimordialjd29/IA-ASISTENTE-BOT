"""
VANEGAS - Definición e Implementación de Todas las Herramientas
Estas son las capacidades que VANEGAS puede usar de forma autónoma.
"""

import os
import json
import subprocess
import psutil
import requests
import tempfile
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from vanegas_memory import (
    save_memory, get_memory, list_memory_keys,
    record_token_usage, get_token_stats,
    update_bot_status, get_bot_status
)
from vanegas_gmail import (
    search_emails, read_email, send_email,
    create_draft, mark_as_read, is_gmail_configured
)


# ============================================================
# DEFINICIÓN DE HERRAMIENTAS PARA CLAUDE (input_schema)
# ============================================================

TOOLS_SCHEMA = [
    {
        "name": "buscar_emails",
        "description": "Busca y lista emails en Gmail. Úsalo para revisar correos nuevos, buscar mensajes específicos o verificar si hay algo importante.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta de búsqueda. Ejemplos: 'is:unread', 'from:cliente@email.com', 'subject:factura is:unread'"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo número de emails a retornar (1-20, default: 10)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "leer_email",
        "description": "Lee el contenido completo de un email específico usando su ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "ID del mensaje de Gmail obtenido con buscar_emails"
                }
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "enviar_email",
        "description": "Envía un email directamente. Úsalo cuando el usuario confirme que quiere enviar el mensaje.",
        "input_schema": {
            "type": "object",
            "properties": {
                "para": {"type": "string", "description": "Email del destinatario"},
                "asunto": {"type": "string", "description": "Asunto del email"},
                "cuerpo": {"type": "string", "description": "Contenido del email"}
            },
            "required": ["para", "asunto", "cuerpo"]
        }
    },
    {
        "name": "crear_borrador_email",
        "description": "Crea un borrador de email en Gmail (NO lo envía). Ideal para que el usuario lo revise antes de enviar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "para": {"type": "string", "description": "Email del destinatario"},
                "asunto": {"type": "string", "description": "Asunto del email"},
                "cuerpo": {"type": "string", "description": "Contenido del email"}
            },
            "required": ["para", "asunto", "cuerpo"]
        }
    },
    {
        "name": "verificar_bot",
        "description": "Verifica el estado y salud de un bot (perfumería, salud u otro). Revisa si está corriendo, sus logs y errores recientes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bot_nombre": {
                    "type": "string",
                    "description": "Nombre del bot: 'perfumeria', 'salud', o cualquier nombre configurado"
                }
            },
            "required": ["bot_nombre"]
        }
    },
    {
        "name": "ver_logs_bot",
        "description": "Lee las últimas líneas del archivo de log de un bot para diagnosticar errores.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bot_nombre": {"type": "string", "description": "Nombre del bot: 'perfumeria' o 'salud'"},
                "lineas": {"type": "integer", "description": "Número de líneas a leer (default: 50)"}
            },
            "required": ["bot_nombre"]
        }
    },
    {
        "name": "reiniciar_bot",
        "description": "Intenta reiniciar un bot que está fallando. SOLO úsalo si el usuario lo solicita o si hay errores críticos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bot_nombre": {"type": "string", "description": "Nombre del bot a reiniciar"}
            },
            "required": ["bot_nombre"]
        }
    },
    {
        "name": "ver_uso_tokens",
        "description": "Muestra estadísticas de consumo de tokens de la API de Claude (uso, costo estimado, tendencias).",
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Período en días: 1 (hoy), 7 (semana), 30 (mes). Default: 1"
                }
            }
        }
    },
    {
        "name": "crear_archivo",
        "description": "Crea un archivo con el contenido especificado. Puede ser código Python, JavaScript, HTML, un script, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta completa del archivo a crear (ej: data/mi_script.py)"},
                "contenido": {"type": "string", "description": "Contenido completo del archivo"},
                "descripcion": {"type": "string", "description": "Breve descripción de qué hace el archivo"}
            },
            "required": ["ruta", "contenido"]
        }
    },
    {
        "name": "leer_archivo",
        "description": "Lee el contenido de un archivo existente.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ruta": {"type": "string", "description": "Ruta del archivo a leer"},
                "lineas": {"type": "integer", "description": "Número de líneas a leer (0 = todo)"}
            },
            "required": ["ruta"]
        }
    },
    {
        "name": "ejecutar_python",
        "description": "Ejecuta código Python y devuelve el resultado. Úsalo para cálculos, análisis de datos, automatizaciones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "codigo": {"type": "string", "description": "Código Python a ejecutar"},
                "timeout": {"type": "integer", "description": "Tiempo máximo de ejecución en segundos (default: 30)"}
            },
            "required": ["codigo"]
        }
    },
    {
        "name": "navegar_web",
        "description": "Obtiene y analiza el contenido de una URL. Útil para revisar páginas web, verificar APIs, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL completa a consultar"},
                "solo_texto": {"type": "boolean", "description": "Si True, extrae solo el texto (sin HTML). Default: True"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "guardar_memoria",
        "description": "Guarda información importante en la memoria persistente de VANEGAS para recordarla en el futuro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clave": {"type": "string", "description": "Nombre identificador de la información"},
                "valor": {"description": "Valor a guardar (puede ser texto, número, lista u objeto)"}
            },
            "required": ["clave", "valor"]
        }
    },
    {
        "name": "recuperar_memoria",
        "description": "Recupera información guardada previamente en la memoria de VANEGAS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clave": {"type": "string", "description": "Nombre de la información a recuperar"}
            },
            "required": ["clave"]
        }
    },
    {
        "name": "listar_memoria",
        "description": "Lista todas las claves guardadas en la memoria de VANEGAS.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "estado_sistema",
        "description": "Obtiene el estado general del sistema: CPU, memoria RAM, disco disponible y procesos activos.",
        "input_schema": {"type": "object", "properties": {}}
    },
]


# ============================================================
# IMPLEMENTACIÓN DE HERRAMIENTAS
# ============================================================

def _get_bot_config(bot_nombre: str) -> dict:
    """Obtiene la configuración de un bot por nombre."""
    nombre = bot_nombre.lower()
    if "perfum" in nombre or nombre == "chu":
        return {
            "display_name": os.getenv("BOT_PERFUMERIA_NAME", "Chu (Perfumeria)"),
            "url": os.getenv("BOT_PERFUMERIA_URL", "https://perfumeria-bot-production.up.railway.app"),
        }
    elif "salud" in nombre or "health" in nombre:
        return {
            "display_name": os.getenv("BOT_SALUD_NAME", "Bot Salud"),
            "url": os.getenv("BOT_SALUD_URL", ""),
        }
    return None


def tool_buscar_emails(query: str = "is:unread", max_results: int = 10) -> str:
    if not is_gmail_configured():
        return "❌ Gmail no está configurado. Ejecuta: python setup_vanegas.py"

    emails = search_emails(query, max_results)
    if not emails:
        return f"📭 No se encontraron emails con: '{query}'"

    if emails and "error" in emails[0]:
        return f"❌ {emails[0]['error']}"

    result = f"📧 **{len(emails)} email(s) encontrados** (query: {query})\n\n"
    for i, e in enumerate(emails, 1):
        result += f"**{i}.** [{e['id'][:8]}...]\n"
        result += f"   De: {e['de']}\n"
        result += f"   Asunto: {e['asunto']}\n"
        result += f"   Fecha: {e['fecha']}\n"
        result += f"   Preview: {e['preview'][:150]}\n\n"

    return result


def tool_leer_email(message_id: str) -> str:
    if not is_gmail_configured():
        return "❌ Gmail no está configurado."

    email = read_email(message_id)
    if "error" in email:
        return f"❌ {email['error']}"

    return (
        f"📨 **Email completo**\n\n"
        f"**De:** {email['de']}\n"
        f"**Para:** {email['para']}\n"
        f"**Asunto:** {email['asunto']}\n"
        f"**Fecha:** {email['fecha']}\n"
        f"**Etiquetas:** {', '.join(email['etiquetas'])}\n\n"
        f"---\n{email['cuerpo']}"
    )


def tool_enviar_email(para: str, asunto: str, cuerpo: str) -> str:
    result = send_email(para, asunto, cuerpo)
    if result["ok"]:
        return f"✅ Email enviado exitosamente a {para}\nAsunto: {asunto}"
    return f"❌ Error al enviar: {result.get('error')}"


def tool_crear_borrador(para: str, asunto: str, cuerpo: str) -> str:
    result = create_draft(para, asunto, cuerpo)
    if result["ok"]:
        return f"📝 Borrador creado (ID: {result['draft_id']})\nPara: {para}\nAsunto: {asunto}"
    return f"❌ Error: {result.get('error')}"


def tool_verificar_bot(bot_nombre: str) -> str:
    """Verifica el estado de un bot via HTTP (bots desplegados en Railway)."""
    config = _get_bot_config(bot_nombre)
    if not config:
        return f"Bot '{bot_nombre}' no reconocido. Usa: 'perfumeria' o 'salud'"

    display_name = config["display_name"]
    url = config.get("url", "")

    resultado = [f"**Estado de {display_name}**\n"]

    if not url:
        resultado.append(f"URL no configurada. Agrega BOT_{bot_nombre.upper()}_URL en las variables de entorno.")
        update_bot_status(display_name, "sin_url")
        return "\n".join(resultado)

    resultado.append(f"URL: {url}")

    # Ping HTTP al bot
    try:
        start = datetime.now()
        resp = requests.get(url, timeout=10, allow_redirects=True)
        latencia = int((datetime.now() - start).total_seconds() * 1000)

        # Cualquier respuesta HTTP = bot activo en Railway (aunque sea 502)
        resultado.append(f"Estado: ACTIVO - responde en {latencia}ms (HTTP {resp.status_code})")
        update_bot_status(display_name, "activo")

        # Intentar leer respuesta JSON si existe
        try:
            data = resp.json()
            resultado.append(f"Respuesta: {json.dumps(data, ensure_ascii=False)[:300]}")
        except Exception:
            resultado.append(f"Respuesta: {resp.text[:200]}")

    except requests.exceptions.ConnectionError:
        resultado.append("Conexion rechazada - bot CAIDO o no responde")
        update_bot_status(display_name, "caido", "Connection refused")
    except requests.exceptions.Timeout:
        resultado.append("Timeout - bot tarda mas de 10 segundos en responder")
        update_bot_status(display_name, "timeout")
    except Exception as e:
        resultado.append(f"Error verificando: {e}")
        update_bot_status(display_name, "error", str(e))

    return "\n".join(resultado)


def tool_ver_logs_bot(bot_nombre: str, lineas: int = 50) -> str:
    config = _get_bot_config(bot_nombre)
    if not config:
        return f"❌ Bot '{bot_nombre}' no reconocido."

    bot_path = Path(config["path"])
    if not bot_path.exists():
        return f"❌ Directorio del bot no encontrado: {bot_path}"

    log_files = list(bot_path.glob("*.log")) + list(bot_path.glob("logs/*.log"))
    if not log_files:
        return f"📋 No se encontró archivo de log en {bot_path}"

    log_file = sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]

    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        last_lines = all_lines[-lineas:]
        content = "".join(last_lines)
        return f"📋 **Últimas {lineas} líneas de {log_file.name}:**\n\n```\n{content}\n```"
    except Exception as e:
        return f"❌ Error leyendo log: {e}"


def tool_reiniciar_bot(bot_nombre: str) -> str:
    config = _get_bot_config(bot_nombre)
    if not config:
        return f"❌ Bot '{bot_nombre}' no reconocido."

    bot_path = Path(config["path"])
    script = config["script"]
    runtime = config["runtime"]
    display_name = config["display_name"]

    if not bot_path.exists():
        return f"❌ Directorio no encontrado: {bot_path}"

    # Matar proceso existente
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or [])
            if script in cmdline:
                proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    import time
    time.sleep(2)

    # Iniciar proceso nuevo
    try:
        if runtime == "node":
            log_path = bot_path / "vanegas_restart.log"
            with open(log_path, "w") as log:
                proc = subprocess.Popen(
                    ["node", script],
                    cwd=str(bot_path),
                    stdout=log,
                    stderr=log,
                    start_new_session=True
                )
            update_bot_status(display_name, "reiniciado")
            return f"✅ {display_name} reiniciado (PID: {proc.pid})"
        else:
            return f"❌ Runtime '{runtime}' no soportado para reinicio automático"
    except Exception as e:
        update_bot_status(display_name, "error", str(e))
        return f"❌ Error al reiniciar: {e}"


def tool_ver_uso_tokens(dias: int = 1) -> str:
    stats = get_token_stats(dias)
    periodo = "hoy" if dias == 1 else f"últimos {dias} días"

    return (
        f"📊 **Uso de Tokens Claude ({periodo})**\n\n"
        f"🔢 Llamadas a la API: {stats['llamadas_api']}\n"
        f"📥 Tokens entrada: {stats['tokens_entrada']:,}\n"
        f"📤 Tokens salida: {stats['tokens_salida']:,}\n"
        f"💾 Cache escritura: {stats['tokens_cache_escritura']:,}\n"
        f"⚡ Cache lectura: {stats['tokens_cache_lectura']:,}\n"
        f"📈 Total tokens: {stats['total_tokens']:,}\n"
        f"💵 Costo estimado: ${stats['costo_estimado_usd']:.4f} USD\n\n"
        f"_Modelo: Claude Opus 4.6 | $5/1M entrada | $25/1M salida_"
    )


def tool_crear_archivo(ruta: str, contenido: str, descripcion: str = "") -> str:
    try:
        filepath = Path(ruta)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(contenido)

        size = filepath.stat().st_size
        desc_text = f"\n📝 {descripcion}" if descripcion else ""
        return f"✅ Archivo creado: {ruta} ({size} bytes){desc_text}"
    except Exception as e:
        return f"❌ Error al crear archivo: {e}"


def tool_leer_archivo(ruta: str, lineas: int = 0) -> str:
    try:
        filepath = Path(ruta)
        if not filepath.exists():
            return f"❌ Archivo no encontrado: {ruta}"

        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            if lineas > 0:
                content = "".join(f.readlines()[:lineas])
            else:
                content = f.read()

        size = filepath.stat().st_size
        return f"📄 **{ruta}** ({size} bytes):\n\n```\n{content[:5000]}\n```"
    except Exception as e:
        return f"❌ Error al leer archivo: {e}"


def tool_ejecutar_python(codigo: str, timeout: int = 30) -> str:
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False,
                                         encoding="utf-8") as f:
            f.write(codigo)
            temp_path = f.name

        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8"
        )

        os.unlink(temp_path)

        output = result.stdout[:3000] if result.stdout else ""
        error = result.stderr[:1000] if result.stderr else ""

        if result.returncode == 0:
            return f"✅ **Código ejecutado exitosamente:**\n\n```\n{output}\n```"
        else:
            return f"❌ **Error (código {result.returncode}):**\n\n```\n{error}\n```\n\nSalida:\n```\n{output}\n```"

    except subprocess.TimeoutExpired:
        return f"⏱️ Tiempo de ejecución excedido ({timeout}s)"
    except Exception as e:
        return f"❌ Error al ejecutar código: {e}"


def tool_navegar_web(url: str, solo_texto: bool = True) -> str:
    import re
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        content = resp.text
        if solo_texto:
            # Quitar scripts y estilos
            content = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL)
            content = re.sub(r"<style[^>]*>.*?</style>", "", content, flags=re.DOTALL)
            # Quitar HTML tags
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

        return f"🌐 **{url}** (HTTP {resp.status_code}):\n\n{content[:4000]}"

    except requests.exceptions.Timeout:
        return f"⏱️ Timeout conectando a {url}"
    except requests.exceptions.HTTPError as e:
        return f"❌ HTTP Error: {e}"
    except Exception as e:
        return f"❌ Error: {e}"


def tool_guardar_memoria(clave: str, valor) -> str:
    return save_memory(clave, valor)


def tool_recuperar_memoria(clave: str) -> str:
    value = get_memory(clave)
    if value is None:
        return f"❌ No se encontró '{clave}' en la memoria"
    return f"🧠 **{clave}:** {json.dumps(value, ensure_ascii=False, indent=2)}"


def tool_listar_memoria() -> str:
    keys = list_memory_keys()
    if not keys:
        return "🧠 La memoria está vacía"
    result = "🧠 **Memoria de VANEGAS:**\n\n"
    for k in keys:
        result += f"• `{k['key']}` (actualizado: {k['updated_at'][:16]})\n"
    return result


def tool_estado_sistema() -> str:
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\") if os.name == "nt" else psutil.disk_usage("/")

    return (
        f"💻 **Estado del Sistema**\n\n"
        f"🖥️  CPU: {cpu}%\n"
        f"🧠 RAM: {ram.percent}% usada ({ram.used // 1024**2:,} MB / {ram.total // 1024**2:,} MB)\n"
        f"💾 Disco: {disk.percent}% usado ({disk.free // 1024**3:.1f} GB libres)\n"
        f"⏰ Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    )


# ============================================================
# DISPATCHER - Ejecuta la herramienta solicitada por Claude
# ============================================================

def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Ejecuta la herramienta solicitada por Claude y retorna el resultado."""
    try:
        dispatch = {
            "buscar_emails": lambda i: tool_buscar_emails(
                i.get("query", "is:unread"), i.get("max_results", 10)
            ),
            "leer_email": lambda i: tool_leer_email(i["message_id"]),
            "enviar_email": lambda i: tool_enviar_email(i["para"], i["asunto"], i["cuerpo"]),
            "crear_borrador_email": lambda i: tool_crear_borrador(i["para"], i["asunto"], i["cuerpo"]),
            "verificar_bot": lambda i: tool_verificar_bot(i["bot_nombre"]),
            "ver_logs_bot": lambda i: tool_ver_logs_bot(i["bot_nombre"], i.get("lineas", 50)),
            "reiniciar_bot": lambda i: tool_reiniciar_bot(i["bot_nombre"]),
            "ver_uso_tokens": lambda i: tool_ver_uso_tokens(i.get("dias", 1)),
            "crear_archivo": lambda i: tool_crear_archivo(i["ruta"], i["contenido"], i.get("descripcion", "")),
            "leer_archivo": lambda i: tool_leer_archivo(i["ruta"], i.get("lineas", 0)),
            "ejecutar_python": lambda i: tool_ejecutar_python(i["codigo"], i.get("timeout", 30)),
            "navegar_web": lambda i: tool_navegar_web(i["url"], i.get("solo_texto", True)),
            "guardar_memoria": lambda i: tool_guardar_memoria(i["clave"], i["valor"]),
            "recuperar_memoria": lambda i: tool_recuperar_memoria(i["clave"]),
            "listar_memoria": lambda i: tool_listar_memoria(),
            "estado_sistema": lambda i: tool_estado_sistema(),
        }

        if tool_name not in dispatch:
            return f"❌ Herramienta '{tool_name}' no reconocida"

        return dispatch[tool_name](tool_input)

    except KeyError as e:
        return f"❌ Parámetro requerido faltante: {e}"
    except Exception as e:
        return f"❌ Error ejecutando {tool_name}: {type(e).__name__}: {e}"
