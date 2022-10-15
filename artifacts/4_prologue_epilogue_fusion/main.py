from artifact import bench


def main():
    for executor in [
        '--exec ort',
        '--exec ansor',
        '--exec hidet',
    ]:
        for model in [
            '--model resnet50_conv_0',
            '--model resnet50_conv_1',
            '--model resnet50_conv_2',
            '--model resnet50_conv_3',
            '--model resnet50_conv_4',
            '--model resnet50_conv_5',
            '--model resnet50_conv_6',
            '--model resnet50_conv_7',
            '--model resnet50_conv_8',
            '--model resnet50_conv_9',
            '--model resnet50_conv_10',
            '--model resnet50_conv_11',
            '--model resnet50_conv_12',
            '--model resnet50_conv_13',
            '--model resnet50_conv_14',
            '--model resnet50_conv_15',
            '--model resnet50_conv_16',
            '--model resnet50_conv_17',
            '--model resnet50_conv_18',
            '--model resnet50_conv_19',
            '--model resnet50_conv_20',
            '--model resnet50_conv_21',
            '--model resnet50_conv_22',
        ]:
            bench('{} {}'.format(executor, model))


if __name__ == '__main__':
    main()
