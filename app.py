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
import re

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

client = OpenAI()
agent  = Agent()

MAX_ENTRADAS = 16   # Límite de entradas por subsistema


class Message(BaseModel):
    message: str


# ═══════════════════════════════════════════════════
# TABLA DE VERDAD
# ═══════════════════════════════════════════════════

def calcular_tabla(entradas, salidas):
    """Calcula la tabla de verdad matemáticamente."""
    combinaciones = list(itertools.product([0, 1], repeat=len(entradas)))
    tabla = []
    for combo in combinaciones:
        contexto = dict(zip(entradas, combo))
        fila     = dict(contexto)
        for salida in salidas:
            try:
                resultado = int(eval(salida["expresion_eval"], {"__builtins__": {}}, contexto))
            except Exception:
                resultado = -1
            fila[salida["nombre"]] = resultado
        tabla.append(fila)
    return tabla


# ═══════════════════════════════════════════════════
# EXPRESIÓN CANÓNICA SOP
# ═══════════════════════════════════════════════════

def expresion_canonica(entradas, salida_nombre, tabla):
    """Genera la expresión canónica SOP desde la tabla de verdad."""
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


# ═══════════════════════════════════════════════════
# SIMPLIFICACIÓN CON SYMPY
# ═══════════════════════════════════════════════════

def simplificar_con_sympy(entradas, salida_nombre, tabla):
    """Simplifica la expresión usando sympy."""
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

    simplificada     = simplify_logic(expr, form="dnf")
    simplificada_str = str(simplificada)

    if simplificada_str == "False": return "0"
    if simplificada_str == "True":  return "1"

    terminos = simplificada_str.split(" | ")
    terminos_display = []
    for t in terminos:
        t       = t.strip().replace("(", "").replace(")", "")
        factores = t.split(" & ")
        display  = ""
        for f in factores:
            f        = f.strip()
            display += f[1:] + "'" if f.startswith("~") else f
        terminos_display.append(display)

    return " + ".join(terminos_display) if terminos_display else "0"


# ═══════════════════════════════════════════════════
# KARNAUGH
# ═══════════════════════════════════════════════════

def karnaugh_grupos(entradas, salida_nombre, tabla):
    """Encuentra grupos del mapa de Karnaugh."""
    n        = len(entradas)
    minterms = [i for i, fila in enumerate(tabla) if fila[salida_nombre] == 1]

    if not minterms:         return {"mapa": [], "grupos": [], "expresion": "0"}
    if len(minterms) == len(tabla): return {"mapa": [], "grupos": [], "expresion": "1"}

    if n == 1:
        mapa        = [[0], [1]]
        fila_labels = [entradas[0] + "'", entradas[0]]
        col_labels  = []
    elif n == 2:
        mapa        = [[0, 1], [2, 3]]
        fila_labels = [entradas[0] + "'", entradas[0]]
        col_labels  = [entradas[1] + "'", entradas[1]]
    elif n == 3:
        gray_cols   = [0, 1, 3, 2]
        mapa        = [[c for c in gray_cols], [c + 4 for c in gray_cols]]
        fila_labels = [entradas[0] + "'", entradas[0]]
        col_labels  = ["00", "01", "11", "10"]
    else:
        gray        = [0, 1, 3, 2]
        mapa        = [[r * 4 + c for c in gray] for r in gray]
        fila_labels = ["00", "01", "11", "10"]
        col_labels  = ["00", "01", "11", "10"]

    grupos = encontrar_grupos(minterms, mapa, entradas, tabla)
    return {
        "mapa": mapa, "minterms": minterms, "grupos": grupos,
        "fila_labels": fila_labels, "col_labels": col_labels, "n": n
    }


def encontrar_grupos(minterms, mapa, entradas, tabla):
    filas     = len(mapa)
    cols      = len(mapa[0]) if mapa else 0
    n         = len(entradas)
    pos       = {mapa[r][c]: (r, c) for r in range(filas) for c in range(cols)}
    mint_set  = set(minterms)
    grupos    = []
    cubiertos = set()
    colores   = ["#ef4444","#f97316","#eab308","#22c55e",
                 "#06b6d4","#6366f1","#ec4899","#14b8a6"]

    tamaños = []
    t = min(8, 2 ** n)
    while t >= 1:
        tamaños.append(t); t //= 2

    for tam in tamaños:
        for r0 in range(filas):
            for c0 in range(cols):
                for alto in [1, 2, 4]:
                    for ancho in [1, 2, 4]:
                        if alto * ancho != tam: continue
                        if alto > filas or ancho > cols: continue
                        celdas     = [mapa[(r0+dr)%filas][(c0+dc)%cols]
                                      for dr in range(alto) for dc in range(ancho)]
                        celdas_set = set(celdas)
                        if not celdas_set.issubset(mint_set):   continue
                        if celdas_set.issubset(cubiertos):      continue
                        termino    = simplificar_termino_grupo(celdas, entradas, tabla)
                        posiciones = [(pos[c][0], pos[c][1]) for c in celdas]
                        color      = colores[len(grupos) % len(colores)]
                        grupos.append({"celdas": celdas, "posiciones": posiciones,
                                       "termino": termino, "color": color, "tam": tam})
                        cubiertos |= celdas_set
        if cubiertos == mint_set: break
    return grupos


def simplificar_termino_grupo(celdas, entradas, tabla):
    filas_grupo = [tabla[i] for i in celdas]
    termino     = ""
    for var in entradas:
        valores = set(f[var] for f in filas_grupo)
        if len(valores) == 1:
            v        = list(valores)[0]
            termino += var if v == 1 else f"{var}'"
    return termino if termino else "1"


# ═══════════════════════════════════════════════════
# QUINE-McCLUSKEY
# ═══════════════════════════════════════════════════

def quine_mccluskey(entradas, salida_nombre, tabla):
    """Implementa Quine-McCluskey paso a paso."""
    n        = len(entradas)
    minterms = [i for i, f in enumerate(tabla) if f[salida_nombre] == 1]

    if not minterms:              return {"pasos": [], "expresion": "0"}
    if len(minterms) == len(tabla): return {"pasos": [], "expresion": "1"}

    def a_binario(num):        return format(num, f"0{n}b")
    def pueden_combinarse(a, b):
        diff = [i for i in range(n) if a[i] != b[i]]
        return len(diff) == 1, diff[0] if len(diff) == 1 else -1
    def combinar(a, b, pos):
        r = list(a); r[pos] = "-"; return "".join(r)
    def binario_a_termino(b):
        t = ""
        for i, c in enumerate(b):
            if   c == "1": t += entradas[i]
            elif c == "0": t += entradas[i] + "'"
        return t if t else "1"

    grupos = {}
    for m in minterms:
        b = a_binario(m); k = b.count("1")
        grupos.setdefault(k, []).append((b, frozenset([m])))

    pasos     = []
    filas_p1  = [{"minterms": sorted(ms), "binario": b, "unos": k}
                 for k in sorted(grupos) for b, ms in grupos[k]]
    pasos.append({
        "titulo":      "Paso 1 — Mintérminos agrupados por número de unos",
        "explicacion": "Se listan todos los mintérminos en binario y se agrupan según cuántos unos contienen.",
        "tipo":        "tabla_minterms",
        "columnas":    ["Mintérminos", "Binario", "Nº de unos"],
        "filas":       filas_p1
    })

    implicantes_primos = []
    ronda = 1

    while True:
        nuevos_grupos = {}
        usados        = set()
        filas_ronda   = []
        claves        = sorted(grupos.keys())

        for i in range(len(claves) - 1):
            k1, k2 = claves[i], claves[i + 1]
            if k2 - k1 != 1: continue
            for b1, ms1 in grupos[k1]:
                for b2, ms2 in grupos[k2]:
                    ok, pos = pueden_combinarse(b1, b2)
                    if ok:
                        nuevo    = combinar(b1, b2, pos)
                        ms_nuevo = ms1 | ms2
                        k_nuevo  = nuevo.replace("-", "0").count("1")
                        nuevos_grupos.setdefault(k_nuevo, [])
                        if (nuevo, ms_nuevo) not in nuevos_grupos[k_nuevo]:
                            nuevos_grupos[k_nuevo].append((nuevo, ms_nuevo))
                        usados.add((b1, ms1)); usados.add((b2, ms2))
                        filas_ronda.append({
                            "combinacion": f"{sorted(ms1)} + {sorted(ms2)}",
                            "resultado":   nuevo,
                            "termino":     binario_a_termino(nuevo)
                        })

        for k, lst in grupos.items():
            for item in lst:
                if item not in usados:
                    b, ms = item; t = binario_a_termino(b)
                    if t not in [ip["termino"] for ip in implicantes_primos]:
                        implicantes_primos.append({"minterms": sorted(ms), "binario": b, "termino": t})

        if filas_ronda:
            pasos.append({
                "titulo":      f"Paso {ronda + 1} — Combinaciones ronda {ronda}",
                "explicacion": "Se comparan grupos adyacentes. Si difieren en exactamente una posición, se combinan.",
                "tipo":        "tabla_combinaciones",
                "columnas":    ["Combinación", "Resultado", "Término"],
                "filas":       filas_ronda
            })

        if not nuevos_grupos:
            for k, lst in grupos.items():
                for item in lst:
                    b, ms = item; t = binario_a_termino(b)
                    if t not in [ip["termino"] for ip in implicantes_primos]:
                        implicantes_primos.append({"minterms": sorted(ms), "binario": b, "termino": t})
            break

        grupos = nuevos_grupos
        ronda += 1
        if ronda > 10: break

    pasos.append({
        "titulo":      f"Paso {ronda + 1} — Implicantes primos encontrados",
        "explicacion": "Los términos que no pudieron combinarse más son los implicantes primos.",
        "tipo":        "tabla_implicantes",
        "columnas":    ["Mintérminos cubiertos", "Binario", "Término simplificado"],
        "filas":       implicantes_primos
    })

    return {"pasos": pasos, "expresion": " + ".join(ip["termino"] for ip in implicantes_primos) or "0"}


# ═══════════════════════════════════════════════════
# LADDER — COMBINACIONAL
# ═══════════════════════════════════════════════════

def parsear_contacto(token):
    """Parsea token carácter por carácter — variables de un solo carácter."""
    contactos = []
    i = 0
    token = token.strip()
    while i < len(token):
        if token[i] == ' ': i += 1; continue
        if token[i].isalpha():
            var    = token[i]; i += 1
            negado = False
            if i < len(token) and token[i] == "'":
                negado = True; i += 1
            contactos.append({"var": var, "negado": negado})
        else:
            i += 1
    return contactos


def parsear_contacto_display(condicion_display):
    """Parsea condicion_display con nombres multicarácter separados por · o espacios."""
    contactos = []
    partes    = re.split(r'[·\s]+', condicion_display.strip())
    for parte in partes:
        parte = parte.strip()
        if not parte: continue
        negado = parte.endswith("'")
        var    = parte.rstrip("'").strip()
        if var:
            contactos.append({"var": var, "negado": negado})
    return contactos


def expresion_a_ladder(nombre_salida, expresion_simplificada):
    """Convierte expresión SOP a escalones Ladder."""
    if expresion_simplificada in ("0", "1"):
        return [{"contactos": [{"var": expresion_simplificada, "negado": False}],
                 "bobina": nombre_salida}]
    terminos  = [t.strip() for t in expresion_simplificada.split("+")]
    escalones = []
    for termino in terminos:
        termino = termino.strip()
        if not termino: continue
        contactos = parsear_contacto(termino)
        if contactos:
            escalones.append({"contactos": contactos, "bobina": nombre_salida})
    return escalones if escalones else [{"contactos": [], "bobina": nombre_salida}]


def construir_ladder(salidas):
    """Construye Ladder combinacional completo."""
    resultado = {"tipo": "combinacional", "salidas": []}
    for salida in salidas:
        escalones = expresion_a_ladder(salida["nombre"], salida["expresion_simplificada"])
        resultado["salidas"].append({"nombre": salida["nombre"], "escalones": escalones})
    return resultado


# ═══════════════════════════════════════════════════
# LADDER — SECUENCIAL (TEMPORIZADORES)
# ═══════════════════════════════════════════════════

def formatear_tiempo(tiempo_ms):
    if tiempo_ms >= 60000:
        m = tiempo_ms // 60000; s = (tiempo_ms % 60000) // 1000
        return f"{m}min {s}s" if s else f"{m}min"
    elif tiempo_ms >= 1000:
        seg = tiempo_ms / 1000
        return f"{int(seg)}s" if seg == int(seg) else f"{seg:.1f}s"
    return f"{tiempo_ms}ms"


def construir_ladder_temporizadores(entradas, salidas_nombres, temporizadores):
    """Construye estructura Ladder para problemas con temporizadores TON/TOF."""
    escalones_ladder = []
    for timer in temporizadores:
        nombre    = timer["nombre"]
        tipo      = timer["tipo"]
        tiempo_ms = timer["tiempo_ms"]
        salida    = timer["salida"]
        contactos_cond = parsear_contacto_display(timer["condicion_display"])

        escalones_ladder.append({
            "tipo":       "timer_coil",
            "contactos":  contactos_cond,
            "timer": {
                "nombre":          nombre,
                "tipo":            tipo,
                "tiempo_ms":       tiempo_ms,
                "tiempo_display":  formatear_tiempo(tiempo_ms)
            }
        })
        escalones_ladder.append({
            "tipo":      "timer_contact",
            "contactos": [{"var": nombre, "negado": False, "es_timer": True, "tipo_timer": tipo}],
            "bobina":    salida
        })

    return {
        "tipo":     "secuencial",
        "entradas": entradas,
        "salidas":  salidas_nombres,
        "escalones": escalones_ladder
    }


def construir_resumen_temporizadores(temporizadores):
    return [{
        "nombre":         t["nombre"],
        "tipo":           t["tipo"],
        "tipo_texto":     "Timer On Delay — salida activa después del tiempo"
                          if t["tipo"] == "TON"
                          else "Timer Off Delay — salida desactiva después del tiempo",
        "descripcion":    t["descripcion"],
        "condicion":      t["condicion_display"],
        "tiempo_ms":      t["tiempo_ms"],
        "tiempo_display": formatear_tiempo(t["tiempo_ms"]),
        "salida":         t["salida"]
    } for t in temporizadores]


# ═══════════════════════════════════════════════════
# PROCESAMIENTO DE UN SOLO SUBSISTEMA
# ═══════════════════════════════════════════════════

def procesar_subsistema(ss):
    """
    Aplica tabla de verdad, simplificación y Ladder a un subsistema.
    Retorna el subsistema enriquecido con todos los resultados.
    """
    n = len(ss["entradas"])

    if n > MAX_ENTRADAS:
        ss["error"] = (f"Este subsistema tiene {n} entradas, "
                       f"lo cual supera el límite de {MAX_ENTRADAS}. "
                       f"Se recomienda dividirlo en subsistemas más pequeños.")
        return ss

    try:
        ss["tabla"] = calcular_tabla(ss["entradas"], ss["salidas"])

        for salida in ss["salidas"]:
            salida["expresion_canonica"] = expresion_canonica(
                ss["entradas"], salida["nombre"], ss["tabla"]
            )
            if n <= 4:
                salida["metodo"]  = "karnaugh"
                salida["karnaugh"] = karnaugh_grupos(
                    ss["entradas"], salida["nombre"], ss["tabla"]
                )
                salida["expresion_simplificada"] = simplificar_con_sympy(
                    ss["entradas"], salida["nombre"], ss["tabla"]
                )
            else:
                salida["metodo"]  = "quine"
                qm                = quine_mccluskey(
                    ss["entradas"], salida["nombre"], ss["tabla"]
                )
                salida["quine_pasos"]            = qm["pasos"]
                salida["expresion_simplificada"] = qm["expresion"]

        ss["ladder"] = construir_ladder(ss["salidas"])

    except Exception as e:
        ss["error"] = f"Error procesando subsistema: {str(e)}"

    return ss


# ═══════════════════════════════════════════════════
# DEPENDENCIAS ENTRE SUBSISTEMAS
# ═══════════════════════════════════════════════════

def marcar_dependencias(subsistemas):
    """
    Marca qué entradas de cada subsistema son salidas de otro.
    Agrega campo 'entradas_externas': {"VAR": "SS_origen"}
    """
    salidas_globales = {}
    for ss in subsistemas:
        for sal in ss.get("salidas", []):
            salidas_globales[sal["nombre"]] = ss["id"]

    for ss in subsistemas:
        externas = {}
        for entrada in ss.get("entradas", []):
            if entrada in salidas_globales:
                externas[entrada] = salidas_globales[entrada]
        if externas:
            ss["entradas_externas"] = externas

    return subsistemas


# ═══════════════════════════════════════════════════
# ESTADÍSTICAS DEL SISTEMA
# ═══════════════════════════════════════════════════

def calcular_estadisticas(subsistemas):
    """Genera un resumen estadístico del sistema completo."""
    total_entradas  = sum(len(ss.get("entradas", [])) for ss in subsistemas)
    total_salidas   = sum(len(ss.get("salidas",  [])) for ss in subsistemas)
    total_escalones = 0
    for ss in subsistemas:
        if "ladder" in ss and ss["ladder"]:
            for sal in ss["ladder"].get("salidas", []):
                total_escalones += len(sal.get("escalones", []))

    por_prioridad = {1: 0, 2: 0, 3: 0}
    for ss in subsistemas:
        p = ss.get("prioridad", 3)
        por_prioridad[p] = por_prioridad.get(p, 0) + 1

    return {
        "total_subsistemas": len(subsistemas),
        "total_entradas":    total_entradas,
        "total_salidas":     total_salidas,
        "total_escalones":   total_escalones,
        "por_prioridad": {
            "emergencia":  por_prioridad.get(1, 0),
            "advertencia": por_prioridad.get(2, 0),
            "operacion":   por_prioridad.get(3, 0)
        },
        "dependencias": sum(
            1 for ss in subsistemas if ss.get("entradas_externas")
        )
    }


# ═══════════════════════════════════════════════════
# PROCESAMIENTO MODULAR
# ═══════════════════════════════════════════════════

def procesar_modular(data):
    """
    Procesa cada subsistema independientemente,
    marca dependencias y calcula estadísticas.
    """
    # Ordenar por prioridad (emergencias primero)
    subsistemas = sorted(
        data.get("subsistemas", []),
        key=lambda s: s.get("prioridad", 3)
    )

    # Procesar cada subsistema
    subsistemas = [procesar_subsistema(ss) for ss in subsistemas]

    # Marcar dependencias cruzadas
    subsistemas = marcar_dependencias(subsistemas)

    # Estadísticas generales
    estadisticas = calcular_estadisticas(subsistemas)

    return JSONResponse({
        "tipo":            "modular",
        "resumen_general": data.get("resumen_general", ""),
        "subsistemas":     subsistemas,
        "estadisticas":    estadisticas
    })


# ═══════════════════════════════════════════════════
# PROCESAMIENTO COMBINACIONAL
# ═══════════════════════════════════════════════════

def procesar_combinacional(data):
    """Procesa problema combinacional simple (un solo bloque)."""
    if "entradas" not in data or "salidas" not in data:
        return JSONResponse({"error": "Faltan campos 'entradas' o 'salidas'."})

    n = len(data["entradas"])
    if n > MAX_ENTRADAS:
        return JSONResponse({
            "error": (f"El problema tiene {n} entradas, lo cual supera el límite "
                      f"de {MAX_ENTRADAS}. El sistema lo dividirá automáticamente "
                      f"en subsistemas si vuelves a describir el problema con más detalle "
                      f"sobre las funciones de cada grupo de variables.")
        })

    data["tabla"] = calcular_tabla(data["entradas"], data["salidas"])

    for salida in data["salidas"]:
        salida["expresion_canonica"] = expresion_canonica(
            data["entradas"], salida["nombre"], data["tabla"]
        )
        if n <= 4:
            salida["metodo"]   = "karnaugh"
            salida["karnaugh"] = karnaugh_grupos(
                data["entradas"], salida["nombre"], data["tabla"]
            )
            salida["expresion_simplificada"] = simplificar_con_sympy(
                data["entradas"], salida["nombre"], data["tabla"]
            )
        else:
            salida["metodo"] = "quine"
            qm               = quine_mccluskey(
                data["entradas"], salida["nombre"], data["tabla"]
            )
            salida["quine_pasos"]            = qm["pasos"]
            salida["expresion_simplificada"] = qm["expresion"]

    data["ladder"] = construir_ladder(data["salidas"])
    return JSONResponse(data)


# ═══════════════════════════════════════════════════
# PROCESAMIENTO SECUENCIAL
# ═══════════════════════════════════════════════════

def procesar_secuencial(data):
    """Procesa problema secuencial con temporizadores."""
    if "temporizadores" not in data:
        return JSONResponse({
            "error": "El modelo no devolvió temporizadores para el problema secuencial."
        })

    data["ladder_secuencial"] = construir_ladder_temporizadores(
        data.get("entradas", []),
        data.get("salidas",  []),
        data["temporizadores"]
    )
    data["resumen_timers"] = construir_resumen_temporizadores(data["temporizadores"])
    return JSONResponse(data)


# ═══════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/chat")
def chat(body: Message):
    agent.messages.append({"role": "user", "content": body.message})

    # Bucle hasta respuesta final del agente
    while True:
        response = client.responses.create(
            model="gpt-4o-mini",
            input=agent.messages,
            tools=agent.tools
        )
        called_tool = agent.process_response(response)
        if not called_tool:
            break

    # Obtener último mensaje del asistente
    last = None
    for o in reversed(agent.messages):
        if isinstance(o, dict) and o.get("role") == "assistant":
            last = o
            break

    if not last:
        return JSONResponse({"error": "No se obtuvo respuesta del modelo."})

    # Limpiar posibles backticks
    text = last["content"] if isinstance(last["content"], str) else ""
    text = text.strip().strip("```json").strip("```").strip()

    try:
        data = json.loads(text)
    except Exception:
        return JSONResponse({"error": f"El modelo no devolvió JSON válido: {text}"})

    tipo = data.get("tipo", "")

    if tipo == "modular":
        return procesar_modular(data)
    elif tipo == "combinacional":
        return procesar_combinacional(data)
    elif tipo == "secuencial":
        return procesar_secuencial(data)
    else:
        return JSONResponse({
            "error": f"Tipo de problema no reconocido: '{tipo}'. "
                     f"El modelo debe devolver 'modular', 'combinacional' o 'secuencial'."
        })