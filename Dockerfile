# Judge-mode image: the real app, no keys needed, one private copy per visitor.
# No Docker-in-Docker: helpers that run code are refused in judge mode.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY examples ./examples
RUN pip install . && useradd --create-home app
USER app

# Render sets PORT; locally it is 8787. RENDER_EXTERNAL_HOSTNAME is added to the allowed hosts by the app itself.
ENV PORT=8787
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/healthz',timeout=4)"
CMD ["bridge", "serve", "--judge-mode", "--host", "0.0.0.0"]
