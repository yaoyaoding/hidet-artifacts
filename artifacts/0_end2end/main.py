from artifact import bench
import hidet


def main():
    for executor in [
       '--exec torch',
       '--exec ort',
       '--exec autotvm',
       '--exec ansor',
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
