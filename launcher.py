import subprocess
import webbrowser
import time

# Iniciar servidor FastAPI con uvicorn
server = subprocess.Popen(
    ["uvicorn", "app:app", "--reload"],
)

# Esperar unos segundos para que arranque
time.sleep(3)

# Abrir navegador automáticamente
webbrowser.open("http://127.0.0.1:8000")

# Esperar a que el servidor termine
server.wait()