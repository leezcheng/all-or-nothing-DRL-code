import torch

from heuristicsAndBoundsCode.train import *


class Qt_DRL:
    def __init__(self, para):
        self.L = para.L
        self.p = para.p
        self.SL = para.SL
        self.Y = self._calc_Y()
        self.P = self._calc_P()
        self.agent = Agent(para, self.P)

    def test(self, It, q_vector):
        state = torch.from_numpy(np.concatenate(([self.SL, It], q_vector))).float().cpu()
        with torch.no_grad():
            qt = self.agent.act(state)
            qt = qt.cpu().numpy()
        return int(np.round(qt))

    def load_pth(self, sample_id):
        self.agent.load_state_dict(torch.load('train/model/model_sample%s.pth' % sample_id))
        self.agent.eval()
        return self

    def _calc_P(self):
        p = self.p
        Y = self.Y
        L = self.L
        sum_Y = np.ones((1, L - 1)) @ Y
        P = [[p ** y * (1 - p) ** (L - 1 - y) for y in sum_Y[0]]]
        return np.array(P)

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
    group = get_group()
    group.sample_test(test_model=[Qt_LIR, Qt_WNH, Qt_BASE, Qt_DRL],
                      N=500,
                      seed_file='seed/seed_test_500_2.json') # seed_test_100_2.json
