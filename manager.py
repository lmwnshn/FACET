# from typing_extensions import ParamSpec
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.model_selection import KFold

# Detector classes
from detectors.random_forest import RandomForest

# Explainer classes
from explainers import *
from explainers.best_candidate import AFT
from explainers.ocean import OCEAN
from explainers.mace import MACE
from explainers.facet import FACET
from explainers.facet_trees import FACETTrees
from explainers.facet_paths import FACETPaths
from explainers.facet_grow import FACETGrow
from explainers.facet_bb import FACETBranchBound
from explainers.facet_index import FACETIndex
from explainers.rf_ocse import RFOCSE


class MethodManager():
    def __init__(self, explainer=None, hyperparameters=None, random_state=None):
        self.random_forest = RandomForest(hyperparameters=hyperparameters, random_state=random_state)
        self.explainer = self.init_explainer(explainer=explainer, hyperparameters=hyperparameters)

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
            return FACET(model=self, hyperparameters=hyperparameters)
        elif explainer == "FACETTrees":
            return FACETTrees(model=self, hyperparameters=hyperparameters)
        elif explainer == "FACETPaths":
            return FACETPaths(model=self, hyperparameters=hyperparameters)
        elif explainer == "FACETGrow":
            return FACETGrow(model=self, hyperparameters=hyperparameters)
        elif explainer == "FACETBranchBound":
            return FACETBranchBound(model=self, hyperparameters=hyperparameters)
        elif explainer == "FACETIndex":
            return FACETIndex(manger=self, hyperparameters=hyperparameters)
        else:
            print("Unknown explainer type of " + explainer)
            print("using FACETIndex")
            return FACETIndex(manger=self, hyperparameters=hyperparameters)

    def train(self, x, y=None):
        self.random_forest.train(x, y)

    def predict(self, x):
        return self.random_forest.predict(x)

    def prepare(self, data=None):
        self.explainer.prepare(data)

    def explain(self, x, y):
        return self.explainer.explain(x, y)
