from artifact import bench


def main():
    for executor in [
        '--exec hidet',
        '--exec ansor',
        '--exec autotvm',
    ]:
        for model in [
            # a conv-bn-relu subgraph in resnet50 with conv2d:
            # input: [1, 256, 28, 28], weight: [256, 256, 3, 3], padding: 1, stride: 2
            '--model op_resnet50_conv_2',
        ]:
            bench('{} {}'.format(executor, model))


if __name__ == '__main__':
    main()
