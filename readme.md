installation:
    conda:
        1. conda create -n «env_name» python=«version>=3.10»
        2. pip install -r requirements.txt
        3. python demo_fti.py

    docker:
        docker build -t paulo/gen_agents_native_demo:1.0 .
        docker run paulo/gen_agents_native_demo:1.0