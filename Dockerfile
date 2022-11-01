FROM nvidia/cuda:11.6.0-devel-ubuntu20.04 as base

COPY . /root/hidet

ENV TZ=America/Toronto
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    git \
    vim \
    python3 \
    llvm-10 \
    ccache \
    software-properties-common \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir -r /root/hidet/requirements.txt && \
    python3 -m pip install --no-cache-dir --upgrade cmake && \
    hash -r  # refresh the hash

RUN ln -s /usr/bin/python3 /usr/bin/python

RUN cd /root/hidet && \
    mkdir build && \
    cd build && \
    cmake .. && \
    make -j 8 && \
    rm -rf /root/hidet/build/3rdparty

RUN echo export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/root/hidet/build/lib >> ~/.bashrc && \
    echo export PYTHONPATH=$PYTHONPATH:/root/hidet/python:/root/hidet/3rdparty/tvm/python >> ~/.bashrc && \
    echo alias python=python3 >> ~/.bashrc

WORKDIR /root/hidet/artifacts
