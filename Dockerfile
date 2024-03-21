FROM langchain/langchain:latest

WORKDIR /app

COPY requirements.txt ./

RUN pip install --upgrade pip &&\
    pip install -r requirements.txt

COPY . .

CMD [ "python", "-u","./demo_fti.py"]

