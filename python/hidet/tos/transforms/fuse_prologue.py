from typing import List
from .base import GraphPass, PassContext, logger
from hidet.ir.expr import Var, var, TensorElement
from hidet.tos.ir import FlowGraph, Operator, Tensor
from hidet.ir.dialects.compute import TensorNode, GridCompute
from hidet.tos.ir.functors import clone, analyze_usage
from hidet.ir.task import Task, Prologue, Epilogue, is_injective_task, is_unary_injective_task
from hidet.ir.functors import rewrite, collect
from hidet.utils import prod, strict_zip, py
from .common import concat_op_name
from .utils import is_barrier


def update_params(task: Task, op: Operator, op_input: Tensor, task_input: TensorNode, op_extra_inputs: List[Tensor], task_extra_inputs: List[TensorNode]):
    """
    Update parameters of task and operator.

    Parameters
    ----------
    task: Task
        The task to update.
    op: Operator
        The operator to update.
    op_input: Tensor
        The original operator input to remove.
    task_input: TensorNode
        The original task input to remove.
    task_extra_inputs: List[TensorNode]
        The extra task inputs to add.
    op_extra_inputs: List[Tensor]
        The extra operator inputs to add.
    """
    task_param_inputs = task.parameters[:len(op.inputs)]
    task_param_outputs = task.parameters[len(op.inputs):]

    # remove original input
    op.inputs = [v for v in op.inputs if v is not op_input]
    task_param_inputs = [v for v in task_param_inputs if v is not task_input]

    # add extra inputs
    op.inputs.extend(op_extra_inputs)
    task_param_inputs.extend(task_extra_inputs)

    # update task parameters
    task.parameters = task_param_inputs + task_param_outputs


def try_fuse(graph: FlowGraph, usage) -> bool:
    # for u_op in graph.nodes:
    for u_op in reversed(graph.nodes):
        if is_barrier(u_op):
            continue
        # v_op -> u_op => (v_op as prologue) u_op
        u_task = u_op.task
        # if is_injective_task(u_task) and not is_sink_op(u_op, usage):
        # if is_injective_task(u_task):
        #     continue
        for i, u_input in enumerate(u_op.inputs):
            if len(usage[u_input]) > 1:
                # should not fuse op that has been used by multiple times
                continue

            v_op = u_input.op
            if v_op is None:
                # u_input is a graph input
                continue
            if is_barrier(v_op):
                continue

            if len(v_op.outputs) != 1:
                # only fuse op with single output
                continue

            if not is_injective_task(v_op.task):
                # only fuse injective op
                continue

            u_task_input: TensorNode = u_task.parameters[i]

            v_task = v_op.task
            if len(v_task.prologues) + len(v_task.epilogues) > 0:
                # todo: add support for these cases.
                continue
            v_task_output = v_task.outputs[0]

            task = None
            if u_task_input in u_task.inputs:
                # u_input is an input of original task
                prologue = Prologue(
                    extra_inputs=v_task.inputs,
                    indices=v_task_output.grid_compute.axes,
                    value=v_task_output.grid_compute.value
                )
                task = u_task.copy()
                task.prologues[u_task_input] = prologue
            else:
                # u_input is used in a prologue or epilogue
                for original_task_input, existed_prologue in u_task.prologues.items():
                    if u_task_input in existed_prologue.extra_inputs:
                        # u_input is used in an existing prologue
                        tensor_elements: List[TensorElement] = collect(existed_prologue.value, TensorElement)
                        gc = v_task_output.grid_compute
                        rmap = {te: rewrite(gc.value, {a: b for a, b in strict_zip(gc.axes, te.indices)})
                                for te in tensor_elements if te.base is u_task_input}
                        value = rewrite(existed_prologue.value, rmap)
                        filtered_extra_inputs = [extra_input for extra_input in existed_prologue.extra_inputs
                                                 if extra_input is not u_task_input]
                        prologue = Prologue(
                            extra_inputs=filtered_extra_inputs + v_task.inputs,
                            indices=existed_prologue.indices,
                            value=value
                        )
                        task = u_task.copy()
                        task.prologues[original_task_input] = prologue

                for original_task_output, existed_epilogue in u_task.epilogues.items():
                    if u_task_input in existed_epilogue.extra_inputs:
                        # u_input is used in an existing epilogue
                        tensor_elements: List[TensorElement] = collect(existed_epilogue.value, TensorElement)
                        gc = v_task_output.grid_compute
                        rmap = {te: rewrite(gc.value, {a: b for a, b in strict_zip(gc.axes, te.indices)})
                                for te in tensor_elements if te.base is u_task_input}
                        value = rewrite(existed_epilogue.value, rmap)
                        filtered_extra_inputs = [inp for inp in existed_epilogue.extra_inputs if inp is not u_task_input]
                        epilogue = Epilogue(
                            extra_inputs= filtered_extra_inputs + v_task.inputs,
                            indices=existed_epilogue.indices,
                            orig_value=existed_epilogue.orig_value,
                            value=value,
                            out_indices=existed_epilogue.out_indices,
                            out_tensor=existed_epilogue.out_tensor
                        )
                        task = u_task.copy()
                        task.epilogues[original_task_output] = epilogue

            if task is None:
                raise ValueError('Input {} has not been used in task.'.format(u_task_input))

            task.name = '{}_{}'.format(v_task.name, u_task.name)
            update_params(
                task=task,
                op=u_op,
                op_input=u_input,
                task_input=u_task_input,
                op_extra_inputs=v_op.inputs,
                task_extra_inputs=v_task.inputs,
            )
            u_op.task = task
            if PassContext.current().configs['verbose']:
                logger.info('Fused prologue {} {}'.format(py.color_text(v_op.name, idx=1), py.color_text(u_op.name, idx=2)))
                logger.debug('u_task')
                logger.debug(u_task)
                logger.debug('v_task')
                logger.debug(v_task)
                logger.debug('fused_task')
                logger.debug(task)
            graph.nodes.remove(v_op)

            return True

    return False


class FuseProloguePass(GraphPass):

    def process_graph(self, graph: FlowGraph) -> FlowGraph:
        graph = clone(graph)
        usage = analyze_usage(graph)
        graph.update_nodes()

        while True:
            success = try_fuse(graph, usage)
            if not success:
                break
        return graph


def fuse_prologue_pass() -> GraphPass:
    return FuseProloguePass()
