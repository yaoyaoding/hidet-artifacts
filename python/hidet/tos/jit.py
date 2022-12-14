from typing import Optional, Callable, Dict, List, Union
import numpy as np
import os
import time
import functools
import inspect
import hidet
from hidet.tos import Tensor
from hidet.tos.ir.graph import FlowGraph
from hidet.tos.tensor import symbol_like
from hidet.ffi import cuda


def get_type_repr(value):
    import numpy as np
    from hidet.tos import Tensor

    if isinstance(value, (str, int, float)):
        return str(type(value).__name__)
    elif isinstance(value, list):
        items = [get_type_repr(v) for v in value]
        return '[{}]'.format(', '.join(items))
    elif isinstance(value, tuple):
        items = [get_type_repr(v) for v in value]
        return '({})'.format(', '.join(items))
    elif isinstance(value, dict):
        for v in value.keys():
            if not isinstance(v, str):
                raise TypeError('Only support str as dict key, got {}'.format(type(v)))
        keys = list(v for v in value.keys())
        items = [get_type_repr(v) for v in value.values()]
        return '{{{}}}'.format(', '.join('{}: {}'.format(k, v) for k, v in zip(keys, items)))
    elif isinstance(value, Tensor):
        shape_repr = ', '.join(str(v) for v in value.shape)
        return '{}[{}]'.format(value.dtype, shape_repr)
    elif isinstance(value, np.ndarray):
        shape_repr = ', '.join(str(v) for v in value.shape)
        return 'np.{}[{}]'.format(value.dtype, shape_repr)
    else:
        raise TypeError('Does not support type {} for jit.'.format(type(value)))


def get_bind_repr(bind: inspect.BoundArguments) -> str:
    items = []
    for name, value in bind.arguments:
        items += '{}: {}'.format(name, get_type_repr(value))
    return 'BindRepr({})'.format(', '.join(items))


class JitGraph:
    # todo: use inspect package to support more wide range input and outputs
    def __init__(
            self,
            func: Callable,
            opt: bool = False,
            parallel_k: str = 'default',
            save_ir_dir: Optional[str] = './outs',
            mma: str = 'wmma_tf32_f32',
    ):
        self.func: Callable = func
        self.cached_graph: Dict[str, FlowGraph] = {}

        self.parallel_k = parallel_k
        self.opt = opt
        self.save_ir_dir = os.path.join(save_ir_dir, func.__name__)
        self.mma = mma

    def __str__(self):
        items = []
        for args_repr, graph in self.cached_graph.items():
            items.extend([args_repr, ' => ', str(graph), '\n'])
        return ''.join(items)

    @staticmethod
    def args_representation(*args):
        for arg in args:
            if not isinstance(arg, Tensor):
                raise NotImplementedError('Currently only support Tensor argument, got {}.'.format(type(arg)))

        args_repr = get_type_repr(args)
        return args_repr

    def flow_graph_for(self, *args) -> FlowGraph:
        args_repr = self.args_representation(*args)

        if args_repr not in self.cached_graph:
            symbol_inputs = [symbol_like(arg) for arg in args]
            symbol_outputs = self.func(*symbol_inputs)
            graph = hidet.trace_from(symbol_outputs, inputs=symbol_inputs)
            if self.opt:
                with hidet.tos.PassContext() as ctx:
                    ctx.save_graph_instrument(self.save_ir_dir)
                    ctx.set_mma(self.mma)
                    if self.parallel_k == 'default':
                        ctx.set_parallel_k(default=True)
                    elif self.parallel_k == 'disabled':
                        ctx.set_parallel_k(disabled=True)
                    else:
                        ctx.set_parallel_k(nparts=int(self.parallel_k))
                    graph = hidet.tos.optimize(graph)
            self.cached_graph[args_repr] = graph
        graph: FlowGraph = self.cached_graph[args_repr]
        return graph

    def __call__(self, *args):
        graph = self.flow_graph_for(*args)
        return graph(*args)

    def benchmark(self, *args, warmup=10, number=10, repeat=10, median=True) -> Union[float, List[float]]:
        graph = self.flow_graph_for(*args)
        cuda_graph = graph.cuda_graph()
        cuda_graph.set_input_tensors(args)

        results = []
        for i in range(warmup):
            cuda_graph.run()
            cuda.device_synchronize()
        for i in range(repeat):
            cuda.device_synchronize()
            start_time = time.time()
            for j in range(number):
                cuda_graph.run()
            cuda.device_synchronize()
            end_time = time.time()
            results.append((end_time - start_time) * 1000 / number)

        if median:
            return float(np.median(results))
        else:
            return results


def jit(opt=False, save_ir_dir='./outs', parallel_k='default', mma='simt'):
    def decorator(func):
        jit_graph = JitGraph(
            func=func,
            opt=opt,
            parallel_k=parallel_k,
            save_ir_dir=save_ir_dir,
            mma=mma
        )
        return jit_graph

    return decorator
