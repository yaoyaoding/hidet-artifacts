from artifact import bench


def main():
    for executor in [
        '--exec ansor',
        '--exec autotvm',
        '--exec hidet',
    ]:
        for model in [
            '--model op_matmul_nn_4',   # 2048x2048x2048
            '--model op_matmul_nn_5',   # 2039x2039x2039
            '--model op_matmul_nn_6',   # 2047x2047x2047
            '--model op_matmul_nn_7',   # 2046x2046x2046
            '--model op_matmul_nn_8',   # 2045x2045x2045
            '--model op_matmul_nn_9',   # 2044x2044x2044
            '--model op_matmul_nn_10',  # 2043x2043x2043
            '--model op_matmul_nn_11',  # 2042x2042x2042
        ]:
            if '_5' in model and ('ansor' in executor or 'autotvm' in executor):
                # both schedulers failed to find a schedule for this input 2039x2039x2039, skip
                # for autotvm, it will fall back to a default schedule.
                # for ansor, it will fall into a dead loop.
                continue
            bench('{} {}'.format(executor, model))


if __name__ == '__main__':
    main()
