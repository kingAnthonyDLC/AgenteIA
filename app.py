from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from agente import Agent
import json
import itertools

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

client = OpenAI()
agent = Agent()


class Message(BaseModel):
    message: str


def calcular_tabla(entradas, salidas):
    """Calcula la tabla de verdad matemáticamente con Python, sin depender del modelo."""
    combinaciones = list(itertools.product([0, 1], repeat=len(entradas)))
    tabla = []

    for combo in combinaciones:
        contexto = dict(zip(entradas, combo))
        fila = dict(contexto)

        for salida in salidas:
            try:
                resultado = int(eval(salida["expresion_eval"], {"__builtins__": {}}, contexto))
            except Exception:
                resultado = -1
            fila[salida["nombre"]] = resultado

        tabla.append(fila)

    return tabla


def expresion_canonica(entradas, salida_nombre, tabla):
    """Genera la expresión canónica SOP (suma de mintérminos) desde la tabla de verdad."""
    minterminos = []

    for fila in tabla:
        if fila[salida_nombre] == 1:
            termino = ""
            for var in entradas:
                if fila[var] == 1:
                    termino += var
                else:
                    termino += f"{var}'"
            minterminos.append(termino)

    if not minterminos:
        return "0"
    if len(minterminos) == len(tabla):
        return "1"

    return " + ".join(minterminos)


@app.get("/", response_class=HTMLResponse)
def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/chat")
def chat(body: Message):
    agent.messages.append({"role": "user", "content": body.message})

    # Bucle hasta obtener respuesta final
    while True:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=agent.messages,
            tools=agent.tools
        )
        called_tool = agent.process_response(response)
        if not called_tool:
            break

    # Obtener el último mensaje del asistente
    last = None
    for o in reversed(agent.messages):
        if isinstance(o, dict) and o.get("role") == "assistant":
            last = o
            break

    if not last:
        return JSONResponse({"error": "No se obtuvo respuesta del modelo."})

    # Limpiar posibles backticks que el modelo pueda incluir
    text = last["content"] if isinstance(last["content"], str) else ""
    text = text.strip().strip("```json").strip("```").strip()

    try:
        data = json.loads(text)
    except Exception:
        return JSONResponse({"error": f"El modelo no devolvió JSON válido: {text}"})

    # Validar estructura mínima
    if "entradas" not in data or "salidas" not in data:
        return JSONResponse({"error": "Faltan campos 'entradas' o 'salidas' en la respuesta."})

    # Python calcula la tabla
    data["tabla"] = calcular_tabla(data["entradas"], data["salidas"])

    # Python genera la expresión canónica SOP para cada salida
    for salida in data["salidas"]:
        salida["expresion_canonica"] = expresion_canonica(
            data["entradas"],
            salida["nombre"],
            data["tabla"]
        )

    return JSONResponse(data)