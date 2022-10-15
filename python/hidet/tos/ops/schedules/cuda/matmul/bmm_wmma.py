import os
from typing import List, Tuple, Union, Optional

from hidet.ir.func import IRModule
from hidet.tos.ops.definitions.matmul.matmul import MatmulTask


def batched_matmul_cuda_schedule_wmma(task: MatmulTask) -> IRModule:
    raise NotImplementedError()


