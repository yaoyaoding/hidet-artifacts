from artifact import bench


def main():
    for executor in [
        '--exec torch',
        '--exec ort',
        '--exec autotvm',
        '--exec ansor',
        '--exec hidet',
    ]:
        for bs in [
            '--bs 1',
            '--bs 4',
            '--bs 8',
        ]:
            model = '--model resnet50'
            bench('{} {} {}'.format(executor, bs, model))


if __name__ == '__main__':
    main()
