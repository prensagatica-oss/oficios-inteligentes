import json
import re
import time
import random
from datetime import date

import requests
import streamlit as st

st.set_page_config(page_title='Oficios Inteligentes', page_icon='📑', layout='wide')

MODEL = 'gemini-3.1-flash-lite'
MAX_BYTES = 10 * 1024 * 1024

PROMPT = '''Eres analista documental técnico, jurídico, presupuestario y comunicacional del gabinete de una senadora de Chile. Tu estándar editorial es el de una matriz ejecutiva de seguimiento de oficios: análisis sustantivo, trazabilidad documental, prudencia en las conclusiones y gestiones accionables.

Analiza ÚNICAMENTE el PDF adjunto. NO busques fuentes externas, NO inventes antecedentes, NO presumas que una solicitud fue contestada, NO conviertas afirmaciones de un oficio en hechos institucionalmente corroborados. Distingue siempre: lo que solicita la senadora, lo que afirma la institución, hechos documentados, contradicciones, vacíos y recomendaciones propias. Cuando el contenido sea insuficiente, indica expresamente "No consta en el documento" o "Pendiente de verificar" y acorta el campo. Si el PDF contiene más de un oficio o respuesta, identifica los folios por separado y advierte sobre la relación documental.

Devuelve ÚNICAMENTE un objeto JSON válido, sin markdown, con estas claves exactas (todos los campos son texto salvo "alertas", que es una lista):
"tipo_doc": "Oficio", "Respuesta de Oficio" u "Oficio y Respuesta".
"nro_oficio": folio de la solicitud parlamentaria (si no consta con certeza, "").
"fecha": fecha del documento principal en YYYY-MM-DD (o "").
"materia": objeto del oficio en 1 a 3 oraciones precisas.
"destino": órgano destinatario del oficio o emisor de la respuesta, identificado con claridad.
"resumen_solicitud": 180 a 300 palabras orientativas, proporcionales a la evidencia. En 2 a 4 párrafos, desarrollar problema y contexto, solicitud exacta, antecedentes técnicos/jurídicos/presupuestarios, localidades, cifras, fechas, organismos, medidas o información pedida y finalidad administrativa. Si solo se adjunta respuesta, identificar si la solicitud original consta literalmente o solo es reconstruible parcialmente.
"resumen_respuesta": 180 a 320 palabras orientativas SI el PDF contiene contestación institucional. Describir organismo y folio de respuesta, qué responde a cada pregunta, cifras y periodos, decisiones/compromisos y sus condiciones, trámites, fechas, anexos, divergencias y solicitudes sin respuesta. Distinguir asignación de transferencia, proyecto propuesto de proyecto financiado, declaración institucional de cumplimiento efectivo. Si solo hay oficio, devolver "".
"analisis_ejecutivo": 220 a 380 palabras orientativas con encabezados breves dentro del texto: SOLICITUD DE LA SENADORA; RESPUESTA DEL ORGANISMO (solo si existe); HALLAZGO Y VACÍOS. Reconstruir el caso con rigor, límites de evidencia, contradicciones, variables presupuestarias, estado verificable y valor para el seguimiento. Evitar duplicación mecánica y extender solo cuando haya sustancia.
"hallazgo": 90 a 170 palabras orientativas sobre el dato central verificable, sus alcances y límites; si falta documentación, detallar qué no quedó acreditado. Citar internamente folios/fechas/páginas del PDF cuando puedan identificarse con certeza.
"potencial_com": exclusivamente "ALTO", "MEDIO" o "BAJO" como clasificación preliminar.
"fundamento_potencial": 100 a 180 palabras que expliquen relevancia regional/nacional, novedad, interés ciudadano, posibilidad de comunicar y condiciones que limitan su difusión. No confundir potencial con hecho demostrado ni riesgo con irregularidad.
"propuesta_com": 130 a 240 palabras orientativas. Proponer formato (reel, comunicado, nota o reserva), enfoque/titular tentativo, 3 a 5 mensajes o puntos narrativos, datos que podrían exhibirse, verificaciones PREVIAS y advertencias de qué no afirmar. Si falta evidencia, recomendar no difundir por ahora y explicar por qué.
"gestion_recomendada": 150 a 260 palabras, separando GESTIONES PREVIAS y GESTIONES POSTERIORES. Indicar organismos competentes, documentos e indicadores concretos por solicitar, contraste de cifras, verificación territorial, plazos solo si constan y alternativas de seguimiento. No afirmar que las gestiones ya ocurrieron.
"recomendacion_ejecutiva": 100 a 180 palabras con decisión práctica y prioridad (alta/media/baja), su fundamento, condición necesaria para comunicar o escalar, y próximo paso verificable.
"estado_gestion": 70 a 150 palabras. Clasificación administrativa propuesta conforme al PDF: solicitud sin respuesta acreditada; respuesta recibida; respuesta parcial; información contradictoria; u otro estado claramente documentado. Identificar lo pendiente y el siguiente hito. No afirmar que se envió un oficio complementario si no consta.
"alertas": lista de hasta 8 observaciones verificables: datos faltantes, contradicciones, folios ambiguos, cifras incomparables, información que requiere cotejo o riesgo de atribución.

Estos rangos son orientativos, NO cuotas de relleno. En oficios de una página o respuestas muy breves, sintetiza cuanto permita la evidencia. Evita fórmulas vacías, retórica, imputaciones de responsabilidades y conclusiones políticas sin sustento. Cuando corresponda, separa hechos, inferencias y propuestas. Escribe en español claro y útil para imprimir, revisar y entregar a jefatura.'''


def key():
    try:
        return st.secrets.get('GEMINI_API_KEY', '')
    except Exception:
        return ''


def gemini_analyze(data: bytes, mime: str, api_key: str) -> dict:
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
    import base64
    payload = {
        'contents': [{'role': 'user', 'parts': [
            {'text': PROMPT},
            {'inline_data': {'mime_type': mime, 'data': base64.b64encode(data).decode('ascii')}}
        ]}],
        'generationConfig': {'temperature': 0.1, 'responseMimeType': 'application/json', 'maxOutputTokens': 7500}
    }
    response = None
    for attempt in range(3):
        try:
            response = requests.post(url, headers={'x-goog-api-key': api_key}, json=payload, timeout=100)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt == 2:
                raise RuntimeError('No se pudo contactar a Gemini después de tres intentos. Inténtalo más tarde.')
            time.sleep(2 ** attempt + random.uniform(0, 0.5))
            continue
        if response.status_code in (500, 502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt + random.uniform(0, 0.5))
            continue
        break
    if response.status_code == 429:
        raise RuntimeError('Se alcanzó un límite de solicitudes de Gemini (HTTP 429). Revisa la cuota gratuita en AI Studio; no se harán reintentos automáticos.')
    if response.status_code == 503:
        raise RuntimeError('Gemini está temporalmente sobrecargado (HTTP 503). Se intentó tres veces. Prueba más tarde; no cambies tu clave.')
    if response.status_code in (400, 401, 403, 404):
        raise RuntimeError(f'Gemini devolvió HTTP {response.status_code}. Revisa los modelos y permisos habilitados para tu proyecto en Google AI Studio.')
    if not response.ok:
        raise RuntimeError(f'Gemini devolvió HTTP {response.status_code}. Vuelve a intentar más tarde o revisa la disponibilidad del servicio.')
    body = response.json()
    candidates = body.get('candidates', [])
    if not candidates:
        raise RuntimeError('Gemini no entregó un análisis. Revisa si el PDF es legible.')
    text = ''.join(p.get('text', '') for p in candidates[0].get('content', {}).get('parts', []))
    return json.loads(text)


st.title('📑 Oficios Inteligentes')
st.caption('Gabinete senatorial · Prototipo de ingreso y análisis documental con IA')

with st.sidebar:
    st.header('Estado de conexión')
    if key():
        st.success('Gemini configurado')
    else:
        st.warning('Gemini pendiente de configurar')
    st.info('Esta primera versión solo analiza: NO escribe en Google Sheets ni en Drive.')
    st.markdown('[Abrir Base de Oficios](https://docs.google.com/spreadsheets/d/1nevQVu-D-er9Hrw1YIJVEyj5gK5_lm3By1tvmrzAaoM/edit)')
    st.markdown('[Carpeta de recepción](https://drive.google.com/drive/folders/1PEhTbJHASJIlng8VpMiYgAm0OgTXgB43)')

st.subheader('Analizar un documento')
st.info('Prueba únicamente con un PDF público y sin información sensible. El nivel gratuito de Gemini puede utilizar los datos para mejorar sus servicios.')
upload = st.file_uploader('Selecciona un oficio o una respuesta institucional', type=['pdf'], accept_multiple_files=False)

if upload:
    data = upload.getvalue()
    st.write(f'**Documento:** {upload.name} · {len(data)/1024:.0f} KB')
    if len(data) > MAX_BYTES:
        st.error('Para esta primera versión se admiten archivos de hasta 10 MB.')
    elif not data.startswith(b'%PDF'):
        st.error('El archivo no parece ser un PDF válido.')
    elif st.button('Analizar con Gemini', type='primary', disabled=not bool(key())):
        try:
            with st.spinner('Analizando PDF...'):
                result = gemini_analyze(data, 'application/pdf', key())
            st.session_state['resultado'] = result
            st.session_state['archivo_nombre'] = upload.name
        except Exception as e:
            st.error(str(e))

if 'resultado' in st.session_state and upload and st.session_state.get('archivo_nombre') == upload.name:
    r = st.session_state['resultado']
    st.divider()
    st.subheader('Revisión del análisis')
    st.caption('Estos campos son propuestas de la IA. Verifícalos con el PDF original antes de incorporarlos a la planilla.')
    col1, col2, col3 = st.columns(3)
    with col1:
        tipo = st.selectbox('Tipo de documento', ['Oficio', 'Respuesta de Oficio', 'Oficio y Respuesta'], index=['Oficio', 'Respuesta de Oficio', 'Oficio y Respuesta'].index(r.get('tipo_doc')) if r.get('tipo_doc') in ['Oficio', 'Respuesta de Oficio', 'Oficio y Respuesta'] else 0)
        nro = st.text_input('Número de oficio', str(r.get('nro_oficio', '')))
    with col2:
        fecha = st.text_input('Fecha YYYY-MM-DD', str(r.get('fecha', '')))
        destino = st.text_input('Destinatario / institución', str(r.get('destino', '')))
    with col3:
        potencial = st.selectbox('Potencial comunicacional', ['ALTO', 'MEDIO', 'BAJO'], index=['ALTO', 'MEDIO', 'BAJO'].index(r.get('potencial_com')) if r.get('potencial_com') in ['ALTO', 'MEDIO', 'BAJO'] else 2)
    materia = st.text_area('Materia', str(r.get('materia', '')), height=90)
    st.markdown('### Análisis documental')
    solicitud = st.text_area('Resumen detallado del oficio / solicitud', str(r.get('resumen_solicitud', '')), height=280)
    respuesta = st.text_area('Resumen detallado de la respuesta institucional', str(r.get('resumen_respuesta', '')), height=280)
    analisis = st.text_area('ANÁLISIS EJECUTIVO', str(r.get('analisis_ejecutivo', '')), height=330)
    hallazgo = st.text_area('Hallazgo principal y vacíos documentales', str(r.get('hallazgo', '')), height=180)
    st.markdown('### Evaluación comunicacional')
    fundamento = st.text_area('Fundamento del potencial comunicacional', str(r.get('fundamento_potencial', '')), height=190)
    propuesta = st.text_area('PROPUESTA COMUNICACIONAL', str(r.get('propuesta_com', '')), height=250)
    st.markdown('### Seguimiento y decisión ejecutiva')
    gestion = st.text_area('GESTIONES RECOMENDADAS', str(r.get('gestion_recomendada', '')), height=260)
    recomendacion = st.text_area('RECOMENDACIÓN EJECUTIVA', str(r.get('recomendacion_ejecutiva', '')), height=200)
    estado_gestion = st.text_area('ESTADO DE GESTIÓN', str(r.get('estado_gestion', '')), height=180)
    alertas = r.get('alertas', [])
    if alertas:
        st.warning('Observaciones de verificación: ' + ' · '.join(str(x) for x in alertas))
    salida = dict(tipo_doc=tipo, nro_oficio=nro, fecha=fecha, materia=materia, destino=destino, resumen_solicitud=solicitud, resumen_respuesta=respuesta, analisis_ejecutivo=analisis, hallazgo=hallazgo, potencial_com=potencial, fundamento_potencial=fundamento, propuesta_com=propuesta, gestion_recomendada=gestion, recomendacion_ejecutiva=recomendacion, estado_gestion=estado_gestion, alertas=alertas)
    st.download_button('Descargar análisis revisado (JSON)', data=json.dumps(salida, ensure_ascii=False, indent=2), file_name='analisis_oficio.json', mime='application/json')
    st.caption('La sincronización con Buzon_Revision y Base_Oficios se incorporará después de validar esta etapa de análisis.')
