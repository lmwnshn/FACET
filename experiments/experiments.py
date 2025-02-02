import json
import os
import random
import re
import time

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from dataset import load_data, rescale_discrete, rescale_numeric
from manager import MethodManager
from utilities.metrics import average_distance, classification_metrics, percent_valid

TUNED_FACET_SD = {
    "adult": 0.1,
    "cancer": 0.1,
    "compas": 0.1,
    "credit": 0.2,
    "glass": 0.005,
    "magic": 0.001,
    "spambase": 0.01,
    "vertebral": 0.05,
    "loans": 0.05,  # TODO tune on loans
    "loans": 0.05,  # TODO tune on loans
}

# generated as the average minimum point to point distance
# see initial_radius_heuristic
AVG_NN_DIST = {
    "cancer": 0.3290,
    "glass": 0.1516,
    "magic": 0.07162,
    "spambase": 0.1061,
    "vertebral": 0.0992
}
# avgerage dataset distance to nearest point of the oppisite class
AVG_CF_NN_DIST = {
    "cancer": 0.5850,
    "glass": 0.2710,
    "magic": 0.1153,
    "spambase": 0.2594,
    "vertebral": 0.1640
}
# TUNED_FACET_RADII = AVG_NN_DIST

FACET_TUNED_M = {
    "adult": 16,
    "cancer": 16,
    "compas": 16,
    "credit": 16,
    "glass": 16,
    "magic": 16,
    "spambase": 16,
    "vertebral": 16,
    "loans": 16,
}

FACET_TUNED_NRECTS = {
    "adult": 50_000,
    "cancer": 20_000,
    "compas": 20_000,
    "credit": 50_000,
    "glass": 20_000,
    "magic": 20_000,
    "spambase": 20_000,
    "vertebral": 20_000,
    "loans": 20_000,
}


MACE_DEFAULT_PARAMS = {
    "mace_maxtime": 300,
    "mace_epsilon": 1e-7,
    "mace_verbose": False
}

OCEAN_DEFAULT_PARAMS = {
    "ocean_norm": 2,
    "ocean_ilf": True
}

FACET_DEFAULT_PARAMS = {
    "facet_offset": 0.0001,
    "facet_nrects": 20_000,
    "facet_enumerate": "PointBased",
    "facet_sample": "Augment",
    "facet_sd": 0.01,
    "facet_intersect_order": "Axes",
    "facet_verbose": False,
    "facet_search": "BitVector",  # Linear
    "facet_smart_weight": True,
    "rbv_initial_radius": 0.01,
    "rbv_radius_step": 0.01,
    "rbv_radius_growth": "Linear",
    "rbv_num_interval": 16,
    "gbc_intersection": "MinimalWorstGuess",  # "CompleteEnsemble"
}

RFOCSE_DEFAULT_PARAMS = {
    "rfoce_transform": False,
    "rfoce_offset": 0.0001,
    "rfoce_maxtime": 300
}

AFT_DEFAULT_PARAMS = {
    "aft_offset": 0.0001
}

RF_DEFAULT_PARAMS = {
    "rf_ntrees": 100,
    "rf_maxdepth": None,
    "rf_hardvoting": False,
}


GBC_DEFUAULT_PARAMS = {
    "gbc_ntrees": 100,
    "gbc_maxdepth": 3,
    "gbc_learning_rate": 0.1,
    "gbc_loss": "log_loss",
    "gbc_init": "zero",
}

DEFAULT_PARAMS = {
    "RandomForest": RF_DEFAULT_PARAMS,
    "GradientBoostingClassifier": GBC_DEFUAULT_PARAMS,
    "FACET": FACET_DEFAULT_PARAMS,
    "MACE": MACE_DEFAULT_PARAMS,
    "RFOCSE": RFOCSE_DEFAULT_PARAMS,
    "AFT": AFT_DEFAULT_PARAMS,
    "OCEAN": OCEAN_DEFAULT_PARAMS,
}


def check_create_directory(dir_path="./results"):
    '''
    Checks the the directory at `dir_path` exists, if it does not it creates all directories in the path
    '''
    if not os.path.isdir(dir_path):
        os.makedirs(dir_path)

    # find the next availible run_id in the specified results directory
    max_run_id = 0
    dir_names = os.listdir(dir_path)
    for name in dir_names:
        x = re.match("run-(\d{3})", name)  # noqa: W605 (ignore linting from flake)
        if x is not None:
            found_run_id = int(x.group(1))
            if found_run_id > max_run_id:
                max_run_id = found_run_id
    run_id = max_run_id + 1

    # return the run_id and a path to that folder
    run_dir = "run-{:03d}".format(run_id)
    run_path = os.path.join(os.path.abspath(dir_path), run_dir)
    os.makedirs(run_path)
    return run_id, run_path


def execute_run(dataset_name: str, explainer: str, params: dict, output_path: str, iteration: int, test_size=0.2,
                n_explain: int = None, random_state: int = None, preprocessing: str = "Normalize", run_ext="",
                model_type: str = "RandomForest"):
    '''
    dataset_name: the name of a valid dataset to load see datasets.py
    explainer: string name of a valid explainer class
    params: a dictionary of hyper-parameters for the RFModel and explainer to use
    output_path: directory to store run configuration and explanations to, ending with "/"
    iteration: id of the iteration, appended to config and explantion file names
    test_size: what portion of the dataset to reserve for testing
    n_explain: the number of samples to explain, if set to None the entire testing set is explained
    random_state: int value use to reproducibly create the same model and data boostraps
    preprocessing: how to process the dataset. Options are None, `Normalize` (to [0,1]), and `Scale` (u=0, sigma=c)
    '''
    # set appropriate random seeds for reproducibility
    random.seed(random_state)
    np.random.seed(random_state)

    # create the output directory
    if not os.path.isdir(output_path):
        os.makedirs(output_path)

    # store this runs configuration
    config = {}
    config["explainer"] = explainer
    config["iteration"] = iteration
    config["dataset_name"] = dataset_name
    config["preprocessing"] = preprocessing
    config["test_size"] = test_size
    config["n_explain"] = n_explain
    config["output_path"] = output_path
    config["random_state"] = random_state
    config["params"] = params
    with open(output_path + "{}_{}_{}{:03d}_config.json".format(dataset_name, explainer.lower(), run_ext, iteration), "w") as f:
        json_text = json.dumps(config, indent=4)
        f.write(json_text)

    # load and split the datset using random state for repeatability. Select samples to explain
    if preprocessing == "Normalize":
        normalize_numeric = True
        normalize_discrete = True
        do_convert = False
        # MACE requires integer discrete features, this is fine as the RF is the same either way
        # we will later normalize when computing the explanation distance later for comparability
        if explainer == "MACE":
            normalize_discrete = False
            if dataset_name == "adult":  # will treat numeric-real as numeric-int
                normalize_numeric = False  # this handles a pysmt bug with mixed-numeric and non-numeric
                do_convert = True
        if explainer == "RFOCSE":
            normalize_discrete = False
            normalize_numeric = True

    x, y, ds_info = load_data(dataset_name, normalize_numeric, normalize_discrete, do_convert)
    indices = np.arange(start=0, stop=x.shape[0])
    xtrain, xtest, ytrain, ytest, idx_train, idx_test = train_test_split(
        x, y, indices, test_size=test_size, shuffle=True, random_state=random_state)

    if n_explain is not None:
        x_explain = xtest[:n_explain]
        # y_explain = ytest[:n_explain]
        idx_explain = idx_test[:n_explain]
    else:
        x_explain = xtest
        # y_explain = ytest
        idx_explain = idx_test
        n_explain = x_explain.shape[0]

    # create the manager which handles create the RF model and explainer
    manager = MethodManager(explainer=explainer, hyperparameters=params,
                            model_type=model_type)

    # train ane evalute the random forest model
    manager.train(xtrain, ytrain)
    preds = manager.predict(xtest)
    accuracy, precision, recall, f1 = classification_metrics(preds, ytest, verbose=False)

    # prepare the explainer, handles any neccessary preprocessing
    prep_start = time.time()
    manager.explainer.prepare_dataset(x, y, ds_info)
    manager.prepare(xtrain=xtrain, ytrain=ytrain)
    prep_end = time.time()
    prep_time = prep_end-prep_start

    # explain the samples using RF predictions (not ground truth)
    explain_preds = manager.predict(x_explain)
    explain_start = time.time()
    explanations: np.ndarray = manager.explain(x_explain, explain_preds)

    explain_end = time.time()
    explain_time = explain_end - explain_start
    sample_time = explain_time / n_explain

    # check that the returned explanations fit the data type requirements (one-hot, discrete, binary, etc)
    # if not ds_info.check_valid(explanations):
    #     print("WARNING - {} PRODUCED AN EXPLANATION INCOMPATIBLE WITH THE GIVEN DATA SCHEMA".format(explainer))

    # store the returned explantions
    expl_df = pd.DataFrame(ds_info.unscale(explanations), columns=ds_info.col_names)
    # also store the index of the explained sample in the dataset
    expl_df.insert(0, "x_idx", idx_explain)
    explanation_path = output_path + \
        "{}_{}_{}{:03d}_explns.csv".format(dataset_name, explainer.lower(), run_ext, iteration)
    expl_df.to_csv(explanation_path, index=False)

    x_df = pd.DataFrame(ds_info.unscale(x_explain), columns=ds_info.col_names)
    x_df.insert(0, "x_idx", idx_explain)
    x_path = output_path + \
        "{}_{}_{}{:03d}_x.csv".format(dataset_name, explainer.lower(), run_ext, iteration)
    x_df.to_csv(x_path, index=False)

    per_valid = percent_valid(explanations)

    # handle special mace int encoding
    if ds_info.numeric_int_map is not None:
        for i in range(x_explain.shape[0]):
            for col_name in ds_info.numeric_int_map.keys():
                col_id = ds_info.col_names.index(col_name)
                expl_val = np.floor(explanations[i][col_id])
                if expl_val not in [np.inf, -np.inf]:
                    expl_val = int(expl_val)
                    explanations[i][col_id] = ds_info.numeric_int_map[col_name][expl_val]
                x_val = int(np.floor(x_explain[i][col_id]))
                explanations[i][col_id] = ds_info.numeric_int_map[col_name][x_val]

    # if we didn't normalize the data we can't trust the distances
    if not ds_info.normalize_numeric or not ds_info.normalize_discrete:
        # create copies so we don't disturb the underlying data
        x_explain = x_explain.copy()
        explanations = explanations.copy()
        # if we didn't normalize the numeric features, scale them down now
        if not ds_info.normalize_numeric:
            ds_info.normalize_numeric = True
            x_explain = rescale_numeric(x_explain, ds_info, scale_up=False)
            explanations = rescale_numeric(explanations, ds_info, scale_up=False)
            ds_info.normalize_numeric = False
        if not ds_info.normalize_discrete:
            ds_info.normalize_discrete = True
            x_explain = rescale_discrete(x_explain, ds_info, scale_up=False)
            explanations = rescale_discrete(explanations, ds_info, scale_up=False)
            ds_info.normalize_discrete = False

    # evalute the quality of the explanations
    avg_dist = average_distance(x_explain, explanations, distance_metric="Euclidean")  # L2 Norm Euclidean
    avg_manhattan = average_distance(x_explain, explanations, distance_metric="Manhattan")  # L1 Norm Manhattan
    avg_length = average_distance(x_explain, explanations, distance_metric="FeaturesChanged")  # L0 Norm Sparsity

    # store and return the top level results
    results = {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "per_valid": per_valid,
        "avg_dist": avg_dist,
        "avg_manhattan": avg_manhattan,
        "avg_dist": avg_dist,
        "avg_length": avg_length,
        "prep_time": prep_time,
        "explain_time": explain_time,
        "sample_time": sample_time,
        "n_explain": n_explain,
    }

    with open(output_path + "{}_{}_{}{:03d}_result.json".format(dataset_name, explainer.lower(), run_ext, iteration), "w") as f:
        json_text = json.dumps(results, indent=4)
        f.write(json_text)

    return results
