#####Dockerfile######

FROM python:3.9-slim

EXPOSE 8501

WORKDIR /ChatBotDemo2

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -yqq

COPY . .

RUN pip3 install -r requirements.txt

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

ENTRYPOINT ["streamlit", "run", "StartChat2.py", "--server.port=8501", "--server.address=0.0.0.0"]

#######End Dockerfile######