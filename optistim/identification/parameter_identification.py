import matplotlib.pyplot as plt
import numpy as np
from optistim import DingModelFrequency, DingModelPulseDurationFrequency, DingModelIntensityFrequency
from optistim import FunctionalElectricStimulationOptimalControlProgramIdentification
from bioptim import Solver


class DingModelFrequencyParameterIdentification:
    """
    The main class to define an ocp. This class prepares the full program and gives all
    the needed parameters to solve a functional electrical stimulation ocp

    Attributes
    ----------
    model: DingModelFrequency,
        The model to use for the ocp
    force_model_data_path: str | list[str],
        The path to the force model data
    fatigue_model_data_path: str | list[str],
        The path to the fatigue model data
    **kwargs:
        objective: list[Objective]
            Additional objective for the system
        ode_solver: OdeSolver
            The ode solver to use
        use_sx: bool
            The nature of the casadi variables. MX are used if False.
        n_threads: int
            The number of thread to use while solving (multi-threading if > 1)
    """

    def __init__(
        self,
        model: DingModelFrequency | DingModelPulseDurationFrequency | DingModelIntensityFrequency,
        force_model_data_path: str | list[str] = None,
        fatigue_model_data_path: str | list[str] = None,
        **kwargs,
    ):
        # --- Check inputs --- #
        # --- Force model --- #
        if isinstance(force_model_data_path, list):
            for i in range(len(force_model_data_path)):
                if not isinstance(force_model_data_path[i], str):
                    raise TypeError(
                        f"In the given list, all f_muscle_force_model_data_path must be str type,"
                        f" path index n°{i} is not str type"
                    )
                if not force_model_data_path[i].endswith(".pkl"):
                    raise TypeError(
                        f"In the given list, all f_muscle_force_model_data_path must be pickle type and end with .pkl,"
                        f" path index n°{i} is not ending with .pkl"
                    )
        elif isinstance(force_model_data_path, str):
            force_model_data_path = [force_model_data_path]
            if not force_model_data_path[0].endswith(".pkl"):
                raise TypeError(
                    f"In the given list, all f_muscle_force_model_data_path must be pickle type and end with .pkl,"
                    f" path index is not ending with .pkl"
                )
        else:
            raise TypeError(
                f"In the given path, all f_muscle_force_model_data_path must be str type,"
                f" the input is {type(force_model_data_path)} type and not str type"
            )

        # --- Fatigue model --- #
        if isinstance(fatigue_model_data_path, list):
            for i in range(len(fatigue_model_data_path)):
                if not isinstance(fatigue_model_data_path[i], str):
                    raise TypeError(
                        f"In the given list, all f_muscle_fatigue_model_data_path must be str type,"
                        f" path index n°{i} is not str type"
                    )
                if not fatigue_model_data_path[i].endswith(".pkl"):
                    raise TypeError(
                        f"In the given list, all f_muscle_force_model_data_path must be pickle type and end with .pkl,"
                        f" path index n°{i} is not ending with .pkl"
                    )
        elif isinstance(fatigue_model_data_path, str):
            fatigue_model_data_path = [fatigue_model_data_path]
            if not fatigue_model_data_path[0].endswith(".pkl"):
                raise TypeError(
                    f"In the given list, all f_muscle_force_model_data_path must be pickle type and end with .pkl,"
                    f" path index is not ending with .pkl"
                )
        else:
            raise TypeError(
                f"In the given path, all f_muscle_fatigue_model_data_path must be str type,"
                f" the input is {type(fatigue_model_data_path)} type and not str type"
            )

        # --- Data extraction --- #
        # --- Force model --- #
        import pickle

        global_force_model_muscle_data = []
        global_force_model_stim_apparition_time = []
        global_force_model_time_data = []

        force_discontinuity_phase_list = []
        for i in range(len(force_model_data_path)):
            with open(force_model_data_path[i], "rb") as f:
                data = pickle.load(f)
            force_model_data = data["biceps"]

            # Arranging the data to have the beginning time starting at 0 second for all data
            force_model_stim_apparition_time = (
                data["stim_time"]
                if data["stim_time"][0] == 0
                else [stim_time - data["stim_time"][0] for stim_time in data["stim_time"]]
            )

            force_model_time_data = (
                data["time"]
                if data["stim_time"][0] == 0
                else [[(time - data["stim_time"][0]) for time in row] for row in data["time"]]
            )

            """
            # # Average on each force curve
            smallest_list = 0
            for j in range(len(force_model_data)):
                if j == 0:
                    smallest_list = len(force_model_data[j])
                if len(force_model_data[j]) < smallest_list:
                    smallest_list = len(force_model_data[j])
            force_model_data = np.mean([row[:smallest_list] for row in force_model_data], axis=0).tolist()
            """

            force_model_data = [item for sublist in force_model_data for item in sublist]
            force_model_time_data = [item for sublist in force_model_time_data for item in sublist]

            """
            force_model_time_data = force_model_time_data[:smallest_list]
            frequency = 33
            train_duration = 1
            average_stim_apparition = np.linspace(0, train_duration, (frequency*train_duration) + 1)[:-1]
            average_stim_apparition = np.append(average_stim_apparition, force_model_time_data[-1]).tolist()
            """

            # Indexing the current data time on the previous one to ensure time continuity
            if i != 0:
                # average_stim_apparition = average_stim_apparition[1:]
                force_discontinuity_phase_list.append(
                    len(global_force_model_stim_apparition_time[-1]) - 1
                    if force_discontinuity_phase_list == []
                    else force_discontinuity_phase_list[-1] + len(global_force_model_stim_apparition_time[-1]) # + (1 * i - 2)  # TODO : find a better way to fix this than + (1 * i - 2)
                )

                force_model_stim_apparition_time = [
                    stim_time + global_force_model_time_data[i - 1][-1]
                    for stim_time in force_model_stim_apparition_time
                ]

                force_model_time_data = [(time + global_force_model_time_data[i - 1][-1]) for time in force_model_time_data]
                force_model_stim_apparition_time = [(time + global_force_model_time_data[i - 1][-1]) for time in force_model_stim_apparition_time]
                # average_stim_apparition = [(time + global_force_model_time_data[i - 1][-1]) for time in average_stim_apparition]
                # average_stim_apparition = average_stim_apparition[1:]
            # Storing data into global lists
            global_force_model_muscle_data.append(force_model_data)
            global_force_model_stim_apparition_time.append(force_model_stim_apparition_time)
            # global_force_model_stim_apparition_time.append(average_stim_apparition)
            global_force_model_time_data.append(force_model_time_data)
        # Expending global lists
        global_force_model_muscle_data = [item for sublist in global_force_model_muscle_data for item in sublist]
        global_force_model_stim_apparition_time = [
            item for sublist in global_force_model_stim_apparition_time for item in sublist
        ]
        global_force_model_time_data = [item for sublist in global_force_model_time_data for item in sublist]

        # --- Fatigue model --- #
        global_fatigue_model_muscle_data = []
        global_fatigue_model_stim_apparition_time = []
        global_fatigue_model_time_data = []

        fatigue_discontinuity_phase_list = []
        for i in range(len(fatigue_model_data_path)):
            with open(fatigue_model_data_path[i], "rb") as f:
                data = pickle.load(f)
            fatigue_model_data = data["biceps"]
            # Arranging the data to have the beginning time starting at 0 second for all data
            fatigue_model_stim_apparition_time = (
                data["stim_time"]
                if data["stim_time"][0] == 0
                else [stim_time - data["stim_time"][0] for stim_time in data["stim_time"]]
            )
            fatigue_model_time_data = (
                data["time"]
                if data["stim_time"][0] == 0
                else [[(time - data["stim_time"][0]) for time in row] for row in data["time"]]
            )
            # Indexing the current data time on the previous one to ensure time continuity
            if i != 0:
                fatigue_discontinuity_phase_list.append(
                    len(global_fatigue_model_stim_apparition_time[-1]) - 1
                    if fatigue_discontinuity_phase_list == []
                    else fatigue_discontinuity_phase_list[-1] + len(global_fatigue_model_stim_apparition_time[-1]) - 1
                )
                fatigue_model_stim_apparition_time = [
                    stim_time + global_fatigue_model_time_data[i - 1][-1]
                    for stim_time in fatigue_model_stim_apparition_time
                ]
                fatigue_model_time_data = [
                    [(time + global_fatigue_model_time_data[i - 1][-1]) for time in row]
                    for row in fatigue_model_time_data
                ]
            # Expending lists
            fatigue_model_data = [item for sublist in fatigue_model_data for item in sublist]
            fatigue_model_time_data = [item for sublist in fatigue_model_time_data for item in sublist]
            # Storing data into global lists
            global_fatigue_model_muscle_data.append(fatigue_model_data)
            global_fatigue_model_stim_apparition_time.append(fatigue_model_stim_apparition_time)
            global_fatigue_model_time_data.append(fatigue_model_time_data)
        # Expending global lists
        global_fatigue_model_muscle_data = [item for sublist in global_fatigue_model_muscle_data for item in sublist]
        global_fatigue_model_stim_apparition_time = [
            item for sublist in global_fatigue_model_stim_apparition_time for item in sublist
        ]
        global_fatigue_model_time_data = [item for sublist in global_fatigue_model_time_data for item in sublist]

        # --- Building force ocp --- #
        self.force_ocp = FunctionalElectricStimulationOptimalControlProgramIdentification(
            model=model,
            with_fatigue=False,
            stimulated_n_shooting=5,  # 5
            rest_n_shooting=165,  # 165
            force_tracking=[np.array(global_force_model_time_data), np.array(global_force_model_muscle_data)],
            pulse_apparition_time=global_force_model_stim_apparition_time,
            pulse_duration=None,
            pulse_intensity=None,
            discontinuity_in_ocp=force_discontinuity_phase_list,
            use_sx=kwargs["use_sx"] if "use_sx" in kwargs else False,
        )
        # del global_force_model_muscle_data, global_force_model_stim_apparition_time, global_force_model_time_data

        result = self.force_ocp.solve(Solver.IPOPT())
        # result.graphs(show_bounds=True)

        for i in range(len(global_force_model_stim_apparition_time)):
            self.final_time_phase = () if i == 0 else self.final_time_phase + (global_force_model_stim_apparition_time[i] - global_force_model_stim_apparition_time[i - 1],)

        self.n_stim = len(self.final_time_phase)

        stimulation_interval_average = np.mean(self.final_time_phase)
        self.n_shooting = []
        for i in range(self.n_stim):
            if self.final_time_phase[i] > stimulation_interval_average:
                temp_final_time = self.final_time_phase[i]
                rest_n_shooting = int(5 * temp_final_time / stimulation_interval_average)
                self.n_shooting.append(rest_n_shooting)
            else:
                self.n_shooting.append(5)

        self.force_at_node = []
        temp_time = []
        for i in range(self.n_stim):
            for j in range(self.n_shooting[i]):
                temp_time.append(sum(self.final_time_phase[:i]) + j * self.final_time_phase[i] / (self.n_shooting[i]))
        self.force_at_node = np.interp(temp_time, np.array(global_force_model_time_data), np.array(global_force_model_muscle_data)).tolist()

        # --- Print force model results --- #
        print(result.parameters)
        result_merged = result.merge_phases()
        plt.scatter(result_merged.time, result_merged.states["F"][0], label="identification")
        # global_force_model_muscle_data = np.array(
        #     np.where(np.array(global_force_model_muscle_data) < 0, 0, global_force_model_muscle_data)
        # ).tolist()
        plt.scatter(temp_time, self.force_at_node, label="tracking")
        # for discontinuity in force_discontinuity_phase_list:
        for i in range(len(global_force_model_stim_apparition_time)):
            # plt.axvline(x=temp_time[sum(self.n_shooting[:stim])], ls='--', color='black')
            plt.axvline(x=global_force_model_stim_apparition_time[i], ls='--', color='black')
        plt.legend()
        plt.show()

        # --- Building fatigue ocp --- #
        self.fatigue_ocp = FunctionalElectricStimulationOptimalControlProgramIdentification(
            model=model,
            with_fatigue=True,
            stimulated_n_shooting=5,  # 5
            # rest_n_shooting=165,  # 165
            force_tracking=[np.array(global_fatigue_model_time_data), np.array(global_fatigue_model_muscle_data)],
            pulse_apparition_time=global_fatigue_model_stim_apparition_time,
            pulse_duration=None,
            pulse_intensity=None,
            a_rest=result.parameters["a_rest"][0][0],
            km_rest=result.parameters["km_rest"][0][0],
            tau1_rest=result.parameters["tau1_rest"][0][0],
            tau2=result.parameters["tau2"][0][0],
            # a_rest=1582.43,
            # km_rest=1,
            # tau1_rest=0.0034,
            # tau2=0.2032,
            discontinuity_in_ocp=fatigue_discontinuity_phase_list,
            use_sx=kwargs["use_sx"] if "use_sx" in kwargs else False,
        )
    #
    # # del global_fatigue_model_muscle_data, global_fatigue_model_stim_apparition_time, global_fatigue_model_time_data
    #
        result_fatigue = self.fatigue_ocp.solve(Solver.IPOPT())
        # --- Print fatigue model results --- #
        print(result_fatigue.parameters)
        result_merged = result.merge_phases()
        plt.plot(result_merged.time, result_merged.states["F"][0], label="identification")
        global_fatigue_model_muscle_data = np.array(
            np.where(np.array(global_fatigue_model_muscle_data) < 0, 0, global_fatigue_model_muscle_data)
        ).tolist()
        plt.plot(global_fatigue_model_time_data, global_fatigue_model_muscle_data, label="tracking")
        plt.legend()
        plt.show()


if __name__ == "__main__":
    DingModelFrequencyParameterIdentification(
        model=DingModelFrequency,
        force_model_data_path=["D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_70_1.pkl",
                               "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_70_2.pkl",
                               "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_70_3.pkl"],
                               # "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_90_1.pkl",
                               # "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_90_2.pkl",
                               # "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_90_3.pkl",
                               # "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_110_1.pkl",
                               # "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_110_2.pkl",
                               # "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_110_3.pkl"],
        fatigue_model_data_path=[
            "D:/These/Programmation/Modele_Musculaire/optistim/data_process/biceps_force_fatigue_0.pkl"
        ],
        use_sx=True,
    )