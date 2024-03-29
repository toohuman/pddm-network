from utilities import operators

import numpy as np

class Agent:

    preferences     = None
    evidence        = int
    interactions    = int
    since_change    = int
    form_closure    = False

    def __init__(self, preferences, states, random_instance, rng):

        self.preferences = preferences
        self.evidence = 0
        self.interactions = 0
        self.since_change = 0
        self.random_instance = random_instance
        self.rng = rng


    def steady_state(self, threshold):
        """ Check if agent has reached a steady state. """

        return True if self.since_change >= threshold else False


    @staticmethod
    def combine(prefs1, prefs2):
        """
        A renormalised sum of the two preference sets.
        """

        # Combine the preference sets
        preferences = prefs1 | prefs2

        # Now remove inconsistencies
        consistent_prefs = [(x,y) for x,y in preferences if (y,x) not in preferences]
        preferences = set(consistent_prefs)

        if Agent.form_closure:
            preferences = operators.transitive_closure(preferences)

        return preferences


    def evidential_updating(self, preferences):
        """
        Update the agent's preferences based on the evidence they received.
        Increment the evidence counter.
        """

        # Form the transitive closure of the combined preference
        # prior to updating.
        # if self.form_closure:
        #     operators.transitive_closure(preferences)

        # Track the number of iterations.
        if preferences == self.preferences:
            self.since_change += 1
        else:
            self.since_change = 0

        self.preferences = preferences
        self.evidence += 1


    def update_preferences(self, preferences):
        """
        Update the agent's preferences based on having combined their preferences with
        those of another agent.
        Increment the interaction counter.
        """

        # Form the transitive closure of the combined preference
        # prior to updating.
        # if self.form_closure:
        #     operators.transitive_closure(preferences)

        # Track the number of iterations.
        if preferences == self.preferences:
            self.since_change += 1
        else:
            self.since_change = 0

        self.preferences = preferences
        self.interactions += 1


    def find_evidence(self, states, true_prefs, noise_value, comparison_errors):
        """ Generate a random piece of evidence from the set of unknown preference relations. """

        evidence = set()

        expanded_preferences = self.preferences | {(y,x) for x, y in self.preferences}
        possible_evidence = true_prefs.difference(expanded_preferences)
        # print(possible_evidence)

        try:
            choice = self.random_instance.sample(possible_evidence, 1)[0]
            # print(choice)
        except ValueError:
            return evidence

        if noise_value is None:
            evidence.add(choice)
            return evidence

        difference = abs(choice[0] - choice[1]) - 1
        comp_error = comparison_errors[difference]

        if self.random_instance.random() > comp_error:
            evidence.add(choice)
        else:
            evidence.add((choice[1], choice[0]))

        return evidence


    def random_evidence(self, states, true_order, noise_value, comparison_errors):
        """ Generate a random piece of evidence regardless of current belief. """

        evidence = set()
        shuffled_states = [x for x in range(states)]
        self.random_instance.shuffle(shuffled_states)
        index_i = shuffled_states.pop()
        index_j = shuffled_states.pop()

        pos_i = true_order.index(index_i)
        pos_j = true_order.index(index_j)

        if pos_i < pos_j:
            best_index = index_i
            worst_index = index_j
        else:
            best_index = index_j
            worst_index = index_i

        if noise_value is None:
            evidence.add((best_index, worst_index))
            return evidence

        difference = abs(pos_i - pos_j) - 1
        comp_error = comparison_errors[difference]

        if self.random_instance.random() > comp_error:
            evidence.add((best_index, worst_index))
        else:
            evidence.add((worst_index, best_index))

        return evidence


class Bandwidth(Agent):
    """
    A bandwidth-limited agent that, during pairwise consensus formation, cannot transmit
    the entire length of its preference ordering but instead sends a subset of preferences.
    """

    def __init__(self, preferences, states, random_instance, rng):
        super().__init__(preferences, states, random_instance, rng)


    @staticmethod
    def combine(prefs1, prefs2, random_instance, bandwidth_limit = None):
        """
        A renormalised sum of the two preference sets.
        """

        # Combine the preference sets
        if bandwidth_limit is None:
            preferences = prefs1 | prefs2

            # Now remove inconsistencies
            consistent_prefs = [(x,y) for x,y in preferences if (y,x) not in preferences]
            preferences = set(consistent_prefs)

            if Agent.form_closure:
                preferences = operators.transitive_closure(preferences)

            return preferences
        else:
            set1 = set(random_instance.sample(list(prefs1), bandwidth_limit)) if bandwidth_limit <= len(prefs1) else prefs1
            set2 = set(random_instance.sample(list(prefs2), bandwidth_limit)) if bandwidth_limit <= len(prefs2) else prefs2
            preferences1 = prefs1 | set2
            preferences2 = set1 | prefs2

            # Now remove inconsistencies
            consistent_prefs1 = [(x,y) for x,y in preferences1 if (y,x) not in preferences1]
            preferences1 = set(consistent_prefs1)
            consistent_prefs2 = [(x,y) for x,y in preferences2 if (y,x) not in preferences2]
            preferences2 = set(consistent_prefs2)

            if Agent.form_closure:
                preferences1 = operators.transitive_closure(preferences1)
                preferences2 = operators.transitive_closure(preferences2)

        return (preferences1, preferences2)


class Probabilistic(Agent):
    """
    A probabilistic agent represents its belief by a probability distribution over the set of states.
    By updating their beliefs according to the updating/fusion rules implemented below, a preference
    ordering should be obtainable from their belief.
    """

    def __init__(self, preferences, states, random_instance, rng):
        super().__init__(preferences, states, random_instance, rng)
        # Alongside initialising an uncertain preference set, a probabilistic agent
        # also needs an uncertain probability distribution over the set of states.
        self.belief = [1/states for x in range(states)]


    @staticmethod
    def combine(belief1, belief2):
        """
        Probabilistic updating using the product operator. This combines two (possibly conflicting)
        probability distributions into a single probability distribution.
        """

        # Using the product operator defined in (Lee at al. 2018) and detailed further in (Lawry et al. 2019).
        # When compared with a possibilistic approach, this operator can be adjusted to produce probabilistic
        # rankings of states.
        product_sum = np.dot(belief1, belief2)
        new_belief = [
            (belief1[i] * belief2[i]) /
            product_sum
            for i in range(len(belief1))
        ]
        # print(belief1, belief2, "product = ", product_sum)
        # print(new_belief)

        # Adding a dampening factor to the product rule
        # Jonathan's preferred lambda value: 0.1
        var_lambda = 0.1
        new_belief = [
            (var_lambda * 1/len(new_belief)) + ((1 - var_lambda) * belief)
            for belief in new_belief
        ]
        # print(new_belief)
        # print()

        invalid_belief = np.isnan(np.sum(new_belief))

        if not invalid_belief:
            return new_belief
        else:
            # Operator undefined for two inconsistent beliefs.
            return None


    def evidential_updating(self, belief):
        """
        Update the agent's preferences based on the evidence they received.
        Increment the evidence counter.
        """

        if belief is None:
            self.since_change += 1
            return

        # Track the number of iterations.
        if belief == self.belief:
            self.since_change += 1
        else:
            self.since_change = 0

        # print(belief)

        self.belief = belief
        self.identify_preferences()
        self.evidence += 1


    def update_preferences(self, belief):
        """
        Update the agent's preferences based on having combined their preferences with
        those of another agent.
        Increment the interaction counter.
        """

        if belief is None:
            self.since_change += 1
            return

        # Track the number of iterations.
        if belief == self.belief:
            self.since_change += 1
        else:
            self.since_change = 0

        # print(belief)

        self.belief = belief
        self.identify_preferences()
        self.interactions += 1


    def identify_preferences(self):
        """ Identify the preference ordering from the agent's current belief. """

        # Generate preference set from probability distribution:
        # - compare all elements pairwise
        # - if x > y, add (x, y), elif y > x, add (y, x), else, skip.

        self.preferences = set()

        for x, i in enumerate(self.belief):
            for y, j in enumerate(self.belief):
                if y <= x:
                    continue
                if i > j:
                    self.preferences.add((x,y))
                elif j > i:
                    self.preferences.add((y,x))


    def random_evidence(self, states, true_order, noise_value, quality_values, comparison_errors):
        """ Generate a random piece of evidence regardless of current belief. """

        evidence = [0.0 for x in range(states)]

        random_state = self.random_instance.choice([x for x in range(states)])

        if noise_value is None:
            evidence[random_state] = (((states - 1) * quality_values[random_state]) + 1)/states
            for i, ev in enumerate(evidence):
                if i != random_state:
                    evidence[i] = (1 - quality_values[random_state])/states

            return evidence

        # TODO: Finish noisy evidence

        # Noise model 1: Normal distribution around q_i

        epsilon = self.rng.normal(0, noise_value)
        random_sample = quality_values[random_state] + epsilon
        while (random_sample := quality_values[random_state] + epsilon) < 0 or random_sample > 1:
            epsilon = self.rng.normal(0, noise_value)

        evidence[random_state] = (((states - 1) * (quality_values[random_state] + epsilon)) + 1)/states
        for i, ev in enumerate(evidence):
            if i != random_state:
                evidence[i] = (1 - quality_values[random_state] - epsilon)/states

        # Noise model 2: Binary model of learning the wrong quality value if two states
        # are erroneously compared

        return evidence


class Average(Probabilistic):
    """
    A probabilistic agent represents its belief by a probability distribution over the set of states.
    In contrast to the probabilistc agent, an averaging agent simply adopts an averaging fusion operator
    in order to combine the beliefs of two agents and form a pairwise consensus.
    """

    @staticmethod
    def combine(belief1, belief2):
        """
        Probabilistic updating using the product operator. This combines two (possibly conflicting)
        probability distributions into a single probability distribution.
        """

        # We implement an averaging operator that simply takes the midpoint between the two beliefs
        # in an element-wise manner.
        new_belief = [(belief1[i] + belief2[i]) / 2 for i in range(len(belief1))]

        invalid_belief = np.isnan(np.sum(new_belief))

        if not invalid_belief:
            return new_belief
        else:
            # Operator undefined for two inconsistent beliefs.
            return None
