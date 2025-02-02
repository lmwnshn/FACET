import os

import pandas as pd
from tqdm.auto import tqdm

from .experiments import DEFAULT_PARAMS, FACET_TUNED_M, FACET_TUNED_NRECTS, TUNED_FACET_SD, execute_run


def compare_methods(ds_names, explainers=["FACET", "OCEAN", "RFOCSE", "AFT", "MACE"], iterations=[0, 1, 2, 3, 4], fmod=None, ntrees=10, max_depth=5, model_type: str = "RandomForest", max_time=300, gbc_intersection: str = "MinimalWorstGuess"):
    '''
    Experiment to compare the performance of different explainers on the same ensemble
    '''
    # print the top level variables
    print("Comparing methods:")
    print("\tds_names:", ds_names)
    print("\texplainers:", explainers)
    print("\tmodel:", model_type)
    print("\titerations:", iterations)
    if model_type == "GradientBoostingClassifier":
        print("\tFACET intersection:", gbc_intersection)

    # create the output path
    if fmod is not None:
        csv_path = "./results/compare_methods_" + fmod + ".csv"
        experiment_path = "./results/compare-methods-" + fmod + "/"
    else:
        csv_path = "./results/compare_methods.csv"
        experiment_path = "./results/compare-methods/"

    params = DEFAULT_PARAMS
    # set ensemble size
    params["RandomForest"]["rf_ntrees"] = ntrees
    params["RandomForest"]["rf_maxdepth"] = max_depth
    params["GradientBoostingClassifier"]["rf_ntrees"] = ntrees
    params["GradientBoostingClassifier"]["rf_maxdepth"] = max_depth
    # set max time for slow methods
    params["RFOCSE"]["rfoce_maxtime"] = max_time
    params["MACE"]["mace_maxtime"] = max_time
    # set how FACET intersects rects if we're explaining gbc
    params["FACET"]["gbc_intersection"] = gbc_intersection

    total_runs = len(ds_names) * len(explainers) * len(iterations)
    progress_bar = tqdm(total=total_runs, desc="Overall Progress", position=0, disable=False)

    for iter in iterations:
        for expl in explainers:
            for ds in ds_names:
                # set the number of trees
                params["FACET"]["facet_sd"] = TUNED_FACET_SD[ds]
                params["FACET"]["rbv_num_interval"] = FACET_TUNED_M[ds]
                params["FACET"]["facet_nrects"] = FACET_TUNED_NRECTS[ds]
                run_result = execute_run(
                    dataset_name=ds,
                    explainer=expl,
                    params=params,
                    output_path=experiment_path,
                    iteration=iter,
                    test_size=0.2,
                    n_explain=20,
                    random_state=iter,
                    preprocessing="Normalize",
                    run_ext="",
                    model_type=model_type,
                )
                df_item = {
                    "dataset": ds,
                    "explainer": expl,
                    "n_trees": ntrees,
                    "max_depth": max_depth,
                    "iteration": iter,
                    "model_type": model_type,
                    "gbc_intersection": gbc_intersection,
                    **run_result
                }
                experiment_results = pd.DataFrame([df_item])
                if not os.path.exists(csv_path):
                    experiment_results.to_csv(csv_path, index=False)
                else:
                    experiment_results.to_csv(csv_path, index=False, mode="a", header=False,)

                progress_bar.update()
    progress_bar.close()
    print("Finished comparing methods!")
