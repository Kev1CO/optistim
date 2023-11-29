import numpy as np

from bioptim import (
    BiMapping,
    # BiMappingList, parameter mapping not yet implemented
    BoundsList,
    ConstraintFcn,
    ConstraintList,
    ControlType,
    DynamicsList,
    InitialGuessList,
    InterpolationType,
    Node,
    Objective,
    ObjectiveFcn,
    ObjectiveList,
    OdeSolver,
    OptimalControlProgram,
    ParameterList,
    ParameterObjectiveList,
    PhaseDynamics,
)

from ..custom_objectives import CustomObjective
from ..fourier_approx import FourierSeries
from cocofest import DingModelFrequency, DingModelPulseDurationFrequency, DingModelIntensityFrequency


class OcpFes:
    """
    The main class to define an ocp. This class prepares the full program and gives all
    the needed parameters to solve a functional electrical stimulation ocp

    Methods
    -------
    from_frequency_and_final_time(self, frequency: int | float, final_time: float, round_down: bool)
        Calculates the number of stim (phases) for the ocp from frequency and final time
    from_frequency_and_n_stim(self, frequency: int | float, n_stim: int)
        Calculates the final ocp time from frequency and stimulation number
    """

    @staticmethod
    def prepare_ocp(
        model: DingModelFrequency | DingModelPulseDurationFrequency | DingModelIntensityFrequency = None,
        n_stim: int = None,
        n_shooting: int = None,
        final_time: int | float = None,
        pulse_mode: str = "Single",
        frequency: int | float = None,
        round_down: bool = False,
        time_min: int | float = None,
        time_max: int | float = None,
        time_bimapping: bool = False,
        pulse_time: int | float = None,
        pulse_time_min: int | float = None,
        pulse_time_max: int | float = None,
        pulse_time_bimapping: bool = False,
        pulse_intensity: int | float = None,
        pulse_intensity_min: int | float = None,
        pulse_intensity_max: int | float = None,
        pulse_intensity_bimapping: bool = False,
        force_tracking: list = None,
        end_node_tracking: int | float = None,
        custom_objective: list[Objective] = None,
        use_sx: bool = True,
        ode_solver: OdeSolver = OdeSolver.RK4(n_integration_steps=1),
        n_threads: int = 1,
    ):
        """
        This definition prepares the ocp to be solved
        .
        Attributes
        ----------
            model: DingModelFrequency | DingModelPulseDurationFrequency| DingModelIntensityFrequency
                The model type used for the ocp
            n_stim: int
                Number of stimulation that will occur during the ocp, it is as well refer as phases
            n_shooting: int
                Number of shooting point for each individual phases
            final_time: float
                Refers to the final time of the ocp
            force_tracking: list[np.ndarray, np.ndarray]
                List of time and associated force to track during ocp optimisation
            end_node_tracking: int | float
                Force objective value to reach at the last node
            time_min: int | float
                Minimum time for a phase
            time_max: int | float
                Maximum time for a phase
            time_bimapping: bool
                Set phase time constant
            pulse_time: int | float
                Setting a chosen pulse time among phases
            pulse_time_min: int | float
                Minimum pulse time for a phase
            pulse_time_max: int | float
                Maximum pulse time for a phase
            pulse_time_bimapping: bool
                Set pulse time constant among phases
            pulse_intensity: int | float
                Setting a chosen pulse intensity among phases
            pulse_intensity_min: int | float
                Minimum pulse intensity for a phase
            pulse_intensity_max: int | float
                Maximum pulse intensity for a phase
            pulse_intensity_bimapping: bool
                Set pulse intensity constant among phases
            custom_objective: list[Objective]
                Additional objective for the system
            ode_solver: OdeSolver
                The ode solver to use
            use_sx: bool
                The nature of the casadi variables. MX are used if False.
            n_threads: int
                The number of thread to use while solving (multi-threading if > 1)
        """

        OcpFes._sanity_check(
            model=model,
            n_stim=n_stim,
            n_shooting=n_shooting,
            final_time=final_time,
            pulse_mode=pulse_mode,
            frequency=frequency,
            time_min=time_min,
            time_max=time_max,
            time_bimapping=time_bimapping,
            pulse_time=pulse_time,
            pulse_time_min=pulse_time_min,
            pulse_time_max=pulse_time_max,
            pulse_time_bimapping=pulse_time_bimapping,
            pulse_intensity=pulse_intensity,
            pulse_intensity_min=pulse_intensity_min,
            pulse_intensity_max=pulse_intensity_max,
            pulse_intensity_bimapping=pulse_intensity_bimapping,
            force_tracking=force_tracking,
            end_node_tracking=end_node_tracking,
            custom_objective=custom_objective,
            use_sx=use_sx,
            ode_solver=ode_solver,
            n_threads=n_threads,
        )

        OcpFes._sanity_check_2(n_stim=n_stim, final_time=final_time, frequency=frequency, round_down=round_down)

        n_stim, final_time = OcpFes._build_phase_parameter(
            n_stim=n_stim, final_time=final_time, frequency=frequency, pulse_mode=pulse_mode, round_down=round_down
        )

        force_fourier_coef = None if force_tracking is None else OcpFes._build_fourrier_coeff(force_tracking)
        end_node_tracking = end_node_tracking
        models = [model] * n_stim
        n_shooting = [n_shooting] * n_stim
        final_time_phase, constraints, phase_time_bimapping = OcpFes._build_phase_time(
            final_time=final_time,
            n_stim=n_stim,
            pulse_mode=pulse_mode,
            time_min=time_min,
            time_max=time_max,
            time_bimapping=time_bimapping,
        )
        parameters, parameters_bounds, parameters_init, parameter_objectives = OcpFes._build_parameters(
            model=model,
            n_stim=n_stim,
            pulse_time=pulse_time,
            pulse_time_min=pulse_time_min,
            pulse_time_max=pulse_time_max,
            pulse_time_bimapping=pulse_time_bimapping,
            pulse_intensity=pulse_intensity,
            pulse_intensity_min=pulse_intensity_min,
            pulse_intensity_max=pulse_intensity_max,
            pulse_intensity_bimapping=pulse_intensity_bimapping,
        )

        if len(constraints) == 0 and len(parameters) == 0:
            raise ValueError(
                "This is not an optimal control problem,"
                " add parameter to optimize or use the IvpFes method to build your problem"
            )

        dynamics = OcpFes._declare_dynamics(models, n_stim)
        x_bounds, x_init = OcpFes._set_bounds(model, n_stim)
        objective_functions = OcpFes._set_objective(
            n_stim, n_shooting, force_fourier_coef, end_node_tracking, custom_objective
        )

        return OptimalControlProgram(
            bio_model=models,
            dynamics=dynamics,
            n_shooting=n_shooting,
            phase_time=final_time_phase,
            objective_functions=objective_functions,
            time_phase_mapping=phase_time_bimapping,
            x_init=x_init,
            x_bounds=x_bounds,
            constraints=constraints,
            parameters=parameters,
            parameter_bounds=parameters_bounds,
            parameter_init=parameters_init,
            parameter_objectives=parameter_objectives,
            control_type=ControlType.NONE,
            use_sx=use_sx,
            ode_solver=ode_solver,
            n_threads=n_threads,
        )

    @staticmethod
    def _sanity_check(
        model=None,
        n_stim=None,
        n_shooting=None,
        final_time=None,
        pulse_mode=None,
        frequency=None,
        time_min=None,
        time_max=None,
        time_bimapping=None,
        pulse_time=None,
        pulse_time_min=None,
        pulse_time_max=None,
        pulse_time_bimapping=None,
        pulse_intensity=None,
        pulse_intensity_min=None,
        pulse_intensity_max=None,
        pulse_intensity_bimapping=None,
        force_tracking=None,
        end_node_tracking=None,
        custom_objective=None,
        use_sx=None,
        ode_solver=None,
        n_threads=None,
    ):
        if not isinstance(model, DingModelFrequency | DingModelPulseDurationFrequency | DingModelIntensityFrequency):
            raise TypeError(
                "model must be a DingModelFrequency, DingModelPulseDurationFrequency or DingModelIntensityFrequency type"
            )

        if n_stim:
            if isinstance(n_stim, int):
                if n_stim <= 0:
                    raise ValueError("n_stim must be positive")
            else:
                raise TypeError("n_stim must be int type")

        if n_shooting:
            if isinstance(n_shooting, int):
                if n_shooting <= 0:
                    raise ValueError("n_shooting must be positive")
            else:
                raise TypeError("n_shooting must be int type")

        if final_time:
            if isinstance(final_time, int | float):
                if final_time <= 0:
                    raise ValueError("final_time must be positive")
            else:
                raise TypeError("final_time must be int or float type")

        if pulse_mode:
            if pulse_mode not in ("Single", "Doublet", "Triplet"):
                raise NotImplementedError(f"Pulse mode '{pulse_mode}' is not yet implemented")

        if frequency:
            if isinstance(frequency, int | float):
                if frequency <= 0:
                    raise ValueError("frequency must be positive")
            else:
                raise TypeError("frequency must be int or float type")

        if time_min is not None and time_max is None or time_min is None and time_max is not None:
            raise ValueError("time_min and time_max must be both entered or none of them in order to work")

        if time_bimapping:
            if not isinstance(time_bimapping, bool):
                raise TypeError("time_bimapping must be bool type")

        if isinstance(model, DingModelPulseDurationFrequency):
            if pulse_time is None and pulse_time_min is not None and pulse_time_max is None:
                raise ValueError("Time pulse or Time pulse min max bounds need to be set for this model")
            if pulse_time is not None and pulse_time_min is not None and pulse_time_max is not None:
                raise ValueError("Either Time pulse or Time pulse min max bounds need to be set for this model")
            if (
                pulse_time_min is not None
                and pulse_time_max is None
                or pulse_time_min is None
                and pulse_time_max is not None
            ):
                raise ValueError("Both Time pulse min max bounds need to be set for this model")

            minimum_pulse_duration = model.pd0

            if pulse_time is not None:
                if isinstance(pulse_time, int | float):
                    if pulse_time < minimum_pulse_duration:
                        raise ValueError(
                            f"The pulse duration set ({pulse_time})"
                            f" is lower than minimum duration required."
                            f" Set a value above {minimum_pulse_duration} seconds "
                        )
                else:
                    raise TypeError("Wrong pulse_time type, only int or float accepted")

            elif pulse_time_min is not None and pulse_time_max is not None:
                if not isinstance(pulse_time_min, int | float) or not isinstance(pulse_time_max, int | float):
                    raise TypeError("pulse_time_min and pulse_time_max must be equal int or float type")
                if pulse_time_max < pulse_time_min:
                    raise ValueError("The set minimum pulse duration is higher than maximum pulse duration.")
                if pulse_time_min < minimum_pulse_duration:
                    raise ValueError(
                        f"The pulse duration set ({pulse_time_min})"
                        f" is lower than minimum duration required."
                        f" Set a value above {minimum_pulse_duration} seconds "
                    )
            else:
                raise ValueError(
                    "Time pulse parameter has not been set, input either pulse_time or pulse_time_min and"
                    " pulse_time_max"
                )

            if pulse_time_bimapping is not None:
                if pulse_time_bimapping is True:
                    raise NotImplementedError("Parameter mapping in bioptim not yet implemented")
                    # parameter_bimapping.add(name="pulse_duration", to_second=[0 for _ in range(n_stim)], to_first=[0])

        if isinstance(model, DingModelIntensityFrequency):
            if pulse_intensity is None and pulse_intensity_min is None and pulse_intensity_max is None:
                raise ValueError("Intensity pulse or Intensity pulse min max bounds need to be set for this model")
            if pulse_intensity is not None and pulse_intensity_min is not None and pulse_intensity_max is not None:
                raise ValueError(
                    "Either Intensity pulse or Intensity pulse min max bounds need to be set for this model"
                )
            if (
                pulse_intensity_min is not None
                and pulse_intensity_max is None
                or pulse_intensity_min is None
                and pulse_intensity_max is not None
            ):
                raise ValueError("Both Intensity pulse min max bounds need to be set for this model")

            minimum_pulse_intensity = model.min_pulse_intensity()

            if pulse_intensity is not None:
                if not isinstance(pulse_intensity, int | float):
                    raise TypeError("pulse_intensity must be int or float type")
                if pulse_intensity < minimum_pulse_intensity:
                    raise ValueError(
                        f"The pulse intensity set ({pulse_intensity})"
                        f" is lower than minimum intensity required."
                        f" Set a value above {minimum_pulse_intensity} mA "
                    )

            elif pulse_intensity_min is not None and pulse_intensity_max is not None:
                if not isinstance(pulse_intensity_min, int | float) or not isinstance(pulse_intensity_max, int | float):
                    raise TypeError("pulse_intensity_min and pulse_intensity_max must be int or float type")
                if pulse_intensity_max < pulse_intensity_min:
                    raise ValueError("The set minimum pulse intensity is higher than maximum pulse intensity.")
                if pulse_intensity_min < minimum_pulse_intensity:
                    raise ValueError(
                        f"The pulse intensity set ({pulse_intensity_min})"
                        f" is lower than minimum intensity required."
                        f" Set a value above {minimum_pulse_intensity} mA "
                    )
            else:
                raise ValueError(
                    "Intensity pulse parameter has not been set, input either pulse_intensity or pulse_intensity_min"
                    " and pulse_intensity_max"
                )

            if pulse_intensity_bimapping is not None:
                if pulse_intensity_bimapping is True:
                    raise NotImplementedError("Parameter mapping in bioptim not yet implemented")

        if force_tracking is not None:
            if isinstance(force_tracking, list):
                if isinstance(force_tracking[0], np.ndarray) and isinstance(force_tracking[1], np.ndarray):
                    if len(force_tracking[0]) != len(force_tracking[1]) and len(force_tracking) != 2:
                        raise ValueError(
                            "force_tracking time and force argument must be same length and force_tracking "
                            "list size 2"
                        )
                else:
                    raise TypeError("force_tracking argument must be np.ndarray type")
            else:
                raise TypeError("force_tracking must be list type")

        if end_node_tracking:
            if not isinstance(end_node_tracking, int | float):
                raise TypeError("end_node_tracking must be int or float type")

        if custom_objective:
            if not isinstance(custom_objective, list):
                raise TypeError("custom_objective must be a list type")
            if not all(isinstance(x, Objective) for x in custom_objective):
                raise TypeError("All elements in objective must be an Objective type")

        if not isinstance(ode_solver, (OdeSolver.RK1, OdeSolver.RK2, OdeSolver.RK4, OdeSolver.COLLOCATION)):
            raise TypeError("ode_solver must be a OdeSolver type")

        if not isinstance(use_sx, bool):
            raise TypeError("use_sx must be a bool type")

        if not isinstance(n_threads, int):
            raise TypeError("n_thread must be a int type")

    @staticmethod
    def _sanity_check_2(n_stim, final_time, frequency, round_down):
        if n_stim is None and final_time is None and frequency is None:
            raise ValueError("At least two variable must be set from n_stim, final_time or frequency")

        if n_stim and final_time and frequency:
            if n_stim != final_time * frequency:
                raise ValueError(
                    "Can not satisfy n_stim equal to final_time * frequency with the given parameters."
                    "Consider setting only two of the three parameters"
                )

        if round_down:
            if not isinstance(round_down, bool):
                raise TypeError("round_down must be bool type")

    @staticmethod
    def _build_fourrier_coeff(force_tracking):
        return FourierSeries().compute_real_fourier_coeffs(force_tracking[0], force_tracking[1], 50)

    @staticmethod
    def _build_phase_time(final_time, n_stim, pulse_mode, time_min, time_max, time_bimapping):
        constraints = ConstraintList()
        final_time_phase = None
        # parameter_bimapping = BiMappingList()
        phase_time_bimapping = None

        if time_min is None and time_max is None:
            if pulse_mode == "Single":
                step = final_time / n_stim
                final_time_phase = (step,)
                for i in range(n_stim - 1):
                    final_time_phase = final_time_phase + (step,)

            elif pulse_mode == "Doublet":
                doublet_step = 0.005
                step = final_time / (n_stim / 2) - doublet_step
                final_time_phase = (doublet_step,)
                for i in range(int(n_stim / 2)):
                    final_time_phase = final_time_phase + (step,)
                    final_time_phase = final_time_phase + (doublet_step,)

            elif pulse_mode == "Triplet":
                doublet_step = 0.005
                triplet_step = 0.005
                step = final_time / (n_stim / 3) - doublet_step - triplet_step
                final_time_phase = (
                    doublet_step,
                    triplet_step,
                )
                for i in range(int(n_stim / 3)):
                    final_time_phase = final_time_phase + (step,)
                    final_time_phase = final_time_phase + (doublet_step,)
                    final_time_phase = final_time_phase + (triplet_step,)

        else:
            for i in range(n_stim):
                constraints.add(
                    ConstraintFcn.TIME_CONSTRAINT,
                    node=Node.END,
                    min_bound=time_min,
                    max_bound=time_max,
                    phase=i,
                )

            if time_bimapping is True:
                phase_time_bimapping = BiMapping(to_second=[0 for _ in range(n_stim)], to_first=[0])

            final_time_phase = [0.01] * n_stim

        return final_time_phase, constraints, phase_time_bimapping

    @staticmethod
    def _build_parameters(
        model,
        n_stim,
        pulse_time,
        pulse_time_min,
        pulse_time_max,
        pulse_time_bimapping,
        pulse_intensity,
        pulse_intensity_min,
        pulse_intensity_max,
        pulse_intensity_bimapping,
    ):
        parameters = ParameterList()
        parameters_bounds = BoundsList()
        parameters_init = InitialGuessList()
        parameter_objectives = ParameterObjectiveList()
        if isinstance(model, DingModelPulseDurationFrequency):
            if pulse_time is None and pulse_time_min is not None and pulse_time_max is None:
                raise ValueError("Time pulse or Time pulse min max bounds need to be set for this model")
            if pulse_time is not None and pulse_time_min is not None and pulse_time_max is not None:
                raise ValueError("Either Time pulse or Time pulse min max bounds need to be set for this model")
            if (
                pulse_time_min is not None
                and pulse_time_max is None
                or pulse_time_min is None
                and pulse_time_max is not None
            ):
                raise ValueError("Both Time pulse min max bounds need to be set for this model")

            minimum_pulse_duration = DingModelPulseDurationFrequency().pd0

            if pulse_time is not None:
                if isinstance(pulse_time, int | float):
                    if pulse_time < minimum_pulse_duration:
                        raise ValueError(
                            f"The pulse duration set ({pulse_time})"
                            f" is lower than minimum duration required."
                            f" Set a value above {minimum_pulse_duration} seconds "
                        )

                    parameters_bounds.add(
                        "pulse_duration",
                        min_bound=np.array([pulse_time] * n_stim),
                        max_bound=np.array([pulse_time] * n_stim),
                        interpolation=InterpolationType.CONSTANT,
                    )
                    parameters_init["pulse_duration"] = np.array([pulse_time] * n_stim)
                    parameters.add(
                        parameter_name="pulse_duration",
                        function=DingModelPulseDurationFrequency.set_impulse_duration,
                        size=n_stim,
                    )
                else:
                    raise ValueError("Wrong pulse_time type, only int or float accepted")

            elif pulse_time_min is not None and pulse_time_max is not None:
                if not isinstance(pulse_time_min, int | float) or not isinstance(pulse_time_max, int | float):
                    raise ValueError("pulse_time_min and pulse_time_max must be equal int or float type")
                if pulse_time_max < pulse_time_min:
                    raise ValueError("The set minimum pulse duration is higher than maximum pulse duration.")
                if pulse_time_min < minimum_pulse_duration:
                    raise ValueError(
                        f"The pulse duration set ({pulse_time_min})"
                        f" is lower than minimum duration required."
                        f" Set a value above {minimum_pulse_duration} seconds "
                    )

                parameters_bounds.add(
                    "pulse_duration",
                    min_bound=[pulse_time_min],
                    max_bound=[pulse_time_max],
                    interpolation=InterpolationType.CONSTANT,
                )
                parameters_init["pulse_duration"] = np.array([0] * n_stim)
                parameters.add(
                    parameter_name="pulse_duration",
                    function=DingModelPulseDurationFrequency.set_impulse_duration,
                    size=n_stim,
                )

            else:
                raise ValueError(
                    "Time pulse parameter has not been set, input either pulse_time or pulse_time_min and"
                    " pulse_time_max"
                )

            parameter_objectives.add(
                ObjectiveFcn.Parameter.MINIMIZE_PARAMETER,
                weight=0.0001,
                quadratic=True,
                target=0,
                key="pulse_duration",
            )

            if pulse_time_bimapping is not None:
                if pulse_time_bimapping is True:
                    raise ValueError("Parameter mapping in bioptim not yet implemented")
                    # parameter_bimapping.add(name="pulse_duration", to_second=[0 for _ in range(n_stim)], to_first=[0])
                    # TODO : Fix Bimapping in Bioptim

        if isinstance(model, DingModelIntensityFrequency):
            if pulse_intensity is None and pulse_intensity_min is None and pulse_intensity_max is None:
                raise ValueError("Intensity pulse or Intensity pulse min max bounds need to be set for this model")
            if pulse_intensity is not None and pulse_intensity_min is not None and pulse_intensity_max is not None:
                raise ValueError(
                    "Either Intensity pulse or Intensity pulse min max bounds need to be set for this model"
                )
            if (
                pulse_intensity_min is not None
                and pulse_intensity_max is None
                or pulse_intensity_min is None
                and pulse_intensity_max is not None
            ):
                raise ValueError("Both Intensity pulse min max bounds need to be set for this model")

            is_ = DingModelIntensityFrequency().Is
            bs = DingModelIntensityFrequency().bs
            cr = DingModelIntensityFrequency().cr
            minimum_pulse_intensity = (np.arctanh(-cr) / bs) + is_

            if pulse_intensity is not None:
                if not isinstance(pulse_intensity, int | float):
                    raise ValueError("pulse_intensity must be int or float type")
                if pulse_intensity < minimum_pulse_intensity:
                    raise ValueError(
                        f"The pulse intensity set ({pulse_intensity})"
                        f" is lower than minimum intensity required."
                        f" Set a value above {minimum_pulse_intensity} mA "
                    )
                parameters_bounds.add(
                    "pulse_intensity",
                    min_bound=np.array([pulse_intensity] * n_stim),
                    max_bound=np.array([pulse_intensity] * n_stim),
                    interpolation=InterpolationType.CONSTANT,
                )
                parameters_init["pulse_intensity"] = np.array([pulse_intensity] * n_stim)
                parameters.add(
                    parameter_name="pulse_intensity",
                    function=DingModelIntensityFrequency.set_impulse_intensity,
                    size=n_stim,
                )

            elif pulse_intensity_min is not None and pulse_intensity_max is not None:
                if not isinstance(pulse_intensity_min, int | float) or not isinstance(pulse_intensity_max, int | float):
                    raise ValueError("pulse_intensity_min and pulse_intensity_max must be int or float type")
                if pulse_intensity_max < pulse_intensity_min:
                    raise ValueError("The set minimum pulse intensity is higher than maximum pulse intensity.")
                if pulse_intensity_min < minimum_pulse_intensity:
                    raise ValueError(
                        f"The pulse intensity set ({pulse_intensity_min})"
                        f" is lower than minimum intensity required."
                        f" Set a value above {minimum_pulse_intensity} mA "
                    )

                parameters_bounds.add(
                    "pulse_intensity",
                    min_bound=[pulse_intensity_min],
                    max_bound=[pulse_intensity_max],
                    interpolation=InterpolationType.CONSTANT,
                )
                intensity_avg = (pulse_intensity_min + pulse_intensity_max) / 2
                parameters_init["pulse_intensity"] = np.array([intensity_avg] * n_stim)
                parameters.add(
                    parameter_name="pulse_intensity",
                    function=DingModelIntensityFrequency.set_impulse_intensity,
                    size=n_stim,
                )

            else:
                raise ValueError(
                    "Intensity pulse parameter has not been set, input either pulse_intensity or pulse_intensity_min"
                    " and pulse_intensity_max"
                )

            parameter_objectives.add(
                ObjectiveFcn.Parameter.MINIMIZE_PARAMETER,
                weight=0.0001,
                quadratic=True,
                target=0,
                key="pulse_intensity",
            )

            if pulse_intensity_bimapping is not None:
                if pulse_intensity_bimapping is True:
                    raise ValueError("Parameter mapping in bioptim not yet implemented")
                # parameter_bimapping.add(name="pulse_intensity", to_second=[0 for _ in range(n_stim)], to_first=[0])
                # TODO : Fix Bimapping in Bioptim

        return parameters, parameters_bounds, parameters_init, parameter_objectives

    @staticmethod
    def _declare_dynamics(models, n_stim):
        dynamics = DynamicsList()
        for i in range(n_stim):
            dynamics.add(
                models[i].declare_ding_variables,
                dynamic_function=models[i].dynamics,
                expand_dynamics=True,
                expand_continuity=False,
                phase=i,
                phase_dynamics=PhaseDynamics.ONE_PER_NODE,
            )
        return dynamics

    @staticmethod
    def _set_bounds(model, n_stim):
        # ---- STATE BOUNDS REPRESENTATION ---- #
        #
        #                    |‾‾‾‾‾‾‾‾‾‾x_max_middle‾‾‾‾‾‾‾‾‾‾‾‾x_max_end‾
        #                    |          max_bounds              max_bounds
        #    x_max_start     |
        #   _starting_bounds_|
        #   ‾starting_bounds‾|
        #    x_min_start     |
        #                    |          min_bounds              min_bounds
        #                     ‾‾‾‾‾‾‾‾‾‾x_min_middle‾‾‾‾‾‾‾‾‾‾‾‾x_min_end‾

        # Sets the bound for all the phases
        x_bounds = BoundsList()
        variable_bound_list = model.name_dof
        starting_bounds, min_bounds, max_bounds = (
            model.standard_rest_values(),
            model.standard_rest_values(),
            model.standard_rest_values(),
        )

        for i in range(len(variable_bound_list)):
            if variable_bound_list[i] == "Cn" or variable_bound_list[i] == "F":
                max_bounds[i] = 1000
            elif variable_bound_list[i] == "Tau1" or variable_bound_list[i] == "Km":
                max_bounds[i] = 1
            elif variable_bound_list[i] == "A":
                min_bounds[i] = 0

        starting_bounds_min = np.concatenate((starting_bounds, min_bounds, min_bounds), axis=1)
        starting_bounds_max = np.concatenate((starting_bounds, max_bounds, max_bounds), axis=1)
        middle_bound_min = np.concatenate((min_bounds, min_bounds, min_bounds), axis=1)
        middle_bound_max = np.concatenate((max_bounds, max_bounds, max_bounds), axis=1)

        for i in range(n_stim):
            for j in range(len(variable_bound_list)):
                if i == 0:
                    x_bounds.add(
                        variable_bound_list[j],
                        min_bound=np.array([starting_bounds_min[j]]),
                        max_bound=np.array([starting_bounds_max[j]]),
                        phase=i,
                        interpolation=InterpolationType.CONSTANT_WITH_FIRST_AND_LAST_DIFFERENT,
                    )
                else:
                    x_bounds.add(
                        variable_bound_list[j],
                        min_bound=np.array([middle_bound_min[j]]),
                        max_bound=np.array([middle_bound_max[j]]),
                        phase=i,
                        interpolation=InterpolationType.CONSTANT_WITH_FIRST_AND_LAST_DIFFERENT,
                    )

        x_init = InitialGuessList()
        for i in range(n_stim):
            for j in range(len(variable_bound_list)):
                x_init.add(variable_bound_list[j], model.standard_rest_values()[j], phase=i)

        return x_bounds, x_init

    @staticmethod
    def _set_objective(n_stim, n_shooting, force_fourier_coef, end_node_tracking, custom_objective):
        # Creates the objective for our problem
        objective_functions = ObjectiveList()
        if custom_objective:
            for i in range(len(custom_objective)):
                objective_functions.add(custom_objective[i])

        if force_fourier_coef is not None:
            for phase in range(n_stim):
                for i in range(n_shooting[phase]):
                    objective_functions.add(
                        CustomObjective.track_state_from_time,
                        custom_type=ObjectiveFcn.Mayer,
                        node=i,
                        fourier_coeff=force_fourier_coef,
                        key="F",
                        quadratic=True,
                        weight=1,
                        phase=phase,
                    )

        if end_node_tracking:
            if isinstance(end_node_tracking, int | float):
                objective_functions.add(
                    ObjectiveFcn.Mayer.MINIMIZE_STATE,
                    node=Node.END,
                    key="F",
                    quadratic=True,
                    weight=1,
                    target=end_node_tracking,
                    phase=n_stim - 1,
                )

        return objective_functions

    @staticmethod
    def _build_phase_parameter(n_stim, final_time, frequency=None, pulse_mode="Single", round_down=False):
        pulse_mode_multiplier = 1 if pulse_mode == "Single" else 2 if pulse_mode == "Doublet" else 3
        if n_stim and frequency:
            final_time = n_stim / frequency / pulse_mode_multiplier

        if final_time and frequency:
            n_stim = final_time * frequency * pulse_mode_multiplier
            if round_down or n_stim.is_integer():
                n_stim = int(n_stim)
            else:
                raise ValueError(
                    "The number of stimulation needs to be integer within the final time t, set round down"
                    "to True or set final_time * frequency to make the result a integer."
                )

        return n_stim, final_time