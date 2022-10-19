from typing import List, Optional, Tuple, Union
from functools import lru_cache
import json
from tabulate import tabulate
import os
import time
import numpy as np
import argparse
import hidet as hi
import hidet
from hidet import Tensor
from hidet.utils import cuda, nvtx_annotate, hidet_cache_file, error_tolerance
from hidet.utils.git_utils import get_repo_sha, get_repo_commit_date


import os
os.environ["PATH"] = os.environ["PATH"]+":/usr/local/cuda/bin/"


class BenchResult:
    def __init__(self, latencies: List[float] = None, outputs: List[Tensor] = None, configs: str = None):
        self.latencies = latencies
        self.outputs: Optional[List[Tensor]] = outputs
        self.configs = configs


short2long = {
    'f16': 'float16',
    'f32': 'float32',
    'bf16': 'bfloat16'
}


def environment_info(args) -> str:
    return str(tabulate(
        headers=[
            'Name', 'Value'
        ],
        tabular_data=[
            ['Commit', get_repo_sha()],
            ['GPU', cuda.query_device_name()],
            ['Arch', cuda.query_arch()],
            ['Compute Capacity', cuda.query_compute_capability()],
            ['Current SM Clock (MHz)', cuda.query_gpu_current_clock()],
            ['Current Memory Clock (MHz)', cuda.query_memory_current_clock()],
            ['Warmup/Number/Repeat', '{} / {} / {}'.format(args.warmup, args.number, args.repeat)]
        ]
    ))


@lru_cache()
def get_onnx_model(name: str, batch_size: int) -> Tuple[str, List[str], List[hidet.Tensor]]:
    from hidet.testing import onnx_models
    return onnx_models.get_onnx_model(name, batch_size)


def run_with_onnx(model_path: str, input_names: List[str], input_tensors: List[hidet.Tensor]) -> List[np.ndarray]:
    import onnxruntime
    onnx_session = onnxruntime.InferenceSession(model_path, providers=['CPUExecutionProvider'])  # use cpu executor for high accuracy
    onnx_outputs = onnx_session.run(None, input_feed={name: tensor.numpy() for name, tensor in zip(input_names, input_tensors)})
    return onnx_outputs


def benchmark_run(run_func, warmup, number, repeat) -> List[float]:
    results = []
    with nvtx_annotate('warmup'):
        for i in range(warmup):
            run_func()
            cuda.device_synchronize()
    for i in range(repeat):
        with nvtx_annotate(f'repeat {i}'):
            cuda.device_synchronize()
            start_time = time.time()
            for j in range(number):
                run_func()
            cuda.device_synchronize()
            end_time = time.time()
        results.append((end_time - start_time) * 1000 / number)
    return results


def bench_torch(args, out_dir) -> BenchResult:
    from hidet.testing.torch_models.all import get_torch_model
    result = BenchResult()
    model, input_dict = get_torch_model(args.model, batch_size=args.bs)

    def run_func():
        model(**input_dict)

    result.latencies = benchmark_run(run_func, warmup=args.warmup, number=args.number, repeat=args.repeat)
    result.configs = 'fp32'
    result.outputs = None
    return result


def bench_hidet(args, out_dir) -> BenchResult:
    result = BenchResult()
    # print('args', args, 'time stamp', time.time())

    # configs
    result.configs = 'sp{}_{}_{}_{}_pk_{}'.format(args.hidet_space, args.mma, args.precision, args.reduce_precision, args.parallel_k)

    # latencies and outputs
    graph_path = hidet_cache_file(
        'hidet_graph',
        args.model,
        'bs_{}_{}'.format(args.bs, result.configs),
        'graph.pickle'
    )
    onnx_path, input_names, input_tensors = get_onnx_model(name=args.model, batch_size=args.bs)

    hidet.space_level(args.hidet_space)

    if os.path.exists(graph_path) and not args.disable_graph_cache:
        graph = hidet.load_graph(graph_path)
    else:
        if args.disable_graph_cache:
            print('disabled graph cache, rebuilding...')
        t1 = time.time()
        model = hidet.tos.frontend.onnx_utils.from_onnx(onnx_path)
        symbol_inputs = [hi.symbol_like(data) for data in input_tensors]
        outputs = model(*symbol_inputs)
        graph: hi.FlowGraph = hi.trace_from(outputs, inputs=symbol_inputs)
        with hidet.tos.PassContext() as ctx:
            ctx.save_graph_instrument(out_dir=os.path.join(out_dir, 'ir'))
            ctx.set_precision(short2long[args.precision])
            ctx.set_reduce_precision(short2long[args.reduce_precision])
            ctx.set_mma(args.mma)
            if args.parallel_k == 'disabled':
                ctx.set_parallel_k(disabled=True)
            elif args.parallel_k == 'default':
                ctx.set_parallel_k(default=True)
            elif args.parallel_k == 'search':
                ctx.set_parallel_k(search=True)
            else:
                ctx.set_parallel_k(nparts=int(args.parallel_k))

            graph = hi.tos.transforms.optimize(graph)

        hidet.save_graph(graph, graph_path + '.tmp')
        os.rename(graph_path + '.tmp', graph_path)

        graph(*input_tensors)
        t2 = time.time()
        with open(os.path.join(os.path.dirname(graph_path), 'tuning_time.txt'), 'w') as f:
            f.write(str((t2 - t1) / 60.0) + ' minutes')

    cuda_graph = graph.cuda_graph()
    result.outputs = cuda_graph.run_with_inputs(input_tensors)
    result.latencies = benchmark_run(lambda: cuda_graph.run(), args.warmup, args.number, args.repeat)

    return result


def bench_trt(args, out_dir) -> BenchResult:
    from hidet.utils.tensorrt_utils import create_engine_from_onnx, engine_benchmark, engine_inspect, engine_profiler, engine_inference
    result = BenchResult()

    # configs
    configs = []
    if args.trt_fp16:
        configs.append('fp16')
    if args.trt_tf32:
        configs.append('tf32')
    if len(configs) == 0:
        configs.append('fp32')
    result.configs = '_'.join(configs)

    # latencies
    onnx_path, input_names, input_tensors = get_onnx_model(name=args.model, batch_size=args.bs)
    engine = create_engine_from_onnx(
        onnx_model_path=onnx_path,
        workspace_bytes=512 << 20,  # 512 MiB
        input_shapes={name: tensor.shape for name, tensor in zip(input_names, input_tensors)},
        use_tf32=args.trt_tf32,
        use_fp16=args.trt_fp16
    )
    dummy_inputs_dict = {name: tensor for name, tensor in zip(input_names, input_tensors)}
    result.latencies = engine_benchmark(
        engine=engine,
        dummy_inputs=dummy_inputs_dict,
        warmup=args.warmup, number=args.number, repeat=args.repeat
    )

    # outputs
    result.outputs = list(engine_inference(engine, inputs=dummy_inputs_dict).values())

    # extra information
    with open(os.path.join(out_dir, 'engine_inspect.json'), 'w') as f:
        json.dump(engine_inspect(engine), f, indent=2)
    with open(os.path.join(out_dir, 'engine_trace.json'), 'w') as f:
        json.dump(engine_profiler(engine, dummy_inputs_dict), f, indent=2)

    return result


def bench_ort(args, out_dir) -> BenchResult:
    from hidet.utils.ort_utils import create_ort_session, ort_benchmark, ort_inference
    result = BenchResult()

    # configs
    result.configs = 'provider_{}'.format(args.ort_provider)
    provider = {
        'cuda': 'CUDAExecutionProvider',
        'trt': 'TensorrtExecutionProvider'
    }[args.ort_provider]

    # latencies
    onnx_path, input_names, input_tensors = get_onnx_model(name=args.model, batch_size=args.bs)
    session = create_ort_session(onnx_path, provider=provider)
    inputs = {name: tensor for name, tensor in zip(input_names, input_tensors)}
    result.latencies = ort_benchmark(
        session,
        dummy_inputs=inputs,
        warmup=args.warmup, number=args.number, repeat=args.repeat
    )

    # outputs
    result.outputs = list(ort_inference(session, inputs=inputs).values())

    return result


def bench_tvm(args, out_dir) -> BenchResult:
    from hidet.utils.tvm_utils import tvm_graph_module_from_onnx, tvm_benchmark, tvm_inference
    result = BenchResult()

    # configs
    if args.exec == 'autotvm':
        trial = args.autotvm_trial
    elif args.exec == 'ansor':
        trial = args.ansor_trial
    else:
        trial = 1
    result.configs = 'trial_{}'.format(trial)

    # latencies
    onnx_path, input_names, input_tensors = get_onnx_model(name=args.model, batch_size=args.bs)
    gmod = tvm_graph_module_from_onnx(
        onnx_model_path=onnx_path,
        input_shapes={
            name: tensor.shape for name, tensor in zip(input_names, input_tensors)
        },
        tune_autotvm=(args.exec == 'autotvm'),
        tune_ansor=(args.exec == 'ansor'),
        tune_trial_per_task=trial
    )
    inputs = {name: tensor for name, tensor in zip(input_names, input_tensors)}
    result.latencies = tvm_benchmark(
        gmod,
        dummy_inputs=inputs,
        warmup=args.warmup, number=args.number, repeat=args.repeat
    )

    # outputs
    result.outputs = tvm_inference(gmod, inputs)

    return result


def bench(command_line_args: Optional[str] = None):
    if command_line_args:
        args = parser.parse_args(command_line_args.strip().split())
    else:
        args = parser.parse_args()
    # output dir
    out_dir = os.path.join(args.out_dir,
                           '{}_{}'.format(get_repo_commit_date(), get_repo_sha(short=True)),
                           cuda.query_device_name(short=True),
                           'models')
    exec_name = 'bs{}_{}_{}_{}_{}'.format(args.bs, args.model, args.exec, args.precision, args.reduce_precision)
    if args.exec == 'hidet':
        exec_name += '_space{}_pk_{}'.format(args.hidet_space, args.parallel_k)
    elif args.exec in ['autotvm', 'ansor']:
        trial = args.autotvm_trial if args.exec == 'autotvm' else args.ansor_trial
        exec_name += '_trial{}'.format(trial)
    out_dir = os.path.join(out_dir, exec_name)
    os.makedirs(out_dir, exist_ok=True)

    # bench
    bench_dict = {
        'hidet': bench_hidet,
        'trt': bench_trt,
        'ort': bench_ort,
        'autotvm': bench_tvm,
        'ansor': bench_tvm,
        'tvm': bench_tvm,
        'torch': bench_torch,
    }
    bench_func = bench_dict[args.exec]
    with nvtx_annotate(message=args.exec):
        with hidet.utils.py.Timer() as timer:
            result: BenchResult = bench_func(args, out_dir)

    # error tolerance
    onnx_path, input_names, input_tensors = get_onnx_model(name=args.model, batch_size=args.bs)
    onnx_outputs = run_with_onnx(model_path=onnx_path, input_names=input_names, input_tensors=input_tensors)
    et = -1.0
    if result.outputs is not None:
        for baseline_output, onnx_output in zip(result.outputs, onnx_outputs):
            et = max(et, error_tolerance(baseline_output.numpy(), onnx_output))

    # write results
    with open(os.path.join(out_dir, 'env.txt'), 'w') as f:
        f.write(environment_info(args))
    with open(os.path.join(out_dir, 'raw.json'), 'w') as f:
        raw = {
            'latency': result.latencies,
            'bench_time': timer.elapsed_seconds()
        }
        json.dump(raw, f, indent=2)
    with open(os.path.join(out_dir, 'args.json'), 'w') as f:
        json.dump(args.__dict__, f, indent=2)
    with open(os.path.join(out_dir, 'summary.txt'), 'w') as f:
        # model mode space median std
        head = '{:>10} {:>20} {:>12} {:>40} {:>10} {:>10} {:>10} {:>10}\n'.format(
            'BatchSize', 'Model', 'Executor', 'Config', 'Space', 'Latency', 'Std', 'Error'
        )
        summary = '{:>10} {:>20} {:>12} {:>40} {:10} {:10.3f} {:10.3f} {:10.3f}\n'.format(
            args.bs,
            args.model,
            args.exec,
            result.configs,
            args.hidet_space,
            float(np.median(result.latencies)),
            float(np.std(result.latencies)),
            et
        )
        print(head + summary)
        f.write(head + summary)


parser = argparse.ArgumentParser(description='Hidet model benchmark script.')

# ======

# general parameters
parser.add_argument('--model', type=str,
                    # choices=['resnet50', 'inception_v3', 'mobilenet_v2', 'bert', 'bart'],
                    required=True,
                    help='The model to benchmark.')
parser.add_argument('--exec', type=str, choices=['hidet', 'trt', 'ort', 'tvm', 'autotvm', 'ansor', 'tf', 'tf_xla', 'torch'], required=True,
                    help='Executor.')
parser.add_argument('--out_dir', type=str, default='./results/',
                    help='Output directory.')
parser.add_argument('--warmup', type=int, default=10, help='Number of warmups.')
parser.add_argument('--number', type=int, default=10, help='Number of runs per repeat.')
parser.add_argument('--repeat', type=int, default=10, help='Number of repeats.')

# ======

# executor parameters
# hidet executor parameters
parser.add_argument('--precision', choices=['f16', 'bf16', 'f32'], default='f32')
parser.add_argument('--reduce_precision', choices=['f16', 'f32'], default='f32')
parser.add_argument('--mma', choices=['simt', 'wmma', 'mma'], default='simt')
parser.add_argument('--hidet_space', type=int, choices=[0, 1, 2], default=2, help='The space level of each operator in the model. Large space level means longer compilation time and better performance.')
parser.add_argument('--parallel_k', choices=['disabled', 'default', 'search', '2', '4', '6', '8'], default='default')
parser.add_argument('--disable-graph-cache', action='store_true')

# tvm number of trial per task
parser.add_argument('--ansor_trial', type=int, default=800, help='Number of trial per task in autotvm and ansor, default 800.')
parser.add_argument('--autotvm_trial', type=int, default=1000, help='Number of trial per task in autotvm and ansor, default 800.')

# tensorrt configs
parser.add_argument('--trt_tf32', action='store_true')
parser.add_argument('--trt_fp16', action='store_true')

# onnx runtime configs
parser.add_argument('--ort_provider', choices=['cuda', 'trt'], default='cuda')

# ======

# model agnostic parameters
parser.add_argument('--bs', type=int, default=1, help='Batch size.')

# model specific parameters
# bert
parser.add_argument('--bert_seq_length', type=int, default=128, help='Sequence length of bert input.')
parser.add_argument('--bert_hidden_size', type=int, default=768, help='Hidden size of bert.')
parser.add_argument('--bert_vocab_size', type=int, default=30522, help='Vocabulary size of bert.')


