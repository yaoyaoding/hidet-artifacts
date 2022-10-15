import os

from hidet.ir.func import IRModule
from .base import PassInstrument


class SaveIRInstrument(PassInstrument):
    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        self.index = 0
        os.makedirs(out_dir, exist_ok=True)

    def before_all_passes(self, ir_module: IRModule):
        # first clean all json starting with indices
        for fname in os.listdir(self.out_dir):
            fpath = os.path.join(self.out_dir, fname)
            parts = fname.split('_')
            if os.path.isfile(fpath) and len(parts) > 1 and parts[0].isdigit() and fname.endswith('.txt'):
                os.remove(fpath)
        with open(os.path.join(self.out_dir, '0_Origin.txt'), 'w') as f:
            f.write(str(ir_module))
            self.index += 1

    def after_pass(self, pass_name: str, ir_module: IRModule):
        with open(os.path.join(self.out_dir, '{}_{}.txt'.format(self.index, pass_name)), 'w') as f:
            f.write(str(ir_module))
            self.index += 1
