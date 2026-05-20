try:
    from heuristicsAndBoundsCode.main import *
except ModuleNotFoundError:
    from main import *
import matplotlib.pyplot as plt
from scipy.stats import norm
from scipy.stats import gamma

if __name__ == '__main__':
    group = get_group()

    if os.path.exists('seed/seed_test_500_2.json'):
        with open('seed/seed_test_500_2.json') as f:
            arr = json.load(f)
            seed_list = np.array(arr)

    for i, para in enumerate(group.sample):
        sample_id = i + 1
        model = Model(para)

        D_data = {}
        y_data = {}

        for s in range(len(seed_list)):
            seed = seed_list[s]

            np.random.seed(seed[0])
            if model.D_type == 'gamma':
                D_list = np.round(np.random.gamma(shape=model.k, scale=model.theta, size=model.T)).astype(int)
            else:
                D_list = np.round(np.random.normal(loc=model.mu, scale=model.sigma, size=model.T)).astype(int)
            D_list = np.where(D_list >= 0, D_list, 0)
            np.random.seed(seed[1])
            y_list = np.random.binomial(n=1, p=model.p, size=model.T).astype(int)

            for d in D_list:
                if d in D_data:
                    D_data[d] += 1
                else:
                    D_data[d] = 1

            for y in y_list:
                y = np.round(y, 1)
                if y in y_data:
                    y_data[y] += 1
                else:
                    y_data[y] = 1

        D_data_index = [x for x in range(max(D_data.keys()) + 1)]
        D_data_list = [D_data[x] / (len(seed_list) * model.T) if x in D_data else 0 for x in D_data_index]

        y_data_index = [0, 1]
        y_data_list = [y_data[0] / (len(seed_list) * model.T), y_data[1] / (len(seed_list) * model.T)]

        x_vec = np.linspace(0, max(D_data.keys()), 500)
        y_vec = gamma.pdf(x_vec, model.k, scale=model.theta) if model.D_type == 'gamma' else norm.pdf(x_vec, model.mu,
                                                                                                      model.sigma)

        plt.bar(y_data_index, y_data_list, label='y_sample')
        plt.scatter([0, 1], [1 - model.p, model.p], color='r', marker='x', label='y_pdf')

        plt.bar(D_data_index, D_data_list, label='D_sample')
        plt.plot(x_vec, y_vec, color='r', label='D_pdf')

        plt.xticks(D_data_index, fontsize=(5 if max(D_data.keys()) > 30 else 7) if max(D_data.keys()) > 20 else 9)
        plt.xlabel('value')
        plt.title('prob')
        plt.legend()
        plt.savefig('sample/sample%s.pdf' % sample_id, dpi=600, format='pdf')
        plt.savefig('sample/sample%s.png' % sample_id, dpi=600, format='png')
        plt.close()

        print('sample: %s/%s' % (sample_id, len(group.sample)))
