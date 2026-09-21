"""Entry point for the packaged .exe — starts the API + opens the browser."""
import socket
import threading
import time
import webbrowser

import uvicorn


def _free_port(start=8000) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _open_browser(url: str) -> None:
    time.sleep(1.5)
    webbrowser.open(url)


def main() -> None:
    from config import settings
    from main import app  # backend/main.py's FastAPI() instance
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    settings.frontend_url = url  # the exe serves the UI itself, on whatever port was free
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
