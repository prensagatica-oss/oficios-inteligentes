# Oficios Inteligentes — etapa 1

Aplicación Streamlit para procesar un PDF con Gemini Flash-Lite, verificar manualmente el resultado y descargar JSON.

## Publicación gratuita en Streamlit Community Cloud
1. Crear un repositorio PRIVADO en GitHub y subir `app.py`, `requirements.txt` y `.gitignore` (NO subir claves).
2. Acceder a https://share.streamlit.io, vincular GitHub y desplegar `app.py`.
3. Configurar el secreto `GEMINI_API_KEY = "la-clave-que-creaste"` en el panel **Secrets** de la app, nunca en el repositorio.
4. Configurar la app como **privada** e invitar solo a los asesores autorizados.
5. Probar con un PDF público, no sensible.

## Limitaciones de esta primera etapa
- No lee ni escribe Google Sheets, no sube PDF a Drive y no sincroniza registros.
- Cada pulsación «Analizar» hace una consulta a Gemini. Hay límites en el nivel gratuito.
- La clave API nunca debe pegarse en el repositorio ni compartirse con los usuarios.
- La API gratuita no es adecuada para información sensible sin autorización institucional.
