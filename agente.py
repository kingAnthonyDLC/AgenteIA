import os
import json

class Agent:
    def __init__(self):
        self.setup_tools()
        self.messages = [
            {"role": "system", "content": """Eres un experto en automatización industrial y diseño de circuitos Ladder para PLC.

            Analiza la descripción del usuario y determina cuál de estos cuatro tipos de problema es:
            INSTRUCCIÓN CRÍTICA: Responde SIEMPRE y ÚNICAMENTE con el JSON
            correspondiente al tipo detectado. NUNCA incluyas explicaciones,
            texto introductorio, markdown, títulos con ###, fórmulas con \(,
            ni bloques de código con ```. Si tu respuesta contiene cualquier
            texto fuera del JSON, es incorrecta. Solo el objeto JSON, nada más.
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            TIPO 1 — COMBINACIONAL
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Úsalo cuando: el problema tiene pocas entradas (máximo 12), sin memoria,
            sin temporizadores y las salidas dependen únicamente del estado actual.

            {
            "tipo": "combinacional",
            "resumen": "descripción breve",
            "entradas": ["A", "B"],
            "salidas": [
                {
                "nombre": "S1",
                "descripcion": "cuándo se activa",
                "expresion_display": "A·B'",
                "expresion_eval": "A and not B"
                }
            ]
            }
             ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            TIPO 1B — ALEATORIO
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Úsalo cuando: el usuario pide que el sistema genere combinaciones
            al azar, o cuando describe cuántas combinaciones corresponden a
            cada salida pero NO especifica cuáles son.

            {
            "tipo": "aleatorio",
            "resumen": "descripción breve del sistema",
            "entradas": ["A", "B", "C", "D", "E"],
            "excluir_cero": true,
            "salidas": [
                {
                "nombre": "G",
                "descripcion": "combinación ganadora",
                "cantidad": 5
                },
                {
                "nombre": "R",
                "descripcion": "combinación perdedora",
                "cantidad": 10
                },
                {
                "nombre": "Y",
                "descripcion": "combinación empate",
                "cantidad": 17
                }
            ]
            }

            REGLAS para tipo aleatorio:
            - Usa "cantidad" en lugar de expresion_eval o expresion_display
            - Si el usuario dice "las demás" o "el resto", calcula la cantidad:
            total_combinaciones = 2^n (donde n = número de entradas)
            si excluir_cero=true, total_combinaciones -= 1
            cantidad_resto = total_combinaciones - suma de las otras cantidades
            - Si las cantidades no suman exactamente el total disponible, devuelve error en el JSON:
            {"tipo": "error", "mensaje": "Las cantidades no suman el total de combinaciones posibles"}
            - Las salidas deben ser mutuamente exclusivas (solo una activa por combinación)
             REGLAS para tipo aleatorio:
            - Si el usuario dice "las demás", "el resto" o no especifica la cantidad
            de una salida, usa "cantidad": 0 para esa salida.
            - Python calculará automáticamente cuántas combinaciones le corresponden.
            - Solo puede haber UNA salida con "cantidad": 0.
            - Nada más. Solo el JSON, sin backticks.

            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            TIPO 2 — SECUENCIAL
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Úsalo cuando: el problema menciona tiempo, retardo, segundos, minutos,
            "después de", "sigue funcionando", TON o TOF.

            {
            "tipo": "secuencial",
            "resumen": "descripción breve",
            "entradas": ["NivelAlto", "Falla"],
            "salidas": ["Bomba", "Alarma"],
            "temporizadores": [
                {
                "nombre": "T1",
                "tipo": "TON",
                "descripcion": "retardo de arranque",
                "entrada": "NivelAlto",
                "condicion_eval": "NivelAlto and not Falla",
                "condicion_display": "NivelAlto · Falla'",
                "tiempo_ms": 5000,
                "salida": "Bomba"
                }
            ]
            }

            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            TIPO 3 — MODULAR
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Úsalo cuando: el problema tiene entre 13 y 24 entradas totales y puede
            dividirse en grupos funcionales independientes de máximo 12 entradas cada uno.

            {
            "tipo": "modular",
            "resumen_general": "descripción del sistema",
            "subsistemas": [
                {
                "id": "SS1",
                "nombre": "Sistema de Seguridad",
                "prioridad": 1,
                "descripcion": "gestiona paradas de emergencia",
                "depende_de": [],
                "entradas": ["PB_STOP", "T_ALTA"],
                "salidas": [
                    {
                    "nombre": "PARO",
                    "descripcion": "para el sistema",
                    "expresion_display": "PB_STOP + T_ALTA",
                    "expresion_eval": "PB_STOP or T_ALTA"
                    }
                ]
                }
            ]
            }

            Prioridades: 1=Emergencia, 2=Advertencia, 3=Operación normal.
            Máximo 12 entradas por subsistema. Las salidas de un SS pueden ser entradas de otro.

            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            TIPO 4 — CAPAS (sistemas industriales complejos)
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Úsalo cuando: el problema tiene más de 24 entradas, o tiene memoria de marcha
            (circuito Set/Reset), enclavamientos, exclusión mutua entre salidas, jerarquía
            de alarmas, o secuencia obligatoria de rearme.
            En estos casos NO se genera tabla de verdad. Las expresiones se infieren
            directamente de la lógica descrita.

            {
            "tipo": "capas",
            "resumen_general": "descripción completa del sistema",
            "entradas": [
                {"id": "I0",  "nombre": "Pulsador inicio",         "tipo": "pulsador"},
                {"id": "I1",  "nombre": "Pulsador parada",         "tipo": "pulsador"},
                {"id": "I2",  "nombre": "Paro emergencia",         "tipo": "seguridad"},
                {"id": "I8",  "nombre": "Fuga detectada",          "tipo": "seguridad"},
                {"id": "I13", "nombre": "Nivel mínimo crudo",      "tipo": "sensor"},
                {"id": "I16", "nombre": "Sensor producto GLP",     "tipo": "sensor"}
            ],
            "salidas": [
                {"id": "Q0",  "nombre": "Habilitación general",    "tipo": "habilitacion"},
                {"id": "Q1",  "nombre": "Memoria de marcha",       "tipo": "memoria"},
                {"id": "Q13", "nombre": "Luz roja",                "tipo": "alarma"},
                {"id": "Q5",  "nombre": "Válvula GLP",             "tipo": "valvula"}
            ],
            "variables_internas": [
                {
                "id": "FALLA_CRITICA",
                "descripcion": "cualquier condición crítica activa",
                "expresion_display": "I2 + I8 + I9 + I10 + I11 + I12 + I6'",
                "expresion_eval": "I2 or I8 or I9 or I10 or I11 or I12 or not I6"
                },
                {
                "id": "ADVERTENCIA",
                "descripcion": "condición de advertencia sin falla crítica",
                "expresion_display": "TANQUE_LLENO + DOS_SENSORES",
                "expresion_eval": "TANQUE_LLENO or DOS_SENSORES"
                }
            ],
            "capas": [
                {
                "id": "C1",
                "nombre": "Seguridad y Fallas Críticas",
                "prioridad": 1,
                "descripcion": "detecta fallas críticas y activa alarmas de paro",
                "entradas_usadas": ["I2", "I6", "I8", "I9", "I10", "I11", "I12"],
                "salidas": [
                    {
                    "id": "Q13",
                    "nombre": "Luz roja",
                    "tipo": "normal",
                    "descripcion": "activa ante falla crítica",
                    "expresion_display": "I2 + I8 + I9 + I10 + I11 + I12 + I6'",
                    "expresion_eval": "I2 or I8 or I9 or I10 or I11 or I12 or not I6"
                    },
                    {
                    "id": "Q14",
                    "nombre": "Alarma sonora",
                    "tipo": "normal",
                    "descripcion": "activa con falla crítica",
                    "expresion_display": "FALLA_CRITICA",
                    "expresion_eval": "I2 or I8 or I9 or I10 or I11 or I12 or not I6"
                    }
                ]
                },
                {
                "id": "C2",
                "nombre": "Habilitación y Memoria de Marcha",
                "prioridad": 2,
                "descripcion": "controla arranque, parada y memoria del sistema",
                "entradas_usadas": ["I0", "I1", "I3", "I4", "I6", "I7"],
                "salidas_previas_usadas": ["FALLA_CRITICA"],
                "salidas": [
                    {
                    "id": "Q1",
                    "nombre": "Memoria de marcha",
                    "tipo": "set_reset",
                    "descripcion": "se activa con I0 y se resetea con I1 o falla crítica",
                    "condicion_set_display": "I0 · I3 · FALLA_CRITICA' · I6 · I7",
                    "condicion_set_eval": "I0 and I3 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and I6 and I7",
                    "condicion_reset_display": "I1 + FALLA_CRITICA",
                    "condicion_reset_eval": "I1 or I2 or I8 or I9 or I10 or I11 or I12 or not I6"
                    },
                    {
                    "id": "Q0",
                    "nombre": "Habilitación general",
                    "tipo": "normal",
                    "descripcion": "activa cuando Q1 está activo y no hay falla",
                    "expresion_display": "Q1 · FALLA_CRITICA'",
                    "expresion_eval": "Q1 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6)"
                    }
                ]
                },
                {
                "id": "C3",
                "nombre": "Actuadores Base",
                "prioridad": 3,
                "descripcion": "controla bomba principal y calentador",
                "entradas_usadas": ["I13", "I15"],
                "salidas_previas_usadas": ["Q0", "FALLA_CRITICA"],
                "salidas": [
                    {
                    "id": "Q2",
                    "nombre": "Bomba principal",
                    "tipo": "normal",
                    "descripcion": "requiere Q0 activo, nivel mínimo y sin falla",
                    "expresion_display": "Q0 · I13 · FALLA_CRITICA'",
                    "expresion_eval": "Q0 and I13 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6)"
                    },
                    {
                    "id": "Q3",
                    "nombre": "Calentador",
                    "tipo": "normal",
                    "descripcion": "requiere bomba activa y flujo confirmado",
                    "expresion_display": "Q2 · I15 · FALLA_CRITICA'",
                    "expresion_eval": "Q2 and I15 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6)"
                    }
                ]
                },
                {
                "id": "C4",
                "nombre": "Despacho y Válvulas",
                "prioridad": 4,
                "descripcion": "controla bomba de despacho y válvulas de producto con exclusión mutua",
                "entradas_usadas": ["I15", "I16", "I17", "I18", "I19", "I20", "I21",
                                    "I22", "I23", "I24", "I25", "I26", "I27"],
                "salidas_previas_usadas": ["Q2", "FALLA_CRITICA"],
                "exclusion_mutua": ["Q5", "Q6", "Q7", "Q8", "Q9", "Q10"],
                "variantes": [
                    {
                    "id": "V4",
                    "descripcion": "Si I25=1 (tanque diésel lleno): apagar Q4 y Q8, activar Q12, NO activar Q13"
                    }
                ],
                "salidas": [
                    {
                    "id": "Q4",
                    "nombre": "Bomba de despacho",
                    "tipo": "normal",
                    "descripcion": "activa con Q2 activo, flujo confirmado, sin falla y sin tanque diésel lleno",
                    "expresion_display": "Q2 · I15 · FALLA_CRITICA' · I25'",
                    "expresion_eval": "Q2 and I15 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not I25"
                    },
                    {
                    "id": "Q5",
                    "nombre": "Válvula GLP",
                    "tipo": "exclusion_mutua",
                    "descripcion": "abre solo con sensor GLP activo, tanque no lleno y sin otras válvulas",
                    "expresion_display": "Q4 · I16 · I22' · FALLA_CRITICA' · (I17+I18+I19+I20+I21)'",
                    "expresion_eval": "Q4 and I16 and not I22 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not (I17 or I18 or I19 or I20 or I21)"
                    },
                    {
                    "id": "Q6",
                    "nombre": "Válvula nafta",
                    "tipo": "exclusion_mutua",
                    "descripcion": "abre solo con sensor nafta activo, tanque no lleno y sin otras válvulas",
                    "expresion_display": "Q4 · I17 · I23' · FALLA_CRITICA' · (I16+I18+I19+I20+I21)'",
                    "expresion_eval": "Q4 and I17 and not I23 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not (I16 or I18 or I19 or I20 or I21)"
                    },
                    {
                    "id": "Q7",
                    "nombre": "Válvula queroseno",
                    "tipo": "exclusion_mutua",
                    "descripcion": "abre solo con sensor queroseno activo, tanque no lleno y sin otras válvulas",
                    "expresion_display": "Q4 · I18 · I24' · FALLA_CRITICA' · (I16+I17+I19+I20+I21)'",
                    "expresion_eval": "Q4 and I18 and not I24 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not (I16 or I17 or I19 or I20 or I21)"
                    },
                    {
                    "id": "Q8",
                    "nombre": "Válvula diésel",
                    "tipo": "exclusion_mutua",
                    "descripcion": "bloqueada si tanque diésel lleno (Variante 4)",
                    "expresion_display": "Q4 · I19 · I25' · FALLA_CRITICA' · (I16+I17+I18+I20+I21)'",
                    "expresion_eval": "Q4 and I19 and not I25 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not (I16 or I17 or I18 or I20 or I21)"
                    },
                    {
                    "id": "Q9",
                    "nombre": "Válvula gasóleo",
                    "tipo": "exclusion_mutua",
                    "descripcion": "abre solo con sensor gasóleo activo, tanque no lleno y sin otras válvulas",
                    "expresion_display": "Q4 · I20 · I26' · FALLA_CRITICA' · (I16+I17+I18+I19+I21)'",
                    "expresion_eval": "Q4 and I20 and not I26 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not (I16 or I17 or I18 or I19 or I21)"
                    },
                    {
                    "id": "Q10",
                    "nombre": "Válvula residuo",
                    "tipo": "exclusion_mutua",
                    "descripcion": "abre solo con sensor residuo activo, tanque no lleno y sin otras válvulas",
                    "expresion_display": "Q4 · I21 · I27' · FALLA_CRITICA' · (I16+I17+I18+I19+I20)'",
                    "expresion_eval": "Q4 and I21 and not I27 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not (I16 or I17 or I18 or I19 or I20)"
                    }
                ]
                },
                {
                "id": "C5",
                "nombre": "Señalización",
                "prioridad": 5,
                "descripcion": "luces de estado del sistema",
                "salidas_previas_usadas": ["Q0", "FALLA_CRITICA", "ADVERTENCIA"],
                "salidas": [
                    {
                    "id": "Q11",
                    "nombre": "Luz verde",
                    "tipo": "normal",
                    "descripcion": "sistema en operación normal sin advertencias ni fallas",
                    "expresion_display": "Q0 · FALLA_CRITICA' · ADVERTENCIA'",
                    "expresion_eval": "Q0 and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6) and not ADVERTENCIA"
                    },
                    {
                    "id": "Q12",
                    "nombre": "Luz amarilla",
                    "tipo": "normal",
                    "descripcion": "advertencia operativa: tanque lleno, dos sensores activos o tanque diésel lleno",
                    "expresion_display": "ADVERTENCIA · FALLA_CRITICA'",
                    "expresion_eval": "ADVERTENCIA and not (I2 or I8 or I9 or I10 or I11 or I12 or not I6)"
                    }
                ]
                }
            ],
            "escenarios_validacion": [
                {
                "nombre": "Falla crítica bloquea actuadores",
                "entradas": {"I2": 1, "I0": 1, "I6": 1, "I7": 1, "I3": 1},
                "salidas_esperadas": {"Q0": 0, "Q2": 0, "Q13": 1, "Q14": 1}
                },
                {
                "nombre": "Arranque normal",
                "entradas": {"I0": 1, "I3": 1, "I6": 1, "I7": 1, "I2": 0, "I8": 0,
                            "I9": 0, "I10": 0, "I11": 0, "I12": 0, "I13": 1},
                "salidas_esperadas": {"Q0": 1, "Q1": 1, "Q2": 1, "Q13": 0}
                },
                {
                "nombre": "Variante 4 tanque diesel lleno",
                "entradas": {"I25": 1, "Q2": 1, "I6": 1},
                "salidas_esperadas": {"Q4": 0, "Q8": 0, "Q12": 1, "Q13": 0}
                },
                {
                "nombre": "Dos sensores activos simultáneamente",
                "entradas": {"I16": 1, "I17": 1, "Q4": 1},
                "salidas_esperadas": {"Q5": 0, "Q6": 0, "Q12": 1}
                }
            ]
            }

            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            REGLAS GENERALES PARA TODOS LOS TIPOS
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            - Responde ÚNICAMENTE con el JSON correspondiente al tipo detectado
            - Sin texto adicional, sin backticks, sin explicaciones fuera del JSON
            - expresion_display: notación algebraica booleana con prima (') para negaciones
            - expresion_eval: sintaxis Python válida con and, or, not y paréntesis
            - Para tipo "capas": NO generes tabla de verdad, las expresiones se infieren directamente
            - Para tipo "capas" con Set/Reset: incluye condicion_set y condicion_reset por separado
            - Para tipo "capas" con exclusión mutua: lista las salidas en el campo "exclusion_mutua"
            - Identifica y lista TODOS los escenarios de validación críticos del problema"""}
        ]

    def setup_tools(self):
        self.tools = [
            {
                "type": "function",
                "name": "list_files_in_dir",
                "description": "Lista los archivos que existen en un directorio dado (por defecto es el directorio actual)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory": {
                            "type": "string",
                            "description": "Directorio para listar (opcional). Por defecto es el directorio actual"
                        }
                    },
                    "required": []
                }
            },
            {
                "type": "function",
                "name": "read_file",
                "description": "Lee el contenido de un archivo en una ruta especificada",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "La ruta del archivo a leer"
                        }
                    },
                    "required": ["path"]
                }
            },
            {
                "type": "function",
                "name": "edit_file",
                "description": "Edita el contenido de un archivo reemplazando prev_text por new_text. Crea el archivo si no existe.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "La ruta del archivo a editar"
                        },
                        "prev_text": {
                            "type": "string",
                            "description": "El texto que se va a buscar para reemplazar (puede ser vacío para archivos nuevos)"
                        },
                        "new_text": {
                            "type": "string",
                            "description": "El texto que reemplazará a prev_text (o el texto para un archivo nuevo)"
                        }
                    },
                    "required": ["path", "new_text"]
                }
            }
        ]

    # Herramienta: Listar archivos
    def list_files_in_dir(self, directory="."):
        print("  ⚙️ Herramienta llamada: list_files_in_dir")
        try:
            files = os.listdir(directory)
            return {"files": files}
        except Exception as e:
            return {"error": str(e)}

    # Herramienta: Leer archivos
    def read_file(self, path):
        print("  ⚙️ Herramienta llamada: read_file")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            err = f"Error al leer el archivo {path}: {str(e)}"
            print(err)
            return err

    # Herramienta: Editar archivos
    def edit_file(self, path, new_text, prev_text=""):
        print("  ⚙️ Herramienta llamada: edit_file")
        try:
            existed = os.path.exists(path)
            if existed and prev_text:
                content = self.read_file(path)
                if prev_text not in content:
                    return f"Texto '{prev_text}' no encontrado en el archivo"
                content = content.replace(prev_text, new_text)
            else:
                dir_name = os.path.dirname(path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                content = new_text

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            action = "editado" if existed and prev_text else "creado"
            return f"Archivo {path} {action} exitosamente"
        except Exception as e:
            err = f"Error al crear o editar el archivo {path}: {str(e)}"
            print(err)
            return err

    def process_response(self, response):
        # Almacenar salidas en el historial
        self.messages += response.output

        for output in response.output:
            if output.type == "function_call":
                fn_name = output.name
                args = json.loads(output.arguments)

                print(f"  - El modelo considera llamar a la herramienta: {fn_name}")
                print(f"  - Argumentos: {args}")

                if fn_name == "list_files_in_dir":
                    result = self.list_files_in_dir(**args)
                elif fn_name == "read_file":
                    result = self.read_file(**args)
                elif fn_name == "edit_file":
                    result = self.edit_file(**args)
                else:
                    result = {"error": f"Herramienta '{fn_name}' no reconocida"}

                # Agregar resultado al historial
                self.messages.append({
                    "type": "function_call_output",
                    "call_id": output.call_id,
                    "output": json.dumps({"result": result})
                })

                return True

            elif output.type == "message":
                # Guardar el mensaje del asistente en el historial correctamente
                content = "\n".join(
                    part.text for part in output.content
                    if hasattr(part, "text")
                )
                self.messages.append({
                    "role": "assistant",
                    "content": content
                })
                print(f"  ✓ Respuesta del modelo recibida ({len(content)} caracteres)")

        return False