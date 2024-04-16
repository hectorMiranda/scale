FROM nvidia/cuda:12.4.0-devel-ubuntu22.04

# Set the working directory inside the container
WORKDIR /pai


RUN apt update && apt upgrade -y
RUN apt-get update
RUN apt install net-tools -y
RUN apt install software-properties-common -y
RUN add-apt-repository ppa:deadsnakes/ppa -y
RUN apt update
RUN apt install python3.10 -y
RUN apt install python-is-python3 -y
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN update-alternatives --config python3
RUN curl https://bootstrap.pypa.io/get-pip.py | python
RUN apt install python3-pip -y
RUN apt install python3.10-distutils -y
RUN apt install npm -y
RUN apt-get install libsndfile1 -y 
RUN apt install libasound2-dev -y
RUN apt install ffmpeg -y
RUN apt-get install autotools-dev -y
RUN apt-get install automake -y
RUN apt-get install libtool -y
RUN git clone https://github.com/espeak-ng/espeak-ng.git
WORKDIR /pai/espeak-ng
RUN ./autogen.sh
RUN ./configure --without-pulseaudio
RUN make
RUN make install

# Copy the current directory contents into the container at /pai
COPY . /pai

WORKDIR /pai/web
RUN npm install

# Install Rust compiler
RUN apt-get install curl -y
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Update pip, setuptools, and wheel
RUN python3 -m pip install --upgrade pip setuptools wheel

WORKDIR /pai/api
# Use python3 -m pip to ensure correct pip is used
RUN python3 -m pip install -r requirements.txt
RUN CMAKE_ARGS="-DLLAMA_CUBLAS=on" python3 -m pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
#RUN python3 -m pip install TTS simpleaudio gtts
#fixing attempt to uninstall blinker...
RUN python3 -m pip install --default-timeout=1000 --ignore-installed TTS simpleaudio gtts


WORKDIR /pai

# Expose port 4000 for the application
EXPOSE 4000

# Correctly use the --prefix option by separating it and its argument
CMD ["npm", "start", "--prefix", "/pai/web"]