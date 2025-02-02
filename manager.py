# from typing_extensions import ParamSpec
import random

import numpy as np

from detectors.gradient_boosting_classifier import GradientBoostingClassifier
# Detector classes
from detectors.random_forest import RandomForest
# Explainer classes
from explainers.best_candidate import AFT
from explainers.facet import FACET
from explainers.mace import MACE
from explainers.ocean import OCEAN
from explainers.rf_ocse import RFOCSE


class MethodManager():
    def __init__(self, explainer: str = None, hyperparameters: dict = None,
                 random_state: int = None, model_type: str = "RandomForest"):
        self.params = hyperparameters
        self.model_type = model_type
        if model_type == "RandomForest":
            self.model = RandomForest(hyperparameters=hyperparameters, random_state=random_state)
        elif model_type == "GradientBoostingClassifier":
            self.model = GradientBoostingClassifier(hyperparameters=hyperparameters, random_state=random_state)
        else:
            print("Unknown model_type!, using RandomForest")
            self.model_type = "RandomForest"
            self.model = RandomForest(hyperparameters=hyperparameters, random_state=random_state)

        if explainer is not None:
            self.explainer = self.init_explainer(explainer=explainer, hyperparameters=hyperparameters)
        self.random_state = random_state

    def init_explainer(self, explainer, hyperparameters):
        if explainer == "AFT":
            return AFT(manager=self, hyperparameters=hyperparameters)
        elif explainer == "OCEAN":
            return OCEAN(manager=self, hyperparameters=hyperparameters)
        elif explainer == "MACE":
            return MACE(manager=self, hyperparameters=hyperparameters)
        elif explainer == "RFOCSE":
            return RFOCSE(manager=self, hyperparameters=hyperparameters)
        elif explainer == "FACET":
            return FACET(manager=self, hyperparameters=hyperparameters)
        else:
            print("Unknown explainer type of " + explainer)
            print("using FACET")
            return FACET(manager=self, hyperparameters=hyperparameters)

    def set_explainer(self, explainer=None, random_state=None):
        random.seed(random_state)
        np.random.seed(random_state)
        self.explainer = self.init_explainer(explainer=explainer, hyperparameters=self.params)

    def train(self, x, y=None):
        self.model.train(x, y)

    def predict(self, x):
        return self.model.predict(x)

    def prepare(self, xtrain: np.ndarray = None, ytrain: np.ndarray = None):
        self.explainer.prepare(xtrain, ytrain)

    def explain(self, x: np.ndarray, y: np.ndarray, k: int = 1, constraints: np.ndarray = None,
                weights: np.ndarray = None, max_dist: float = np.inf, opt_robust=False,
                min_robust: float = None, return_regions: bool = False) -> np.ndarray:
        return self.explainer.explain(x=x, y=y, k=k, constraints=constraints, weights=weights, max_dist=max_dist, opt_robust=opt_robust, min_robust=min_robust, return_regions=return_regions)
