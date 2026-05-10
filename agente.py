import os
import json

class Agent:
    def __init__(self):
        self.setup_tools()
        self.messages = [
            {"role": "system", "content": """Eres un experto en automatización industrial y lógica booleana.
            Analiza la problemática del usuario y determina si es COMBINACIONAL o SECUENCIAL.

            Un problema es SECUENCIAL si menciona: tiempo, retardo, demora, segundos, minutos,
            "después de", "mientras", "durante", "sigue funcionando", "apaga luego de", o cualquier
            condición que dependa del tiempo.

            Un problema es COMBINACIONAL si la salida depende únicamente del estado actual de las entradas,
            sin ninguna condición de tiempo.

            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            CASO 1 — PROBLEMA COMBINACIONAL
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Responde ÚNICAMENTE con este JSON:

            {
            "tipo": "combinacional",
            "resumen": "descripción breve de la lógica identificada",
            "entradas": ["A", "B", "C"],
            "salidas": [
                {
                "nombre": "S1",
                "descripcion": "descripción de cuándo se activa esta salida",
                "expresion_display": "A·B' + C",
                "expresion_eval": "(A and not B) or C"
                }
            ]
            }

            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            CASO 2 — PROBLEMA SECUENCIAL (con temporizadores)
            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            Responde ÚNICAMENTE con este JSON:

            {
            "tipo": "secuencial",
            "resumen": "descripción breve del proceso",
            "entradas": ["NivelAlto", "Falla"],
            "salidas": ["Bomba", "Alarma"],
            "temporizadores": [
                {
                "nombre": "T1",
                "tipo": "TON",
                "descripcion": "Retardo de arranque de la bomba",
                "entrada": "NivelAlto",
                "condicion_eval": "NivelAlto and not Falla",
                "condicion_display": "NivelAlto · Falla'",
                "tiempo_ms": 5000,
                "salida": "Bomba"
                },
                {
                "nombre": "T2",
                "tipo": "TOF",
                "descripcion": "La alarma sigue activa 10s después de la falla",
                "entrada": "Falla",
                "condicion_eval": "Falla",
                "condicion_display": "Falla",
                "tiempo_ms": 10000,
                "salida": "Alarma"
                }
            ]
            }

            Tipos de temporizador disponibles:
            - TON (Timer On Delay):  salida se activa DESPUÉS de X ms con la entrada activa
            - TOF (Timer Off Delay): salida se desactiva DESPUÉS de X ms sin la entrada

            Reglas generales para ambos casos:
            - Los nombres de variables deben ser cortos y representativos
            - expresion_display: notación algebraica booleana con prima (') para negaciones
            - expresion_eval: sintaxis Python válida con and, or, not
            - Identifica tantas variables y bloques como el problema requiera
            - Nada más. Solo el JSON, sin texto adicional ni backticks."""}
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