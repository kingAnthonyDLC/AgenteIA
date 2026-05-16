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

MAX_ENTRADAS = 16


class Message(BaseModel):
    message: str


# ═══════════════════════════════════════════════════
# UTILIDADES COMUNES
# ═══════════════════════════════════════════════════

def parsear_contacto(token):
    """Parsea token carácter por carácter — variables de un solo carácter."""
    contactos = []
    i = 0
    token = token.strip()
    while i < len(token):
        if token[i] == ' ':
            i += 1
            continue
        if token[i].isalpha():
            var    = token[i]
            i     += 1
            negado = False
            if i < len(token) and token[i] == "'":
                negado = True
                i     += 1
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
        if not parte:
            continue
        negado = parte.endswith("'")
        var    = parte.rstrip("'").strip()
        if var:
            contactos.append({"var": var, "negado": negado})
    return contactos


def formatear_tiempo(tiempo_ms):
    if tiempo_ms >= 60000:
        m = tiempo_ms // 60000
        s = (tiempo_ms % 60000) // 1000
        return f"{m}min {s}s" if s else f"{m}min"
    elif tiempo_ms >= 1000:
        seg = tiempo_ms / 1000
        return f"{int(seg)}s" if seg == int(seg) else f"{seg:.1f}s"
    return f"{tiempo_ms}ms"


# ═══════════════════════════════════════════════════
# TABLA DE VERDAD
# ═══════════════════════════════════════════════════

def calcular_tabla(entradas, salidas):
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
    minterminos = []
    for fila in tabla:
        if fila[salida_nombre] == 1:
            termino = ""
            for var in entradas:
                termino += var if fila[var] == 1 else f"{var}'"
            minterminos.append(termino)
    if not minterminos:         return "0"
    if len(minterminos) == len(tabla): return "1"
    return " + ".join(minterminos)


# ═══════════════════════════════════════════════════
# SIMPLIFICACIÓN CON SYMPY
# ═══════════════════════════════════════════════════

def simplificar_con_sympy(entradas, salida_nombre, tabla):
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
    n        = len(entradas)
    minterms = [i for i, fila in enumerate(tabla) if fila[salida_nombre] == 1]
    if not minterms:                    return {"mapa": [], "grupos": [], "expresion": "0"}
    if len(minterms) == len(tabla):     return {"mapa": [], "grupos": [], "expresion": "1"}

    if n == 1:
        mapa = [[0], [1]]
        fila_labels = [entradas[0] + "'", entradas[0]]
        col_labels  = []
    elif n == 2:
        mapa = [[0, 1], [2, 3]]
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
    return {"mapa": mapa, "minterms": minterms, "grupos": grupos,
            "fila_labels": fila_labels, "col_labels": col_labels, "n": n}


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
                        if not celdas_set.issubset(mint_set): continue
                        if celdas_set.issubset(cubiertos):    continue
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
    n        = len(entradas)
    minterms = [i for i, f in enumerate(tabla) if f[salida_nombre] == 1]
    if not minterms:                    return {"pasos": [], "expresion": "0"}
    if len(minterms) == len(tabla):     return {"pasos": [], "expresion": "1"}

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

    pasos    = []
    filas_p1 = [{"minterms": sorted(ms), "binario": b, "unos": k}
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
                "titulo":      f"Paso {ronda+1} — Combinaciones ronda {ronda}",
                "explicacion": "Se comparan grupos adyacentes. Si difieren en una posición, se combinan.",
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
        grupos = nuevos_grupos; ronda += 1
        if ronda > 10: break

    pasos.append({
        "titulo":      f"Paso {ronda+1} — Implicantes primos encontrados",
        "explicacion": "Los términos que no pudieron combinarse más son los implicantes primos.",
        "tipo":        "tabla_implicantes",
        "columnas":    ["Mintérminos cubiertos", "Binario", "Término simplificado"],
        "filas":       implicantes_primos
    })
    return {"pasos": pasos, "expresion": " + ".join(ip["termino"] for ip in implicantes_primos) or "0"}


# ═══════════════════════════════════════════════════
# LADDER COMBINACIONAL
# ═══════════════════════════════════════════════════

def expresion_a_ladder(nombre_salida, expresion_simplificada):
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
    resultado = {"tipo": "combinacional", "salidas": []}
    for salida in salidas:
        escalones = expresion_a_ladder(salida["nombre"], salida["expresion_simplificada"])
        resultado["salidas"].append({"nombre": salida["nombre"], "escalones": escalones})
    return resultado


# ═══════════════════════════════════════════════════
# LADDER SECUENCIAL
# ═══════════════════════════════════════════════════

def construir_ladder_temporizadores(entradas, salidas_nombres, temporizadores):
    escalones_ladder = []
    for timer in temporizadores:
        contactos_cond = parsear_contacto_display(timer["condicion_display"])
        escalones_ladder.append({
            "tipo":      "timer_coil",
            "contactos": contactos_cond,
            "timer": {
                "nombre":         timer["nombre"],
                "tipo":           timer["tipo"],
                "tiempo_ms":      timer["tiempo_ms"],
                "tiempo_display": formatear_tiempo(timer["tiempo_ms"])
            }
        })
        escalones_ladder.append({
            "tipo":      "timer_contact",
            "contactos": [{"var": timer["nombre"], "negado": False,
                           "es_timer": True, "tipo_timer": timer["tipo"]}],
            "bobina":    timer["salida"]
        })
    return {"tipo": "secuencial", "entradas": entradas,
            "salidas": salidas_nombres, "escalones": escalones_ladder}


def construir_resumen_temporizadores(temporizadores):
    return [{
        "nombre":         t["nombre"],
        "tipo":           t["tipo"],
        "tipo_texto":     "Timer On Delay" if t["tipo"] == "TON" else "Timer Off Delay",
        "descripcion":    t["descripcion"],
        "condicion":      t["condicion_display"],
        "tiempo_ms":      t["tiempo_ms"],
        "tiempo_display": formatear_tiempo(t["tiempo_ms"]),
        "salida":         t["salida"]
    } for t in temporizadores]


# ═══════════════════════════════════════════════════
# LADDER POR CAPAS — construcción de escalones
# ═══════════════════════════════════════════════════

def expresion_display_a_escalones(expr_display, bobina_id):
    """
    Convierte una expresion_display con nombres multicarácter
    a escalones Ladder. Separa por + (paralelo) y cada término
    en contactos en serie.
    """
    if not expr_display or expr_display in ("0", "1"):
        return [{"contactos": [{"var": expr_display or "0", "negado": False}],
                 "bobina": bobina_id, "tipo": "normal"}]

    terminos  = [t.strip() for t in expr_display.split("+")]
    escalones = []
    for termino in terminos:
        termino = termino.strip()
        if not termino: continue
        contactos = parsear_contacto_display(termino)
        if contactos:
            escalones.append({"contactos": contactos, "bobina": bobina_id, "tipo": "normal"})
    return escalones if escalones else [{"contactos": [], "bobina": bobina_id, "tipo": "normal"}]


def construir_ladder_capa(capa):
    """
    Construye los escalones Ladder de una capa.
    Soporta tipos: normal, set_reset, exclusion_mutua.
    """
    escalones = []

    for salida in capa.get("salidas", []):
        sid   = salida.get("id", salida.get("nombre", "Q?"))
        tipo  = salida.get("tipo", "normal")

        if tipo == "set_reset":
            # Escalón SET
            if salida.get("condicion_set_display"):
                cts_set = parsear_contacto_display(salida["condicion_set_display"])
                escalones.append({
                    "tipo":      "set",
                    "contactos": cts_set,
                    "bobina":    sid,
                    "label":     f"SET {sid}"
                })
            # Escalón RESET
            if salida.get("condicion_reset_display"):
                cts_rst = parsear_contacto_display(salida["condicion_reset_display"])
                escalones.append({
                    "tipo":      "reset",
                    "contactos": cts_rst,
                    "bobina":    sid,
                    "label":     f"RST {sid}"
                })

        elif tipo in ("normal", "exclusion_mutua"):
            expr = salida.get("expresion_display", "")
            escs = expresion_display_a_escalones(expr, sid)
            # Marcar exclusión mutua para visualización
            for e in escs:
                e["exclusion_mutua"] = (tipo == "exclusion_mutua")
            escalones.extend(escs)

    return escalones


# ═══════════════════════════════════════════════════
# VALIDACIÓN DE ESCENARIOS
# ═══════════════════════════════════════════════════

def evaluar_escenario(escenario, variables_internas, capas_data):
    """
    Evalúa un escenario de validación contra las expresiones de las capas.
    Retorna resultado por salida: esperado vs obtenido.
    """
    entradas_esc  = escenario.get("entradas", {})
    esperadas     = escenario.get("salidas_esperadas", {})

    # Contexto base con las entradas del escenario
    contexto = {k: v for k, v in entradas_esc.items()}

    # Agregar variables internas al contexto
    for vi in variables_internas:
        vid = vi["id"]
        try:
            val = int(bool(eval(vi["expresion_eval"], {"__builtins__": {}}, contexto)))
        except Exception:
            val = 0
        contexto[vid] = val

    # Evaluar salidas de cada capa en orden
    for capa in capas_data:
        for salida in capa.get("salidas", []):
            sid  = salida.get("id", salida.get("nombre", ""))
            tipo = salida.get("tipo", "normal")

            if tipo == "set_reset":
                # Usar condicion_set para determinar estado
                expr = salida.get("condicion_set_eval", "False")
            else:
                expr = salida.get("expresion_eval", "False")

            try:
                val = int(bool(eval(expr, {"__builtins__": {}}, contexto)))
            except Exception:
                val = 0
            contexto[sid] = val

    # Comparar con esperadas
    resultados = []
    aprobado   = True
    for salida_id, val_esperado in esperadas.items():
        val_obtenido = contexto.get(salida_id, -1)
        ok           = (val_obtenido == val_esperado)
        if not ok: aprobado = False
        resultados.append({
            "salida":    salida_id,
            "esperado":  val_esperado,
            "obtenido":  val_obtenido,
            "ok":        ok
        })

    return {
        "nombre":     escenario.get("nombre", "Escenario"),
        "aprobado":   aprobado,
        "resultados": resultados,
        "entradas":   entradas_esc
    }


def validar_todos_escenarios(escenarios, variables_internas, capas_data):
    resultados = []
    for esc in escenarios:
        r = evaluar_escenario(esc, variables_internas, capas_data)
        resultados.append(r)
    total    = len(resultados)
    aprobados = sum(1 for r in resultados if r["aprobado"])
    return {
        "total":     total,
        "aprobados": aprobados,
        "fallidos":  total - aprobados,
        "escenarios": resultados
    }


# ═══════════════════════════════════════════════════
# ESTADÍSTICAS DEL SISTEMA DE CAPAS
# ═══════════════════════════════════════════════════

def estadisticas_capas(data):
    capas   = data.get("capas", [])
    entradas = data.get("entradas", [])
    salidas  = data.get("salidas",  [])

    total_escalones = 0
    for capa in capas:
        escalones = construir_ladder_capa(capa)
        total_escalones += len(escalones)

    set_reset     = sum(1 for c in capas for s in c.get("salidas", []) if s.get("tipo") == "set_reset")
    excl_mutua    = sum(1 for c in capas for s in c.get("salidas", []) if s.get("tipo") == "exclusion_mutua")
    vars_internas = len(data.get("variables_internas", []))

    return {
        "total_capas":        len(capas),
        "total_entradas":     len(entradas),
        "total_salidas":      len(salidas),
        "total_escalones":    total_escalones,
        "vars_internas":      vars_internas,
        "bobinas_set_reset":  set_reset,
        "exclusiones_mutuas": excl_mutua
    }


# ═══════════════════════════════════════════════════
# PROCESAMIENTO POR CAPAS
# ═══════════════════════════════════════════════════

def procesar_capas(data):
    """
    Procesa un sistema industrial complejo por capas funcionales.
    No genera tabla de verdad — las expresiones vienen directamente del modelo.
    """
    capas             = data.get("capas", [])
    variables_internas = data.get("variables_internas", [])
    escenarios        = data.get("escenarios_validacion", [])

    # Ordenar capas por prioridad
    capas = sorted(capas, key=lambda c: c.get("prioridad", 99))

    # Construir Ladder por capa
    capas_con_ladder = []
    for capa in capas:
        capa_resultado = dict(capa)
        capa_resultado["escalones_ladder"] = construir_ladder_capa(capa)
        capas_con_ladder.append(capa_resultado)

    # Validar escenarios
    validacion = validar_todos_escenarios(escenarios, variables_internas, capas)

    # Estadísticas
    stats = estadisticas_capas(data)

    return JSONResponse({
        "tipo":               "capas",
        "resumen_general":    data.get("resumen_general", ""),
        "entradas":           data.get("entradas", []),
        "salidas":            data.get("salidas",  []),
        "variables_internas": variables_internas,
        "capas":              capas_con_ladder,
        "validacion":         validacion,
        "estadisticas":       stats
    })


# ═══════════════════════════════════════════════════
# PROCESAMIENTO MODULAR
# ═══════════════════════════════════════════════════

def procesar_subsistema(ss):
    n = len(ss["entradas"])
    if n > MAX_ENTRADAS:
        ss["error"] = (f"Subsistema con {n} entradas supera el límite de {MAX_ENTRADAS}. "
                       f"Se recomienda dividirlo en subsistemas más pequeños.")
        return ss
    try:
        ss["tabla"] = calcular_tabla(ss["entradas"], ss["salidas"])
        for salida in ss["salidas"]:
            salida["expresion_canonica"] = expresion_canonica(
                ss["entradas"], salida["nombre"], ss["tabla"])
            if n <= 4:
                salida["metodo"]   = "karnaugh"
                salida["karnaugh"] = karnaugh_grupos(
                    ss["entradas"], salida["nombre"], ss["tabla"])
                salida["expresion_simplificada"] = simplificar_con_sympy(
                    ss["entradas"], salida["nombre"], ss["tabla"])
            else:
                salida["metodo"] = "quine"
                qm               = quine_mccluskey(
                    ss["entradas"], salida["nombre"], ss["tabla"])
                salida["quine_pasos"]            = qm["pasos"]
                salida["expresion_simplificada"] = qm["expresion"]
        ss["ladder"] = construir_ladder(ss["salidas"])
    except Exception as e:
        ss["error"] = f"Error procesando subsistema: {str(e)}"
    return ss


def marcar_dependencias(subsistemas):
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


def calcular_estadisticas_modular(subsistemas):
    total_entradas  = sum(len(ss.get("entradas", [])) for ss in subsistemas)
    total_salidas   = sum(len(ss.get("salidas",  [])) for ss in subsistemas)
    total_escalones = 0
    for ss in subsistemas:
        if "ladder" in ss and ss["ladder"]:
            for sal in ss["ladder"].get("salidas", []):
                total_escalones += len(sal.get("escalones", []))
    por_prioridad = {}
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
        "dependencias": sum(1 for ss in subsistemas if ss.get("entradas_externas"))
    }


def procesar_modular(data):
    subsistemas = sorted(data.get("subsistemas", []), key=lambda s: s.get("prioridad", 3))
    subsistemas = [procesar_subsistema(ss) for ss in subsistemas]
    subsistemas = marcar_dependencias(subsistemas)
    estadisticas = calcular_estadisticas_modular(subsistemas)
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
    if "entradas" not in data or "salidas" not in data:
        return JSONResponse({"error": "Faltan campos 'entradas' o 'salidas'."})
    n = len(data["entradas"])
    if n > MAX_ENTRADAS:
        return JSONResponse({
            "error": (f"El problema tiene {n} entradas y supera el límite de {MAX_ENTRADAS}. "
                      f"Describe el problema con más detalle sobre las funciones de cada grupo "
                      f"para que el sistema lo divida automáticamente.")
        })
    data["tabla"] = calcular_tabla(data["entradas"], data["salidas"])
    for salida in data["salidas"]:
        salida["expresion_canonica"] = expresion_canonica(
            data["entradas"], salida["nombre"], data["tabla"])
        if n <= 4:
            salida["metodo"]   = "karnaugh"
            salida["karnaugh"] = karnaugh_grupos(
                data["entradas"], salida["nombre"], data["tabla"])
            salida["expresion_simplificada"] = simplificar_con_sympy(
                data["entradas"], salida["nombre"], data["tabla"])
        else:
            salida["metodo"] = "quine"
            qm               = quine_mccluskey(
                data["entradas"], salida["nombre"], data["tabla"])
            salida["quine_pasos"]            = qm["pasos"]
            salida["expresion_simplificada"] = qm["expresion"]
    data["ladder"] = construir_ladder(data["salidas"])
    return JSONResponse(data)


# ═══════════════════════════════════════════════════
# PROCESAMIENTO SECUENCIAL
# ═══════════════════════════════════════════════════

def procesar_secuencial(data):
    if "temporizadores" not in data:
        return JSONResponse({"error": "El modelo no devolvió temporizadores."})
    data["ladder_secuencial"] = construir_ladder_temporizadores(
        data.get("entradas", []),
        data.get("salidas",  []),
        data["temporizadores"]
    )
    data["resumen_timers"] = construir_resumen_temporizadores(data["temporizadores"])
    return JSONResponse(data)

import random

def procesar_aleatorio(data):
    """
    Genera una tabla de verdad aleatoria respetando las
    cantidades por salida, luego la procesa como combinacional.
    """
    entradas     = data.get("entradas", [])
    salidas_def  = data.get("salidas",  [])
    excluir_cero = data.get("excluir_cero", True)
    n            = len(entradas)

    todas = list(itertools.product([0, 1], repeat=n))
    if excluir_cero:
        todas = [c for c in todas if any(v == 1 for v in c)]
    total_disponible = len(todas)

    # ── NUEVO: calcular automáticamente la salida sin cantidad ──
    sin_cantidad = [s for s in salidas_def if not s.get("cantidad")]
    con_cantidad = [s for s in salidas_def if s.get("cantidad")]

    if len(sin_cantidad) == 1:
        # Calcular la cantidad que falta
        suma_conocida = sum(s["cantidad"] for s in con_cantidad)
        restante      = total_disponible - suma_conocida
        if restante < 0:
            return JSONResponse({
                "error": (f"Las cantidades conocidas ({suma_conocida}) ya superan "
                          f"el total de combinaciones disponibles ({total_disponible}).")
            })
        sin_cantidad[0]["cantidad"] = restante

    elif len(sin_cantidad) > 1:
        return JSONResponse({
            "error": "Solo puede haber una salida con cantidad no especificada (el resto)."
        })

    # Validar que ahora sí sumen correctamente
    suma = sum(s.get("cantidad", 0) for s in salidas_def)
    if suma != total_disponible:
        return JSONResponse({
            "error": (f"Las cantidades suman {suma} pero hay "
                      f"{total_disponible} combinaciones disponibles "
                      f"({'excluyendo' if excluir_cero else 'incluyendo'} "
                      f"la combinación cero). Ajusta las cantidades.")
        })

    # Mezclar aleatoriamente y asignar salidas
    combinaciones = list(todas)
    random.shuffle(combinaciones)

    tabla = []
    idx   = 0
    for salida in salidas_def:
        cantidad = salida.get("cantidad", 0)
        for combo in combinaciones[idx:idx + cantidad]:
            fila = dict(zip(entradas, combo))
            for s in salidas_def:
                fila[s["nombre"]] = 1 if s["nombre"] == salida["nombre"] else 0
            tabla.append(fila)
        idx += cantidad

    # Ordenar la tabla por valor binario para mejor lectura
    tabla.sort(key=lambda f: sum(f[e] * (2 ** (n-1-i)) for i, e in enumerate(entradas)))

    # Construir salidas en formato compatible con procesar_combinacional
    salidas_completas = []
    for salida in salidas_def:
        nombre = salida["nombre"]
        # Generar expresion_eval desde la tabla
        minterminos_eval = []
        minterminos_disp = []
        for fila in tabla:
            if fila[nombre] == 1:
                termino_eval = " and ".join(
                    e if fila[e] == 1 else f"not {e}"
                    for e in entradas
                )
                termino_disp = "".join(
                    e if fila[e] == 1 else f"{e}'"
                    for e in entradas
                )
                minterminos_eval.append(f"({termino_eval})")
                minterminos_disp.append(termino_disp)

        expresion_eval    = " or ".join(minterminos_eval) if minterminos_eval else "False"
        expresion_display = " + ".join(minterminos_disp)  if minterminos_disp else "0"

        salidas_completas.append({
            "nombre":           nombre,
            "descripcion":      salida.get("descripcion", ""),
            "expresion_display": expresion_display,
            "expresion_eval":   expresion_eval
        })

    # Procesar como combinacional normal
    data_combinacional = {
        "tipo":    "combinacional",
        "resumen": data.get("resumen", "") + " [Combinaciones generadas aleatoriamente]",
        "entradas": entradas,
        "salidas":  salidas_completas,
        "tabla":    tabla,
        "aleatorio": True
    }

    # Simplificación
    for salida in data_combinacional["salidas"]:
        salida["expresion_canonica"] = expresion_canonica(
            entradas, salida["nombre"], tabla
        )
        # Con 5 variables → Quine-McCluskey
        if n <= 4:
            salida["metodo"]   = "karnaugh"
            salida["karnaugh"] = karnaugh_grupos(
                entradas, salida["nombre"], tabla
            )
            salida["expresion_simplificada"] = simplificar_con_sympy(
                entradas, salida["nombre"], tabla
            )
        else:
            salida["metodo"] = "quine"
            qm = quine_mccluskey(entradas, salida["nombre"], tabla)
            salida["quine_pasos"]            = qm["pasos"]
            salida["expresion_simplificada"] = qm["expresion"]

    data_combinacional["ladder"] = construir_ladder(data_combinacional["salidas"])

    return JSONResponse(data_combinacional)

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

    text = last["content"] if isinstance(last["content"], str) else ""
    text = text.strip().strip("```json").strip("```").strip()

    try:
        data = json.loads(text)
    except Exception:
        return JSONResponse({"error": f"El modelo no devolvió JSON válido: {text}"})

    tipo = data.get("tipo", "")

    if   tipo == "aleatorio":     return procesar_aleatorio(data)
    elif tipo == "capas":         return procesar_capas(data)
    elif tipo == "modular":       return procesar_modular(data)
    elif tipo == "combinacional": return procesar_combinacional(data)
    elif tipo == "secuencial":    return procesar_secuencial(data)
    else:
        return JSONResponse({
            "error": (f"Tipo de problema no reconocido: '{tipo}'. "
                      f"El modelo debe devolver 'capas', 'modular', 'combinacional' o 'secuencial'.")
        })