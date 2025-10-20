import os
from pathlib import Path

import pandas as pd

# from src.ground_truth.akvo_gt_check.gt_config import EXCELVERSION, YEAR
from gt_config import EXCELVERSION, YEAR

# from src.ground_truth.akvo_gt_check.SurveyCTO_GroundTruthCollectionv3 import \
from SurveyCTO_GroundTruthCollectionv3 import \
    SurveyCTO_GroundTruthCollectionv3


class ExcelParser:
    @staticmethod
    def parse_subplots(dir_output: Path) -> pd.DataFrame:
        files_list = []
        directory = dir_output / "ground-truth" / YEAR
        list_subfolders_with_paths = [
            f.name for f in os.scandir(directory) if f.is_dir()
        ]

        parsers = {
            "Ground Truth Collection v3": SurveyCTO_GroundTruthCollectionv3,
        }

        for version in list_subfolders_with_paths:
            print(version)

            files_list.append(
                parsers[version]().parse_subplots(
                    dir_output / "ground-truth" / YEAR / version
                )
            )
        concat_df = pd.concat(files_list)

        return concat_df

    @staticmethod
    def parse_plots(dir_output: Path) -> pd.DataFrame:
        files_list = []
        directory = dir_output / "ground-truth" / YEAR
        list_subfolders_with_paths = [
            f.name for f in os.scandir(directory) if f.is_dir()
        ]

        parsers = {
            "Ground Truth Collection v3": SurveyCTO_GroundTruthCollectionv3,
        }

        for version in list_subfolders_with_paths:
            print(version)

            files_list.append(
                parsers[version]().parse_plots(
                    dir_output / "ground-truth" / YEAR / version
                )
            )
        concat_df = pd.concat(files_list)

        return concat_df
