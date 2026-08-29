import torch
from train_seasonal import *


class Qt_DRL:
    def __init__(self, para):
        self.para = para
        self.L = para.L
        self.p = para.p
        self.tau = para.tau
        self.T = para.T
        self.Y = self._calc_Y()
        self.P = self._calc_P()
        self.agent = Agent(para, self.P)

    def test(self, It, q_vector, t=0):
        SL = self.para.SL_t(t + self.L)
        s = math.sin(2 * math.pi * t / self.tau)
        c = math.cos(2 * math.pi * t / self.tau)
        tn = t / self.T
        # state: [SL, It, q_2..q_L, sin, cos, t_norm]
        state = torch.from_numpy(
            np.concatenate(([SL, It], q_vector, [s, c, tn]))
        ).float().cpu()
        with torch.no_grad():
            qt = self.agent.act(state)
            qt = qt.cpu().numpy()
        return float(np.round(qt))

    def load_pth(self, sample_id):
        path = 'train/model/model_seasonal_sample%s.pth' % sample_id
        self.agent.load_state_dict(torch.load(path))
        self.agent.eval()
        return self

    def _calc_P(self):
        p = self.p
        Y = self.Y
        L = self.L
        sum_Y = np.ones((1, L - 1)) @ Y
        return np.array([[p ** y * (1 - p) ** (L - 1 - y) for y in sum_Y[0]]])

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


if __name__ == '__main__':
    group = get_group_seasonal()
    group.sample_test(test_model=[Qt_LIR, Qt_WNH, Qt_DRL],
                      N=5,
                      seed_file='seed/seed_test_500_2.json')
