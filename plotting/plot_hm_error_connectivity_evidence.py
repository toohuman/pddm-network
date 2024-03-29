import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import seaborn as sns; sns.set(font_scale=1)

PERC_LOWER = 10
PERC_UPPER = 90

agents_set = [100]
states_set = [10, 20]
evidence_rates = [0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
evidence_strings = ["{:.3f}".format(x) for x in evidence_rates]
noise_values = [0.0, 1.0, 5.0, 10.0, 20.0, 100.0]
connectivity_values = [0.0, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0]
connectivity_strings = ["{:.2f}".format(x) for x in connectivity_values]

result_directory = "../../results/test_results/pddm-network/"

for a, agents in enumerate(agents_set):
    for s, states in enumerate(states_set):
        for n, noise in enumerate(noise_values):

            heatmap_results = np.array([[0.0 for x in connectivity_values] for y in evidence_rates])

            skip = True

            for e, er in enumerate(reversed(evidence_rates)):
                for c, con in enumerate(connectivity_values):

                    file_name_parts = [
                        "error",
                        agents, "agents",
                        states, "states",
                        "{}".format(con),"con",
                        "{:.3f}".format(er), "er",
                        "{:.3f}".format(noise), "nv",
                        "no_cl"
                    ]
                    file_ext = ".csv"
                    file_name = "_".join(map(lambda x: str(x), file_name_parts)) + file_ext

                    steady_state_results = []
                    average_error = 0.0

                    try:
                        with open(result_directory + file_name, "r") as file:
                            for line in file:
                                steady_state_results = line

                        steady_state_results = [float(x) for x in steady_state_results.strip().split(",")]

                        average_error = np.average(steady_state_results)

                        heatmap_results[e][c] = average_error

                        skip = False

                    except FileNotFoundError:
                        # Add obvious missing entry into final results array here
                        heatmap_results[e][c] = 1.0

            if skip:
                continue

            print(heatmap_results)
            cmap = sns.cm.rocket_r
            ax = sns.heatmap(
                heatmap_results,
                # center=0,
                cmap=cmap,
                cbar_kws={"shrink": .75},
                xticklabels=connectivity_strings,
                yticklabels=list(reversed(evidence_strings)),
                vmin=0, vmax=0.5,
                linewidths=.5,
                annot=True,
                annot_kws={"size": 8},
                fmt=".2f",
                square=True
            )
            plt.title("Average error | {} agents, {} states, {} noise".format(agents, states, noise))
            ax.set(xlabel='Connectivity', ylabel='Evidence rate')
            # plt.show()
            plt.savefig("../../results/graphs/pddm-network/hm_error_{}_agents_{}_states_{:.2f}_noise_er_con.pdf".format(agents, states, noise), bbox_inches="tight")
            plt.clf()