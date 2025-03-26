import gradio as gr
from datetime import datetime
import os

# .
import speech_recognition as sr  #procesar voz y capturar lo que el usuario dice a través del micrófono.
from langchain_community.llms import Ollama # Modelo LLM
from gtts import gTTS  # Para convertir respuesta de LLM en voz
import os  # Acceder a archivos del sistema
#from playsound import playsound  # Para reproducir audio sin dependencias externas
import pygame  # Para reproducir audio

from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate

import time
import psycopg2
import json
import psycopg2
import json
from datetime import datetime, timedelta


# Variable global para el tiempo de inicio de la conversación
start_time = None

# Inicializar pygame para reproducir audio
pygame.mixer.init()

# 📌 Configuración de conexión a PostgreSQL
DB_CONFIG = {
    "dbname": "atom_db",
    "user": "atom",
    "password": "atom123",
    "host": "localhost",
    "port": "5433"
}

# Función para capturar audio en tiempo real
def capturar_audio():
    # Objeto Recognizer para manejar la captura y transcripción de audio
    recognizer = sr.Recognizer()
    with sr.Microphone() as source: #Abre el micrófono como fuente de audio
        print("Escuchando...")
        audio = recognizer.listen(source) #Capturamos el audio del micrófono.
        try:
            #Transcribir el audio a texto en español
            text = recognizer.recognize_google(audio, language="es-ES")
            print("Usuario:", text)
            return text  #texto transcrito
        except sr.UnknownValueError:
            print("No se pudo entender el audio")
        except sr.RequestError as e:
            print(f"Error al solicitar resultados: {e}")

# Función para convertir texto a voz
#def texto_a_voz(texto, archivo_salida="respuesta.mp3"):
def texto_a_voz(texto):
    # Generar un nombre único para el archivo de audio
    archivo_salida = f"respuesta_{int(time.time())}.mp3"

    # Convertir texto a voz
    tts = gTTS(text=texto, lang="es") #objeto para convertir el texto en voz en español
    tts.save(archivo_salida) #Guarda la voz generada en un archivo MP3
    print(f"Agente:", texto)


    # Reproducir el archivo de audio usando pygame
    pygame.mixer.music.load(archivo_salida)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():  # Esperar a que termine la reproducción
        pygame.time.Clock().tick(10)

    # Eliminar el archivo de audio después de reproducirlo
    #os.remove(archivo_salida)

def parse_respuesta(respuesta):
    """Parsea la respuesta del modelo LLM asegurando que sea un JSON válido."""
    try:
        if isinstance(respuesta, str):  # Si es un string, intenta convertirlo en JSON
            respuesta = json.loads(respuesta.strip())
        
        if isinstance(respuesta, dict):  # Verifica estructura esperada
            return {
                "intencion": respuesta.get("intencion", ""),
                "nombre": respuesta.get("nombre"),
                "empresa": respuesta.get("empresa"),
                "necesidad": respuesta.get("necesidad"),
                "presupuesto": respuesta.get("presupuesto"),
                "respuesta": respuesta.get("respuesta", "No tengo información para responder.")
            }
        else:
            raise ValueError("La respuesta no es un diccionario válido")
    
    except json.JSONDecodeError:
        print("❌ Error al convertir la respuesta en JSON:", respuesta)
        return {"respuesta": respuesta}  # Devolver un valor por defecto



def guardar_interaccion_bd(entrada_usuario, respuesta_parseada, duracion_interaccion=timedelta(seconds=15)):
    """Guarda la interacción en la base de datos PostgreSQL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        
        query = """
        INSERT INTO interacciones_voz (
            entrada_usuario, respuesta_agente, intencion, nombre_usuario, empresa, necesidad, 
            presupuesto, datos_json, duracion_interaccion, finalizada
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """
        
        values = (
            entrada_usuario,
            respuesta_parseada["respuesta"],
            respuesta_parseada["intencion"],
            respuesta_parseada["nombre"],
            respuesta_parseada["empresa"],
            respuesta_parseada["necesidad"],
            respuesta_parseada["presupuesto"],
            json.dumps(respuesta_parseada),
            duracion_interaccion,
            False  # La interacción no está finalizada por defecto
        )
        
        cur.execute(query, values)
        conn.commit()
        
        cur.close()
        conn.close()
        
        print("✅ Interacción guardada en la base de datos")
    except Exception as e:
        print(f"❌ Error al guardar en la BD: {e}")


# Configurar el prompt personalizado  3
prompt_template_bryan = PromptTemplate(
    input_variables=["historial", "entrada"],
    template="""
    Eres un asistente virtual de ATOM diseñado para interactuar con prospectos a través de voz.
    Tu objetivo es:
    
    1. Comprender la intención del usuario (preguntar por un producto, solicitar información, expresar dudas, etc.).
    2. Extraer información clave de la conversación:
        - Nombre del usuario (si lo menciona).
        - Empresa o negocio (si lo menciona).
        - Necesidad específica o problema que busca resolver.
        - Presupuesto estimado (si lo menciona).
    3. Responder de manera clara y útil, solo en español. No inventes respuestas si no tienes suficiente información.

    Historial de la conversación:
    {historial}

    Entrada del usuario:
    {entrada}


    Basado en esta entrada, responde EXCLUSIVAMENTE con un JSON bien formado con el siguiente esquema:
    {{
        "intencion": "<intención detectada>",
        "nombre": "<nombre del usuario si lo menciona, o null>",
        "empresa": "<empresa del usuario si lo menciona, o null>",
        "necesidad": "<resumen de la necesidad del usuario>",
        "presupuesto": "<presupuesto si lo menciona, o null>",
        "respuesta": "<tu respuesta en español>"
    }}

    Si algún dato no se menciona, usa `null` en su lugar.
    """
)


# Configurar el modelo de lenguaje y la memoria de la conversación
#llm_ollama = Ollama(model="tinyllama", temperature=0.2)
llm_ollama = Ollama(model="mistral", temperature=0.2)

memory = ConversationBufferMemory(memory_key="historial")  # Memoria para mantener el contexto

conversacion = ConversationChain(llm=llm_ollama, 
                                 memory=memory,
                                 prompt=prompt_template_bryan,
                                 input_key="entrada"  # Asegura que la entrada del usuario se pase correctamente
                                 )


# Interacción en tiempo real
print("Bienvenido al Agente de Voz de ATOM. ¿En qué puedo ayudarte hoy?")
texto_a_voz("Bienvenido al Agente de Voz de ATOM. ¿En qué puedo ayudarte hoy?")



# Versión adaptada para Gradio
def procesar_interaccion(texto_usuario, historial_chat):
    try:
        # Procesar con tu flujo existente
        respuesta_llm = conversacion.invoke({"entrada": texto_usuario})["response"]
        respuesta_parseada = parse_respuesta(respuesta_llm)
        guardar_interaccion_bd(texto_usuario, respuesta_parseada)
        
        # Generar archivo de audio
        archivo_audio = f"respuesta_gradio_{int(time.time())}.mp3"
        tts = gTTS(text=respuesta_parseada["respuesta"], lang="es")
        tts.save(archivo_audio)
        
        # Actualizar historial del chat
        nuevo_historial = historial_chat + [(texto_usuario, respuesta_parseada["respuesta"])]
        
        return nuevo_historial, "", archivo_audio
        
    except Exception as e:
        print(f"Error: {e}")
        return historial_chat, f"Error: {str(e)}", None

def capturar_audio_gradio():
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        print("Escuchando...")
        audio = recognizer.listen(source)
        try:
            texto = recognizer.recognize_google(audio, language="es-ES")
            print("Usuario:", texto)
            return texto
        except sr.UnknownValueError:
            return "No se pudo entender el audio"
        except sr.RequestError as e:
            return f"Error en el reconocimiento: {e}"

# Interfaz Gradio
with gr.Blocks(title="Agente de Voz ATOM") as demo:
    gr.Markdown("## Agente de Voz ATOM - Asistente Virtual")
    
    with gr.Row():
        with gr.Column():
            audio_input = gr.Audio(source="microphone", type="filepath", label="Habla ahora")
            btn_procesar_audio = gr.Button("Procesar Audio")
        with gr.Column():
            text_input = gr.Textbox(label="O escribe tu mensaje")
            btn_procesar_texto = gr.Button("Enviar Texto")
    
    chatbot = gr.Chatbot(label="Historial de Conversación")
    audio_output = gr.Audio(autoplay=True, label="Respuesta del Agente")
    clear_btn = gr.Button("Limpiar Conversación")
    
    estado_chat = gr.State([])
    
    def procesar_audio(audio_file):
        if audio_file:
            recognizer = sr.Recognizer()
            with sr.AudioFile(audio_file) as source:
                audio_data = recognizer.record(source)
                try:
                    texto = recognizer.recognize_google(audio_data, language="es-ES")
                    return texto
                except:
                    return ""
        return ""
    
    def procesar_con_audio(audio_file, historial):
        texto = procesar_audio(audio_file)
        if texto:
            return procesar_interaccion(texto, historial)
        return historial, "No se pudo procesar el audio", None
    
    btn_procesar_audio.click(
        procesar_con_audio,
        inputs=[audio_input, estado_chat],
        outputs=[chatbot, text_input, audio_output]
    )
    
    btn_procesar_texto.click(
        procesar_interaccion,
        inputs=[text_input, estado_chat],
        outputs=[chatbot, text_input, audio_output]
    )
    
    clear_btn.click(
        lambda: ([], []),
        outputs=[chatbot, estado_chat]
    )

# Iniciar la aplicación
if __name__ == "__main__":
    # Mensaje de bienvenida inicial
    print("Iniciando interfaz Gradio...")
    mensaje_bienvenida = "Bienvenido al Agente de Voz de ATOM. ¿En qué puedo ayudarte hoy?"
    archivo_bienvenida = "bienvenida.mp3"
    tts = gTTS(text=mensaje_bienvenida, lang="es")
    tts.save(archivo_bienvenida)
    
    demo.launch(server_port=7860, server_name="0.0.0.0")