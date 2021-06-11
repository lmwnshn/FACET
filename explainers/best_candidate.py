from explainer import Explainer
from sklearn.ensemble import IsolationForest as skIsolationForest
import numpy as np
from utilities.metrics import euclidean_distance


class BestCandidate(Explainer):
    def __init__(self, model, distance_metric="Euclidean", hyperparameters=None):
        self.model = model

        # select the distance function which corresonds to the provided distance metric
        if distance_metric == "Euclidean":
            self.distance_fn = euclidean_distance
        else:
            print("Unknown distance function {}, using Euclidean distance for explainer".format(distance_metric))
            self.distance_fn = euclidean_distance

    def explain(self, x, y):
        '''
        A method for explaining the samples in x by finding the best candidate contrastive examples generated by the model's detectors

        Parameters
        ----------
        x               : an array of samples, dimensions (nsamples, nfeatures)
        y               : an array of labels which correspond to the labels, (nsamples, )

        Returns
        -------
        best_examples : an array of contrastive examples with dimensions (nsamples, nfeatures). Each of final_examples[i] corresponds to
        the best examples which explains x[i] from those suggested by the detectors
        '''

        # key array dimensions
        nsamples = x.shape[0]
        nfeatures = x.shape[1]
        ndetectors = self.model.ndetectors

        # an array to store the candidates proposed by each detector
        candidate_examples = np.empty(shape=(ndetectors, nsamples, nfeatures))
        # an array to store the distance between each of the candidates and the corresponding sample of x
        candidate_dists = np.empty(shape=(ndetectors, nsamples))
        # an arry to store the models predicted class for each of the candidates
        candidate_preds = np.empty(shape=(ndetectors, nsamples))

        # for each detector
        for i in range(ndetectors):
            print("explaining detector", i)

            # get the candidates for this detector
            det_candidates = self.model.detectors[i].get_candidate_examples(x, y)
            candidate_examples[i] = det_candidates

            # predict and save the class for each candidate using the model
            # temporarilty swapping invalid candiates (rep by [inf, inf, ... , inf]) to zero
            idx_inf = (det_candidates == np.inf).any(axis=1)
            det_candidates[idx_inf] = np.tile(0, (nfeatures,))
            candidate_preds[i] = self.model.predict(det_candidates)
            det_candidates[idx_inf] = np.tile(np.inf, (nfeatures,))

            # if an example doesn't result in a changed class prediciton, set it to inf
            idx_unchaged_class = candidate_preds[i] == y
            candidate_examples[i][idx_unchaged_class] = np.tile(np.inf, (nfeatures,))

            # compute and save the distance for each candidate
            candidate_dists[i] = self.distance_fn(x, det_candidates)

        # find which model suggests the best candidate for each sample
        idx_best_example = np.argmin(candidate_dists, axis=0)

        # select the best examples
        best_examples = np.empty(shape=(nsamples, nfeatures))
        for i in range(x.shape[0]):
            best_examples[i] = candidate_examples[idx_best_example[i]][i]

        return best_examples
