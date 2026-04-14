"""
VANEGAS - Módulo de Integración con Gmail
Maneja autenticación OAuth2 y operaciones de Gmail.
"""

import os
import json
import base64
import re
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]

_service = None


def get_gmail_service():
    """Obtiene o crea el servicio de Gmail autenticado."""
    global _service
    if _service:
        return _service

    creds_path = os.getenv("GMAIL_CREDENTIALS_PATH", "data/gmail_credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "data/gmail_token.json")

    creds = None

    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(creds_path).exists():
                raise FileNotFoundError(
                    f"No se encontró {creds_path}. "
                    "Descarga las credenciales OAuth2 desde Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)

        Path(token_path).parent.mkdir(exist_ok=True)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    _service = build("gmail", "v1", credentials=creds)
    return _service


def _decode_body(payload) -> str:
    """Decodifica el cuerpo de un email de base64."""
    body = ""
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    elif "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part.get("body", {}).get("data", "")
                if data:
                    body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    break
            elif part["mimeType"] == "text/html" and not body:
                data = part.get("body", {}).get("data", "")
                if data:
                    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    # Extrae texto limpio del HTML
                    body = re.sub(r"<[^>]+>", "", html)
                    body = re.sub(r"\s+", " ", body).strip()
    return body[:3000]  # Limitar a 3000 chars


def search_emails(query: str = "is:unread", max_results: int = 10) -> list:
    """
    Busca emails en Gmail.
    query: Consulta de búsqueda de Gmail (ej: 'is:unread', 'from:someone@gmail.com')
    max_results: Máximo de resultados (máx 50)
    """
    try:
        service = get_gmail_service()
        max_results = min(max_results, 50)

        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()

        messages = result.get("messages", [])
        emails = []

        for msg in messages[:max_results]:
            msg_data = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["From", "To", "Subject", "Date"]
            ).execute()

            headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
            snippet = msg_data.get("snippet", "")

            emails.append({
                "id": msg["id"],
                "de": headers.get("From", ""),
                "para": headers.get("To", ""),
                "asunto": headers.get("Subject", "(Sin asunto)"),
                "fecha": headers.get("Date", ""),
                "preview": snippet[:200]
            })

        return emails

    except HttpError as e:
        return [{"error": f"Error de Gmail: {str(e)}"}]
    except Exception as e:
        return [{"error": f"Error: {str(e)}"}]


def read_email(message_id: str) -> dict:
    """
    Lee el contenido completo de un email.
    message_id: ID del mensaje de Gmail
    """
    try:
        service = get_gmail_service()
        msg = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = _decode_body(msg.get("payload", {}))

        return {
            "id": message_id,
            "de": headers.get("From", ""),
            "para": headers.get("To", ""),
            "asunto": headers.get("Subject", "(Sin asunto)"),
            "fecha": headers.get("Date", ""),
            "cuerpo": body,
            "etiquetas": msg.get("labelIds", [])
        }

    except HttpError as e:
        return {"error": f"Error de Gmail: {str(e)}"}
    except Exception as e:
        return {"error": f"Error: {str(e)}"}


def send_email(to: str, subject: str, body: str, html: bool = False) -> dict:
    """
    Envía un email directamente.
    to: Destinatario
    subject: Asunto
    body: Cuerpo del mensaje
    html: Si es True, el cuerpo es HTML
    """
    try:
        service = get_gmail_service()

        if html:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body, "html"))
        else:
            message = MIMEText(body, "plain")

        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        return {"ok": True, "id": result["id"], "mensaje": f"Email enviado a {to}"}

    except HttpError as e:
        return {"ok": False, "error": f"Error de Gmail: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_draft(to: str, subject: str, body: str) -> dict:
    """
    Crea un borrador de email (no lo envía).
    to: Destinatario
    subject: Asunto
    body: Cuerpo del mensaje
    """
    try:
        service = get_gmail_service()
        message = MIMEText(body, "plain")
        message["to"] = to
        message["subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().drafts().create(
            userId="me",
            body={"message": {"raw": raw}}
        ).execute()

        return {
            "ok": True,
            "draft_id": result["id"],
            "mensaje": f"Borrador creado para {to} - Asunto: {subject}"
        }

    except HttpError as e:
        return {"ok": False, "error": f"Error de Gmail: {str(e)}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def mark_as_read(message_id: str) -> dict:
    """Marca un email como leído."""
    try:
        service = get_gmail_service()
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]}
        ).execute()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def is_gmail_configured() -> bool:
    """Verifica si Gmail está configurado."""
    creds_path = os.getenv("GMAIL_CREDENTIALS_PATH", "data/gmail_credentials.json")
    return Path(creds_path).exists()
