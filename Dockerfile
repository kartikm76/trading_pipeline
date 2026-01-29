FROM public.ecr.aws/emr-serverless/spark/emr-7.1.0:latest

USER root

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Create app directory and copy the source code
RUN mkdir -p /app/src
COPY src/main.py /app/
COPY src /app/src

# Set working directory
WORKDIR /app

# The entrypoint isn't needed here as EMR defines it,
# but we set the user back to the default Spark user
USER hadoop
