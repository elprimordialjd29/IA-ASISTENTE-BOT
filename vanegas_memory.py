"""
VANEGAS - Módulo de Memoria Persistente
Almacena contexto, historial y datos entre sesiones usando SQLite.
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path


DB_PATH = Path("data/vanegas.db")


def init_db():
    """Inicializa la base de datos SQLite con todas las tablas necesarias."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Memoria general (clave-valor)
    c.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Historial de conversación con el usuario
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    # Registro de tokens usados
    c.execute("""
        CREATE TABLE IF NOT EXISTS token_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            cache_read_tokens INTEGER DEFAULT 0,
            task TEXT DEFAULT 'general'
        )
    """)

    # Estado de bots monitoreados
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_status (
            bot_name TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            last_check TEXT NOT NULL,
            last_error TEXT,
            error_count INTEGER DEFAULT 0
        )
    """)

    # Emails procesados (para no repetir alertas)
    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_emails (
            message_id TEXT PRIMARY KEY,
            subject TEXT,
            sender TEXT,
            processed_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_memory(key: str, value) -> str:
    """Guarda un valor en la memoria persistente."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO memory (key, value, updated_at) VALUES (?, ?, ?)",
        (key, json.dumps(value), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return f"✅ Guardado: {key}"


def get_memory(key: str):
    """Recupera un valor de la memoria persistente."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM memory WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None


def list_memory_keys() -> list:
    """Lista todas las claves guardadas en memoria."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT key, updated_at FROM memory ORDER BY updated_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"key": r[0], "updated_at": r[1]} for r in rows]


def add_conversation_turn(role: str, content: str):
    """Agrega un turno al historial de conversación."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversation_history (role, content, timestamp) VALUES (?, ?, ?)",
        (role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_recent_conversation(limit: int = 20) -> list:
    """Obtiene los últimos N turnos de conversación."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM conversation_history ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    # Revertir para que estén en orden cronológico
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def clear_conversation_history():
    """Limpia el historial de conversación."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM conversation_history")
    conn.commit()
    conn.close()


def record_token_usage(input_tokens: int, output_tokens: int,
                       cache_creation: int = 0, cache_read: int = 0,
                       task: str = "general"):
    """Registra el uso de tokens de una llamada a la API."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO token_usage
        (timestamp, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens, task)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), input_tokens, output_tokens,
          cache_creation, cache_read, task))
    conn.commit()
    conn.close()


def get_token_stats(days: int = 1) -> dict:
    """Obtiene estadísticas de uso de tokens en los últimos N días."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cutoff = datetime.now().isoformat()[:10]  # fecha de hoy

    if days == 1:
        # Hoy
        c.execute("""
            SELECT SUM(input_tokens), SUM(output_tokens),
                   SUM(cache_creation_tokens), SUM(cache_read_tokens),
                   COUNT(*)
            FROM token_usage
            WHERE timestamp >= ?
        """, (cutoff + "T00:00:00",))
    else:
        # Últimos N días
        from datetime import timedelta
        cutoff_dt = datetime.now() - timedelta(days=days)
        c.execute("""
            SELECT SUM(input_tokens), SUM(output_tokens),
                   SUM(cache_creation_tokens), SUM(cache_read_tokens),
                   COUNT(*)
            FROM token_usage
            WHERE timestamp >= ?
        """, (cutoff_dt.isoformat(),))

    row = c.fetchone()
    conn.close()

    input_t = row[0] or 0
    output_t = row[1] or 0
    cache_create_t = row[2] or 0
    cache_read_t = row[3] or 0
    calls = row[4] or 0

    # Precios de Claude Opus 4.6 por millón de tokens
    input_cost = (input_t / 1_000_000) * 5.0
    output_cost = (output_t / 1_000_000) * 25.0
    cache_write_cost = (cache_create_t / 1_000_000) * 6.25
    cache_read_cost = (cache_read_t / 1_000_000) * 0.5

    return {
        "periodo_dias": days,
        "llamadas_api": calls,
        "tokens_entrada": input_t,
        "tokens_salida": output_t,
        "tokens_cache_escritura": cache_create_t,
        "tokens_cache_lectura": cache_read_t,
        "total_tokens": input_t + output_t,
        "costo_estimado_usd": round(input_cost + output_cost + cache_write_cost + cache_read_cost, 4)
    }


def update_bot_status(bot_name: str, status: str, error: str = None):
    """Actualiza el estado de un bot monitoreado."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if error:
        c.execute("""
            INSERT OR REPLACE INTO bot_status
            (bot_name, status, last_check, last_error, error_count)
            VALUES (?, ?, ?, ?,
                COALESCE((SELECT error_count FROM bot_status WHERE bot_name = ?), 0) + 1)
        """, (bot_name, status, datetime.now().isoformat(), error, bot_name))
    else:
        c.execute("""
            INSERT OR REPLACE INTO bot_status
            (bot_name, status, last_check, last_error, error_count)
            VALUES (?, ?, ?, NULL, 0)
        """, (bot_name, status, datetime.now().isoformat()))

    conn.commit()
    conn.close()


def get_bot_status(bot_name: str = None) -> list:
    """Obtiene el estado de todos o un bot específico."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if bot_name:
        c.execute("SELECT * FROM bot_status WHERE bot_name = ?", (bot_name,))
    else:
        c.execute("SELECT * FROM bot_status")

    rows = c.fetchall()
    conn.close()
    return [
        {
            "nombre": r[0], "estado": r[1], "ultimo_check": r[2],
            "ultimo_error": r[3], "errores": r[4]
        }
        for r in rows
    ]


def mark_email_processed(message_id: str, subject: str, sender: str):
    """Marca un email como procesado para no repetir alertas."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO processed_emails (message_id, subject, sender, processed_at)
        VALUES (?, ?, ?, ?)
    """, (message_id, subject, sender, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def is_email_processed(message_id: str) -> bool:
    """Verifica si un email ya fue procesado."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,))
    result = c.fetchone() is not None
    conn.close()
    return result
