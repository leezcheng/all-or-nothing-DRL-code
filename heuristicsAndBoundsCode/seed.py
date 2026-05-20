import json
import numpy as np
import matplotlib.pyplot as plt


def new_seed():
    seed_list = np.random.choice(range(1000), 1000, replace=False).reshape((500, 2)).tolist()
    with open('seed/seed_test_500_2.json', 'w') as f:
        json.dump(seed_list, f)

    seed_list = np.random.choice(np.array(range(1000)) + 1000, 1000, replace=False).reshape((500, 2)).tolist()
    with open('seed/seed_train_500_2.json', 'w') as f:
        json.dump(seed_list, f)


if __name__ == '__main__':
    pass
