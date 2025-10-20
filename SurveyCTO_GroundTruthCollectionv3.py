import geopandas as gpd
import numpy as np
import pandas as pd

# from src.ground_truth.akvo_gt_check.gt_check_functions import (
from gt_check_functions import (

    create_gt_plotid, geom_from_scto_str)


class SurveyCTO_GroundTruthCollectionv3:
    def parse_plots(self, plot_dir):
        files = plot_dir.glob("*.xlsx")
        plots = []
        for file in files:
            plots.append(pd.read_excel(file))
        df = (
            pd.concat(plots)
            .dropna(subset=["gt_plot"])
            .reset_index()
            .assign(
                plot_id=lambda x: x.apply(create_gt_plotid, axis=1),
                enumerator=lambda x: x.apply(lambda row: f"{row.enumerator} ({row.enumerator_id})", axis=1),
                collection_date=lambda x: x.starttime.dt.strftime("%Y-%m-%d"),
                device=lambda x: x.device_info.str.split("SurveyCTO").str[0]
            )
            .assign(
                geometry=lambda x: x.apply(
                    geom_from_scto_str,
                    column="gt_plot",
                    accuracy_m=10,
                    axis=1,
                )
            )
            .pipe(gpd.GeoDataFrame, crs=4326)[["plot_id", "enumerator", "enumerator_id", "collection_date", "device", "geometry"]]
        )
        return df

    def parse_subplots(self, dir):
        files = (dir).glob("*.xlsx")

        plots = []
        for file in files:
            #plots.append(pd.read_excel(file))
            plots.append(pd.read_excel(file))

        df = pd.concat(plots)
        print(df.head(5))
        df = (
            df.reset_index()
            .assign(plot_id=lambda x: x.apply(create_gt_plotid, axis=1))
            .groupby("plot_id")
            .apply(self.parse_polygon)
            .reset_index(level=0)
            .set_crs(4326)
        )
        return df

    def parse_tree_list(self, dir):
        files = (dir / "ground-truth").glob("*.xlsx")
        plots = []
        for file in files:
            plots.append(pd.read_excel(file))
        df = pd.concat(plots)
        df_trees = (
            df.reset_index()
            .assign(plot_id=lambda x: x.apply(create_gt_plotid, axis=1))
            .groupby("plot_id")
            .apply(self.parse_trees)
            .reset_index(level=0)
        )
        return df_trees

    def parse_polygon(self, df):
        plot_id = df.name
        row = df.iloc[0]
        enumerator_name = row.enumerator
        enumerator_id = row.enumerator_id
        collection_date = row.starttime.strftime("%Y-%m-%d")
        device_type = row.device_info.split("SurveyCTO")[0]
        subplots = []

        for i in range(1, 17):
            subplot_id = f"{plot_id}_{i}"
            polygon = geom_from_scto_str(row, f"gt_subplot_{i}", accuracy_m=10)

            subplots.append(
                {
                    "geometry": polygon,
                    "subplot_id": subplot_id,
                    "enumerator_id": enumerator_id,
                    "enumerator": enumerator_name,
                    "collection_date": collection_date,
                    "device": device_type,
                }
            )
        return gpd.GeoDataFrame.from_records(subplots)

    def parse_trees(self, row):
        plot_id = row.name
        df_vegetation_list = []
        nr_subplots_list = [c for c in row.columns if "gt_subplot_" in c]
        for i in nr_subplots_list:
            subplot_nr = i.split("gt_subplot_")[1]
            nr_trees = [c for c in row.columns if f"nr_trees_{subplot_nr}_" in c]

            for t in nr_trees:
                n_trees = row[t].iloc[0]
                if np.isnan(n_trees):
                    continue
                tree_nr = t.split("_")[3]

                if not np.isnan(n_trees):
                    df_vegetation_list.append(
                        pd.DataFrame(
                            {
                                "subplot_id": np.repeat(
                                    f"{plot_id}_{subplot_nr}", n_trees
                                ),
                                "collection_date": np.repeat(
                                    row["starttime"].iloc[0].strftime("%Y/%m/%d"),
                                    n_trees,
                                ),
                                "enumerator_name": np.repeat(
                                    row["enumerator_name"], n_trees
                                ),
                                "vegetation_type": np.repeat("tree_over_1.3m", n_trees),
                                "species": np.repeat(
                                    row[
                                        "tree_plant_crop_species_"
                                        f"{subplot_nr}_{tree_nr}"
                                    ],
                                    n_trees,
                                ),
                                "other_species": np.repeat(
                                    row[f"other_species_{subplot_nr}_{tree_nr}"],
                                    n_trees,
                                ),
                                "tree_height_m": np.repeat(
                                    row[f"tree_height_m_{subplot_nr}_{tree_nr}"],
                                    n_trees,
                                ),
                                "crop_height_m": np.repeat(
                                    row[f"crop_height_m_{subplot_nr}_{tree_nr}"],
                                    n_trees,
                                ),
                                "nr_grouped_trees": np.repeat(
                                    n_trees,
                                    n_trees,
                                ),
                                "total_nr_stems": np.repeat(
                                    row[f"nr_stems_{subplot_nr}_{tree_nr}"],
                                    n_trees,
                                ),
                                "tree_circumference_cm": np.repeat(
                                    row[
                                        f"tree_circumference_cm_{subplot_nr}_{tree_nr}"
                                    ],
                                    n_trees,
                                ),
                                "diameter_cm": np.repeat(
                                    row[f"tree_circumference_cm_{subplot_nr}_{tree_nr}"]
                                    .iloc[0]
                                    .astype(float)
                                    / np.pi,
                                    n_trees,
                                ),
                                "prune_height_m": np.repeat(
                                    row[f"prune_heigth_{subplot_nr}_{tree_nr}"],
                                    n_trees,
                                ),
                                "crop_count": np.repeat(
                                    row[f"nr_trees_{subplot_nr}_{tree_nr}"].iloc[0],
                                    n_trees,
                                ),
                                "crop_percentage": np.repeat(
                                    row[
                                        f"coverage_percentage_{subplot_nr}_{tree_nr}"
                                    ].iloc[0],
                                    n_trees,
                                ),
                                "year": np.repeat(
                                    row[f"tree_year_planted_{subplot_nr}_{tree_nr}"]
                                    .iloc[0]
                                    .strftime("%Y"),
                                    n_trees,
                                ),
                                "comments": np.repeat(
                                    row[f"tree_comments_{subplot_nr}_{tree_nr}"],
                                    n_trees,
                                ),
                            }
                        )
                    )

        if len(df_vegetation_list) > 0:
            df_vegetation = pd.concat(df_vegetation_list, ignore_index=True)

            df_vegetation["species"] = df_vegetation.apply(
                lambda x: x.species if pd.isna(x.other_species) else x.other_species,
                axis=1,
            )
            df_vegetation["avg_stems"] = (
                df_vegetation["total_nr_stems"] / df_vegetation["nr_grouped_trees"]
            )
            df_vegetation["vegetation_height_m"] = df_vegetation.apply(
                lambda x: x.crop_height_m
                if pd.isna(x.tree_height_m)
                else x.tree_height_m,
                axis=1,
            )
            df_vegetation["crop_count"] = df_vegetation.apply(
                lambda x: x.crop_percentage / 100
                if pd.isna(x.crop_count)
                else x.crop_count,
                axis=1,
            )
        else:
            df_vegetation = pd.DataFrame(columns=["species", "diameter_cm", "height_m"])
        return df_vegetation[
            [
                "subplot_id",
                "collection_date",
                "enumerator_name",
                "vegetation_type",
                "species",
                "vegetation_height_m",
                "diameter_cm",
                "year",
                "avg_stems",
                "prune_height_m",
                "crop_count",
                "comments",
                "other_species",
                "tree_height_m",
                "crop_height_m",
                "tree_circumference_cm",
                "nr_grouped_trees",
                "total_nr_stems",
                "crop_percentage",
            ]
        ].sort_values(
            ["subplot_id", "vegetation_type", "nr_grouped_trees"],
            ascending=[True, False, False],
        )
