from typing import List, Union

from .arithmatic import square
from .utils import Task, Operator, Tensor, TensorNode, IRModule, compute, reduce, input_like, normalize_dim


class ReduceTask(Task):
    def __init__(self, x: TensorNode, dims: List[int], keep_dim: bool, reduce_type: str, accumulate_dtype: str = 'float32'):
        x_shape = x.const_shape()
        y_shape = []
        for i in range(len(x_shape)):
            if i in dims:
                if keep_dim:
                    y_shape.append(1)
            else:
                y_shape.append(x_shape[i])

        def fcompute(*indices):
            def reduce_fcompute(*reduce_indices):
                x_indices = []
                p = 0
                q = 0
                for i in range(len(x_shape)):
                    if i not in dims:
                        x_indices.append(indices[p])
                        p += 1
                    else:
                        x_indices.append(reduce_indices[q])
                        q += 1
                        if keep_dim:
                            p += 1
                assert p == len(indices) and q == len(reduce_indices)
                return x[x_indices]

            reduce_shape = [x_shape[i] for i in dims]
            return reduce(shape=reduce_shape, fcompute=reduce_fcompute,
                          reduce_type=reduce_type, accumulate_dtype=accumulate_dtype)

        y = compute(name='y', shape=y_shape, fcompute=fcompute, scope='global')

        self.dims: List[int] = dims
        self.keep_dim: bool = keep_dim
        self.reduce_type: str = reduce_type

        super().__init__(
            name='reduce_{}'.format(reduce_type),
            inputs=[x],
            outputs=[y],
            attributes={
                'dims': dims,
                'keep_dim': keep_dim,
                'reduce_type': reduce_type,
                'accumulate_dtype': accumulate_dtype
            }
        )

    def implement_cuda(self) -> IRModule:
        from ..schedules import cuda_schedule_reduce_by_default, cuda_schedule_reduce_by_warp_reduce
        rank = len(self.inputs[0].const_shape())
        if rank - 1 in self.dims:
            # reduce over last dimension
            return cuda_schedule_reduce_by_warp_reduce(self)
        else:
            # last dimension has not been reduced
            return cuda_schedule_reduce_by_default(self)

    def fast_implement(self, space_level: int) -> bool:
        return True


class ReduceMeanOp(Operator):
    def __init__(self, x: Tensor, dims: List[int], keep_dim: bool = False):
        dims = normalize_dim(dims, rank=len(x.shape))
        super().__init__(
            inputs=[x],
            task=ReduceTask(input_like(x, 'x'), dims, keep_dim, 'avg'),
            attributes={
                'dims': dims,
                'keep_dim': keep_dim
            }
        )


class ReduceSumOp(Operator):
    def __init__(self, x: Tensor, dims: List[int], keep_dim: bool = False):
        dims = normalize_dim(dims, rank=len(x.shape))
        super().__init__(
            inputs=[x],
            task=ReduceTask(input_like(x, 'x'), dims, keep_dim, 'sum'),
            attributes={
                'dims': dims,
                'keep_dim': keep_dim
            }
        )


def reduce_mean(x: Tensor, dims: Union[int, List[int]], keep_dim: bool = False) -> Tensor:
    if isinstance(dims, int):
        dims = [dims]
    return ReduceMeanOp(x, dims, keep_dim).get_output(0)


def reduce_sum(x: Tensor, dims: Union[int, List[int]], keep_dim: bool = False) -> Tensor:
    if isinstance(dims, int):
        dims = [dims]
    return ReduceSumOp(x, dims, keep_dim).get_output(0)


def reduce_var(x: Tensor, dims: Union[int, List[int]], keep_dim: bool = False) -> Tensor:
    x = x - x.mean(dims=dims, keep_dim=True)
    return square(x).mean(dims=dims, keep_dim=keep_dim)
