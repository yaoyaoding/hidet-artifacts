#!/bin/bash

# the following environment variables allow TVM to use all the cores of the machine
# if your machine has a different number of threads other than 24, change the value of TVM_NUM_THREADS accordingly
export TVM_BIND_THREADS=0
export TVM_NUM_THREADS=24

python ./0_end2end/main.py
python ./1_latency_distribution/main.py
python ./2_input_sensitivity/main.py
python ./3_batch_size/main.py
python ./4_prologue_epilogue_fusion/main.py
python ./5_tensorrt/main.py
