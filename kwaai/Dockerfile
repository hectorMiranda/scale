FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt upgrade -y && apt-get update
RUN apt install -y net-tools software-properties-common curl git npm \
    libsndfile1 libasound2-dev ffmpeg pkg-config

# Add the deadsnakes PPA for Python 3.10
RUN add-apt-repository ppa:deadsnakes/ppa -y


# Install Python 3.10 and set it as the default Python version
RUN apt update && apt install -y --fix-missing python3-distutils python3.10 python3.10-distutils python-is-python3
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN update-alternatives --config python3

# Install pip for Python 3.10
#RUN curl https://bootstrap.pypa.io/get-pip.py | python3
RUN curl https://bootstrap.pypa.io/get-pip.py | python3 && python3 -m pip install --upgrade pip


# Clone the PAIAssistant repository
RUN git clone https://github.com/Kwaai-AI-Lab/PAIAssistant.git

# Install npm dependencies for the web component
RUN cd PAIAssistant/web && npm install

# Install underlying libraries for sentencepiece
RUN apt-get install -y libprotobuf-dev protobuf-compiler pkg-config

#RUN pip install sentencepiece

#RUN apt-get install -y libprotobuf-dev protobuf-compiler pkg-config
# Install prerequisites for building Sentencepiece
RUN apt-get install -y git build-essential cmake libprotobuf-dev protobuf-compiler pkg-config

# Clone Sentencepiece repository
RUN git clone https://github.com/google/sentencepiece.git

# Build and install Sentencepiece
RUN cd sentencepiece && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make -j $(nproc) && \
    make install

# Update shared library cache
RUN ldconfig -v

# Increase the pip resolution limit
ENV PIP_RESOLVER_MAX_ROUND_TRIPS=500000

# Install Python dependencies for the API component
RUN cd /PAIAssistant/api && pip install -r requirements.txt

# Install espeak-ng for text-to-speech
RUN git clone https://github.com/espeak-ng/espeak-ng.git && \
    cd espeak-ng && \
    ./autogen.sh && \
    ./configure --without-pulseaudio && \
    make && \
    make install

# Install llama-cpp-python with CMake arguments
RUN CMAKE_ARGS="-DLLAMA_CUBLAS=on" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir

# Set the working directory to PAIAssistant
WORKDIR /PAIAssistant

# Expose the ports used by the web and API services
EXPOSE 4000 7860

# Command to start the services 
CMD cd web && npm start & cd ../api && python api.py
