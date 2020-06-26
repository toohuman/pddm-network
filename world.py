import argparse
import networkx as nx
import numpy as np
import random
import sys

from agents.agent import Agent
from utilities import operators
from utilities import preferences
from utilities import results

tests = 100
iteration_limit = 10_000
steady_state_threshold = 100

mode = "symmetric" # ["symmetric" | "asymmetric"]
form_closure = False
evidence_only = False

# Set the graph type

# Erdos-Reyni: random | Watts-Strogatz: small-world.
random_graphs = ["ER", "WS"]
# What we are calling "pathological" cases.
specialist_graphs = ["line", "star"]
clique_graphs = [
    "connected_star", "complete_star",
    "caveman", "complete_caveman"
]
graph_type = "ER"

evidence_rates = [0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
evidence_rate = 1.0
noise_values = [0.0, 1.0, 5.0, 10.0, 20.0, 100.0]
noise_value = 0.0
connectivity_values = [0.0, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0]
connectivity_value = 1.0
# Store the generated comparison error values so that we only need to generate them once.
comparison_errors = []

# Set the initialisation function for agent preferences - option to add additional
# initialisation functions later.
init_preferences = preferences.ignorant_pref_generator

def initialisation(
    num_of_agents, states, network, connectivity, random_instance
):
    """
    This initialisation function runs before any other part of the code. Starting with
    the creation of agents and the initialisation of relevant variables.
    """
    agents = [Agent(init_preferences(states), form_closure) for x in range(num_of_agents)]

    if graph_type == "ER":
        edges = nx.gnp_random_graph(num_of_agents, connectivity, random_instance).edges

    edges = map(lambda x: (agents[x[0]], agents[x[1]]), edges)
    network.update(edges, agents)

    return

def main_loop(
    states: int, network, true_order: [], mode: str, random_instance
):
    """
    The main loop performs various actions in sequence until certain conditions are
    met, or the maximum number of iterations is reached.
    """

    # For each agent, provided that the agent is to receive evidence this iteration
    # according to the current evidence rate, have the agent perform evidential
    # updating.
    reached_convergence = True
    for agent in network.nodes:

        if random_instance.random() <= evidence_rate:

            # Generate a random piece of evidence, selecting from the set of unknown states.
            # evidence = preferences.random_evidence(
            #     states,
            #     true_order,
            #     noise_value,
            #     comparison_errors,
            #     random_instance
            # )
            evidence = preferences.random_evidence(
                states,
                full_true_order,
                noise_value,
                comparison_errors,
                random_instance
            )
            agent.evidential_updating(operators.combine(agent.preferences, evidence))

        reached_convergence &= agent.steady_state(steady_state_threshold)

    if reached_convergence:
        return False
    elif evidence_only:
        return True

    # Consensus formation/belief combination:
    # Agents combine their beliefs at random.

    # Symmetric model: a single pair of agents is selected per iteration
    # and they both adopt the resulting combination.
    if mode == "symmetric":

        try:
            chosen_nodes = random_instance.choice(list(network.edges))
        except IndexError:
            return True

        agent1, agent2 = agents[chosen_nodes[0]], agents[chosen_nodes[1]]

        new_preference = operators.combine(agent1.preferences, agent2.preferences)

        # Symmetric, so both agents adopt the combination preference.
        agent1.update_preferences(new_preference)
        agent2.update_preferences(new_preference)

    # Asymmetric
    # if mode == "asymmetric":
    #   ...

    return True


def main():
    """
    Main function for simulation experiments. Allows us to initiate start-up
    separately from main loop, and to extract results from the main loop at
    request. For example, the main_loop() will return FALSE when agents have
    fully converged according to no. of interactions unchanged. Alternatively,
    data can be processed for each iteration, or each test.
    """

    # Parse the arguments of the program, e.g., agents, states, random init.
    parser = argparse.ArgumentParser(description="Preference-based distributed\
    decision-making in a multi-agent environment.")
    parser.add_argument("states", type=int, help="Produces the preference ordering:\
        1 > ... > n.")
    parser.add_argument("agents", type=int)
    parser.add_argument("-c", "--connectivity", type=float, help="Connectivity of the random graph in [0,1],\
        e.g., probability of an edge between any two nodes.")
    parser.add_argument("-r", "--random", type=bool, help="Random seeding of the RNG.")
    arguments = parser.parse_args()

    if arguments.connectivity is None and connectivity_value is not None:
        arguments.connectivity = connectivity_value

    if arguments.connectivity is None:
        print("Usage error: Connectivity must be specified for node-only graph.")
        sys.exit(0)

    # Create an instance of a RNG that is either seeded for consistency of simulation
    # results, or create using a random seed for further testing.
    random_instance = random.Random()
    random_instance.seed(128) if arguments.random == None else random_instance.seed()

    # Output variables
    directory = "../results/test_results/pddm-network/"
    file_name_params = []

    print("Connectivity:", arguments.connectivity)
    print("Evidence rate:", evidence_rate)
    print("Noise value:", noise_value)

    comparison_errors[:] = []
    if noise_value is not None:
        for state in range(1, arguments.states):
            comparison_errors.append(
                preferences.comparison_error(
                    state / arguments.states,
                    noise_value
                )
            )
    print(comparison_errors)

    # True state of the world
    true_order = []
    true_prefs = []
    opposite_prefs = []

    true_order = [x for x in reversed(range(arguments.states))]
    true_prefs = init_preferences(arguments.states)
    opposite_prefs = init_preferences(arguments.states)
    for i in range(len(true_order) - 1):
        true_prefs.add((true_order[i], true_order[i + 1]))
        opposite_prefs.add((true_order[i + 1],true_order[i]))
    true_prefs = operators.transitive_closure(true_prefs)
    opposite_prefs = operators.transitive_closure(opposite_prefs)

    # Set up the collecting of results
    # preference_results = [
    #     [
    #         [0.0 for x in range(arguments.states)] for y in range(tests)
    #     ] for z in range(iteration_limit + 1)
    # ]
    # preference_results = np.array(preference_results)
    loss_results = [
        [ 0.0 for y in range(tests) ] for z in range(iteration_limit + 1)
    ]
    loss_results = np.array(loss_results)
    steady_state_results = [
        [ 0.0 for y in range(arguments.agents) ] for z in range(tests)
    ]
    steady_state_results = np.array(steady_state_results)

    # Repeat the initialisation and loop for the number of simulation runs required
    max_iteration = 0
    for test in range(tests):

        network = nx.Graph()

        # Initial setup of agents and environment.
        initialisation(
            arguments.agents,
            arguments.states,
            network,
            arguments.connectivity,
            random_instance
        )

        # Pre-loop results based on agent initialisation.
        for agent in network.nodes:
            # prefs = results.identify_preference(agent.preferences)
            # for pref in prefs:
            #     preference_results[0][test][pref] += 1.0 / len(prefs)
            loss_results[0][test] += results.loss(agent.preferences, true_prefs)

        # Main loop of the experiments. Starts at 1 because we have recorded the agents'
        # initial state above, at the "0th" index.
        for iteration in range(1, iteration_limit + 1):
            print("Test #{} - Iteration #{}    ".format(test, iteration), end="\r")
            max_iteration = iteration if iteration > max_iteration else max_iteration
            # While not converged, continue to run the main loop.
            if main_loop(arguments.states, network, true_order, mode, random_instance):
                for a, agent in enumerate(agents):
                    # prefs = results.identify_preference(agent.preferences)
                    # for pref in prefs:
                    #     preference_results[iteration][test][pref] += 1.0 / len(prefs)
                    loss = results.loss(agent.preferences, true_prefs)
                    loss_results[iteration][test] += loss
                    if iteration == iteration_limit:
                        steady_state_results[test][a] = loss

            # If the simulation has converged, end the test.
            else:
                # print("Converged: ", iteration)
                for a, agent in enumerate(agents):
                    # prefs = results.identify_preference(agent.preferences)
                    # for pref in prefs:
                    #     preference_results[iteration][test][pref] += 1.0 / len(prefs)
                    loss = results.loss(agent.preferences, true_prefs)
                    loss_results[iteration][test] += loss
                    steady_state_results[test][a] = loss
                for iter in range(iteration + 1, iteration_limit + 1):
                    # preference_results[iter][test] = np.copy(preference_results[iteration][test])
                    loss_results[iter][test] = np.copy(loss_results[iteration][test])
                # Simulation has converged, so break main loop.
                break
    print()

    # Post-loop results processing (normalisation).
    # preference_results /= len(agents)
    loss_results /= len(agents)

    # Recording of results.
    # First, add parameters in sequence.
    # directory += "{0}/{1}/".format(arguments.agents, arguments.states)
    file_name_params.append("{}_agents".format(arguments.agents))
    file_name_params.append("{}_states".format(arguments.states))
    if arguments.connectivity is not None:
        file_name_params.append("{}_con".format(arguments.connectivity))
    file_name_params.append("{:.3f}_er".format(evidence_rate))
    if noise_value is not None:
        file_name_params.append("{:.3f}_nv".format(noise_value))
    if form_closure is False:
        file_name_params.append("no_cl")
    # Then write the results given the parameters.
    # results.write_to_file(
    #     directory,
    #     "preferences",
    #     file_name_params,
    #     preference_results,
    #     max_iteration,
    #     array_data = True
    # )
    results.write_to_file(
        directory,
        "loss",
        file_name_params,
        loss_results,
        max_iteration
    )
    results.write_to_file(
        directory,
        "steady_state_loss",
        file_name_params,
        steady_state_results,
        tests
    )


if __name__ == "__main__":

    # "standard" | "evidence" | "noise" | "en" | "ce" | "cen"
    test_set = "standard"

    if test_set == "standard":

        # Profiling setup.
        # import cProfile, pstats, io
        # pr = cProfile.Profile()
        # pr.enable()
        # END

        main()

        # Profile post-processing.
        # pr.disable()
        # s = io.StringIO()
        # sortby = 'cumulative'
        # ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        # ps.print_stats()
        # print(s.getvalue())
        # END

    elif test_set == "evidence":

        for er in evidence_rates:
            evidence_rate = er
            main()

    elif test_set == "noise":

        for nv in noise_values:
            noise_value = nv
            main()

    elif test_set == "en":

        for er in evidence_rates:
            evidence_rate = er

            for nv in noise_values:
                noise_value = nv
                main()

    elif test_set == "ce":

        for con in connectivity_values:
            connectivity_value = con

            for er in evidence_rates:
                evidence_rate = er
                main()

    elif test_set == "cen":

        for con in connectivity_values:
            connectivity_value = con

            for er in evidence_rates:
                evidence_rate = er

                for nv in noise_values:
                    noise_value = nv
                    main()