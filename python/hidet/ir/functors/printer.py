from typing import Dict, Optional, List
from hidet.ir.node import Node
from hidet.ir.func import IRModule, Function
from hidet.ir.type import ScalarType, TensorType, TypeNode
from hidet.ir.expr import Constant, Var, Call, TensorElement, Add, Multiply, Expr, LessThan, FloorDiv, Mod, Equal, Div, Sub, Not, Or, And, Let, IfThenElse, TensorSlice, RightShift, LeftShift, BitwiseNot, BitwiseOr, BitwiseAnd, Neg, Cast
from hidet.ir.stmt import SeqStmt, IfStmt, ForStmt, AssignStmt, BufferStoreStmt, EvaluateStmt, Stmt, AssertStmt, BlackBoxStmt, AsmStmt, ReturnStmt, LetStmt
from hidet.ir.dialects.compute import TensorNode, ScalarNode
from hidet.ir.dialects.lowlevel import VoidType, PointerType, Dereference, Address, ReferenceType, TensorPointerType, Reference
from hidet.ir.dialects.pattern import AnyExpr
from hidet.ir.layout import RowMajorLayout, ColumnMajorLayout
from hidet.ir.task import Task, Prologue, Epilogue, InverseMap
from hidet.utils.doc import Doc, NewLine, Text, doc_join
from hidet.utils.namer import Namer

from .base import StmtExprFunctor, TypeFunctor, NodeFunctor


class IRPrinter(StmtExprFunctor, TypeFunctor):
    def __init__(self):
        super().__init__()
        self.namer = Namer()
        self.ir_module: Optional[IRModule] = None

    def __call__(self, node):
        return self.visit(node)

    def visit(self, obj):
        if isinstance(obj, (list, tuple)):
            return doc_join([self(v) for v in obj], ', ')
        elif isinstance(obj, dict):
            return doc_join([self(k) + ': ' + self(v) for k, v in obj.items()], ', ')
        elif isinstance(obj, str):
            return Text(obj.replace('\n', '\\n').replace('\t', '\\t'))
        elif isinstance(obj, (int, float)):
            return Text(str(obj))
        elif isinstance(obj, TypeNode):
            return TypeFunctor.visit(self, obj)
        elif isinstance(obj, Function):
            return self.visit_Function(obj)
        elif isinstance(obj, IRModule):
            return self.visit_IRModule(obj)
        elif isinstance(obj, (Expr, Stmt)):
            return NodeFunctor.visit(self, obj)
        elif isinstance(obj, Task):
            return self.visit_Task(obj)
        elif isinstance(obj, Prologue):
            return self.visit_Prologue(obj)
        elif isinstance(obj, Epilogue):
            return self.visit_Epilogue(obj)
        elif isinstance(obj, InverseMap):
            return self.visit_InverseMap(obj)
        elif obj is None:
            return Text('None')
        else:
            return object.__repr__(obj)

    def visit_Function(self, func: Function):
        self.namer.clear()
        doc = Doc()

        # parameters
        doc += 'fn('
        param_docs = []
        for i in range(len(func.params)):
            param = func.params[i]
            param_docs.append([NewLine(), self(param), ': ', self(param.type)])
        doc += doc_join(param_docs, Text(', '))
        doc += ')'
        doc = doc.indent(6)

        # const locals
        for local_var, local_value in func.local_const_vars:
            doc += (NewLine() + Text('declare ') + self(local_var) + Text(': ') + self(local_var.type) + ' = ' + self(local_value)).indent(4)

        # locals
        for local_var in func.local_vars:
            doc += (NewLine() + Text('declare ') + self(local_var) + Text(': ') + self(local_var.type)).indent(4)

        # body
        doc += self(func.body).indent(4)

        return doc

    def visit_IRModule(self, ir_module: IRModule):
        doc = Doc()
        self.ir_module = ir_module
        if ir_module.task is not None:
            doc += str(ir_module.task)
        doc += NewLine()
        for name, func in ir_module.functions.items():
            doc += ['def ', name, ' ', self(func), NewLine(), NewLine()]
        return doc

    def visit_Add(self, e: Add):
        return Text('(') + self(e.a) + ' + ' + self(e.b) + ')'

    def visit_Sub(self, e: Sub):
        return Text('(') + self(e.a) + ' - ' + self(e.b) + ')'

    def visit_Multiply(self, e: Multiply):
        return Text('(') + self(e.a) + ' * ' + self(e.b) + ')'

    def visit_Div(self, e: Div):
        return Text('(') + self(e.a) + ' / ' + self(e.b) + ')'

    def visit_Mod(self, e: Mod):
        return Text('(') + self(e.a) + ' % ' + self(e.b) + ')'

    def visit_FloorDiv(self, e: FloorDiv):
        return Text('(') + self(e.a) + ' / ' + self(e.b) + ')'

    def visit_Neg(self, e: Neg):
        return Text('(-') + self(e.a) + ')'

    def visit_LessThan(self, e: LessThan):
        return Text('(') + self(e.a) + ' < ' + self(e.b) + ')'

    def visit_LessEqual(self, e: LessThan):
        return Text('(') + self(e.a) + ' <= ' + self(e.b) + ')'

    def visit_Equal(self, e: Equal):
        return Text('(') + self(e.a) + ' == ' + self(e.b) + ')'

    def visit_And(self, e: And):
        return Text('(') + self(e.a) + ' && ' + self(e.b) + ')'

    def visit_Or(self, e: Or):
        return Text('(') + self(e.a) + ' || ' + self(e.b) + ')'

    def visit_Not(self, e: Not):
        return Text('!') + self(e.a)

    def visit_BitwiseAnd(self, e: BitwiseAnd):
        return '(' + self(e.a) + ' & ' + self(e.b) + ')'

    def visit_BitwiseOr(self, e: BitwiseOr):
        return '(' + self(e.a) + ' | ' + self(e.b) + ')'

    def visit_BitwiseNot(self, e: BitwiseNot):
        return '(~' + self(e.base) + ')'

    def visit_LeftShift(self, e: LeftShift):
        return '(' + self(e.base) + ' << ' + self(e.cnt) + ')'

    def visit_RightShift(self, e: RightShift):
        return '(' + self(e.base) + ' >> ' + self(e.cnt) + ')'

    def visit_TensorElement(self, e: TensorElement):
        return self(e.base) + '[' + self(e.indices) + ']'

    def visit_TensorSlice(self, e: TensorSlice):
        subscriptions = []
        for index, start, end in zip(e.indices, e.starts, e.ends):
            if index is not None:
                subscriptions.append(self(index))
            else:
                doc = Doc()
                if start is not None:
                    doc += self(start)
                doc += ':'
                if end is not None:
                    doc += self(end)
                subscriptions.append(doc)
        return self(e.base) + '[' + doc_join(subscriptions, ', ') + ']'

    def visit_IfThenElse(self, e: IfThenElse):
        return '(' + self(e.cond) + ' ? ' + self(e.then_expr) + ' : ' + self(e.else_expr) + ')'

    def visit_Call(self, e: Call):
        doc = Doc()
        # name
        doc += e.func_var.hint
        # launch
        func_name = e.func_var.hint
        if self.ir_module and func_name in self.ir_module.functions:
            func = self.ir_module.functions[func_name]
            if func.kind == 'cuda_kernel':
                doc += '<<<' + self(func.attrs['cuda_grid_dim']) + ', ' + self(func.attrs['cuda_block_dim']) + '>>>'
        # params
        doc += '(' + self(e.args) + ')'
        return doc

    def visit_Let(self, e: Let):
        return Text('let(') + self(e.var) + '=' + self(e.value) + ': ' + self(e.body) + ')'

    def visit_Cast(self, e: Cast):
        return Text('cast(') + self(e.target_type) + ', ' + self(e.expr) + ')'

    def visit_Reference(self, e: Reference):
        return Text('Ref(') + self(e.expr) + ')'

    def visit_Dereference(self, e: Dereference):
        return Text('*') + self(e.expr)

    def visit_Address(self, e: Address):
        return Text('&') + self(e.expr)

    def visit_Var(self, e: Var):
        return Text(self.namer.get_name(e))

    def visit_Constant(self, e: Constant):
        if e.value is None:
            return self('Constant(None, type=') + self(e.data_type) + ')'
        if e.is_tensor():
            return 'ConstTensor({}, {})'.format(e.value.shape, e.data_type)
        else:
            dtype = e.data_type.name
            if dtype == 'float32':
                ret = '{}f'.format(float(e.value))
            elif dtype == 'float16':
                ret = 'half({})'.format(float(e.value))
            elif dtype == 'int32':
                ret = '{}'.format(int(e.value))
            else:
                ret = '{}({})'.format(dtype, e.value)
            return Text(ret)

    def visit_EvaluateStmt(self, stmt: EvaluateStmt):
        return NewLine() + self(stmt.expr)

    def visit_BufferStoreStmt(self, stmt: BufferStoreStmt):
        doc = NewLine()
        doc += self(stmt.buf)
        doc += '[' + self(stmt.indices) + ']'
        doc += ' = ' + self(stmt.value)
        return doc

    def visit_AssignStmt(self, stmt: AssignStmt):
        return NewLine() + self(stmt.var) + ' = ' + self(stmt.value)

    def visit_LetStmt(self, stmt: LetStmt):
        doc = Doc()
        for bind_var, bind_value in zip(stmt.bind_vars, stmt.bind_values):
            doc += NewLine() + 'let ' + self(bind_var) + ' = ' + self(bind_value)
        doc += self(stmt.body)
        # doc += self(stmt.body).indent()
        return doc

    def visit_ForStmt(self, stmt: ForStmt):
        rng = Text('range(') + self(stmt.extent) + ')'
        doc = NewLine() + Text('for ') + self(stmt.loop_var) + ' in ' + rng
        if stmt.unroll is not None:
            if stmt.unroll:
                doc += '[unroll]'
            else:
                doc += '[no-unroll]'
        doc += self(stmt.body).indent(4)
        return doc

    def visit_IfStmt(self, stmt: IfStmt):
        doc = NewLine() + Text('if ') + self(stmt.cond)
        doc += self(stmt.then_body).indent(4)
        if stmt.else_body:
            doc += NewLine() + Text('else')
            doc += self(stmt.else_body).indent(4)
        return doc

    def visit_ReturnStmt(self, stmt: ReturnStmt):
        doc = NewLine() + Text('return')
        if stmt.ret_value:
            doc += ' ' + self(stmt.ret_value)
        return doc

    def visit_AssertStmt(self, stmt: AssertStmt):
        return NewLine() + 'assert(' + self(stmt.cond) + ', ' + stmt.msg + ')'

    def visit_AsmStmt(self, stmt: AsmStmt):
        volatile_doc = 'volatile ' if stmt.is_volatile else ''
        template_doc = '"' + Text(stmt.template_string) + '"'
        output_docs = []
        for label, expr in zip(stmt.output_labels, stmt.output_exprs):
            output_docs.append('"' + Text(label) + '"' + '(' + self(expr) + ')')
        input_docs = []
        for label, expr in zip(stmt.input_labels, stmt.input_exprs):
            input_docs.append('"' + Text(label) + '"' + '(' + self(expr) + ')')
        return NewLine() + 'asm ' + volatile_doc + '(' + template_doc + ' : ' + doc_join(output_docs, ', ') + ' : ' + doc_join(input_docs, ', ') + ');'

    def visit_BlackBoxStmt(self, stmt: BlackBoxStmt):
        expr_docs = [str(self(e)) for e in stmt.exprs]
        stmt_string: str = stmt.template_string.format(*expr_docs)
        lines = stmt_string.split('\n')
        doc = Text('')
        for line in lines:
            doc += NewLine() + line
        return doc

    def visit_SeqStmt(self, stmt: SeqStmt):
        doc = Doc()
        for idx, s in enumerate(stmt.seq):
            doc += self(s)
        return doc

    def visit_ScalarType(self, t: ScalarType):
        return Text('{}'.format(t.name))

    def visit_TensorType(self, t: TensorType):
        assert t.scope is not None
        if isinstance(t.layout, RowMajorLayout):
            layout = 'row_major'
        elif isinstance(t.layout, ColumnMajorLayout):
            layout = 'column_major'
        elif t.layout is None:
            layout = 'None'
        else:
            layout = type(t.layout).__name__
        items = [self(t.scalar_type), '[' + self(t.shape) + ']', self(t.scope.name), self(layout)]
        return Text('tensor(') + doc_join(items, ', ') + ')'

    def visit_PointerType(self, t: PointerType):
        return Text('PointerType(') + self(t.base_type) + ')'

    def visit_TensorPointerType(self, t: TensorPointerType):
        return Text('TensorPointerType(') + self(t.tensor_type) + ')'

    def visit_ReferenceType(self, t: ReferenceType):
        return Text('ReferenceType(') + self(t.base_type) + ')'

    def visit_VoidType(self, t: VoidType):
        return Text('VoidType')

    def visit_AnyExpr(self, e: AnyExpr):
        return Text('AnyExpr')

    def print_tensor_nodes(self, nodes: List[TensorNode], exclude_nodes: List[TensorNode] = None) -> Doc:
        from hidet.ir.functors import collect
        if exclude_nodes is None:
            exclude_nodes = []
        nodes: List[TensorNode] = collect(nodes, TensorNode)
        doc = Doc()
        for node in reversed(nodes):
            if node in exclude_nodes:
                continue
            if node.grid_compute is None:
                doc += NewLine() + self.namer.get_name(node) + ': ' + self(node.data_type)
            else:
                gc = node.grid_compute
                items = [
                    '[' + self(gc.shape) + ']',
                    '(' + self(gc.axes) + ') => ' + self(gc.value),
                ]
                doc += NewLine() + self.namer.get_name(node) + ': ' + 'grid(' + doc_join(items, ', ') + ')'
        return doc

    def visit_Task(self, e: Task):
        lines = [
            Text('name: ') + e.name,
            Text('parameters: ') + (NewLine() + doc_join(['{}: {}'.format(self.namer.get_name(v), self(v.data_type)) for v in e.parameters], NewLine())).indent(),
            Text('inputs: ') + '[' + doc_join([self.namer.get_name(v) for v in e.inputs], ', ') + ']',
            Text('outputs: ') + '[' + doc_join([self.namer.get_name(v) for v in e.outputs], ', ') + ']',
            Text('computations: ') + self.print_tensor_nodes(e.outputs).indent(),
            Text('attributes: {') + self(e.attributes) + '}'
        ]
        front_part = doc_join(lines, NewLine())
        inverse_map_doc = Doc()
        prologue_doc = Doc()
        epilogue_doc = Doc()
        if e.inverse_map:
            inverse_map_doc += NewLine() + Text('inverse_map:')
            for tensor, inverse_map in e.inverse_map.items():
                inverse_map_doc += (NewLine() + self.namer.get_name(tensor) + ': ' + self(inverse_map)).indent()
        if e.prologues:
            prologue_doc += NewLine() + Text('prologue:')
            for tensor, prologue in e.prologues.items():
                prologue_doc += (NewLine() + self.namer.get_name(tensor) + ': ' + self(prologue)).indent()
        if e.epilogues:
            epilogue_doc += NewLine() + Text('epilogue:')
            for tensor, epilogue in e.epilogues.items():
                epilogue_doc += (NewLine() + self.namer.get_name(tensor) + ': ' + self(epilogue)).indent()
        return Text('Task(') + (NewLine() + front_part + inverse_map_doc + prologue_doc + epilogue_doc).indent() + NewLine() + ')'

    def visit_Prologue(self, e: Prologue):
        from hidet.ir.functors import collect
        items = [
            '(' + self(e.indices) + ') => ' + self(e.value),
            'extra_inputs: [' + self(e.extra_inputs) + ']'
        ]
        doc = 'Prologue(' + doc_join(items, ', ') + ')'
        nodes = [node for node in collect(e.value, TensorNode) if node.grid_compute is not None]
        if len(nodes) > 0:
            doc += self.print_tensor_nodes(nodes, exclude_nodes=[]).indent()
        return doc

    def visit_Epilogue(self, e: Epilogue):
        from hidet.ir.functors import collect
        items = [
            '(' + self(e.indices) + ')',
            self(e.orig_value) + ' => ' + self(e.value),
            'out_indices=(' + self(e.out_indices) + ')',
            'out_tensor=' + self(e.out_tensor) + ')'
        ]
        doc = doc_join(items, ', ')
        # ret = 'Epilogue((' + self(e.indices) + '), ' + self(e.orig_value) + ' => ' + self(e.value) + ', out_indices=(' + self(e.out_indices) + '), out_tensor=' + self(e.out_tensor) + ')'
        nodes = [node for node in collect(e.value, TensorNode) if node.grid_compute is not None]
        if len(nodes) > 0:
            doc += self.print_tensor_nodes(nodes, exclude_nodes=[]).indent()
        return doc

    def visit_InverseMap(self, e: InverseMap):
        return 'InverseMap([' + self(e.axes) + '] => [' + self(e.indices) + '])'

    def visit_ScalarNode(self, e: ScalarNode):
        if e.reduce_compute is None:
            return self.namer.get_name(e, e.name)
        else:
            rc = e.reduce_compute
            items = [
                '[' + self(rc.shape) + ']',
                '(' + self(rc.axes) + ') => ' + self(rc.value),
                self(rc.reduce_type)
            ]
            return 'reduce(' + doc_join(items, ', ') + ')'

    def visit_TensorNode(self, e: TensorNode):
        return self.namer.get_name(e)


def astext(obj: Node) -> str:
    if isinstance(obj, Node):
        printer = IRPrinter()
        return str(printer(obj))
    else:
        raise ValueError()
