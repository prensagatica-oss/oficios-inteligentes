import json
import re
from datetime import date

import requests
import streamlit as st

st.set_page_config(page_title='Oficios Inteligentes', page_icon='📑', layout='wide')

MODEL = 'gemini-2.5-flash-lite'
MAX_BYTES = 10 * 1024 * 1024

PROMPT = '''Eres analista documental del gabinete de una senadora de Chile. Analiza el PDF adjunto únicamente a partir de su contenido. Extrae información verificable. No inventes fechas, folios, respuestas o compromisos.
Devuelve exclusivamente un objeto JSON con estas claves exactas:
"tipo_doc" ("Oficio", "Respuesta de Oficio" u "Oficio y Respuesta"),
"nro_oficio" (texto o ""), "fecha" (YYYY-MM-DD o ""),
"materia" (resumen de una oración), "destino" (institución destinataria o emisora),
"resumen_solicitud" (máximo 55 palabras o ""),
"resumen_respuesta" (máximo 65 palabras o "" si no hay respuesta),
"hallazgo" (dato verificable, con cifra/fecha cuando exista; o ""),
"potencial_com" ("ALTO", "MEDIO" o "BAJO"),
"propuesta_com" (una oración, condicional y sin afirmaciones no verificadas),
"gestion_recomendada" (una gestión administrativa concreta o ""),
"alertas" (lista de hasta 5 dudas o datos no encontrados).
Si el documento es solo un oficio enviado, no deduzcas que existe respuesta. Si aparecen múltiples números de oficio y no se puede decidir el principal, deja nro_oficio vacío y explica en alertas.
Prioriza precisión por encima de interpretaciones políticas o comunicacionales. No uses información externa al PDF.'''


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
        'generationConfig': {'temperature': 0.1, 'responseMimeType': 'application/json', 'maxOutputTokens': 1900}
    }
    response = requests.post(url, params={'key': api_key}, json=payload, timeout=100)
    if response.status_code == 429:
        raise RuntimeError('Se alcanzó la cuota gratuita de Gemini. Inténtalo más tarde; no se realizó ningún cobro desde la aplicación.')
    if not response.ok:
        raise RuntimeError(f'Gemini devolvió HTTP {response.status_code}. Revisa la clave, permisos y cuota del proyecto. No se mostrará el detalle por seguridad.')
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
    st.success('Gemini configurado' if key() else 'Gemini pendiente de configurar') if key() else st.warning('Gemini pendiente de configurar')
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
    materia = st.text_area('Materia', str(r.get('materia', '')), height=80)
    solicitud = st.text_area('Resumen de solicitud', str(r.get('resumen_solicitud', '')), height=100)
    respuesta = st.text_area('Resumen de respuesta', str(r.get('resumen_respuesta', '')), height=100)
    hallazgo = st.text_area('Hallazgo', str(r.get('hallazgo', '')), height=80)
    propuesta = st.text_area('Propuesta comunicacional', str(r.get('propuesta_com', '')), height=80)
    gestion = st.text_area('Gestión recomendada', str(r.get('gestion_recomendada', '')), height=80)
    alertas = r.get('alertas', [])
    if alertas:
        st.warning('Observaciones de verificación: ' + ' · '.join(str(x) for x in alertas))
    salida = dict(tipo_doc=tipo, nro_oficio=nro, fecha=fecha, materia=materia, destino=destino, resumen_solicitud=solicitud, resumen_respuesta=respuesta, hallazgo=hallazgo, potencial_com=potencial, propuesta_com=propuesta, gestion_recomendada=gestion, alertas=alertas)
    st.download_button('Descargar análisis revisado (JSON)', data=json.dumps(salida, ensure_ascii=False, indent=2), file_name='analisis_oficio.json', mime='application/json')
    st.caption('La sincronización con Buzon_Revision y Base_Oficios se incorporará después de validar esta etapa de análisis.')
