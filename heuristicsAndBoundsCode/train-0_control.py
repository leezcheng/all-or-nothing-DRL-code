import os
import json
import numpy as np
import matplotlib.pyplot as plt


def summary(RED_FLAG):
    gap_list = []
    for sample_id in range(1, 432 + 1):
        if os.path.exists('train/data/losses_sample%s.json' % sample_id) and os.path.exists(
                'train/figure/gap_sample%s.png' % sample_id):
            with open('train/data/losses_sample%s.json' % sample_id) as f:
                arr = json.load(f)
                gap = np.log(arr[-1])
                gap_list.append(gap)
        else:
            gap_list.append(1e4 - sample_id)

    plt.plot(list(range(1, len(gap_list) + 1)), [x if x <= 3.5 else 3.5 for x in gap_list])
    plt.plot(list(range(1, len(gap_list) + 1)), [RED_FLAG for _ in gap_list], color='r')
    plt.xlabel('sample')
    plt.title('gap')
    plt.show()

    plt.plot(list(range(1, len(gap_list) + 1)), [x if x <= 3.5 else 3.5 for x in sorted(gap_list)])
    plt.plot(list(range(1, len(gap_list) + 1)), [RED_FLAG for _ in gap_list], color='r')
    plt.xlabel('sorted sample')
    plt.title('gap')
    plt.show()

    bad = np.sum([1 if x > RED_FLAG else 0 for x in gap_list])
    print('%s/%s, %s%%' % (bad, len(gap_list), np.round(bad / len(gap_list) * 100)))


def redraw(threshold, sample_list=()):
    if len(sample_list) == 0:
        sample_list = range(1, 432 + 1)
    for sample_id in sample_list:
        if os.path.exists('train/data/losses_sample%s.json' % sample_id):
            with open('train/data/losses_sample%s.json' % sample_id) as f:
                losses = json.load(f)
                if np.log(losses[-1]) <= threshold:
                    plt.plot(list(range(1, len(losses) + 1)), [np.round(np.log(x), 2) for x in losses])
                    plt.plot(list(range(1, len(losses) + 1)), [0 for _ in losses], color='r')
                    plt.xlabel('episode')
                    plt.title('gap')
                    plt.savefig('train/figure/gap_sample%s.pdf' % sample_id, dpi=600, format='pdf')
                    plt.savefig('train/figure/gap_sample%s.png' % sample_id, dpi=600, format='png')
                    plt.close()
                    print("redraw: 'train/figure/gap_sample%s.png'" % sample_id)


def retrain():
    retrain_list = []
    for sample_id in retrain_list:
        '''if os.path.exists('train/figure/gap_sample%s.png'%sample_id):
            os.remove('train/figure/gap_sample%s.png'%sample_id)
        if os.path.exists('train/model/model_sample%s.pth'%sample_id):
            os.remove('train/model/model_sample%s.pth'%sample_id)'''

        if os.path.exists('train/data/losses_sample%s.json' % sample_id):
            with open('train/data/losses_sample%s.json' % sample_id) as f:
                arr = json.load(f)
                gap = np.log(arr[-1])

                print('sample %s, gap: %0.2f%%' % (sample_id, gap))


if __name__ == '__main__':
    summary(RED_FLAG=-0.0)
    '''redraw(threshold=-1, sample_list=())'''
    '''retrain()'''
