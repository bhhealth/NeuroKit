# -*- coding: utf-8 -*-
import numpy as np
import matplotlib.pyplot as plt
from scipy.interpolate import Akima1DInterpolator
from neurokit2.signal import signal_distort


def ppg_simulate(duration=120, sampling_rate=1000, heart_rate=70,
                 frequency_modulation=0.3, ibi_randomness=0.1,
                 drift=0, motion_amplitude=0.1,
                 powerline_amplitude=0.01, burst_number=0, burst_amplitude=1,
                 random_state=None, show=False):
    """Simulate a photoplethysmogram (PPG) signal.

    Phenomenological approximation of PPG. The PPG wave is described with four
    landmarks: wave onset, location of the systolic peak, location of the
    dicrotic notch and location of the diastolic peaks. These landmarks are
    defined as x and y coordinates (in a  time series). These coordinates are
    then interpolated at the desired sampling rate to obtain the PPG signal.

    Parameters
    ----------
    duration : int
        Desired recording length in seconds. The default is 120.
    sampling_rate : int
        The desired sampling rate (in Hz, i.e., samples/second). The default is
        1000.
    heart_rate : int
        Desired simulated heart rate (in beats per minute). The default is 70.
    frequency_modulation : float
        Float between 0 and 1. Determines how pronounced respiratory sinus
        arrythmia (RSA) is (0 corresponds to absence of RSA). The default is
        0.3.
    ibi_randomness : float
        Float between 0 and 1. Determines how much random noise there is in the
        duration of each PPG wave (0 corresponds to absence of variation). The
        default is 0.1.
    drift : float
        Float between 0 and 1. Determines how pronounced the baseline drift
        (.05 Hz) is (0 corresponds to absence of baseline drift). The default
        is 1.
    motion_amplitude : float
        Float between 0 and 1. Determines how pronounced the motion artifact
        (0.5 Hz) is (0 corresponds to absence of motion artifact). The default
        is 0.1.
    powerline_amplitude : float
        Float between 0 and 1. Determines how pronounced the powerline artifact
        (50 Hz) is (0 corresponds to absence of powerline artifact). Note that
        powerline_amplitude > 0 is only possible if 'sampling_rate' is >= 500.
        The default is 0.1.
    burst_amplitude : float
        Float between 0 and 1. Determines how pronounced high frequency burst
        artifacts are (0 corresponds to absence of bursts). The default is 1.
    burst_number : int
        Determines how many high frequency burst artifacts occur. The default
        is 0.
    show : bool
        If true, returns a plot of the landmarks and interpolated PPG. Useful
        for debugging.
    random_state : int
        Seed for the random number generator. Keep it fixed for reproducible
        results.

    Returns
    -------
    ppg : array
        A vector containing the PPG.

    Examples
    --------
    >>> import neurokit2 as nk
    >>>
    >>> ppg = ppg = nk.ppg_simulate(duration=40, sampling_rate=500,
    >>>                             heart_rate=75, random_state=42, show=True)

    See Also
    --------
    ecg_simulate, rsp_simulate, eda_simulate, emg_simulate
    """
    # At the requested sampling rate, how long is a period at the requested
    # heart-rate and how often does that period fit into the requested
    # duration?
    period = 60 / heart_rate   # in seconds
    n_period = int(np.floor(duration / period))
    periods = np.ones(n_period) * period

    # Seconds at which waves begin.
    x_onset = np.cumsum(periods)
    # Add respiratory sinus arrythmia (frequency modulation).
    periods, x_onset = _frequency_modulation(x_onset, periods,
                                             modulation_frequency=.05,
                                             modulation_strength=frequency_modulation)
    # Randomly modulate duration of waves by subracting a random value between
    # 0 and 20% of the wave duration (see function definition).
    x_onset = _random_x_offset(x_onset, np.diff(x_onset), ibi_randomness)
    # Corresponding signal amplitudes.
    y_onset = np.random.normal(0, .1, n_period)

    # Seconds at which the systolic peaks occur within the waves.
    x_sys = x_onset + 0.175 * periods
    # Corresponding signal amplitudes.
    y_sys = y_onset + np.random.normal(1.5, .25, n_period)

    # Seconds at which the dicrotic notches occur within the waves.
    x_notch = x_onset + 0.4 * periods
    # Corresponding signal amplitudes (percentage of systolic peak height).
    y_notch = y_sys * np.random.normal(.49, .01, n_period)

    # Seconds at which the diatolic peaks occur within the waves.
    x_dia = x_onset + 0.45 * periods
    # Corresponding signal amplitudes (percentage of systolic peak height).
    y_dia = y_sys * np.random.normal(.51, .01, n_period)

    x_all = np.concatenate((x_onset, x_sys, x_notch, x_dia))
    x_all.sort(kind="mergesort")
    x_all = np.rint(x_all * sampling_rate).astype(int)    # convert seconds to samples

    y_all = np.zeros(n_period * 4)
    y_all[0::4] = y_onset
    y_all[1::4] = y_sys
    y_all[2::4] = y_notch
    y_all[3::4] = y_dia

    if show:
        fig, (ax0, ax1) = plt.subplots(nrows=2, ncols=1, sharex=True)
        ax0.scatter(x_all, y_all, c="r")

    # Interpolate a continuous signal between the landmarks (i.e., Cartesian
    # coordinates).
    f = Akima1DInterpolator(x_all, y_all)
    samples = np.arange(0, int(np.ceil(duration * sampling_rate)))
    ppg = f(samples)
    # Remove NAN (values outside interpolation range, i.e., after last sample).
    ppg[np.isnan(ppg)] = np.nanmean(ppg)

    if show:
        ax0.plot(ppg)

    # Add baseline drift.
    if drift > 0:
        drift_freq = .05
        if drift_freq < (1 / duration) * 2:
            drift_freq = (1 / duration) * 2
        ppg = signal_distort(ppg, sampling_rate=sampling_rate,
                             noise_amplitude=drift,
                             noise_frequency=drift_freq,
                             random_state=random_state,
                             silent=True)
    # Add motion artifacts.
    if motion_amplitude > 0:
        motion_freq = .5
        ppg = signal_distort(ppg, sampling_rate=sampling_rate,
                             noise_amplitude=motion_amplitude,
                             noise_frequency=motion_freq,
                             random_state=random_state,
                             silent=True)
    # Add high frequency bursts.
    if burst_amplitude > 0:
        ppg = signal_distort(ppg, sampling_rate=sampling_rate,
                             artifacts_amplitude=burst_amplitude,
                             artifacts_frequency=100,
                             n_artifacts=burst_number,
                             random_state=random_state,
                             silent=True)
    # Add powerline noise.
    if powerline_amplitude > 0:
        ppg = signal_distort(ppg, sampling_rate=sampling_rate,
                             powerline_amplitude=powerline_amplitude,
                             powerline_frequency=50, random_state=random_state,
                             silent=True)

    if show:
        ax1.plot(ppg)

    return ppg


def _frequency_modulation(seconds, periods, modulation_frequency,
                          modulation_strength):
    """
    modulator_frequency determines the frequeny at which respiratory sinus
    arrythmia occues (in Hz);
    modulator_strength must be between 0 and 1
    """
    # Apply a very conservative Nyquist criterion.
    nyquist = (1 / periods[0]) * .1
    if modulation_frequency > nyquist:
        print(f"Please choose a modulation frequency lower than {nyquist}.")
        return

    # Generate a sine with mean 1.1 and amplitude modulation_strength. i.e.,
    # ranging from 1.1 - modulation_strength to 1.1 + modulation_strength. Note
    # That the mean must be 1.1 rather than 1 in order to not produce periods
    # of duration 0 (i.e., at minimum the duration period is scaled down to
    # .1 * period instead of 0 * period).
    modulator = modulation_strength * np.sin(2 * np.pi * modulation_frequency *
                                             seconds) + 1.1
    periods_modulated = periods * modulator
    seconds_modulated = np.cumsum(periods_modulated)
    seconds_modulated -= seconds_modulated[0]    # make sure seconds start at zero

    return periods_modulated, seconds_modulated


def _random_x_offset(x, x_diff, offset_weight):
    """
    For each xi and the preceding xi-1, subtract offset_weight * (xi - xi-1)
    from xi;
    offset weight must be between 0 and 1
    """
    offsets = []

    for i in x_diff:
        max_offset = offset_weight * i
        offset = np.random.uniform(0, max_offset)    # unpack with [0]
        offsets.append(offset)

    x[1:] -= offsets

    return x


def _amplitude_modulation():
    # TODO
    pass
