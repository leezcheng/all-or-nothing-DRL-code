import numpy as np

from heuristicsAndBoundsCode.test import *
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
import seaborn as sns
import pandas as pd

if __name__ == '__main__':
    group = get_group()
    model_list = [Model(para) for para in group.sample]

    test_model = [Qt_LIR, Qt_WNH, Qt_DRL]  # [Qt_LIR, Qt_WNH, Qt_DRL]

    for sample_id in [3, 220]:  # 3,220
        model = model_list[sample_id - 1]

        if model.L == 2:
            qt_list = [Qt(model).load_pth(sample_id) if Qt.__name__ == 'Qt_DRL' else Qt(model) for Qt in test_model]
            SL = model.SL

            I_lb, I_ub = (-300, int(np.ceil(SL / 10)) * 10)  # model.bound['It']
            q_lb, q_ub = model.bound['qt']
            q_lb, q_ub = (int(np.floor(q_lb / 10)) * 10, int(np.ceil(q_ub / 10)) * 10)

            action = [[] for _ in test_model]

            for It in range(I_lb, I_ub + 1):
                if It % 10 == 0:
                    print('It:', It)
                for q_vector in range(q_lb, q_ub + 1):
                    for i, qt in enumerate(qt_list):
                        action[i].append(qt.test(It, np.array([q_vector])))

            action = np.array(action)
            action = np.where(action > 0, action, 0)
            aim = (I_ub + 1 - I_lb, q_ub + 1 - q_lb)
            action = [np.array(x).reshape(aim[0], aim[1]) for x in action]

            for i, df in enumerate(action):
                f, ax = plt.subplots(figsize=(8, 7))
                title = qt_list[i].__class__.__name__.split('_')[-1]
                ax.set_title(title)
                with sns.axes_style("white"):
                    sns.heatmap(df[::-1, :], cmap="RdBu_r", annot=False, vmin=np.min(action), vmax=np.max(action))
                plt.xlabel('pipeline order')
                plt.ylabel('on-hand inventory')
                plt.xticks(np.arange(0, q_ub + 1 - q_lb), np.arange(q_lb, q_ub + 1))
                plt.yticks(np.arange(0, I_ub + 1 - I_lb), np.arange(I_lb, I_ub + 1)[::-1])
                ax.xaxis.set_major_locator(MultipleLocator(10))
                ax.yaxis.set_major_locator(MultipleLocator(30))
                plt.savefig('action/sample%s_%s.pdf' % (sample_id, title), dpi=600, format='pdf')
                plt.savefig('action/sample%s_%s.png' % (sample_id, title), dpi=600, format='png')
                plt.show()

            action_delta = [df - action[-1] for df in action[:-1]]
            for i, df in enumerate(action_delta):
                f, ax = plt.subplots(figsize=(8, 7))
                title = qt_list[i].__class__.__name__.split('_')[-1] + ' (increment)'
                ax.set_title(title)
                with sns.axes_style("white"):
                    sns.heatmap(df[::-1, :], cmap="RdBu_r", annot=False, vmin=np.min(action_delta),
                                vmax=np.max(action_delta))
                plt.xlabel('pipeline order')
                plt.ylabel('on-hand inventory')
                plt.xticks(np.arange(0, q_ub + 1 - q_lb), np.arange(q_lb, q_ub + 1))
                plt.yticks(np.arange(0, I_ub + 1 - I_lb), np.arange(I_lb, I_ub + 1)[::-1])
                ax.xaxis.set_major_locator(MultipleLocator(10))
                ax.yaxis.set_major_locator(MultipleLocator(30))
                plt.savefig('action/sample%s_%s.pdf' % (sample_id, title), dpi=600, format='pdf')
                plt.savefig('action/sample%s_%s.png' % (sample_id, title), dpi=600, format='png')
                plt.show()
