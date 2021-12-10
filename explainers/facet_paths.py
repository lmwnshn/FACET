from explainers.explainer import Explainer
import numpy as np

import networkx as nx
from networkx.algorithms.approximation import clique

from utilities.metrics import dist_euclidean
from utilities.metrics import dist_features_changed

import matplotlib.pyplot as plt
from sklearn import tree


class FACET(Explainer):
    def __init__(self, model, hyperparameters=None):
        self.model = model
        self.parse_hyperparameters(hyperparameters)
        self.build_graph()

    def build_graph(self):
        rf_detector = self.model.detectors[0]
        adjacency = self.compute_adjacency(rf_detector)
        adjacency = np.floor(adjacency)  # consider only fully disjoint trees for merging

        # create a graph from the adjacency matrix using networkx
        self.G = nx.Graph(adjacency)

        # identify the largest set of trees which are fully disjoint in the features they use this is done by finding the largest complete (i.e. fully connectected) subgraph
        # returns a set of node indices representing trees in the forest
        self.fully_disjoint_trees = list(clique.max_clique(self.G))
        n_majority = (int)(np.floor(rf_detector.ntrees / 2) + 1)
        self.trees_to_explain = self.fully_disjoint_trees[:n_majority]

    def explain(self, x, y):
        '''
        Parameters
        ----------
        x               : an array of samples, dimensions (nsamples, nfeatures)
        y               : an array of labels which correspond to the labels, (nsamples, )

        Returns
        -------
        xprime : an array of contrastive examples with dimensions (nsamples, nfeatures)
        '''
        # TODO implement, temporarilty returning a copy of the data
        xprime = x.copy()  # an array for the constructed contrastive examples
        preds = self.model.predict(xprime)
        failed_explanation = (preds == y)
        xprime[failed_explanation] = np.tile(np.inf, x.shape[1])
        return xprime

    def compute_adjacency(self, rf_detector):
        trees = rf_detector.model.estimators_
        ntrees = len(trees)
        self.build_paths(trees)

        # Build matrix for tree subset similarity using jaccard index
        adjacency = np.zeros(shape=(ntrees, ntrees))

        possible_merges = [[{} for _ in range(ntrees)] for _ in range(ntrees)]
        all_stats = []

        for i in range(ntrees):
            for k in range(ntrees):
                t1 = trees[i]
                t2 = trees[k]

                f1 = t1.feature_importances_
                f2 = t2.feature_importances_

                shared_features = (f1 > 0) & (f2 > 0)

                # if shared_features.sum() == 0:
                #     adjacency[i][k] = 1
                #     adjacency[k][i] = 1

                is_resolveable, t1_t2_merges, stats = self.check_resolveable(i, k, shared_features)
                if is_resolveable:
                    adjacency[i][k] = 1
                    adjacency[k][i] = 1
                if(i != k):
                    possible_merges[i][k] = t1_t2_merges
                    all_stats.append(stats)
                else:
                    all_stats.append(np.array([0, 0, 0]))

        np.fill_diagonal(adjacency, 0)  # remove self edges
        n_mergeable_paths, n_unmergeable_paths, n_merges = self.merge_stats(possible_merges)
        all_stats = np.vstack(all_stats)
        n_valid_pairs = all_stats[:, 0:1].sum()
        n_mergeable_pairs = all_stats[:, 1:2].sum()
        n_unmergeable_pairs = all_stats[:, 2:3].sum()

        return adjacency

    def build_paths(self, trees):
        ntrees = len(trees)
        all_paths = [[] for _ in range(ntrees)]
        for i in range(ntrees):
            all_paths[i] = self.__in_order_path(t=trees[i], built_paths=[])
        self.all_paths = all_paths

    def merge_stats(self, possible_merges):
        n_mergeable_paths = 0
        n_unmergeable_paths = 0
        n_merges = 0

        ntrees = len(possible_merges)
        for i in range(ntrees):
            for k in range(ntrees):
                for p1_id, merge_paths in possible_merges[i][k].items():
                    n_merges += len(merge_paths)
                    if len(merge_paths) == 0:
                        n_unmergeable_paths += 1
                    else:
                        n_mergeable_paths += 1

        return n_mergeable_paths, n_unmergeable_paths, n_merges

    def check_resolveable(self, i, k, shared_features):

        nfeatures = len(shared_features)
        t1_paths = self.all_paths[i]
        t2_paths = self.all_paths[k]

        mergeable_paths = {}
        n_path_combos = 0
        n_mergable_combos = 0
        n_unmergable_combos = 0

        # check that each path in t1 can be sythesized with at least one path in t2
        all_sythesizeable = True
        total_paths = len(t1_paths)
        n_collisions = 0
        n_unresolveable_collisions = 0
        for p1 in t1_paths:
            one_sythesizeable = False
            p1_collision = False
            n1 = p1[-1:, 0:1][0][0]
            mergeable_paths[n1] = []
            for p2 in t2_paths:
                n2 = p2[-1:, 0:1][0][0]
                if self.same_outcome(p1, p2):
                    n_path_combos += 1
                    feature_resolveable = np.array([False] * nfeatures)
                    for fi in range(nfeatures):  # feature i
                        if self.share_feature(p1, p2, fi):
                            feature_resolveable[fi] = self.is_resolveable(p1, p2, fi)
                            p1_collision = True
                        else:
                            feature_resolveable[fi] = True
                    path_resolveable = feature_resolveable.all()
                    if path_resolveable:
                        mergeable_paths[n1].append(n2)
                        one_sythesizeable = True
                        n_mergable_combos += 1
                    else:
                        n_unmergable_combos += 1

            # record statistics
            if p1_collision:
                n_collisions += 1
            if not one_sythesizeable:
                all_sythesizeable = False
                n_unresolveable_collisions += 1

        # print("total {}, collisions: {}, unresolveable: {}".format(total_paths, n_collisions, n_unresolveable_collisions))

        stats = np.array([n_path_combos, n_mergable_combos, n_unmergable_combos])

        return all_sythesizeable, mergeable_paths, stats

    def share_feature(self, p1, p2, fi):
        '''
        Returns true if the two paths both use feature_i in at least one node, false otherwise.

        Parameters
        ----------
        p1, p2: array results from __in_order_path
        fi: int index of feature i
        '''
        p1_features = p1[:, 1:2]
        p2_features = p2[:, 1:2]

        return (fi in p1_features) and (fi in p2_features)

        # if the feature is not shared between trees there can be no collision
        if not shared_features[feature_i]:
            return False
        else:
            # check if both paths lead to the counterfactual class and
            # use the collision feature in at least one of their nodes
            consider_p1 = self.consider_path(p1, feature_i, counter_class)
            consider_p2 = self.consider_path(p2, feature_i, counter_class)
            return (consider_p1 and consider_p2)

    def has_collision(self, p1, p2, shared_features, feature_i, counter_class):
        '''
        Returns true if the two paths have a collision, false otherwise. A collision occurs when two paths lead to the same type of leaf node and share at least one feature in their critical
        '''
        # if the feature is not shared between trees there can be no collision
        if not shared_features[feature_i]:
            return False
        else:
            # check if both paths lead to the counterfactual class and
            # use the collision feature in at least one of their nodes
            consider_p1 = self.consider_path(p1, feature_i, counter_class)
            consider_p2 = self.consider_path(p2, feature_i, counter_class)
            return (consider_p1 and consider_p2)

    def is_resolveable(self, p1, p2, feature_i):
        '''
        Find the nodes in p1 and p2 which condition feature_i and check that they don't have conflicting conditions
        For two nodes n1 and n2 which condition feature i n1: x[i] <> a, n2: x[i] <> b, assuming a < b. Return false if the unresolveable condition n1: x[i] < a, n2: x[i] > b is found and true otherwise.
        '''
        idx1 = (p1[:, 1:2] == feature_i).squeeze()
        idx2 = (p2[:, 1:2] == feature_i).squeeze()

        all_resolveable = True

        for cond1, thresh1 in p1[idx1, 2:4]:
            for cond2, thresh2 in p2[idx2, 2:4]:
                if thresh1 < thresh2:
                    fails = (cond2 == 1) and (cond1 == 0)
                elif thresh1 == thresh2:
                    fails = (cond1 != cond2)
                elif thresh1 > thresh2:
                    fails = (cond1 == 1) and (cond2 == 0)

                if fails:
                    all_resolveable = False

        return all_resolveable

    def same_outcome(self, p1, p2):
        '''
        Returns true if and only if p1 and p2 lead to leaf nodes of the same class.
        '''
        p1_pred = p1[-1:, -1:][0][0]
        p2_pred = p2[-1:, -1:][0][0]

        return (p1_pred == p2_pred)

    def consider_path(self, p, feature, counter_class=1):
        pred_class = p[-1:, -1:][0][0]
        path_features = p[:, 1:2]
        return (pred_class == counter_class and feature in path_features)

    def save_tree_figs(self, t1, t2, path="C:/Users/Peter/Downloads/"):
        tree.plot_tree(t1)
        plt.savefig(path + "t1.png")
        tree.plot_tree(t2)
        plt.savefig(path + "t2.png")

    def __in_order_path(self, t, built_paths=[], node_id=0, path=[], path_string=""):
        '''
        An algorithm for pre-order binary tree traversal. This walks throuhg the entire tree generating a list of paths from the root node to a leaf
        and recording the final classification of the leaf node for that path. Paths are stored as `p = [f, g, h, i, j]` where each letter reprsents the
        node_id taken in that path, with `f` being the root node and `j` being the leaf node

        Parameters
        ----------
        t           : the decision tree classifier to travers
        built_paths : the return values, a list of tuples (`class_id` = integer class ID, `path=[f, g, h, i, j]`)
        node_id     : the `node_id` to start traversal at, defaults to root node of tree (`node_id=0`)
        path        : the starting path up to by not including the node referenced by `node_id`, defaults to empty
        path_string : a running text explanation of the features and values used to split along the path
        verbose     : when true prints `path_string` during execution, `default=False`

        Returns
        -------
        None : see the output parameter `built_paths`
        '''

        # build list of paths, each path is represented by a list of nodes
        # Each node is reprsented by a tuple. For internal nodes this is
        #     [node_id, feature, cond, threshold]
        # While for leaf nodes this is
        #     [node_id, -1, -1, class_id]
        # Where cond is 0 for (<= )and 1 for (>)

        # process current node
        feature = t.tree_.feature[node_id]
        if feature >= 0:  # this is an internal node
            threshold = t.tree_.threshold[node_id]

            # process left child, conditioned (<=)
            left_path = path.copy()
            left_path.append([node_id, feature, 0, threshold])
            self.__in_order_path(t=t, built_paths=built_paths, node_id=t.tree_.children_left[node_id], path=left_path)

            # process right node, conditioned (>)
            right_path = path.copy()
            right_path.append([node_id, feature, 1, threshold])
            self.__in_order_path(t=t, built_paths=built_paths, node_id=t.tree_.children_right[node_id], path=right_path)

            return built_paths

        else:  # this is a leaf node
            class_id = np.argmax(t.tree_.value[node_id])
            path = path.copy()
            path.append([node_id, -1, -1, class_id])

            # store the completed path and exit
            finished_path = np.array(path)
            built_paths.append(finished_path)
            return built_paths

    def get_clique(self):
        return self.fully_disjoint_trees

    def parse_hyperparameters(self, hyperparameters):
        self.hyperparameters = hyperparameters

        # distance metric for explanation
        if hyperparameters.get("expl_distance") is None:
            print("No expl_distance function set, using Euclidean")
            self.distance_fn = dist_euclidean
        elif hyperparameters.get("expl_distance") == "Euclidean":
            self.distance_fn = dist_euclidean
        elif hyperparameters.get("expl_distance") == "FeaturesChanged":
            self.distance_fn = dist_features_changed
        else:
            print("Unknown expl_distance function {}, using Euclidean distance".format(hyperparameters.get("expl_distance")))
            self.distance_fn = dist_euclidean

        # greedy sythesis
        if hyperparameters.get("expl_greedy") is None:
            print("No expl_greedy set, defaulting to False")
            self.greedy = False
        else:
            self.greedy = hyperparameters.get("expl_greedy")

        # graph type
        graph_type = hyperparameters.get("facet_graphtype")
        if graph_type is None:
            print("facet_graphtype is not set, defaulting to disjoint")
            self.graph_type = "Disjoint"
        elif graph_type == "Disjoint" or graph_type == "NonDisjoint":
            self.graph_type = graph_type
        else:
            print("unknown facet_graphtype, defaulting to Disjoint")
            self.graph_type = "Disjoint"
