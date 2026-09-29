FROM python:3.12-alpine
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY app.py .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py"]
