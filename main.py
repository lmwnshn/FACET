import numpy as np
from numpy.core.fromnumeric import var
from heead import HEEAD
import matplotlib.pyplot as plt
from utilities.metrics import coverage
from utilities.metrics import classification_metrics
from utilities.metrics import average_distance
from utilities.tree_tools import compute_jaccard
from dataset import load_data
from dataset import DS_NAMES
from experiments import *
import cProfile
import time


def simple_run(dataset_name, ntrees):
    # Load the dataset
    x, y = load_data(dataset_name)
    xtrain, xtest, ytrain, ytest = train_test_split(x, y, test_size=0.2, shuffle=True, random_state=None)

    # Euclidean, FeaturesChanged
    distance = "Euclidean"
    params = {
        "rf_difference": 0.01,
        "rf_distance": distance,
        "rf_k": 1,
        "rf_ntrees": ntrees,
        "rf_maxdepth": 3,
        "rf_threads": 8,
        "expl_greedy": False,
        "expl_distance": distance,
        "facet_graphtype": "disjoint",
        "facet_offset": 0.001,
        "facet_mode": "exhaustive"
    }

    print(params)

    # Create, train, and predict with the model
    model = HEEAD(detectors=["RandomForest"], aggregator="NoAggregator",
                  explainer="FACETBranchBound", hyperparameters=params)
    model.train(xtrain, ytrain)
    model.prepare()
    preds = model.predict(xtest)

    # measure model performance
    accuracy, precision, recall, f1 = classification_metrics(preds, ytest, verbose=False)
    print("accuracy:", accuracy)
    print("precision:", precision)
    print("recall:", recall)
    print("f1:", f1)

    # anomaly detection performance
    # accuracy, precision, recall, f1 = classification_metrics(preds, ytest, verbose=True)

    # Q-stastic
    # Q, qs = model.detectors[0].compute_qs(xtest, ytest)
    # print("Q-Statistic:", Q)

    # jaccard similarity
    J, jaccards = compute_jaccard(model.detectors[0])
    print("Jaccard Index:", J)

    # generate the explanations
    explain = True
    eval_samples = 20
    if explain:
        if eval_samples is not None:
            xtest = xtest[:eval_samples]
            preds = preds[:eval_samples]

        start = time.time()
        explanations = model.explain(xtest, preds)
        end = time.time()
        runtime = end-start
        print("runtime:", runtime)

        if eval_samples is not None:
            sample_time = runtime / eval_samples
            print("sample_time:", sample_time)

        coverage_ratio = coverage(explanations)
        print("coverage_ratio:", coverage_ratio)
        mean_dist = average_distance(xtest, explanations, distance_metric="Euclidean")
        print("mean_dist:", mean_dist)
        mean_length = average_distance(xtest, explanations, distance_metric="FeaturesChanged")
        print("mean_length", mean_length)


if __name__ == "__main__":
    run_ds = DS_NAMES.copy()
    # run_ds.remove("spambase")
    # compare_methods(run_ds, num_iters=1, explainers=["FACETBranchBound"], eval_samples=20)
    # simple_run("vertebral")
    # for ntrees in [5, 10, 15, 20, 25]:
    # simple_run("vertebral", ntrees)
    # time_cliques(ds_names=["cancer"], ntrees=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
    bb_ntrees(["spambase"], explainer="FACETBranchBound", ntrees=[5, 10, 15, 20], num_iters=1)
