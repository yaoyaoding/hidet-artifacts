from typing import List, Callable, Any, Union, Type, Optional, Dict

import operator
from hidet.ir import primitives
from hidet.ir import expr
from hidet.ir.expr import const_like
from hidet.utils import prod
from .utils import Task, Operator, Tensor, TensorNode, InverseMap, compute, input_like
from hidet.tos.tensor import convert


def broadcast_shape(x_shape: List[int], y_shape: List[int]) -> List[int]:
    """
    Broadcast two shapes with the same rule as numpy.
    Please refer to https://numpy.org/doc/stable/user/basics.broadcasting.html for details.
    """
    orig_shapes = x_shape, y_shape
    while len(x_shape) < len(y_shape):
        x_shape = [1] + x_shape
    while len(y_shape) < len(x_shape):
        y_shape = [1] + y_shape
    result_shape = []
    for p, q in zip(x_shape, y_shape):
        if p != q and p != 1 and q != 1:
            raise ValueError('can not broadcast two arrays with shape {} and {}'.format(orig_shapes[0], orig_shapes[1]))
        result_shape.append(max(p, q))
    return result_shape


class UnaryElementwiseTask(Task):
    def __init__(self, name: str, x: TensorNode, op: Callable[[Any], Any]):
        shape = x.const_shape()
        y = compute(
            name='y',
            shape=shape,
            fcompute=lambda *indices: op(x.__getitem__(indices)),
            scope='global'
        )
        super().__init__(
            name=name,
            inputs=[x],
            outputs=[y],
            inverse_map={
                x: InverseMap.from_lambda(lambda *indices: list(indices), num_args=len(x.data_type.shape))
            }
        )


def broadcast_indices(indices, shape, out_shape):
    # used to support broadcast
    pad_dim = len(out_shape) - len(shape)
    indices = list(indices[pad_dim:])
    for idx, dim in enumerate(shape):
        if int(dim) == 1:
            indices[idx] = 0
    return indices


class BinaryElementwiseTask(Task):
    def __init__(self, name: str, x: TensorNode, y: TensorNode, op: Callable[[Any, Any], Any]):
        x_shape = x.const_shape()
        y_shape = y.const_shape()
        z_shape = broadcast_shape(x_shape, y_shape)

        z = compute(
            name='z',
            shape=z_shape,
            fcompute=lambda *indices: op(x[broadcast_indices(indices, x_shape, z_shape)], y[broadcast_indices(indices, y_shape, z_shape)]),
            scope='global'
        )

        super().__init__(
            name=name,
            inputs=[x, y],
            outputs=[z],
            inverse_map={v: InverseMap.identity(len(v_shape)) for v, v_shape
                         in zip([x, y], [x_shape, y_shape]) if prod(v_shape) == prod(z_shape)}
        )


class WhereTask(Task):
    def __init__(self, cond: TensorNode, x: TensorNode, y: TensorNode):
        cond_shape = cond.const_shape()
        x_shape = x.const_shape()
        y_shape = y.const_shape()
        z_shape = broadcast_shape(cond_shape, broadcast_shape(x_shape, y_shape))

        z = compute(
            name='z',
            shape=z_shape,
            fcompute=lambda *indices: expr.if_then_else(
                cond=cond[broadcast_indices(indices, cond_shape, z_shape)],
                then_expr=x[broadcast_indices(indices, x_shape, z_shape)],
                else_expr=y[broadcast_indices(indices, y_shape, z_shape)]
            )
        )

        super().__init__(
            name='where',
            inputs=[cond, x, y],
            outputs=[z],
            inverse_map={v: InverseMap.identity(len(v_shape)) for v, v_shape
                         in zip([cond, x, y], [cond_shape, x_shape, y_shape]) if prod(v_shape) == prod(z_shape)}
        )


class UnaryElementwiseOp(Operator):
    def __init__(self, x: Tensor, op, name: str, attributes: Optional[Dict[str, Any]] = None):
        super().__init__(
            inputs=[x],
            task=UnaryElementwiseTask(name, input_like(x, 'x'), op=op),
            attributes=attributes
        )


class BinaryElementwiseOp(Operator):
    def __init__(self, x: Tensor, y: Tensor, op, name: str):
        super().__init__(
            inputs=[x, y],
            task=BinaryElementwiseTask(name, input_like(x, 'x'), input_like(y, 'y'), op=op)
        )


class AddScalarOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor, scalar: Union[float, int]):
        super().__init__(x, op=lambda v: v + const_like(scalar, v), attributes={'scalar': scalar}, name='adds')


class SubScalarOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor, scalar: Union[float, int]):
        super().__init__(x, op=lambda v: v - const_like(scalar, v), attributes={'scalar': scalar}, name='subs')


class RSubScalarOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor, scalar: Union[float, int]):
        super().__init__(x, op=lambda v: const_like(scalar, v) - v, attributes={'scalar': scalar}, name='rsubs')


class MultiplyScalarOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor, scalar: Union[float, int]):
        super().__init__(x, op=lambda v: v * const_like(scalar, v), attributes={'scalar': scalar}, name='muls')


class DivideScalarOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor, scalar: Union[float, int]):
        super().__init__(x, op=lambda v: v / const_like(scalar, v), attributes={'scalar': scalar}, name='divs')


class RDivideScalarOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor, scalar: Union[float, int]):
        super().__init__(x, op=lambda v: const_like(scalar, v) / v, attributes={'scalar': scalar}, name='rdivs')


class SqrtOp(UnaryElementwiseOp):
    def __init__(self, x):
        super().__init__(x, op=lambda v: primitives.sqrt(v), name='sqrt')


class ErfOp(UnaryElementwiseOp):
    def __init__(self, x):
        super().__init__(x, op=lambda v: primitives.erf(v), name='erf')


class TanhOp(UnaryElementwiseOp):
    def __init__(self, x):
        super().__init__(x, op=lambda v: primitives.tanh(v), name='erf')


class RsqrtOp(UnaryElementwiseOp):
    def __init__(self, x):
        super().__init__(x, op=lambda v: primitives.rsqrt(v), name='rsqrt')


class PowOp(BinaryElementwiseOp):
    def __init__(self, x, y):
        super().__init__(x, y, op=lambda x, y: primitives.pow(x, y), name='pow')


class NegOp(UnaryElementwiseOp):
    def __init__(self, x):
        super().__init__(x, op=lambda v: -v, name='neg')


class AddOp(BinaryElementwiseOp):
    def __init__(self, x: Tensor, y: Tensor):
        super().__init__(x, y, op=lambda a, b: a + b, name='add')


class SubOp(BinaryElementwiseOp):
    def __init__(self, x: Tensor, y: Tensor):
        super().__init__(x, y, op=lambda a, b: a - b, name='sub')


class MultiplyOp(BinaryElementwiseOp):
    def __init__(self, x: Tensor, y: Tensor):
        super().__init__(x, y, op=lambda a, b: a * b, name='mul')


class DivideOp(BinaryElementwiseOp):
    def __init__(self, x: Tensor, y: Tensor):
        super().__init__(x, y, op=lambda a, b: a / b, name='div')


class SinOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor):
        super().__init__(x, op=lambda a: primitives.sin(a), name='sin')


class CosOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor):
        super().__init__(x, op=lambda a: primitives.cos(a), name='cos')


class SquareOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor):
        super().__init__(x, op=lambda a: a * a, name='square')


class CubeOp(UnaryElementwiseOp):
    def __init__(self, x: Tensor):
        super().__init__(x, op=lambda a: a * a * a, name='cube')


class EqualOp(BinaryElementwiseOp):
    def __init__(self, x: Tensor, y: Tensor):
        super().__init__(x, y, lambda a, b: expr.Equal(a, b), name='equal')


class LessOp(BinaryElementwiseOp):
    def __init__(self, x: Tensor, y: Tensor):
        super().__init__(x, y, lambda a, b: a < b, name='less')


class WhereOp(Operator):
    def __init__(self, cond: Tensor, x: Tensor, y: Tensor):
        super().__init__(
            inputs=[cond, x, y],
            task=WhereTask(input_like(cond, 'cond'), input_like(x, 'x'), input_like(y, 'y')),
            name='where'
        )


PythonScalar = Union[float, int]


def binary_arithmatic(
        x: Union[Tensor, float, int],
        y: Union[Tensor, float, int],
        tensor_scalar_op,
        scalar_tensor_op,
        tensor_tensor_op
) -> Union[Tensor, float, int]:
    if not (isinstance(x, (Tensor, float, int)) and isinstance(y, (Tensor, float, int))):
        raise ValueError('Only support add/sub/mul/div between hidet.Tensor, float, and int. got {} and {}'.format(type(x), type(y)))
    if isinstance(x, (float, int)):
        x = convert(x)
    if isinstance(y, (float, int)):
        y = convert(y)
    x_scalar = len(x.shape) == 0 and x.storage is not None
    y_scalar = len(y.shape) == 0 and y.storage is not None
    if x_scalar and y_scalar:
        return tensor_tensor_op(x, y)
    elif y_scalar:
        return tensor_scalar_op(x, y.scalar())
    elif x_scalar:
        return scalar_tensor_op(x.scalar(), y)
    else:
        return tensor_tensor_op(x, y)


def add(x: Union[Tensor, float, int], y: Union[Tensor, float, int]) -> Tensor:
    return binary_arithmatic(
        x, y,
        lambda a, b: AddScalarOp(a, b).get_output(0),
        lambda a, b: AddScalarOp(b, a).get_output(0),
        lambda a, b: AddOp(a, b).get_output(0)
    )


def sub(x: Union[Tensor, float, int], y: Union[Tensor, float, int]) -> Tensor:
    return binary_arithmatic(
        x, y,
        lambda a, b: SubScalarOp(a, b).get_output(0),
        lambda a, b: RSubScalarOp(b, a).get_output(0),
        lambda a, b: SubOp(a, b).get_output(0)
    )


def multiply(x: Union[Tensor, float, int], y: Union[Tensor, float, int]) -> Tensor:
    return binary_arithmatic(
        x, y,
        lambda a, b: MultiplyScalarOp(a, b).get_output(0),
        lambda a, b: MultiplyScalarOp(b, a).get_output(0),
        lambda a, b: MultiplyOp(a, b).get_output(0)
    )


def divide(x: Union[Tensor, float, int], y: Union[Tensor, float, int]) -> Tensor:
    return binary_arithmatic(
        x, y,
        lambda a, b: DivideScalarOp(a, b).get_output(0),
        lambda a, b: RDivideScalarOp(b, a).get_output(0),
        lambda a, b: DivideOp(a, b).get_output(0)
    )


def sqrt(x: Tensor) -> Tensor:
    return SqrtOp(x).get_output(0)


def tanh(x: Tensor) -> Tensor:
    return TanhOp(x).get_output(0)


def pow(x: Tensor, y: Tensor) -> Tensor:
    return PowOp(x, y).get_output(0)


def erf(x: Tensor) -> Tensor:
    return ErfOp(x).get_output(0)


def rsqrt(x: Tensor) -> Tensor:
    return RsqrtOp(x).get_output(0)


def neg(x: Tensor) -> Tensor:
    return NegOp(x).get_output(0)


def sin(x: Tensor) -> Tensor:
    return SinOp(x).get_output(0)


def cos(x: Tensor) -> Tensor:
    return CosOp(x).get_output(0)


def square(x: Tensor) -> Tensor:
    return SquareOp(x).get_output(0)


def cube(x: Tensor) -> Tensor:
    return CubeOp(x).get_output(0)


def equal(x: Tensor, y: Tensor) -> Tensor:
    if x.dtype != y.dtype:
        raise ValueError('Can only compare tensors with the same dtype, but got {} and {}'.format(x.dtype, y.dtype))
    return EqualOp(x, y).get_output(0)


def less(x: Tensor, y: Tensor) -> Tensor:
    return LessOp(x, y).get_output(0)


def where(cond: Tensor, x: Tensor, y: Tensor) -> Tensor:
    if cond.dtype != 'bool':
        raise ValueError('The condition tensor must have dtype "bool", but got {}'.format(cond.dtype))
    return WhereOp(cond, x, y).get_output(0)
