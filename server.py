"""
VANEGAS - Servidor Web FastAPI
WebSocket para chat en tiempo real + API REST + archivos estáticos.
"""

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from pathlib import Path as _Path
load_dotenv(dotenv_path=_Path(__file__).parent / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Importaciones de VANEGAS (lazy para no fallar si faltan deps opcionales)
try:
    from vanegas_agent import VanegasAgent
    from vanegas_memory import get_token_stats, get_recent_conversation
    agent = VanegasAgent()
    logger.info("VanegasAgent inicializado OK")
except Exception as e:
    logger.error(f"Error inicializando VanegasAgent: {e}")
    agent = None

try:
    from vanegas_telegram import VanegasTelegram
    telegram = VanegasTelegram()
except Exception as e:
    logger.warning(f"Telegram no disponible: {e}")
    telegram = None

try:
    from vanegas_monitor import VanegasMonitor
    _notify = telegram.send_notification if telegram else (lambda msg: None)
    monitor = VanegasMonitor(agent, _notify)
except Exception as e:
    logger.warning(f"Monitor no disponible: {e}")
    monitor = None

VANEGAS_PASSWORD = os.getenv("VANEGAS_PASSWORD", "vanegas2024")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Arranca el monitor proactivo al iniciar el servidor."""
    if monitor:
        asyncio.create_task(monitor.start_all())
        logger.info("Monitor proactivo arrancado")
    yield
    logger.info("VANEGAS apagándose...")


app = FastAPI(
    title="VANEGAS - Asistente Personal Autónomo",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar archivos estáticos si el directorio existe
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ─── Autenticación simple ────────────────────────────────────────────────────

def verify_password(password: str) -> bool:
    return password == VANEGAS_PASSWORD


# ─── Rutas HTTP ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Sirve la interfaz web principal."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="""
    <html><body style="background:#0d1117;color:#cdd9e5;font-family:monospace;padding:40px">
    <h2>⚡ VANEGAS arrancado</h2>
    <p>Archivos estáticos no encontrados. Crea el directorio <code>static/</code>.</p>
    </body></html>
    """)


@app.post("/api/auth")
async def authenticate(request: Request):
    body = await request.json()
    password = body.get("password", "")
    if verify_password(password):
        return {"ok": True, "message": "Autenticado"}
    raise HTTPException(status_code=401, detail="Contraseña incorrecta")


@app.get("/api/status")
async def get_status():
    """Estado general del sistema."""
    try:
        stats = get_token_stats(days=1)
        return {
            "ok": True,
            "agent": agent is not None,
            "monitor": monitor is not None,
            "telegram": telegram is not None,
            "tokens_hoy": stats.get("total_tokens", 0),
            "costo_hoy": stats.get("costo_estimado_usd", 0.0),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/tokens")
async def get_token_usage(days: int = 7):
    """Estadísticas de consumo de tokens (incluye desglose diario)."""
    try:
        stats_total = get_token_stats(days=days)
        stats_today = get_token_stats(days=1)

        # Construir desglose por día para la gráfica
        import sqlite3
        from vanegas_memory import DB_PATH
        from datetime import timedelta
        daily = []
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for i in range(days - 1, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            c.execute(
                "SELECT SUM(input_tokens)+SUM(output_tokens) FROM token_usage WHERE timestamp LIKE ?",
                (f"{day}%",)
            )
            row = c.fetchone()
            daily.append({"date": day, "tokens": row[0] or 0})
        conn.close()

        return {
            "ok": True,
            "data": {
                "today_tokens": stats_today.get("total_tokens", 0),
                "total_tokens": stats_total.get("total_tokens", 0),
                "total_cost": stats_total.get("costo_estimado_usd", 0.0),
                "daily": daily,
                "raw": stats_total,
            }
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/history")
async def get_history(limit: int = 20):
    """Historial reciente de conversación."""
    try:
        history = get_recent_conversation(limit=limit)
        return {"ok": True, "data": history}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/daily-summary")
async def trigger_daily_summary(request: Request):
    """Fuerza un resumen diario."""
    body = await request.json()
    if not verify_password(body.get("password", "")):
        raise HTTPException(status_code=401, detail="No autorizado")
    if not agent:
        raise HTTPException(status_code=503, detail="Agente no disponible")
    summary = agent.get_daily_summary()
    return {"ok": True, "summary": summary}


# ─── WebSocket ───────────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, ws: WebSocket):
        await ws.accept()
        self.active[client_id] = ws
        logger.info(f"WS conectado: {client_id} ({len(self.active)} total)")

    def disconnect(self, client_id: str):
        self.active.pop(client_id, None)
        logger.info(f"WS desconectado: {client_id}")

    async def send(self, client_id: str, data: dict):
        ws = self.active.get(client_id)
        if ws:
            await ws.send_json(data)


manager = ConnectionManager()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        # Primera cosa: autenticar
        auth_msg = await websocket.receive_json()
        if auth_msg.get("type") != "auth" or not verify_password(auth_msg.get("password", "")):
            await websocket.send_json({"type": "error", "content": "❌ Contraseña incorrecta"})
            await websocket.close()
            return

        await websocket.send_json({"type": "auth_ok", "content": "✅ Conectado a VANEGAS"})

        # Loop de mensajes
        while True:
            data = await websocket.receive_json()

            if data.get("type") != "message":
                continue

            user_message = data.get("content", "").strip()
            if not user_message:
                continue

            if not agent:
                await websocket.send_json({
                    "type": "error",
                    "content": "❌ Agente no disponible. Verifica ANTHROPIC_API_KEY."
                })
                continue

            # Streaming de la respuesta
            try:
                async for event in agent.stream_message(user_message):
                    await websocket.send_json(event)
            except Exception as e:
                logger.error(f"Error streaming: {e}", exc_info=True)
                await websocket.send_json({
                    "type": "error",
                    "content": f"❌ Error interno: {e}"
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error WS {client_id}: {e}")
    finally:
        manager.disconnect(client_id)


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Iniciando VANEGAS en http://{host}:{port}")
    uvicorn.run("server:app", host=host, port=port, reload=False, log_level="info")
