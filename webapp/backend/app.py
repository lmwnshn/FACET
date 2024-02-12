import numpy as np
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import sys
from webapp.app_utilities import run_facet, parse_dataset_info
from dataset import get_json_paths, DataInfo

# load app confiuration parameters
with open("./webapp/config.json", "r") as config_file:
    APP_CONFIG: dict = json.load(config_file)  # config file with app parameters
API_PORT: int = APP_CONFIG["API_PORT"]  # specified port for RESTful explanation API
DS_NAME: str = APP_CONFIG["DATASET"]  # the dataset we're explaining
DETAILS_PATH, HUMAN_PATH = get_json_paths(
    DS_NAME
)  # the paths to the ds_details, and human_readible info
DS_INFO: DataInfo = None
HUMAN_FORMAT: dict = None

# configure the app
app = Flask(__name__)
CORS(app)
FACET_CORE = None  # the core facet system which generated explanations
SAMPLE_DATA: np.ndarray = None  # teh set of sample instances we populate for the demo


def init_app():
    global FACET_CORE, SAMPLE_DATA, DS_INFO, HUMAN_FORMAT

    print("\nApp initializing...\n")
    try:
        # initialize FACET (load data, train model, index explanations) and get samples
        FACET_CORE, SAMPLE_DATA = run_facet(ds_name=DS_NAME)
        # load the dataset info JSON file which is automatically generated by FACET
        DS_INFO = parse_dataset_info(DETAILS_PATH)
        # load the human readable JSON file used for display formatting
        with open(HUMAN_PATH, "r") as human_format_file:
            HUMAN_FORMAT = json.load(human_format_file)
        # append a mapping to FACET's col_ids x0, x1, ... , xN (from DS_INFO)
        HUMAN_FORMAT["feature_names"] = DS_INFO.col_names
    except Exception as e:
        print(f"ERROR: Failed to run FACET. Details:\n{e}")
        exit(1)
    print("\nApp initialized\n")


init_app()


@app.route("/facet/instances", methods=["GET"])
def get_test_instances():
    num_arrays, array_length = SAMPLE_DATA.shape
    json_data = []

    # Iterate over the arrays and build the dictionary
    samples = DS_INFO.unscale_points(SAMPLE_DATA)
    for instance in samples:
        instance_dict = DS_INFO.point_to_dict(instance)
        json_data.append(instance_dict)

    return jsonify(json_data)


@app.route("/facet/human_format", methods=["GET"])
def get_human_format():
    return jsonify(HUMAN_FORMAT)


@app.route("/data/loans/<path:filename>")
def serve_file(filename):
    root_dir = os.path.dirname(os.path.abspath(__file__))
    visualization_dir = os.path.join(root_dir, "..", "..", "data")
    print(visualization_dir)
    return send_from_directory(os.path.join(visualization_dir, "loans"), filename)


@app.route("/facet/explanations", methods=["POST"])
def facet_explanation():
    """
    This is the main API endpoint for explaining instances. It expects a request JSON object containing the following entries

    Parameters
    ----------
    `instance`: a dictionary with the instance values like {x0: value, ..., xn: value}
    `weights`: a dictionary with the weights values like {x0: weight, ..., xn: weight}
    `k`: an integer for the number of explantions to generate
    `constraints`: a dictionary with the constaints values like {x0: [lower, upper], ..., xn: [lower, upper]}

    Returns
    -------
    `regions: an array of regions dictionaries`
    """

    try:
        data = request.json
        print("request: " + str(data))

        instance = DS_INFO.dict_to_point(data["instance"])
        instance = DS_INFO.scale_points(instance)
        weights = DS_INFO.dict_to_point(data["weights"])
        print("weights", weights)
        weights = np.nan_to_num(weights, nan=1.0)
        weights[weights == 0] = 1.0
        constraints = np.array(data.get("constraints", None)).astype(float)
        constraints = DS_INFO.scale_rects(constraints)[0]
        num_explanations = data.get("num_explanations", 1)

        # if we only have one instance, reshape the arary correctly
        if len(instance.shape) == 1:
            instance = instance.reshape(-1, instance.shape[0])

        # Perform explanations using FACET explain
        prediction = FACET_CORE.predict(instance)
        points, regions = FACET_CORE.explain(
            x=instance,
            y=prediction,
            k=2 * num_explanations,
            constraints=constraints,
            weights=weights,
        )

        # facet generates a lot of duplicate regions, so we get the first k unique regions
        unique_regions = []
        for arr in regions:
            if arr.tolist() not in unique_regions:
                unique_regions.append(arr.tolist())

            if len(unique_regions) == num_explanations:
                break

        unique_regions = [np.array(arr) for arr in unique_regions]

        unscaled_regions = [DS_INFO.unscale_rects(region) for region in unique_regions]
        region_dicts = [DS_INFO.rect_to_dict(region) for region in unscaled_regions]

        return jsonify(region_dicts)

    except Exception as e:
        print(e)
        return "\nError: " + str(e), 500


if __name__ == "__main__":
    app.run(port=API_PORT, debug=True)
