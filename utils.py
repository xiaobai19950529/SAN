from __future__ import absolute_import, division, print_function, unicode_literals

import tensorflow as tf

import data_loader as dl
import numpy as np
import matplotlib.pyplot as plt


class CustomSchedule(tf.keras.optimizers.schedules.LearningRateSchedule):
    def __init__(self, d_model, lr_exp=1, warmup_steps=4000):
        super(CustomSchedule, self).__init__()

        self.d_model = d_model
        self.d_model = tf.cast(self.d_model, tf.float32)

        self.lr_exp = lr_exp
        self.warmup_steps = warmup_steps

    def __call__(self, step):
        arg1 = tf.math.rsqrt(step)
        arg2 = step * (self.warmup_steps ** -1.5)

        return tf.math.rsqrt(self.d_model) * tf.math.minimum(arg1, arg2) * self.lr_exp


def load_dataset(dataset='taxi', load_saved_data=False, batch_size=64, num_weeks_hist=0, num_days_hist=7,
                 num_intervals_hist=3, num_intervals_currday=1, num_intervals_before_predict=1, local_block_len=3):
    data_loader = dl.data_loader(dataset)
    flow_inputs_hist, transition_inputs_hist, ex_inputs_hist, flow_inputs_currday, transition_inputs_currday, \
    ex_inputs_currday, ys_transitions, ys = \
        data_loader.generate_data('train',
                                  num_weeks_hist,
                                  num_days_hist,
                                  num_intervals_hist,
                                  num_intervals_currday,
                                  num_intervals_before_predict,
                                  local_block_len,
                                  load_saved_data)

    dataset = tf.data.Dataset.from_tensor_slices(
        (
            {
                "flow_hist": flow_inputs_hist,
                "trans_hist": transition_inputs_hist,
                "ex_hist": ex_inputs_hist,
                "flow_currday": flow_inputs_currday,
                "trans_currday": transition_inputs_currday,
                "ex_currday": ex_inputs_currday
            },
            {
                "ys_transitions": ys_transitions,
                "ys": ys
            }
        )
    )

    train_size = int(0.8 * flow_inputs_hist.shape[0])

    dataset = dataset.cache()
    dataset = dataset.shuffle(flow_inputs_hist.shape[0])
    train_set = dataset.take(train_size)
    val_set = dataset.skip(train_size)
    train_set = train_set.batch(batch_size).prefetch(tf.data.experimental.AUTOTUNE)
    val_set = val_set.batch(batch_size).prefetch(tf.data.experimental.AUTOTUNE)

    flow_inputs_hist, transition_inputs_hist, ex_inputs_hist, flow_inputs_currday, transition_inputs_currday, \
    ex_inputs_currday, ys_transitions, ys = \
        data_loader.generate_data('test',
                                  num_weeks_hist,
                                  num_days_hist,
                                  num_intervals_hist,
                                  num_intervals_currday,
                                  num_intervals_before_predict,
                                  local_block_len,
                                  load_saved_data)

    test_set = tf.data.Dataset.from_tensor_slices(
        (
            {
                "flow_hist": flow_inputs_hist,
                "trans_hist": transition_inputs_hist,
                "ex_hist": ex_inputs_hist,
                "flow_currday": flow_inputs_currday,
                "trans_currday": transition_inputs_currday,
                "ex_currday": ex_inputs_currday
            },
            {
                "ys_transitions": ys_transitions,
                "ys": ys
            }
        )
    )

    test_set = test_set.cache()
    test_set = test_set.batch(batch_size).prefetch(tf.data.experimental.AUTOTUNE)

    return train_set, val_set, test_set


class early_stop_helper():
    def __init__(self, patience, test_period, start_epoch, thres, in_weight=0.4, out_weight=0.6):
        assert patience % test_period == 0
        self.patience = patience / test_period
        self.start_epoch = start_epoch
        self.thres = thres
        self.count = 0
        self.best_rmse = 2000.0
        self.best_in = 2000.0
        self.best_out = 2000.0
        self.best_epoch = -1
        self.in_weight = in_weight
        self.out_weight = out_weight

    def check(self, in_rmse, out_rmse, epoch):

        if epoch < self.start_epoch:
            return False

        if (self.in_weight * in_rmse + self.out_weight * out_rmse) > self.best_rmse * self.thres:
            self.count += 1
        else:
            self.count = 0
            self.best_rmse = self.in_weight * in_rmse + self.out_weight * out_rmse
            self.best_in = in_rmse
            self.best_out = out_rmse
            self.best_epoch = epoch + 1

        if self.count >= self.patience:
            return True
        else:
            return False

    def get_bestepoch(self):
        return self.best_epoch


def plot_s_attn(trans_mtx):
    fig = plt.figure(figsize=(8, 4))

    trans_mtx = tf.squeeze(trans_mtx[:1, :, :, :], axis=0)
    trans_mtx_in = tf.reduce_mean(trans_mtx[:, :, :2], axis=-1)
    trans_mtx_out = tf.reduce_mean(trans_mtx[:, :, 2:], axis=-1)
    trans_mtx = [trans_mtx_in, trans_mtx_out]

    for slice in range(2):
        ax = fig.add_subplot(1, 2, slice + 1)

        ax.matshow(trans_mtx[slice], cmap='viridis')

        if slice == 0:
            ax.set_xlabel('spatial attention: inflow', fontdict={'fontsize': 16})
        else:
            ax.set_xlabel('spatial attention: outflow', fontdict={'fontsize': 16})

    plt.tight_layout()
    plt.savefig('figures/spatial_attn.png')


def plot_t_attn(attention, layer):
    fig = plt.figure(figsize=(4, 3))

    attention = tf.reduce_mean(attention[layer][:1, :, :, :, :, :], axis=1)
    attention = tf.reduce_mean(attention, axis=1)
    attention = tf.reduce_mean(attention, axis=1)

    ax = fig.add_subplot(1, 1, 1)

    ax.matshow(attention[0][:, :], cmap='viridis')

    fontdict = {'fontsize': 10}

    ax.set_xticks(range(22))
    ax.set_yticks(range(1))

    ax.set_ylim(0.5, -0.5)

    ls = [['day {} - slot {}'.format(j - 7, i) for i in range(3)] for j in range(7)]
    labels = []

    for l in ls:
        labels += l

    labels += ['curr day slot -1']

    ax.set_xticklabels(
        labels,
        fontdict=fontdict, rotation=90)

    # ax.set_yticklabels(['attention'],
    #                    fontdict={'fontsize': 10})

    ax.set_xlabel('temporal attention')

    plt.savefig('figures/temporal_attn.png')


if __name__ == "__main__":
    a, b, c = load_dataset(dataset='taxi', load_saved_data=False, batch_size=64, num_weeks_hist=0, num_days_hist=7,
                           num_intervals_hist=3, num_intervals_currday=1, num_intervals_before_predict=1,
                           local_block_len=3)
