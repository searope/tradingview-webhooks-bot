FROM python:3.11-alpine

COPY src /app
WORKDIR /app
RUN pip install --trusted-host pypi.python.org -r requirements.txt
EXPOSE 80

ENTRYPOINT ["python3", "tvwb.py" , "start", "--port 80"]