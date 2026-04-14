"""
VANEGAS - Asistente de Configuración
Guía paso a paso para configurar VANEGAS por primera vez.
"""

import os
import sys
import json
from pathlib import Path


def print_header(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def print_step(step: int, total: int, description: str):
    print(f"\n[Paso {step}/{total}] {description}")
    print("-" * 45)


def ask(prompt: str, default: str = "") -> str:
    if default:
        val = input(f"{prompt} [{default}]: ").strip()
        return val if val else default
    return input(f"{prompt}: ").strip()


def save_env(config: dict):
    """Guarda la configuración en el archivo .env"""
    env_path = Path(".env")
    lines = []

    # Si ya existe, leer el contenido
    if env_path.exists():
        with open(env_path, "r") as f:
            existing = {}
            for line in f.readlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()
        config = {**existing, **config}  # Nueva config tiene prioridad

    with open(env_path, "w") as f:
        f.write("# VANEGAS Configuration\n\n")
        for key, value in config.items():
            f.write(f"{key}={value}\n")

    print(f"\n✅ Configuración guardada en .env")


def setup_anthropic():
    """Configura la API key de Anthropic."""
    print_step(1, 5, "API de Anthropic (Claude)")
    print("""
Para obtener tu API key de Anthropic:
1. Ve a https://console.anthropic.com/
2. Crea una cuenta o inicia sesión
3. Ve a Settings → API Keys
4. Crea una nueva API key
    """)

    api_key = ask("Pega tu ANTHROPIC_API_KEY")
    if not api_key.startswith("sk-ant-"):
        print("⚠️  La API key debería comenzar con 'sk-ant-'. Verifica que sea correcta.")

    return {"ANTHROPIC_API_KEY": api_key}


def setup_telegram():
    """Configura el bot de Telegram."""
    print_step(2, 5, "Bot de Telegram")
    print("""
Para crear tu bot de Telegram:

1. Abre Telegram y busca: @BotFather
2. Envía el comando: /newbot
3. Sigue las instrucciones (elige nombre y username)
4. Copia el TOKEN que te da BotFather

Para obtener tu Chat ID:
1. Inicia una conversación con tu bot recién creado
2. Envía cualquier mensaje al bot
3. Visita: https://api.telegram.org/bot<TU_TOKEN>/getUpdates
4. Busca el campo "chat":{"id": XXXXXXXX} en el resultado
   O usa el comando /start cuando VANEGAS esté corriendo
    """)

    token = ask("Pega el token de tu bot de Telegram")
    chat_id = ask("Pega tu Chat ID de Telegram (puedes dejarlo vacío por ahora)", "")

    return {
        "TELEGRAM_BOT_TOKEN": token,
        "TELEGRAM_CHAT_ID": chat_id
    }


def setup_gmail():
    """Configura Gmail OAuth2."""
    print_step(3, 5, "Gmail (OAuth2)")
    print("""
Para conectar Gmail:

1. Ve a https://console.cloud.google.com/
2. Crea un proyecto nuevo (o usa uno existente)
3. Busca "Gmail API" en la barra de búsqueda y HABILÍTALA
4. Ve a: APIs y servicios → Credenciales
5. Crea credenciales → ID de cliente OAuth
   - Tipo: Aplicación de escritorio
   - Nombre: VANEGAS
6. Descarga el archivo JSON de credenciales
7. RENÓMBRALO como: gmail_credentials.json
8. CÓPIALO a la carpeta: VANEGAS/data/
    """)

    creds_path = Path("data/gmail_credentials.json")
    if creds_path.exists():
        print(f"✅ Archivo encontrado: {creds_path}")
        authorize = ask("¿Deseas autorizar Gmail ahora? (s/n)", "s").lower()
        if authorize == "s":
            try:
                print("\n🌐 Abriendo navegador para autorizar Gmail...")
                from google_auth_oauthlib.flow import InstalledAppFlow
                SCOPES = [
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.send",
                    "https://www.googleapis.com/auth/gmail.compose",
                    "https://www.googleapis.com/auth/gmail.modify",
                ]
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)
                token_path = Path("data/gmail_token.json")
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                print(f"✅ Gmail autorizado. Token guardado en {token_path}")
            except Exception as e:
                print(f"❌ Error autorizando Gmail: {e}")
                print("   Puedes intentarlo después ejecutando: python setup_vanegas.py")
    else:
        print(f"⚠️  No se encontró {creds_path}")
        print("   Sigue los pasos anteriores y luego ejecuta setup nuevamente.")

    return {
        "GMAIL_CREDENTIALS_PATH": "data/gmail_credentials.json",
        "GMAIL_TOKEN_PATH": "data/gmail_token.json"
    }


def setup_bots():
    """Configura las rutas de los bots a monitorear."""
    print_step(4, 5, "Bots a Monitorear")
    print("""
VANEGAS puede vigilar tus otros bots automáticamente.
Proporciona las rutas relativas a la carpeta VANEGAS/.
    """)

    # Bot Perfumería (ya detectado)
    print("🤖 Bot de Perfumería (Chu):")
    perf_path = ask("  Ruta del bot", "../perfumeria-bot")
    perf_script = ask("  Script principal", "bot.js")
    perf_name = ask("  Nombre del bot", "Chu (Perfumería)")

    # Bot Salud
    print("\n🤖 Bot de Salud:")
    salud_path = ask("  Ruta del bot", "../bot-salud")
    salud_script = ask("  Script principal", "index.js")
    salud_name = ask("  Nombre del bot", "Bot Salud")

    return {
        "BOT_PERFUMERIA_PATH": perf_path,
        "BOT_PERFUMERIA_SCRIPT": perf_script,
        "BOT_PERFUMERIA_NAME": perf_name,
        "BOT_SALUD_PATH": salud_path,
        "BOT_SALUD_SCRIPT": salud_script,
        "BOT_SALUD_NAME": salud_name,
    }


def setup_preferences():
    """Configura preferencias generales."""
    print_step(5, 5, "Preferencias")

    email_interval = ask("¿Cada cuántos minutos revisar emails?", "15")
    bot_interval = ask("¿Cada cuántos minutos verificar bots?", "10")
    token_threshold = ask("¿Umbral de alerta de tokens diarios?", "1000000")
    timezone = ask("¿Zona horaria?", "America/Bogota")

    return {
        "EMAIL_CHECK_INTERVAL": email_interval,
        "BOT_CHECK_INTERVAL": bot_interval,
        "TOKEN_ALERT_THRESHOLD_DAILY": token_threshold,
        "TIMEZONE": timezone
    }


def main():
    print_header("🤖 VANEGAS - Asistente de Configuración")
    print("\nEste asistente te guiará para configurar VANEGAS.")
    print("Puedes presionar Enter para aceptar el valor por defecto [entre corchetes].\n")

    # Crear directorio data
    Path("data").mkdir(exist_ok=True)

    config = {}

    try:
        config.update(setup_anthropic())
        config.update(setup_telegram())
        config.update(setup_gmail())
        config.update(setup_bots())
        config.update(setup_preferences())

        save_env(config)

        print_header("✅ Configuración Completada")
        print("""
Para iniciar VANEGAS:
    python main.py

Para probar la conexión con Claude:
    python main.py --test

Para volver a configurar:
    python setup_vanegas.py

Una vez iniciado, envía /start a tu bot de Telegram.
Si no configuraste el Chat ID, lo obtendrás automáticamente
al enviar /start.
        """)

    except KeyboardInterrupt:
        print("\n\n⛔ Configuración cancelada.")
        sys.exit(0)


if __name__ == "__main__":
    main()
