"""
VANEGAS - Punto de Entrada Principal
Lanza el servidor web FastAPI + monitor proactivo + alertas Telegram.

Uso:
    python main.py           # Iniciar VANEGAS (modo web)
    python main.py --setup   # Asistente de configuración
    python main.py --test    # Probar conexión con Claude
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Forzar UTF-8 en Windows para soportar emojis en la terminal
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

# Crear directorio data al inicio
Path("data").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/vanegas.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("VANEGAS")

for lib in ["httpx", "httpcore", "telegram", "urllib3", "uvicorn.access"]:
    logging.getLogger(lib).setLevel(logging.WARNING)


def check_requirements():
    issues = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        issues.append("❌ ANTHROPIC_API_KEY no está en .env")
    if issues:
        print("\n⚠️  Configuración incompleta:\n")
        for issue in issues:
            print(f"   {issue}")
        print("\nEjecuta: python setup_vanegas.py\n")
        return False
    return True


def run_test():
    from vanegas_memory import init_db
    from vanegas_agent import VanegasAgent

    init_db()
    print("\n🧪 Probando conexión con Claude Opus 4.6...")
    try:
        agent = VanegasAgent()
        response = agent.quick_message("Dime tu nombre y qué puedes hacer en 2 oraciones.")
        print(f"\n✅ VANEGAS responde:\n{response}\n")
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    if "--setup" in sys.argv:
        import subprocess
        subprocess.run([sys.executable, "setup_vanegas.py"])
        sys.exit(0)

    elif "--test" in sys.argv:
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("❌ ANTHROPIC_API_KEY no configurada.")
            sys.exit(1)
        run_test()
        sys.exit(0)

    else:
        if not check_requirements():
            sys.exit(1)

        from vanegas_memory import init_db
        init_db()

        print("\n" + "="*52)
        print("  ⚡ VANEGAS - Asistente Personal Autónomo")
        print("  Powered by Claude Opus 4.6")
        print("="*52)

        port = int(os.getenv("PORT", 8000))
        host = os.getenv("HOST", "0.0.0.0")
        print(f"  🌐 Interfaz web: http://localhost:{port}")
        print(f"  📱 Telegram alertas: {'✅' if os.getenv('TELEGRAM_BOT_TOKEN') else '⚠️  No configurado'}")
        print(f"  📧 Gmail: {'✅' if Path(os.getenv('GMAIL_CREDENTIALS_PATH', 'data/gmail_credentials.json')).exists() else '⚠️  No configurado'}")
        print("="*52)
        print("  Presiona Ctrl+C para detener\n")

        import uvicorn
        uvicorn.run("server:app", host=host, port=port, reload=False, log_level="info")
