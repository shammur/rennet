"""
@motjuste
Created: 08-10-2016

Utilities for plotting
"""
from __future__ import division
import matplotlib.pyplot as plt
from math import ceil


# pylint: disable=too-many-arguments, too-many-locals
def plot_multi(x_list,
               func="plot",
               rows=None,
               cols=4,
               perfigsize=(4, 4),
               subplot_titles=None,
               labels=None,
               fig_title=None,
               show=True,
               *args,
               **kwargs):
    if rows is None:
        rows = ceil(len(x_list) / cols)

    fgsz = (perfigsize[0] * cols, perfigsize[1] * rows)
    fig, ax = plt.subplots(rows, cols, figsize=fgsz)

    fig.suptitle(fig_title)

    at = lambda i: divmod(i, cols)
    if rows == 1:
        at = lambda i: i

    if labels is None:
        labels = [None for _ in range(len(x_list))]

    if subplot_titles is None:
        subplot_titles = list(range(len(x_list)))

    for i, sx in enumerate(x_list):
        if func == "plot":
            ax[at(i)].plot(sx, label=labels[i], *args, **kwargs)
        elif func == "pie":
            ax[at(i)].pie(sx, labels=labels[i], *args, **kwargs)
            ax[at(i)].axis("equal")
        elif func == "hist":
            ax[at(i)].hist(sx, *args, **kwargs)
        elif func == "imshow":
            ax[at(i)].imshow(sx, *args, **kwargs)
        else:
            raise ValueError("Unsupported plotting function {}".format(func))

        # set title for subplot
        ax[at(i)].set_title(subplot_titles[i])

    if show:
        plt.show()
# pylint: enable=too-many-arguments, too-many-locals
