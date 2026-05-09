from openai import OpenAI
from dotenv import load_dotenv
from agente import Agent

load_dotenv()

print("=" * 40)
print("   Agente IA — Tabla de Verdad")
print("=" * 40)
print("Escribe 'salir' para terminar.\n")

client = OpenAI()
agente = Agent()

while True:
    user_input = input("Tú: ").strip()

    if not user_input:
        continue

    if user_input.lower() in ("salir", "exit", "bye", "sayonara"):
        print("Hasta luego!")
        break

    agente.messages.append({"role": "user", "content": user_input})

    while True:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=agente.messages,
            tools=agente.tools
        )

        called_tool = agente.process_response(response)

        if not called_tool:
            break

    # Obtener e imprimir la última respuesta
    last = None
    for o in reversed(agente.messages):
        if isinstance(o, dict) and o.get("role") == "assistant":
            last = o
            break

    if last:
        print(f"\nAsistente:\n{last['content']}\n")
    else:
        print("\nAsistente: (sin respuesta)\n")