FROM jqmcginnis/lst-ai:latest

# Install Flask for HTTP wrapper
RUN pip install --no-cache-dir flask==3.1.0

# Copy HTTP wrapper
COPY server.py /app/server.py

EXPOSE 5000

CMD ["python", "/app/server.py"]
