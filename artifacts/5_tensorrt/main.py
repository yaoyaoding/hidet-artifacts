from artifact import bench


def main():
    for executor in [
        '--exec trt',
        '--exec hidet',
    ]:
        for model in [
            '--model resnet50',
            '--model inception_v3',
            '--model mobilenet_v2',
            '--model bert',
            '--model gpt2'
        ]:
            bench('{} {}'.format(executor, model))


if __name__ == '__main__':
    main()
