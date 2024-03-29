import argparse
import networkx as nx
from networkx.generators.small import sedgewick_maze_graph
import numpy as np
import random
import sys
import time

from agents.agent import *
from utilities import operators
from utilities import preferences
from utilities import results

tests = 100
iteration_limit = 10_000
steady_state_threshold = 100
trajectory_populations = [10, 50, 100]

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

fusion_rates = [1, 5, 10, 20, 30, 40, 50]   # Number of pairs of agents to be selected for belief fusion
fusion_rate = None
evidence_rates = [0.01, 0.05, 0.1, 0.5, 1.0] # [0.01, 0.05, 0.1, 0.5, 1.0]
evidence_rate = 0.01
noise_params = [0.0, 1.0, 2.5, 5.0, 7.5, 10.0, 100.0] # [0.0, 1.0, 2.5, 5.0, 7.5, 10.0, 100.0]
noise_param = 0.01
connectivity_values = [0.0, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0]
connectivity_value = 1.0
# Store the quality values as we only need to generate them once
quality_values = []
# Store the generated comparison error values so that we only need to generate them once.
comparison_errors = []

# Set the type of agent: qualitative or probabilistic
# (Pairwise preferences) Agent | Bandwidth | Probabilistic | Average
prob_agent_types = ["probabilistic", "average"]
agent_type = Probabilistic

print("Agent type:", agent_type.__name__)

if agent_type.__name__.lower() in prob_agent_types:
    noise_params = [0.47, 0.33, 0.21, 0.12, 0.09, 0.07, 0.00]

# Set the initialisation function for agent preferences - option to add additional
# initialisation functions later.
init_preferences = preferences.ignorant_preferences

def initialisation(
    num_of_agents, states, network, connectivity, random_instance, rng
):
    """
    This initialisation function runs before any other part of the code. Starting with
    the creation of agents and the initialisation of relevant variables.
    """
    Agent.form_closure = form_closure
    agents = [agent_type(init_preferences(states), states, random_instance, rng) for x in range(num_of_agents)]

    if graph_type == "ER":
        edges = nx.gnp_random_graph(num_of_agents, connectivity, random_instance).edges

    edges = map(lambda x: (agents[x[0]], agents[x[1]]), edges)
    network.update(edges, agents)

    return

def main_loop(
    states: int, network, true_order: [], true_prefs: [], mode: str, bandwidth_limit: int, random_instance
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
            if agent_type.__name__.lower() in prob_agent_types:
                evidence = agent.random_evidence(
                    states,
                    true_order,
                    noise_param,
                    quality_values,
                    comparison_errors
                )
                agent.evidential_updating(agent_type.combine(agent.belief, evidence))
            elif agent_type.__name__.lower() == "bandwidth":
                evidence = agent.find_evidence(
                    states,
                    true_prefs,
                    noise_param,
                    comparison_errors
                )
                agent.evidential_updating(agent_type.combine(agent.preferences, evidence, random_instance))
            else:
                evidence = agent.find_evidence(
                    states,
                    true_prefs,
                    noise_param,
                    comparison_errors
                )
                agent.evidential_updating(agent_type.combine(agent.preferences, evidence))

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

        network_copy = network.copy()

        if fusion_rate is not None:
            num_of_edges = int(network.number_of_nodes() * (fusion_rate/100))
        else:
            num_of_edges = 1

        for i in range(num_of_edges):
            try:
                agent1, agent2 = random_instance.choice(list(network_copy.edges))
            except IndexError:
                return True

            if agent_type.__name__.lower() in prob_agent_types:
                new_preference = agent_type.combine(agent1.belief, agent2.belief)
            elif agent_type.__name__.lower() == "bandwidth":
                new_preference = agent_type.combine(agent1.preferences, agent2.preferences, random_instance, bandwidth_limit)
            else:
                new_preference = agent_type.combine(agent1.preferences, agent2.preferences)

            if type(new_preference) is tuple:
                agent1.update_preferences(new_preference[0])
                agent2.update_preferences(new_preference[1])
            else:
                # Symmetric, so both agents adopt the combination preference.
                agent1.update_preferences(new_preference)
                agent2.update_preferences(new_preference)

            network_copy.remove_node(agent1)
            network_copy.remove_node(agent2)

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
    rng = np.random.default_rng(128) if arguments.random == None else np.random.default_rng

    # Output variables
    directory = "../results/test_results/pddm-network/"
    if agent_type.__name__.lower() != "agent":
        directory += "{}/".format(agent_type.__name__.lower())
    file_name_params = []

    if fusion_rate is not None:
        print("Fusion rate:", fusion_rate)
    print("Connectivity:", arguments.connectivity)
    print("Evidence rate:", evidence_rate)
    print("Noise value:", noise_param)
    print("Closure:", form_closure)

    # For the probabilistic agent:
    # Set the quality values at uniform intervals i/(n+1) for i = 1, ..., n states.
    quality_values[:] = [round(i/(arguments.states + 1), 5) for i in range(1, arguments.states + 1)]
    print(quality_values)

    bandwidth_limit = None
    if agent_type.__name__.lower() == "bandwidth":
        bandwidth_limit = arguments.states
        print("bandwidth limit:", bandwidth_limit)

    comparison_errors[:] = []
    if noise_param is not None:
        for state in range(1, arguments.states):
            comparison_errors.append(
                preferences.comparison_error(
                    state / arguments.states,
                    noise_param
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
    # print(sorted(true_prefs, reverse=True))

    # Set up the collecting of results
    error_results = np.array([
        [ 0.0 for y in range(tests) ] for z in range(iteration_limit + 1)
    ])
    steady_state_error_results = np.array([
        [ 0.0 for y in range(arguments.agents) ] for z in range(tests)
    ])

    # if agent_type.__name__.lower() in prob_agent_types:
    probability_results = np.array([
        [ [ 0.0 for x in range(arguments.states) ] for y in range(tests) ] for z in range(iteration_limit + 1)
    ])
    steady_state_probability_results = np.array([
        [ [ 0.0 for x in range(arguments.states) ] for y in range(arguments.agents) ] for z in range(tests)
    ])

    preference_results = np.array([
        [ [ 0.0 for x in range(arguments.states - 1) ] for y in range(tests) ] for z in range(iteration_limit + 1)
    ])
    steady_state_preference_results = np.array([
        [ [ 0 for x in range(arguments.states - 1) ] for y in range(arguments.agents) ] for z in range(tests)
    ])

    uncertainty_results = np.array([
        [ 0.0 for y in range(tests) ] for z in range(iteration_limit + 1)
    ])
    steady_state_uncertainty_results = np.array([
        [ 0.0 for y in range(arguments.agents) ] for z in range(tests)
    ])

    process_time_results = [ 0.0 for y in range(tests + 1) ]
    runtime_results = [ 0.0 for y in range(tests + 1) ]

    init_proc_time = time.process_time()
    init_runtime = time.time()

    # Repeat the initialisation and loop for the number of simulation runs required
    max_iteration = 0
    for test in range(tests):

        start_runtime = time.time()
        start_proc_time = time.process_time()

        network = nx.Graph()

        # Initial setup of agents and environment.
        initialisation(
            arguments.agents,
            arguments.states,
            network,
            arguments.connectivity,
            random_instance,
            rng
        )

        # Pre-loop results based on agent initialisation.
        for agent in network.nodes:
            error_results[0][test] += results.error(agent.preferences, true_prefs)
            uncertainty_results[0][test] += results.uncertainty(agent.preferences, true_prefs)

            if agent_type.__name__.lower() in prob_agent_types:
                np.add(probability_results[0][test], agent.belief, out=probability_results[0][test])

        # Main loop of the experiments. Starts at 1 because we have recorded the agents'
        # initial state above, at the "0th" index.
        for iteration in range(1, iteration_limit + 1):
            print("Test #{} - Iteration #{}    ".format(test, iteration), end="\r")
            max_iteration = iteration if iteration > max_iteration else max_iteration
            # While not converged, continue to run the main loop.
            if main_loop(arguments.states, network, true_order, true_prefs, mode, bandwidth_limit, random_instance):
                for a, agent in enumerate(network.nodes):
                    error = results.error(agent.preferences, true_prefs)
                    error_results[iteration][test] += error
                    if agent_type.__name__.lower() in prob_agent_types:
                        np.add(probability_results[iteration][test], agent.belief, out=probability_results[iteration][test])
                        for i in range(arguments.states - 1, 0, -1):
                            if agent.belief[i] > agent.belief[i - 1]:
                                preference_results[iteration][test][arguments.states - 1 - i] += 1
                    uncertainty = results.uncertainty(agent.preferences, true_prefs)
                    uncertainty_results[iteration][test] += uncertainty
                    if iteration == iteration_limit:
                        steady_state_error_results[test][a] = error
                        if agent_type.__name__.lower() in prob_agent_types:
                            steady_state_probability_results[test][a] = agent.belief
                            for i in range(arguments.states - 1, 0, -1):
                                if agent.belief[i] > agent.belief[i - 1]:
                                    steady_state_preference_results[test][a][arguments.states - 1 - i] = 1
                        steady_state_uncertainty_results[test][a] = uncertainty

            # If the simulation has converged, end the test.
            else:
                # print("Converged: ", iteration)
                for a, agent in enumerate(network.nodes):
                    error = results.error(agent.preferences, true_prefs)
                    error_results[iteration][test] += error
                    uncertainty = results.uncertainty(agent.preferences, true_prefs)
                    uncertainty_results[iteration][test] += uncertainty
                    steady_state_error_results[test][a] = error
                    if agent_type.__name__.lower() in prob_agent_types:
                        steady_state_probability_results[test][a] = agent.belief
                        for i in range(arguments.states - 1, 0, -1):
                            if agent.belief[i] > agent.belief[i - 1]:
                                steady_state_preference_results[test][a][arguments.states - 1 - i] = 1
                    steady_state_uncertainty_results[test][a] = uncertainty
                for iter in range(iteration + 1, iteration_limit + 1):
                    error_results[iter][test] = np.copy(error_results[iteration][test])
                    if agent_type.__name__.lower() in prob_agent_types:
                        probability_results[iter][test] = np.copy(probability_results[iteration][test])
                    uncertainty_results[iter][test] = np.copy(uncertainty_results[iteration][test])
                # Simulation has converged, so break main loop.
                break

        process_time_results[test] = time.time() - start_runtime
        runtime_results[test] = time.process_time() - start_proc_time

    print()

    # Timing results
    process_time_results = ["Process time"] + process_time_results
    runtime_results = ["Runtime"] + runtime_results
    process_time_results[-1] =  time.process_time() - init_proc_time
    runtime_results[-1] = time.time() - init_runtime

    # Post-loop results processing (normalisation).
    error_results /= arguments.agents
    if agent_type.__name__.lower() in prob_agent_types:
        probability_results /= arguments.agents
        preference_results /= arguments.agents
    uncertainty_results /= arguments.agents

    # Recording of results. First, add parameters in sequence.

    file_name_params.append("{}a".format(arguments.agents))
    file_name_params.append("{}s".format(arguments.states))

    if graph_type == "ER":
        if arguments.connectivity is not None:
            file_name_params.append("{:.2f}con".format(arguments.connectivity))
    elif graph_type == "WS":
        if arguments.connectivity is not None and arguments.knn is not None:
            file_name_params.append("{}k".format(arguments.knn))
            file_name_params.append("{:.2f}con".format(arguments.connectivity))
    elif graph_type in specialist_graphs + clique_graphs:
        file_name_params.append("{}".format(graph_type))
        if graph_type in clique_graphs:
            file_name_params.append("{}".format(clique_size))

    file_name_params.append("{:.2f}er".format(evidence_rate))
    if noise_param is not None:
        if agent_type.__name__.lower() in prob_agent_types:
            file_name_params.append("{:.2f}nv".format(noise_param))
        else:
            file_name_params.append("{:.1f}nv".format(noise_param))
    if fusion_rate is not None:
        file_name_params.append("{}fr".format(fusion_rate))
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

    if arguments.agents in trajectory_populations:
        results.write_to_file(
            directory,
            "error",
            file_name_params,
            error_results,
            max_iteration
        )

    results.write_to_file(
        directory,
        "steady_state_error",
        file_name_params,
        steady_state_error_results,
        tests
    )

    if agent_type.__name__.lower() in prob_agent_types:
        if arguments.agents in trajectory_populations:
            results.write_to_file(
                directory,
                "probabilities",
                file_name_params,
                probability_results,
                max_iteration,
                array_data=True
            )

        results.write_to_file(
            directory,
            "steady_state_probabilities",
            file_name_params,
            steady_state_probability_results,
            tests,
            array_data=True
        )

        if arguments.agents in trajectory_populations:
            results.write_to_file(
                directory,
                "preferences",
                file_name_params,
                preference_results,
                max_iteration,
                array_data=True
            )

        results.write_to_file(
            directory,
            "steady_state_preferences",
            file_name_params,
            steady_state_preference_results,
            tests,
            array_data=True
        )

    if arguments.agents in trajectory_populations:
        results.write_to_file(
            directory,
            "uncertainty",
            file_name_params,
            uncertainty_results,
            max_iteration
        )

    results.write_to_file(
        directory,
        "steady_state_uncertainty",
        file_name_params,
        steady_state_uncertainty_results,
        tests
    )

    results.write_to_file(
        directory,
        "timings",
        file_name_params,
        [process_time_results, runtime_results],
        2
    )


if __name__ == "__main__":

    # "standard" | "evidence" | "noise" | "en" | "ce" | "cen"
    test_set = "noise"

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

        for nv in noise_params:
            noise_param = nv
            main()

    elif test_set == "en":

        for er in evidence_rates:
            evidence_rate = er

            for nv in noise_params:
                noise_param = nv
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

                for nv in noise_params:
                    noise_param = nv
                    main()