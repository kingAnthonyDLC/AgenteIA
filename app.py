from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
from agente import Agent
from sympy.logic.boolalg import simplify_logic
from sympy import symbols
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
    minterminos = []
    for fila in tabla:
        if fila[salida_nombre] == 1:
            termino = ""
            for var in entradas:
                termino += var if fila[var] == 1 else f"{var}'"
            minterminos.append(termino)
    if not minterminos:
        return "0"
    if len(minterminos) == len(tabla):
        return "1"
    return " + ".join(minterminos)


def simplificar_con_sympy(entradas, salida_nombre, tabla):
    """Simplifica usando sympy y devuelve la expresión mínima."""
    vars_sym = symbols(" ".join(entradas))
    if len(entradas) == 1:
        vars_sym = (vars_sym,)

    mapa = dict(zip(entradas, vars_sym))
    expr = False

    for fila in tabla:
        if fila[salida_nombre] == 1:
            termino = True
            for var in entradas:
                termino = termino & (mapa[var] if fila[var] == 1 else ~mapa[var])
            expr = expr | termino

    simplificada = simplify_logic(expr, form="dnf")

    # Convertir a notación con prima
    resultado = str(simplificada)
    resultado = resultado.replace("~", "").replace(" & ", "").replace(" | ", " + ")
    for var in sorted(entradas, key=len, reverse=True):
        resultado = resultado.replace(f"~{var}", f"{var}'")

    # Sympy usa ~ antes, re-procesar correctamente
    simplificada_str = str(simplify_logic(expr, form="dnf"))
    terminos = simplificada_str.split(" | ")
    terminos_display = []
    for t in terminos:
        t = t.strip().replace("(", "").replace(")", "")
        factores = t.split(" & ")
        display = ""
        for f in factores:
            f = f.strip()
            if f.startswith("~"):
                display += f[1:] + "'"
            else:
                display += f
        terminos_display.append(display)

    return " + ".join(terminos_display) if terminos_display else "0"


# ── KARNAUGH (hasta 4 variables) ──────────────────────────────

def karnaugh_grupos(entradas, salida_nombre, tabla):
    """
    Encuentra los grupos del mapa de Karnaugh y devuelve:
    - La estructura del mapa
    - Los grupos con sus celdas y término simplificado
    """
    n = len(entradas)
    # Índices de mintérminos donde salida=1
    minterms = []
    for i, fila in enumerate(tabla):
        if fila[salida_nombre] == 1:
            minterms.append(i)

    if not minterms:
        return {"mapa": [], "grupos": [], "expresion": "0"}
    if len(minterms) == len(tabla):
        return {"mapa": [], "grupos": [], "expresion": "1"}

    # Construir mapa según número de variables
    if n == 1:
        orden_filas = [0, 1]
        orden_cols = []
        mapa = [[orden_filas[i]] for i in range(2)]
        col_labels = []
        fila_labels = [entradas[0] + "'", entradas[0]]

    elif n == 2:
        # filas: var0, cols: var1
        gray_2 = [0, 1]
        mapa = [[r * 2 + c for c in gray_2] for r in gray_2]
        fila_labels = [entradas[0] + "'", entradas[0]]
        col_labels  = [entradas[1] + "'", entradas[1]]

    elif n == 3:
        # filas: var0 (2), cols: var1,var2 (4) en Gray
        gray_cols = [0, 1, 3, 2]
        mapa = [[r * 4 + c for c in gray_cols] for r in [0, 1]]
        fila_labels = [entradas[0] + "'", entradas[0]]
        col_labels  = ["00", "01", "11", "10"]

    else:  # n == 4
        gray_rows = [0, 1, 3, 2]
        gray_cols = [0, 1, 3, 2]
        mapa = [[r * 4 + c for c in gray_cols] for r in gray_rows]
        fila_labels = ["00", "01", "11", "10"]
        col_labels  = ["00", "01", "11", "10"]

    # Encontrar grupos (potencias de 2: 8,4,2,1) con wrap-around
    grupos = encontrar_grupos(minterms, mapa, entradas, tabla)

    return {
        "mapa": mapa,
        "minterms": minterms,
        "grupos": grupos,
        "fila_labels": fila_labels,
        "col_labels": col_labels,
        "n": n
    }


def encontrar_grupos(minterms, mapa, entradas, tabla):
    """Encuentra agrupaciones válidas de Karnaugh."""
    filas = len(mapa)
    cols  = len(mapa[0]) if mapa else 0
    n     = len(entradas)

    # Posición de cada mintérmino en el mapa
    pos = {}
    for r in range(filas):
        for c in range(cols):
            pos[mapa[r][c]] = (r, c)

    mint_set = set(minterms)
    grupos = []
    cubiertos = set()
    colores = ["#ef4444","#f97316","#eab308","#22c55e",
               "#06b6d4","#6366f1","#ec4899","#14b8a6"]

    tamaños = []
    t = min(8, 2**n)
    while t >= 1:
        tamaños.append(t)
        t //= 2

    for tam in tamaños:
        # Generar todos los rectángulos posibles de tamaño tam
        for r0 in range(filas):
            for c0 in range(cols):
                for alto in [1, 2, 4]:
                    for ancho in [1, 2, 4]:
                        if alto * ancho != tam:
                            continue
                        if alto > filas or ancho > cols:
                            continue
                        celdas = []
                        for dr in range(alto):
                            for dc in range(ancho):
                                idx = mapa[(r0 + dr) % filas][(c0 + dc) % cols]
                                celdas.append(idx)
                        celdas_set = set(celdas)
                        if not celdas_set.issubset(mint_set):
                            continue
                        if celdas_set.issubset(cubiertos):
                            continue
                        # Calcular término simplificado
                        termino = simplificar_termino_grupo(celdas, entradas, tabla)
                        posiciones = [(pos[c][0], pos[c][1]) for c in celdas]
                        color = colores[len(grupos) % len(colores)]
                        grupos.append({
                            "celdas": celdas,
                            "posiciones": posiciones,
                            "termino": termino,
                            "color": color,
                            "tam": tam
                        })
                        cubiertos |= celdas_set

        if cubiertos == mint_set:
            break

    return grupos


def simplificar_termino_grupo(celdas, entradas, tabla):
    """Determina qué variables son constantes en el grupo → término simplificado."""
    filas_grupo = [tabla[i] for i in celdas]
    termino = ""
    for var in entradas:
        valores = set(f[var] for f in filas_grupo)
        if len(valores) == 1:
            v = list(valores)[0]
            termino += var if v == 1 else f"{var}'"
    return termino if termino else "1"


# ── QUINE-McCLUSKEY (5+ variables) ───────────────────────────

def quine_mccluskey(entradas, salida_nombre, tabla):
    """
    Implementa Quine-McCluskey y devuelve los pasos para mostrar al usuario.
    """
    n = len(entradas)
    minterms = [i for i, f in enumerate(tabla) if f[salida_nombre] == 1]

    if not minterms:
        return {"pasos": [], "expresion": "0"}
    if len(minterms) == len(tabla):
        return {"pasos": [], "expresion": "1"}

    def a_binario(num):
        return format(num, f"0{n}b")

    def contar_unos(b):
        return b.count("1")

    def pueden_combinarse(a, b):
        diff = [i for i in range(n) if a[i] != b[i]]
        return len(diff) == 1, diff[0] if len(diff) == 1 else -1

    def combinar(a, b, pos):
        r = list(a)
        r[pos] = "-"
        return "".join(r)

    def binario_a_termino(b):
        t = ""
        for i, c in enumerate(b):
            if c == "1":
                t += entradas[i]
            elif c == "0":
                t += entradas[i] + "'"
        return t if t else "1"

    # Paso 1: agrupar por número de unos
    grupos = {}
    for m in minterms:
        b = a_binario(m)
        k = contar_unos(b)
        grupos.setdefault(k, []).append((b, frozenset([m])))

    pasos = []

    # Tabla paso 1
    filas_p1 = []
    for k in sorted(grupos):
        for b, ms in grupos[k]:
            filas_p1.append({
                "minterms": sorted(ms),
                "binario": b,
                "unos": k
            })

    pasos.append({
        "titulo": "Paso 1 — Mintérminos agrupados por número de unos",
        "explicacion": "Se listan todos los mintérminos (filas con salida=1) en binario y se agrupan según cuántos unos contienen. Solo pueden combinarse grupos adyacentes (diferencia de 1 en cantidad de unos).",
        "tipo": "tabla_minterms",
        "columnas": ["Mintérminos", "Binario", "Nº de unos"],
        "filas": filas_p1
    })

    # Paso 2+: combinaciones sucesivas
    implicantes_primos = []
    usados_global = set()
    ronda = 1

    while True:
        nuevos_grupos = {}
        usados = set()
        filas_ronda = []

        claves = sorted(grupos.keys())
        for i in range(len(claves) - 1):
            k1, k2 = claves[i], claves[i+1]
            if k2 - k1 != 1:
                continue
            for b1, ms1 in grupos[k1]:
                for b2, ms2 in grupos[k2]:
                    ok, pos = pueden_combinarse(b1, b2)
                    if ok:
                        nuevo = combinar(b1, b2, pos)
                        ms_nuevo = ms1 | ms2
                        k_nuevo = contar_unos(nuevo.replace("-", "0"))
                        nuevos_grupos.setdefault(k_nuevo, [])
                        if (nuevo, ms_nuevo) not in nuevos_grupos[k_nuevo]:
                            nuevos_grupos[k_nuevo].append((nuevo, ms_nuevo))
                        usados.add((b1, ms1))
                        usados.add((b2, ms2))
                        filas_ronda.append({
                            "combinacion": f"{sorted(ms1)} + {sorted(ms2)}",
                            "resultado": nuevo,
                            "termino": binario_a_termino(nuevo)
                        })

        # Los no usados son implicantes primos
        for k, lst in grupos.items():
            for item in lst:
                if item not in usados:
                    b, ms = item
                    t = binario_a_termino(b)
                    if t not in [ip["termino"] for ip in implicantes_primos]:
                        implicantes_primos.append({
                            "minterms": sorted(ms),
                            "binario": b,
                            "termino": t
                        })

        if filas_ronda:
            pasos.append({
                "titulo": f"Paso {ronda + 1} — Combinaciones ronda {ronda}",
                "explicacion": f"Se comparan grupos adyacentes. Si dos términos difieren en exactamente una posición, se combinan reemplazando esa posición con '-' (variable eliminada).",
                "tipo": "tabla_combinaciones",
                "columnas": ["Combinación", "Resultado", "Término"],
                "filas": filas_ronda
            })

        if not nuevos_grupos:
            # Agregar restantes como implicantes primos
            for k, lst in grupos.items():
                for item in lst:
                    b, ms = item
                    t = binario_a_termino(b)
                    if t not in [ip["termino"] for ip in implicantes_primos]:
                        implicantes_primos.append({
                            "minterms": sorted(ms),
                            "binario": b,
                            "termino": t
                        })
            break

        grupos = nuevos_grupos
        ronda += 1
        if ronda > 10:
            break

    # Paso final: implicantes primos
    pasos.append({
        "titulo": f"Paso {ronda + 1} — Implicantes primos encontrados",
        "explicacion": "Los términos que no pudieron combinarse más son los implicantes primos. La expresión simplificada es la suma de todos ellos.",
        "tipo": "tabla_implicantes",
        "columnas": ["Mintérminos cubiertos", "Binario", "Término simplificado"],
        "filas": implicantes_primos
    })

    expresion = " + ".join(ip["termino"] for ip in implicantes_primos) or "0"

    return {"pasos": pasos, "expresion": expresion}


@app.get("/", response_class=HTMLResponse)
def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/chat")
def chat(body: Message):
    agent.messages.append({"role": "user", "content": body.message})

    while True:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=agent.messages,
            tools=agent.tools
        )
        called_tool = agent.process_response(response)
        if not called_tool:
            break

    last = None
    for o in reversed(agent.messages):
        if isinstance(o, dict) and o.get("role") == "assistant":
            last = o
            break

    if not last:
        return JSONResponse({"error": "No se obtuvo respuesta del modelo."})

    text = last["content"] if isinstance(last["content"], str) else ""
    text = text.strip().strip("```json").strip("```").strip()

    try:
        data = json.loads(text)
    except Exception:
        return JSONResponse({"error": f"El modelo no devolvió JSON válido: {text}"})

    if "entradas" not in data or "salidas" not in data:
        return JSONResponse({"error": "Faltan campos 'entradas' o 'salidas' en la respuesta."})

    data["tabla"] = calcular_tabla(data["entradas"], data["salidas"])
    n = len(data["entradas"])

    for salida in data["salidas"]:
        salida["expresion_canonica"] = expresion_canonica(
            data["entradas"], salida["nombre"], data["tabla"]
        )
        if n <= 4:
            salida["metodo"] = "karnaugh"
            salida["karnaugh"] = karnaugh_grupos(
                data["entradas"], salida["nombre"], data["tabla"]
            )
            salida["expresion_simplificada"] = simplificar_con_sympy(
                data["entradas"], salida["nombre"], data["tabla"]
            )
        else:
            salida["metodo"] = "quine"
            resultado_qm = quine_mccluskey(
                data["entradas"], salida["nombre"], data["tabla"]
            )
            salida["quine_pasos"] = resultado_qm["pasos"]
            salida["expresion_simplificada"] = resultado_qm["expresion"]

    return JSONResponse(data)