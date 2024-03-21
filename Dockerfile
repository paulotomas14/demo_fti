FROM langchain/langchain:latest

WORKDIR /app

COPY requirements.txt ./

RUN pip install --upgrade pip &&\
    pip install -r requirements.txt

COPY . .

ENV LANGCHAIN_TRACING_V2=true LANGCHAIN_ENDPOINT="https://api.smith.langchain.com" LANGCHAIN_API_KEY="ls__2ed17e2811c94887b6481f8501cebda1" LANGCHAIN_PROJECT="gen_agents_demo" OPENAI_API_KEY="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"

CMD [ "python", "-u","./main.py"]

