installation:
    conda:
        1. conda create -n «env_name» python=«version>=3.10»
        2. pip install -r requirements.txt
        3. python demo_fti.py

    docker:
        1. Start your Docker engine
        2. docker build -t paulo/demo_fti:1.0 .
        3. docker run -it paulo/demo_fti:1.0