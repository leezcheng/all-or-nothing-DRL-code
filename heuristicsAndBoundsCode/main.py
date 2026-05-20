import os
import json
import math
import numpy as np
import pandas as pd
from scipy import stats


def log_print(*args, **kwargs):
    print(*args, **kwargs)
    f = open('test/test.log', 'a')
    if len(list(args)) > 0:
        f.write(' '.join([str(i) for i in list(args)]) + '\n')
    else:
        f.write('\n')
    f.close()


class Para:
    def __init__(self, _para):
        self.D_type = None
        self.L = None
        self.T = None
        self.alpha = None
        self.mu = None
        self.sigma = None
        self.k = None
        self.theta = None
        self.b = None
        self.h = None
        self.p = None
        self.c = None
        self.SL = None
        self.bound = None
        if _para:
            self.__dict__ = dict(self.__dict__, **_para)
            self.SL = self._calc_SL()
            self.bound = self._calc_bound()

    def _calc_bound(self):
        L = self.L
        T = self.T
        p = self.p
        confidence = 0.99
        if self.D_type == 'gamma':
            CI = stats.gamma.interval(confidence, self.k, scale=self.theta)
        else:
            CI = stats.norm.interval(confidence, loc=self.mu, scale=self.sigma)
        D_lb = max(math.floor(CI[0]), 0)
        D_ub = math.ceil(CI[1])
        Q_ub = math.ceil((1 + L) * D_ub / p)
        bound = {}
        bound['D'] = [D_lb, D_ub]
        bound['qt'] = [0, Q_ub]
        bound['It'] = [-T * D_ub * 2, T * D_ub * 2]
        return bound

    def _calc_SL(self):
        L = self.L
        mu = self.mu
        sigma = self.sigma
        p = self.p
        rho = math.sqrt((1 - p) / self.p)
        k = stats.norm.ppf(self.b / (self.b + self.h), 0, 1)
        SL = (L + 1) * mu + k * math.sqrt(
            (L + 1) * sigma ** 2 + max(L, 1) * rho ** 2 / (1 - rho ** 2) * (mu ** 2 + sigma ** 2))
        # SL = round(SL)
        if self.D_type == 'gamma':
            sigma_Q = np.sqrt(sigma ** 2 + (1 - p) * mu)
            bias = sigma_Q * stats.norm.pdf(-mu / sigma_Q, 0, 1) - mu * stats.norm.cdf(-mu / sigma_Q, 0, 1) 
            SL = SL - bias
        return SL

    def __str__(self):
        return str(self.__dict__)


class Qt_BASE:
    def __init__(self, _para):
        self.p = _para.p
        self.SL = _para.SL

    def test(self, It, q_vector):
        obj1 = self.SL - It - np.sum(q_vector)
        obj1 = obj1 if obj1 >= 0 else 0
        obj = obj1
        return obj

class Qt_LIR:
    def __init__(self, _para):
        self.p = _para.p
        self.SL = _para.SL

    def test(self, It, q_vector):
        obj1 = self.SL - It - np.sum(q_vector) * self.p
        obj1 = obj1 if obj1 >= 0 else 0
        # obj = round(1.0 * obj1)
        obj = obj1
        return obj


class Qt_WNH:
    def __init__(self, _para):
        super(Qt_WNH, self).__init__()
        self.L = _para.L
        self.p = _para.p
        self.SL = _para.SL
        self.Y = self._calc_Y()
        self.P = self._calc_P()

    def test(self, It, q_vector):
        obj1 = self.SL - It
        obj2 = -q_vector @ self.Y
        obj = obj1 + obj2
        qt = np.where(obj >= 0, obj, 0) @ self.P.T
        # qt = qt.astype(int)
        return np.squeeze(qt)

    def _calc_Y(self):
        L = self.L
        _obj = [[0], [1]]
        for i in range(1, L - 1):
            obj = []
            for x in _obj:
                for y in [0, 1]:
                    obj += [[y] + x]
            _obj = obj
        return np.array(_obj).T

    def _calc_P(self):
        p = self.p
        Y = self.Y
        L = self.L
        sum_Y = np.ones((1, L - 1)) @ Y
        P = [[p ** y * (1 - p) ** (L - 1 - y) for y in sum_Y[0]]]
        return np.array(P)


class Model(Para):
    def __init__(self, _para):
        para = _para.copy()
        if _para['D_type'] == 'norm':
            para['mu'], para['sigma'] = para['D_para']
            del para['D_para']
        elif _para['D_type'] == 'gamma':
            k, theta = para['D_para']
            para['k'], para['theta'] = k, theta
            para['mu'], para['sigma'] = np.round((k * theta, (k * theta ** 2) ** 0.5), 15)
            del para['D_para']
        super(Model, self).__init__(para)
        self.I0 = 0
        self.q_vector = np.zeros(self.L).astype(int)

    def test(self, qt, **kwargs):
        T = self.T
        p = self.p

        It = kwargs['It']
        q_vector = kwargs['q_vector']
        seed = kwargs['seed']
        kwargs['para'] = self

        np.random.seed(seed[0])
        if self.D_type == 'gamma':
            D_list = np.random.gamma(shape=self.k, scale=self.theta, size=T)
        else:
            D_list = np.random.normal(loc=self.mu, scale=self.sigma, size=T)
        # D_list = np.round(D_list).astype(int)
        D_list = np.where(D_list >= 0, D_list, 0)
        np.random.seed(seed[1])
        y_list = np.random.binomial(n=1, p=p, size=T)
        # y_list = y_list.astype(int)

        total_cost = 0

        for i in range(T):
            y = y_list[i]
            Dt = D_list[i]

            It = It + q_vector[0] * y
            # It = int(It + q_vector[0] * y)
            qt_I = qt.test(It, q_vector[1:])
            qt_I = np.squeeze(qt_I)
            # qt_I = int(np.squeeze(qt_I))

            It = It - Dt
            # It = int(It - Dt)

            cost = self.alpha ** i * (self.c * q_vector[0] * y + self.h * max(It, 0) + self.b * max(-It, 0))

            q_vector = np.append(q_vector[1:], [qt_I])
            # q_vector = q_vector.astype(int)

            total_cost += cost

        total_cost = np.round(total_cost, 2)

        return total_cost

    def batch_test(self, test_model, seed_list, N=10, sample_id=-1):
        cfg = {'It': self.I0, 'q_vector': self.q_vector}
        cost = [[] for _ in range(len(test_model))]
        qt_list = [Qt(self) for Qt in test_model]
        try:
            for i, qt in enumerate(qt_list):
                if qt.__class__.__name__ == 'Qt_DRL':
                    qt_list[i] = qt.load_pth(sample_id)
            for i in range(N):
                cfg['seed'] = seed_list[i]
                for m, qt in enumerate(qt_list):
                    test_cost = self.test(qt, **cfg)
                    cost[m].append(test_cost)
        except Exception as e:
            cost = None
        return cost

    def __str__(self):
        return str(self.__dict__)


class Group:
    def __init__(self, _para):
        self.D_type = None
        self.L = None
        self.T = None
        self.p = None  # change the line position will influence the sample order
        self.b = None  # change the line position will influence the sample order
        self.h = None
        self.c = None
        self.D_para = None
        self.alpha = None

        self.bbh = None
        self.sample = None
        self.keys = None
        if _para:
            self.__dict__ = dict(self.__dict__, **_para)
            self.b = self._calc_b()
            self.sample, self.keys = self._calc_sample()

    def sample_test(self, test_model, N=10, seed_file='seed/seed_test_100_2.json'):
        model_name = [x.__name__ for x in test_model]
        sample_cost = []
        sample_min = []
        sample_max = []
        sample_rank = []
        sample_std = []
        seed_list_arr = None
        if os.path.exists(seed_file):
            with open(seed_file) as f:
                arr = json.load(f)
                seed_list_arr = np.array(arr)
        else:
            print('NO SEED FILE, USE RANDOM SEED!\n' * 4)
        bad_list = []
        cost_list = []
        for i, para in enumerate(self.sample):
            model = Model(para)
            seed_list = seed_list_arr
            log_print('test: %s/%s, N: %s, seed: %s, para: %s' % (
                i + 1, len(self.sample), N, 'json' if seed_list is not None else None, model))
            cost = model.batch_test(test_model, seed_list, N=N, sample_id=i + 1)

            if cost is None:
                bad_list.append(i + 1)
                continue
            else:
                cost_list.append(np.array(cost).tolist())
            cost_avg = np.round([np.mean(x) for x in cost], 2)
            cost_min = np.round([np.min(x) for x in cost], 2)
            cost_max = np.round([np.max(x) for x in cost], 2)
            cost_std = np.round([np.std(x, ddof=1) for x in cost], 2)  # sample std, divided by size-1
            for m, model in enumerate(test_model):
                log_print('model: %s, N: %s, avg_cost: %s, std: %s' % (model.__name__, N, cost_avg[m], cost_std[m]))

            sample_cost.append(cost_avg)
            sample_min.append(cost_min)
            sample_max.append(cost_max)
            sample_std.append(cost_std)

            cost_min_by_col = cost_avg[
                np.argwhere(np.array(model_name) == ('Qt_DRL' if 'Qt_DRL' in model_name else 'Qt_WNH'))]
            sample_rank.append([np.mean(x / cost_min_by_col - 1) for x in cost_avg])
            if not os.path.exists('test/test.stop'):
                exit(-1)

        print('bad_list:', bad_list)
        f = open('test/cost_list.json', 'w')
        json.dump(cost_list, f)
        f.close()

        self._data_proc(model_name, sample_cost, sample_min, sample_max, sample_rank, sample_std, N)

    def _data_proc(self, model_name, sample_cost, sample_min, sample_max, sample_rank, sample_std, N):
        cost_avg = np.array(sample_cost).mean(axis=0)
        cost_avg = np.round(cost_avg, 2)
        cost_min = np.array(sample_min).mean(axis=0)
        cost_min = np.round(cost_min, 2)
        cost_max = np.array(sample_max).mean(axis=0)
        cost_max = np.round(cost_max, 2)
        cost_rank = [np.array(x) for x in sample_rank]
        cost_rank_avg = np.array(cost_rank).mean(axis=0)

        std_avg = np.array(sample_std).mean(axis=0)
        std_avg = np.round(std_avg, 2)

        index = list(range(1, len(sample_cost) + 1))
        log_print('test: %s, sample_size: %s' % (model_name, len(index)))

        sample_compare = [list(self.sample[i].values()) + x.tolist() + [np.argmin(x)] for i, x in enumerate(cost_rank)]

        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)

        self._show_table(
            df=pd.DataFrame(
                np.array([cost_avg, cost_min, cost_max, std_avg,
                          np.array(list(map(lambda x: format(x, '.2%'), np.squeeze(cost_rank_avg))))]),
                index=['Cost', 'Min', 'Max', 'Std', 'Cost Gap'], columns=model_name),
            title='Table 1-1: Comparison',
            file_name='1-1_comparison'
        )

        self._show_table(
            df=pd.DataFrame(self.sample, index=index, columns=self.keys),
            title='Table 1-2: Samples',
            file_name='1-2_samples'
        )

        self._show_table(
            df=pd.DataFrame([x[:-1] + [model_name[int(x[-1])]] for x in sample_compare], index=index,
                            columns=self.keys + model_name + ['MIN']),
            title='Table 1-3: Samples with Average Cost Gap',
            file_name='1-3_samples_with_cost_gap'
        )

        self._show_table(
            df=pd.DataFrame(sample_cost + [cost_avg], index=index + ['AVG'], columns=model_name),
            title='Table 2: Average Cost with N=%s' % N,
            file_name='2_cost'
        )

        self._show_table(
            df=pd.DataFrame(cost_rank + [cost_rank_avg], index=index + ['AVG'], columns=model_name).applymap(
                lambda x: format(x, '.2%')),
            title='Table 3: Average Cost Gap with N=%s' % N,
            file_name='3_cost_gap'
        )

        self._show_table(
            df=pd.DataFrame(sample_std + [std_avg], index=index + ['AVG'], columns=model_name),
            title='Table 4: Average Std with N=%s' % N,
            file_name='4_std'
        )

    def _show_table(self, df, title, file_name):
        log_print()
        log_print(title)
        df.to_csv('table/%s.csv' % file_name)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.max_rows', None)
        pd.set_option('max_colwidth', 200)
        log_print(df)

    def _calc_b(self):
        b = self.b
        if (not self.b) and self.bbh:
            b = 1 / (1 / np.array(self.bbh) - 1) * self.h
            b = np.round(b, 4).tolist()
        self.bbh = None
        return b

    def _calc_sample(self):
        _obj = []
        _keys = []
        for key in self.__dict__:
            if self.__dict__[key]:
                _keys.append(key)
        for key in _keys:
            item = self.__dict__[key]
            if not isinstance(item, list):
                item = [item]
            else:
                item = item
            if len(_obj) == 0:
                _obj = [[x] for x in item]
            else:
                obj = []
                for y in _obj:
                    for x in item:
                        obj += [y + [x]]
                _obj = obj
        _obj = [dict(zip(_keys, x)) for x in _obj]
        log_print('para: %s %s, sample_size: %s' % (len(_keys), _keys, len(_obj)))
        return _obj, _keys

    def __add__(self, x):
        if isinstance(x, Group) and self.keys == x.keys:
            self.sample.extend(x.sample)
        return self


def get_group():
    para = {'L': [2, 5],
            'bbh': [0.85, 0.9, 0.95],
            'h': 1,
            'p': [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95],
            'c': 2,
            'alpha': 0.99,
            'T': [50, 100]}

    para_norm = {'D_type': 'norm',
                 'D_para': [(10, 2), (10, 5)]}  # (mu, sigma)

    para_gamma = {'D_type': 'gamma',
                  'D_para': [(6.25, 1.6), (3.125, 3.2)]}  # (k,theta)

    f = open('test/test.log', 'w')
    f.close()
    f = open('test/test.stop', 'w')
    f.write('delete this file if you want to interrupt the process')
    f.close()

    group = Group(para | para_norm) + Group(para | para_gamma)

    return group


if __name__ == '__main__':
    group = get_group()
    group.sample_test(test_model=[Qt_LIR, Qt_WNH],
                      N=100,
                      seed_file='seed/seed_test_100_2.json')  # seed_test_100_2.json
