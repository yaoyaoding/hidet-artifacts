from typing import List, Dict, Optional

from hidet.ir.dialects.lowlevel import VoidType
from hidet.ir.expr import Var
from hidet.ir.func import Function
from hidet.ir.stmt import Stmt

from .stmt_builder import StmtBuilder


class FunctionBuilder(StmtBuilder):
    def __init__(self, name: str, kind: str, label: str = "", ret_type=VoidType(), grid_dim=None, block_dim=None, dynamic_smem_bytes=None, min_blocks=None, attrs=None):
        super().__init__()
        self.name = name
        self.kind = kind
        self.params: List[Var] = []
        self.ret_type = ret_type
        self.local_vars = []
        self.func: Optional[Function] = None
        self.body: Optional[Stmt] = None
        self.extern_vars = []
        self.attrs: Dict[str] = attrs if attrs else {}
        self.label = label

        if grid_dim:
            self.attrs['cuda_grid_dim'] = grid_dim
        if block_dim:
            self.attrs['cuda_block_dim'] = block_dim
        if dynamic_smem_bytes:
            self.attrs['cuda_dynamic_smem_bytes'] = dynamic_smem_bytes
        if min_blocks:
            self.attrs['cuda_min_blocks'] = min_blocks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.finish_func()

    def extend_params(self, params: List[Var]):
        self.params.extend(params)

    def extend_extern_vars(self, extern_vars: List[Var]):
        self.extern_vars.extend(extern_vars)

    def extend_local_vars(self, local_vars: List[Var]):
        assert isinstance(local_vars, (tuple, list))
        self.local_vars.extend(local_vars)

    def extend_attrs(self, new_attrs: Dict[str, object]):
        self.attrs.update(new_attrs)

    def set_body(self, body: Stmt):
        self.body = body

    def finish_func(self):
        from hidet.ir.primitives.cuda.vars import block_idx, thread_idx
        assert self.func is None
        if 'label' not in self.attrs:
            self.attrs['label'] = self.label
        if self.kind in ['cuda_kernel', 'cuda_device']:
            self.extend_extern_vars([block_idx(dim) for dim in ['x', 'y', 'z']])
            self.extend_extern_vars([thread_idx(dim) for dim in ['x', 'y', 'z']])
        if self.body is None:
            self.body = self.finish()
        self.func = Function(self.name, kind=self.kind, params=self.params, body=self.body, ret_type=self.ret_type, local_vars=self.local_vars,
                             local_const_vars=[], extern_vars=self.extern_vars, attrs=self.attrs)

    def get(self) -> Function:
        assert self.func.body is not None
        return self.func
