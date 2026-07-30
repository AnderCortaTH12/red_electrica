FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# data/ y models/ NO se copian a la imagen: son estado que cambia con
# cada ingesta/reentrenamiento, no código. Se montan como volumenes en
# tiempo de ejecucion (ver README), asi la imagen no hay que
# reconstruirla cuando cambian los datos o el modelo. /health y
# /predict funcionan igual sin ellos (devuelven "ok_sin_modelo" / 503
# de forma controlada, ver src/serving/api.py), asi que la imagen
# arranca y responde aunque no haya nada montado todavia.

EXPOSE 8000

CMD ["uvicorn", "src.serving.api:app", "--host", "0.0.0.0", "--port", "8000"]
