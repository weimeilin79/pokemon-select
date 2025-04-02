FROM apache/beam_python3.12_sdk:2.64.0

COPY df_requirements.txt .

# Pre-install Python dependencies. For reproducibile builds,
# supply all of the dependencies and their versions in a requirements.txt file.
RUN pip install -r df_requirements.txt
