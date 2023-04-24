
# ASPLOS 2023 Artifact Evaluation 
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.7429879.svg)](https://doi.org/10.5281/zenodo.7429879)

This repository contains the artifacts for the paper 

"Hidet: Task Mapping Programming Paradigm for Deep Learning Tensor Programs".

**Note**: This repository hosts the old version of Hidet when submitting the paper and is only used to reproducing the experiments. Please checkout the [hidet-org/hidet](https://github.com/hidet-org/hidet) repository for the latest version of Hidet. 

## Hardware requirements

We did experiment on the following hardware platform

- CPU: Intel Core i9-12900K
- GPU: NVIDIA GeForce RTX 3090 (one with 420 Watt TDP)
- Memory: 64 GiB

Other workstation equipped with a modern NVIDIA GPU should also be able to run the experiments.

The experiments require a Linux system with NVIDIA GPU driver installed.

## Run experiments via docker

We provide a docker image to run the experiments, with pre-configured environment.

### Install docker and nvidia-docker

Please follow the instructions on the [official website](https://github.com/NVIDIA/nvidia-docker) to install docker and 
nvidia-docker.

### Prepare the image

We provide two ways to get the docker image to use. Please choose the one you like.

#### Option 1: use the prebuilt image 

```bash
docker pull yyding/hidet-artifact:latest 
```

#### Option 2: build docker image from Dockerfile

```bash
git clone --recursive git@github.com:yaoyaoding/hidet-artifacts hidet
cd hidet
docker build -t yyding/hidet-artifact:latest .
```

### Run experiments inside docker container

After above step, you can see a docker image named `yyding/hidet-artifact:latest` in your local docker image list via:

```bash
docker image ls
```

You should be able to see something like this:

```text
REPOSITORY              TAG       IMAGE ID       CREATED          SIZE
yyding/hidet-artifact   latest    1074c09962c0   33 minutes ago   13.7GB
```

To run experiments, you need to start a docker container from the image:

```bash
# the following command will start a container based on the image
# you will enter the container after the command at working directory /root/hidet/artifacts
docker run -it --gpus all --rm yyding/hidet-artifact:latest
# when you are in the container, run
bash run.sh
# to run all experiments
```

You can also run experiments in the container one by one. See [here](#run-the-experiments) for details.

## Build and run experiments from source

You can also build and run experiments from source on your host environment.

### Installation

We require the following software to be installed

- cmake 3.19+
- llvm (required by TVM, we used llvm-10)
- ccache (used to accelerate duplicated compilation)

#### NVIDIA CUDA Toolkit

Please follow https://developer.nvidia.com/cuda-downloads guide to install the CUDA toolkit. 

We used NVIDIA Driver 510.73.08 and CUDA 11.6 for our experiments. The newer versions of CUDA should also work.

Please run the following commands to check whether the NVIDIA Driver and CUDA toolkit are installed correctly.

```bash
nvidia-smi
nvcc --version
```

#### Install Hidet and baselines

```bash
# clone hidet repository 
git clone --recursive git@github.com:yaoyaoding/hidet-artifacts hidet
cd hidet

# install the dependencies of hidet and the baselines (e.g., TensorRT, PyTorch, Onnx Runtime)
# the versions of baselines are specified in requirements.txt file.
pip3 install -r requirements.txt

# build hidet and tvm
mkdir build
cd build
cmake ..
make -j8
cd ..

# there should be four dynamic libraries in the build/lib directory:
# libtvm.so, libtvm_runtime.so, libhidet.so, libhidet_runtime.so
ls build/lib

# set the environment variables, it is recommended to set them in your .bashrc file
export HIDET_HOME=`pwd`
export PYTHONPATH=$PYTHONPATH:$HIDET_HOME/python:$HIDET_HOME/artifacts
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$HIDET_HOME/build/lib

# test whether hidet has been installed successfully
python3 -c "import hidet"
python3 -c "import artifact"
```

### Run the experiments

This artifact contains all the experiments in the evaluation section of the paper:

- Experiment 0 (section 6.1): End to end performance comparison (~50 hours)
- Experiment 1 (section 6.2.1): Schedule space comparison (~1 hour)
- Experiment 2 (section 6.2.2): Performance sensitivity over input sizes (~4 hours)
- Experiment 3 (section 6.2.3): Evaluation on different batch sizes (~40 hours)
- Experiment 4 (section 6.2.4): Post-scheduling fusion evaluation (~10 hours)
- Experiment 5 (section 6.2.5): Comparison with TensorRT (~1.5 hour)

The 6 experiments are organized in the `artifacts` directory. Each experiment corresponds to a directory with a `main.py` script. 
Directly run the `main.py` script to launch corresponding experiments. We will automatically cache the optimized operator and models in `.hidet_cache` directory, thus you can stop and restart the experiments at any time. The second run of the experiments will be much faster.

It will take tens of hours to finish all experiments. Most of the time is spent by autotvm and ansor schedulers. If you want to first skip the experiments related to autotvm and ansor, you can comment the line `--exec ansor` and `--exec autotvm` in each `main.py` script.

```bash
cd artifacts

# the following environment variables allow TVM to use all the cores of the machine
# if your machine has a different number of threads other than 24, change the value of TVM_NUM_THREADS accordingly
export TVM_BIND_THREADS=0
export TVM_NUM_THREADS=24

python3 0_end_to_end/main.py
python3 1_latency_distribution/main.py
python3 2_input_sensitivity/main.py
python3 3_batch_size/main.py
python3 4_prolouge_epilogue_fusion/main.py
python3 5_tensorrt/main.py
```
(we store above instructions in `run.sh`, you can run `bash run.sh` to run all experiments).

Each script would have outputs like
```text
 BatchSize                Model     Executor                                   Config      Space    Latency        Std      Error
         1             resnet50        hidet              sp2_simt_f32_f32_pk_default          2      1.184      0.000      0.000

 BatchSize                Model     Executor                                   Config      Space    Latency        Std      Error
         1         inception_v3        hidet              sp2_simt_f32_f32_pk_default          2      1.722      0.005      0.000

 BatchSize                Model     Executor                                   Config      Space    Latency        Std      Error
         1         mobilenet_v2        hidet              sp2_simt_f32_f32_pk_default          2      0.337      0.001      0.000

 BatchSize                Model     Executor                                   Config      Space    Latency        Std      Error
         1                 bert        hidet              sp2_simt_f32_f32_pk_default          2      2.378      0.029      0.000

 BatchSize                Model     Executor                                   Config      Space    Latency        Std      Error
         1                 gpt2        hidet              sp2_simt_f32_f32_pk_default          2      2.608      0.054      0.000
```

You may also see output log like
```text
Compiling task avg_pool2d_rearrange_rearrange_reshape_rearrange...
Compiling task matmul_reshape...
100%|█████████████████████████████████████████████████████████| 177/177 [00:45<00:00,  3.86it/s]
```
This indicates that hidet is compiling the kernel for each operator. The progress bar indicates hidet is tuning a kernel. The compilation and tuning results will be cached in `hidet/.hidet_cache` directory. The subsequent runs will reuse the cached results. Feel free to ignore these logs.

The 8 columns in the output correspond to 
- batch size, 
- model name, 
- executor, 
  - PyTorch: torch
  - Onnx Runtime: ort
  - AutoTVM: autotvm
  - Ansor: ansor
  - TensorRT: tensorrt
  - Hidet: hidet
- config for executor, 
- search space of hidet (please ignore this column for other executor), 
- end to end latency in milliseconds, 
- standard deviation of latency, 
- and the output error (see `hidet.utils.py.error_tolerance` for the definition) compared with onnx runtime with cpu backend. We compared the output to make sure the inference results are correct for each executor.
