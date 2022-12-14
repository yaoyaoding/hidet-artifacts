from typing import List
from .utils import Tensor
from .arithmatic import sqrt, square
from .reduce import reduce_mean, reduce_var


def normalize(x: Tensor, dims: List[int], epsilon: float = 1e-5) -> Tensor:
    x = x - x.mean(dims, keep_dim=True)
    variance = square(x).mean(dims, keep_dim=True)
    return x * (variance + epsilon).rsqrt()


def batch_norm_infer(x: Tensor, running_mean: Tensor, running_var: Tensor, epsilon=1e-5, axis=1) -> Tensor:
    assert len(x.shape) == 4 and axis == 1
    assert len(running_mean.shape) == 1 and len(running_var.shape) == 1
    assert x.shape[1] == running_mean.shape[0] == running_var.shape[0]
    running_mean = running_mean.unsqueeze([0, 2, 3])  # [1, c, 1, 1]
    running_var = running_var.unsqueeze([0, 2, 3])
    return (x - running_mean) * (running_var + epsilon).rsqrt()


def instance_norm(x: Tensor, axis: int = 1, epsilon: float = 1e-5) -> Tensor:
    """
    Instance norm.

    Parameters
    ----------
    x: Tensor
        The data to be normalized.
    axis: int
        The axis of channel dimension.
    epsilon: float
        The epsilon added to variance.

    Returns
    -------
    ret: Tensor
        The normalized tensor.
    """
    dims = [dim for dim in range(2, len(x.shape)) if dim != axis]
    return normalize(x, dims=dims, epsilon=epsilon)


def layer_norm(x: Tensor, num_last_dims: int = 1, epsilon: float = 1e-5) -> Tensor:
    """
    Layer norm.

    Parameters
    ----------
    x: Tensor
        The data to be normalized.
    num_last_dims: int
        The number of dimensions to be normalized, starting from the end dimension of x.
    epsilon: float
        The epsilon added to variance.

    Returns
    -------
    ret: Tensor
        The normalized tensor.
    """
    dims = list(range(len(x.shape) - num_last_dims, len(x.shape)))
    return normalize(x, dims=dims, epsilon=epsilon)
