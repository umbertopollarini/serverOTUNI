# Use Ubuntu 22.04 base image
FROM ubuntu:22.04

# Avoiding user interaction with tzdata
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Rome

RUN apt-get update && apt-get install -y curl
# Install nodejs v18
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
RUN apt-get install -y nodejs

RUN apt update && \
    apt install -y python3 python3-pip -y && \
    rm -rf /var/lib/apt/lists/*
ENV PATH="/usr/bin/python3:$PATH"
# Set LD_LIBRARY_PATH
ENV LD_LIBRARY_PATH=/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH
RUN ldconfig

# Imposta il working directory all'interno del container
WORKDIR /app
# Copia i file Python nella directory corrente del container
COPY . .

# Esegui il comando per installare le dipendenze
ENV CRYPTOGRAPHY_DONT_BUILD_RUST=1

# Installa libffi-dev e libssl-dev
RUN apt-get update && apt-get install -y libffi-dev libssl-dev 

# Installa tzdata e configura il fuso orario
RUN apt-get update && apt-get install -y tzdata
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Installa setuptools
RUN pip install --upgrade pip
RUN pip install setuptools

RUN pip3 install -r requirements.txt

ENV API_PORT=9000
EXPOSE 9000

# Specify the entry point with a shell
ENTRYPOINT ["python3", "server.py"]
