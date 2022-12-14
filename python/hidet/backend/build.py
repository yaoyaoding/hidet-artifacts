from __future__ import annotations
from typing import List, Optional, Dict
import contextlib
import psutil
import multiprocessing
from tqdm import tqdm
import ctypes
import os
import subprocess
import tempfile
from subprocess import PIPE

from hidet.libinfo import get_include_dir
from hidet.ir.func import IRModule
from hidet.ir.type import FuncType
from hidet.ir.task import Task
from hidet.transforms import PassContext, lower
from hidet.runtime import CompiledFunction
from hidet.ffi import PackedFunc
from hidet.ffi.ffi import library_paths
from hidet.utils import cuda, Timer
from hidet.backend import codegen


dlclose = ctypes.CDLL(None).dlclose
dlclose.argtypes = [ctypes.c_void_p]
dlclose.rettype = ctypes.c_int


class LoadedSharedLibrary:
    loaded_cdll_libraries: Dict[str, ctypes.CDLL] = {}
    reference_count: Dict[str, int] = {}

    def __init__(self, lib_path: str):
        self.lib_path: str = lib_path
        if lib_path in self.loaded_cdll_libraries:
            self.cdll: ctypes.CDLL = self.loaded_cdll_libraries[lib_path]
            self.reference_count[lib_path] += 1
        else:
            cdll = ctypes.CDLL(lib_path)
            self.cdll: ctypes.CDLL = cdll
            self.loaded_cdll_libraries[lib_path] = cdll
            self.reference_count[lib_path] = 1

    def __getitem__(self, item):
        ret = self.cdll[item]
        ret._lib = self
        return ret

    def __getattr__(self, item):
        return self[item]

    def __del__(self):
        self.reference_count[self.lib_path] -= 1
        if self.reference_count[self.lib_path] == 0:
            del self.loaded_cdll_libraries[self.lib_path]
            del self.reference_count[self.lib_path]
            dlclose(self.cdll._handle)


def compile_source(src_path: str, out_lib_path: str, keep_ptx=False) -> None:
    """
    Compile the source code in 'src_path' file and output the library to 'out_lib_path'.

    Parameters
    ----------
    src_path: str
        The path to source code.
    out_lib_path: str
        The path to output library.
    keep_ptx: bool, default False
        Whether to keep the ptx code in the same directory of output library.
    """
    src_path = os.path.abspath(src_path)
    out_lib_path = os.path.abspath(out_lib_path)
    cc = cuda.query_compute_capability()

    # dir contains the runtime header file 'hidet/runtime.h'
    include_dirs = [get_include_dir()]
    # dir contains the runtime library 'libhidet_runtime.so'
    library_dirs = [os.path.dirname(library_paths['hidet_runtime'])]

    cc_code = '{}{}'.format(cc[0], cc[1])
    command = [
        'nvcc',
        *['-I{}'.format(include_dir) for include_dir in include_dirs],
        *['-L{}'.format(library_dir) for library_dir in library_dirs],
        '-keep' if keep_ptx else '',
        '-gencode', f'arch=compute_{cc_code},code=sm_{cc_code}',
        '--ptxas-options=-v',
        '--compiler-options', "'-fPIC'",
        '-lineinfo',
        '-lhidet_runtime',
        '--shared', src_path,
        '-o', out_lib_path,
    ]

    try:
        with tempfile.TemporaryDirectory() as working_dir:
            result = subprocess.run(" ".join(command).split(), stderr=PIPE, stdout=PIPE, cwd=working_dir)
            if result.returncode:
                message = ''
                if result.stdout:
                    message += result.stdout.decode() + '\n'
                if result.stderr:
                    message += result.stderr.decode()
                if keep_ptx and os.path.exists(os.path.join(working_dir, os.path.basename(src_path).replace('.cu', '.ptx'))):
                    out_lib_dir = os.path.dirname(out_lib_path)
                    ptx_name = os.path.basename(src_path).replace('.cu', '.ptx')
                    ptx_path = os.path.join(working_dir, ptx_name)
                    target_ptx_path = os.path.join(out_lib_dir, ptx_name)
                    os.rename(ptx_path, target_ptx_path)
                raise Exception('Failed to compile file "{}":\n\n{}'.format(src_path, message))
            out_lib_dir = os.path.dirname(out_lib_path)
            if keep_ptx:
                ptx_name = os.path.basename(src_path).replace('.cu', '.ptx')
                ptx_path = os.path.join(working_dir, ptx_name)
                target_ptx_path = os.path.join(out_lib_dir, ptx_name)
                os.rename(ptx_path, target_ptx_path)
            with open(os.path.join(out_lib_dir, 'nvcc_log.txt'), 'w') as f:
                f.write('Command: {}\n'.format(" ".join(result.args)))
                f.write(result.stdout.decode('utf-8'))
                f.write(result.stderr.decode('utf-8'))
    except subprocess.CalledProcessError as e:
        print(' '.join(command))
        print(e.stderr.decode('utf-8'))
        raise e


def load_task_func(lib_path: str, task) -> CompiledFunction:
    """
    Load task's entry function from dynamic linked library.

    Parameters
    ----------
    lib_path: str
        The dynamic library path.
    task: hidet.tos.task.Task
        The task that corresponds to the dynamic library.

    Returns
    -------
    ret: CompiledFunction
        The loaded function that can be directly called in python.
    """
    try:
        # lib = ctypes.CDLL(lib_path)
        lib = LoadedSharedLibrary(lib_path)
    except OSError as e:
        print("Removed the file '{}'".format(lib_path))
        os.remove(lib_path)
        raise e
    func_name = 'hidet_{}'.format(task.name)
    param_types = [param.data_type for param in task.parameters]
    packed_func = PackedFunc(param_types=param_types, c_func_pointer=lib[func_name])
    return CompiledFunction(name=task.name, packed_func=packed_func)


def load_lib_func(lib_path: str, func_name: str, func_type: FuncType) -> CompiledFunction:
    try:
        # lib = ctypes.CDLL(lib_path)
        lib = LoadedSharedLibrary(lib_path)
    except OSError as e:
        print("Removed the file '{}'".format(lib_path))
        os.remove(lib_path)
        raise e
    func_name = 'hidet_{}'.format(func_name)
    param_types = [param_type for param_type in func_type.param_types]
    packed_func = PackedFunc(param_types=param_types, c_func_pointer=lib[func_name])
    return CompiledFunction(name=func_name, packed_func=packed_func)


class BuildInstance:
    def __init__(self, ir_module, output_dir, keep_ir=False, nvcc_keep=True, verbose=True):
        """
        The build instance.

        Parameters
        ----------
        ir_module: IRModule
            The ir module to build.
        output_dir: str
            The output directory for this build.
        keep_ir: bool
            Whether to keep the ir when lowering. If True, the ir will be stored in '{output_dir}/ir'. Default False.
        nvcc_keep: bool
            Whether to keep the ptx code in the same directory of output library., Default: True
        verbose: bool
            Whether to
        verbose: bool
            Reserved.
        """
        self.ir_module = ir_module
        self.output_dir = output_dir
        self.keep_ir = keep_ir
        self.nvcc_keep = nvcc_keep
        self.verbose = verbose


def build_ir_module_job(build_instance: BuildInstance) -> Optional[str]:
    """
    Build an ir module in build instance.

    Parameters
    ----------
    build_instance: BuildInstance
        The build instance to build.

    Returns
    -------
    lib_path: str
        The path to the built dynamic linked library.
    """
    from hidet.transforms.instruments import SaveIRInstrument
    instruments = []
    os.makedirs(build_instance.output_dir, exist_ok=True)
    if build_instance.keep_ir:
        instruments.append(SaveIRInstrument(out_dir=os.path.join(build_instance.output_dir, 'ir')))
    with PassContext(instruments=instruments):
        ir_module = lower(build_instance.ir_module)
    src_path = os.path.join(build_instance.output_dir, 'source.cu')
    lib_path = os.path.join(build_instance.output_dir, 'lib.so')
    codegen(ir_module, src_out_path=src_path)
    try:
        compile_source(src_path, lib_path)
    except subprocess.CalledProcessError:
        print('Compilation failed for an instance')
        return None
    return lib_path


def batch_build_ir_modules(build_instances, parallel=True, verbose=False) -> List[Optional[CompiledFunction]]:
    """
    Build a batch of ir modules.

    Parameters
    ----------
    build_instances: List[BuildInstance]
        The batch of build instances to build.

    parallel: bool
        Whether build in parallel. Default True.

    verbose: bool
        Whether show the progress and summary. Default False.

    Returns
    -------
    funcs: List[Optional[CompiledFunction]]
        The compiled functions, in the same order as build_instances.
        When the build for a build instance failed, None for that instance is returned.
    """
    with Timer() as timer:
        lib_paths = []
        if parallel:
            # Set the affinity of current process. Some package such as numpy will change affinity of current process,
            # which might limit the parallelism of compilation.
            os.sched_setaffinity(0, range(os.cpu_count()))
            mem_for_worker = 1.5 * 1024 * 1024 * 1024  # 1.5 GiB
            num_workers = min(max(int(psutil.virtual_memory().available // mem_for_worker), 1), psutil.cpu_count())
            with multiprocessing.Pool(processes=num_workers) as pool:
                for lib_path in tqdm(pool.imap(build_ir_module_job, build_instances), total=len(build_instances), disable=not verbose):
                    lib_paths.append(lib_path)
        else:
            lib_paths = map(build_ir_module_job, build_instances)
        assert len(lib_paths) == len(build_instances)
        funcs = [load_task_func(lib_path, instance.ir_module.task) if lib_path else None for lib_path, instance in zip(lib_paths, build_instances)]
    if verbose:
        print('Batch build {} modules within {:.3f} seconds, on average {:.1f} seconds per module.'.format(
            len(build_instances), timer.elapsed_seconds(), timer.elapsed_seconds() / len(build_instances)))
    return funcs
