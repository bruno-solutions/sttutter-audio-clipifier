"""
    Slicer module's homonymous submodule.

    Note: This file is incredibly messy currently
    since multiple people rushed to work on it on
    Friday the 4th of June, 2022.

    Contact Zack Wang at wang5511@purdue.edu for an
    explanation of how this file should eventually
    be structured.
"""

import math
import random
import numpy
import pydub
import librosa
from pydub.utils import register_pydub_effect
from spleeter.audio.adapter import AudioAdapter
from spleeter.separator import Separator


class CriticalTimeIndexes:
    """Saves, mixes, and convert critical time indexes into intervals."""

    def __init__(self):
        self.host = None
        # self.cti = {}
        # self.interval = {}
        self.cti = []
        self.interval = []

    @staticmethod
    def abs_derivative(data):
        """Get the absolute value of the rate of change of each point."""
        raise SyntaxError("Not implemented.")

    """We need to put the function generate_from_beats down somewhere
    We need to create a smart way of putting the critical points into intervals,
    we can use the dict for weighting (diff properties correspond to different weights)"""

    def append(self, item):
        """Appends a critical time to the list of CTIs."""
        self.cti.append(item)

    """Made this not a property for now, will need to decide what to do with this"""

    # @property
    def intervals(self):
        """Generate critical intervals from the critical time indexes.
        Initially, I'm going to try to use a for loop to get every two cti's and put them in as intervals"""
        for i in range(0, len(self.cti)):
            # self.interval.update({"type": "bar_change",
            #                       "timeindex": [self.cti[i], self.cti[i + 1]],
            #                       "weight": "weight"})
            # if 8.5 <= math.fabs(self.cti[i] - self.cti[i + 1]) <= 9:
            self.interval.append([self.cti[i][0], self.cti[i][1]])

    def get_start_point(self, x, arr):
        """
        A binary search to find the nearby point of the target x in array arr
        input:
            x: target number
            arr: target array
        output:
            [low, mid, high]
            if any of these points is not exsit in the range of 0.1, -1 will be returned.
            Otherwise an index will be returned.
        """
        if len(arr) == 0:
            return -1

        low = 0
        mid = 0
        high = len(arr) - 1
        is_found = False

        while low <= high:

            mid = (high + low) // 2

            if arr[mid] < x:
                low = mid + 1

            elif arr[mid] > x:
                high = mid - 1

            else:
                is_found = True
                break

        high += 1

        if is_found:  # x is exist on the arr
            if x == arr[low] or x - arr[low] > 0.1:
                low = -1
            if x == arr[high] or arr[high] - x > 0.1:
                high = -1
        else:  # x is not exist on the arr
            if low != 0 and x - arr[low - 1] > 0.1:
                low = -1
            if high == len(arr) or arr[high + 1] - x > 0.1:
                high = -1
            mid = -1

        return low, mid, high


class VolumeChangeDetector:
    """A handler that hosts the volume change slicer."""

    def __init__(self, data):
        self.data = data
        self.parse_data()

    @staticmethod
    def angled_lp_filter(db_profile, weight=0.1):
        """Filter out unusually high and short volume spikes."""

        buoy = -20.

        for volume in db_profile:
            if buoy < volume <= buoy + weight:
                buoy = volume

            elif buoy + weight < volume:
                buoy += weight

        return buoy

    def parse_data(self, filter_width=441):
        """Extract data and convert it to desired formats."""

        # Convert and filter each section of the data.
        self.filtered = [self.angled_lp_filter(db_profile) \
                         for db_profile in \
                         numpy.pad(
                             librosa.amplitude_to_db(self.data),
                             (0, len(self.data) % filter_width)
                         ).reshape(
                             (len(self.data) - 1) // filter_width + 1,
                             filter_width
                         )
                         ]

    def write_critical_time(self, cti):
        """Writes volume change information to CTI."""
        """Trying to append the volume spikes onto cti but I'm not sure if it is appending one buoy or multiple 
        volume changes """
        for i in range(0, len(self.data)):
            cti.append(self.angled_lp_filter(self.data))


class voice_slicer:
    """The object for slicing due to the vocals"""

    def __init__(self):
        self.prediction = None
        self.separator()

    def separator(self):
        # Uses spleeter to separate the wav file into its distinct parts and
        # create a dict. out of it
        separator = Separator('spleeter:2stems', multiprocess=False)
        file = "./cache/ytdl-fullsong.wav"
        audio_loader = AudioAdapter.default()
        sample_rate = 44100
        waveform, _ = audio_loader.load(file, sample_rate=sample_rate)
        self.prediction = separator.separate(waveform, file)

    def write_critical_time(self, cti):
        # Writes a critical time whenever the volume of the vocals is zero (depends
        # on user-input for time)
        threshold = 0.01
        time_user_input = 9
        amount_of_crits = self.prediction['vocals'].shape[0]
        i = 0
        while not i > amount_of_crits:
            if math.fabs(self.prediction['vocals'][i][0]) <= threshold:
                if i + 44100 * time_user_input + 44100 // 2 <= amount_of_crits:
                    j = i + 44100 * time_user_input - 44100 // 2  # introduce var here to have an anchor point and then use the
                    # anchor point to search in the next for loop
                else:
                    break

                # So if the crit_time has amp. of 0 then search for 0 amp. with the time parameter
                while self.prediction['vocals'][j][0] != self.prediction['vocals'][i + 44100 // 2][0]:
                    if self.prediction['vocals'][j][0] <= threshold:
                        cti.append([i / 44100 * 1000, j / 44100 * 1000])
                        # Go ahead one second in the song
                        break
                    else:
                        # Go to the next sample to test with j
                        j += 44100 // 4
                i += 44100 * 2
            else:
                i += 44100 // 4


class Slicer:
    """The primary object of the slicer module."""

    def __init__(self, base_seg, count):
        self.base_seg = base_seg
        self.count = count

        self.data = None
        self.convert_data()

        self.critical = CriticalTimeIndexes()
        self.clips = []

    def generate_from_beats(self):
        """
        Author Johnson Lin | Get every beat in a song and use that to input a bar of beats
        as critical times
        """

        # Convert the data to appropriate formatting
        self.convert_data()

        # The duration of time (we can also make it an argument)
        time_duration = 21

        # Sampling rate
        sr = 44100

        beat = librosa.beat.beat_track(y=self.data, sr=sr)[1]

        # Change the beats from frames to time (ms)
        beat_time = librosa.frames_to_time(beat, sr=sr) * 1000

        # Get every fourth beat and use append class method to append it to CTI
        for i in range(0, len(beat), time_duration):
            self.critical.append(item=beat_time[i])

        """Need to find the proper location for this"""
        self.critical.intervals()

        return self

    @classmethod
    def invoke_slicers(cls, slicer_methods):
        """
        A method invoker that wraps and registers a
        custom slicer method in pydub's effects list.
        """

        if isinstance(slicer_methods, dict):
            for named_method in slicer_methods.items():
                cls.invoke_slicers(named_method)

        elif isinstance(slicer_methods, tuple):
            name, method = slicer_methods

            @pydub.utils.register_pydub_effect(name)
            def slicer_method_wrap(seg, count, *args, **kwargs):
                return getattr(cls(seg, count), method)(*args, **kwargs). \
                    execute_slicing().clips

        else:
            raise TypeError

    def convert_data(self):
        """Converts the data info librosa-compatible format."""
        data_raw_stereo = numpy.array(
            self.base_seg.get_array_of_samples()
        )

        data_raw_left = data_raw_stereo[::2]

        data_raw_right = data_raw_stereo[1::2]

        data_raw_mono = (
                                data_raw_left + data_raw_right
                        ) / 2

        # Convert int16 or int32 data to float (-1. ~ 1.)
        self.data = data_raw_mono / (1 << (
                self.base_seg.sample_width * 8
        ) - 1)

    def execute_slicing(self):
        """Execute slicing."""

        """Took off extra s at the end of interval in order to be able to call it at the critical time index class"""
        for i in self.critical.interval:
            self.clips.append(
                self.base_seg[i[0]:i[1]]
            )

        return self

    def slice_at_random(self):
        """
        Create slices at random.
        This slicer method is meant to be a template
        for the creation of other slicer methods.
        """

        # Access data, equivalent to data=librosa.load()
        # Alternatively, self.data can be used in place
        # of 'data' directly.
        data = self.data  # pylint: disable=unused-variable

        # The total amount of clips desired is stored
        # in self.count. Loop for self.count.
        for index in range(self.count):  # pylint: disable=unused-variable

            # Calculate random range.
            duration_ms = int(
                self.base_seg.duration_seconds * 1000
            )

            start_ms = random.randint(
                0, duration_ms - 1000
            )

            end_ms = start_ms + random.randint(
                1000, 10000  # 1 to 10 seconds long.
            )

            # Append clip ranges to self.intervals.

            raise SyntaxError("PENDING CHANGE: Append to self.critical instead of self.intervals.")

            # e.g.
            #   self.critical.append({
            #       "type": "major_volume_change",
            #       "index": _time,
            #       "weight": _weight
            #   })

        # Mandatory return-self.
        return self

    def slice_at_volume_change(self):
        """Slice the audio at moments of rapid volume changes."""
        VolumeChangeDetector(self.data). \
            write_critical_time(self.critical.cti)
        return self

    def slice_at_voice(self):
        """Slice the audio according to the vocals of a song"""
        voice_slicer(). \
            write_critical_time(self.critical.cti)
        self.critical.intervals()
        return self

#     # all functions to find critical points
#     def major_pitch_change(self):
#         """
#         Output is in ms
#         Identify major pitch change time
#         return 4/173 or 23 ms if pitch change occurs at the first/second frame
#         search pitch detection algorithm (PDA)
#         Note:
#             If multi-channel input is provided,
#             frequency curves are estimated separately for each channel,
#             so to prevent error, we might need to pass in single channel input
#         """
#         pitches = librosa.yin(self.data,fmin=40, fmax=2200, sr=22050, frame_length=2048)
#         difference = math.fabs(pitches[2]-pitches[1])
#         pos = -1
#         for i in range(1, pitches.size-1):
#             if (math.fabs(pitches[i+1]-pitches[i]))>difference:
#                 difference = math.fabs(pitches[i+1]-pitches[i])
#                 pos = i+1
#         if pos == -1:
#             return 4/173
#         else:
#             return pos * (4/173)

#     def onset_detection(self):
#         """
#         Onset (major sound change) Detection (librosa has this exact function we can use)
#         return an numpy array of onset appearances in time in ms
#         only works for monophonic sound (I think this means single channel sound)
#         """
#         return librosa.onset.onset_detect(y = self.data, sr = 44100, units ='time')
#         #multiplied_onsets = onsets*1000
#         #return multiplied_onsets        

#     def major_tempo_change(self):
#          """
#          Output is in ms
#          Identify major tempo (beats per minute) change time
#          return -1 if no tempo change
#          return location of biggest tempo change
#          Note that most songs could have the same tempo throughout
#          """
#          onset_env = librosa.onset.onset_strength(y = self.data, sr=44100)
#          tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=44100,aggregate=None)

#          difference = math.fabs(tempo[1]-tempo[0])

#          pos=-1
#          for i in range(tempo.size-1):
#              if (math.fabs(tempo[i+1]-tempo[i])) >= difference+2:
#                  difference = math.fabs(tempo[i+1]-tempo[i])
#                  pos = i+1
#          if difference == math.fabs(tempo[1]-tempo[0]):
#              return -1

#          time_from_frame = librosa.frames_to_time(pos, sr=44100)
#          return time_from_frame

# # functions that can be used for debugging if needed in the future

#     def get_real_time_tempo(self):
#         onset_env = librosa.onset.onset_strength(y=self.data,sr=44100)
#         tempo = librosa.beat.tempo(onset_envelope=onset_env,sr=44100,aggregate=None)
#         return tempo

#     def get_tempo(self):
#         return librosa.beat.beat_track(y = self.data, sr = 44100)[0]


#     def get_beat_time(self):
#         beats = librosa.beat.beat_track(y = self.data, sr = 44100)[1]
#         return librosa.frames_to_time(beats, sr=44100)

#     def get_pitch(self):
#         return librosa.yin(self.data,fmin=40, fmax=2200, sr=22050, frame_length=2048)

#     def get_amplitude(self):
#         return self

#     def get_volume(self):
#         return librosa.amplitude_to_db(S=self.data,ref=0)

# @classmethod
# def generate_from_beats(cls, data):
#     """
#     Author: Johnson Lin

#     Return a list of pair list of critical times in ms.
#     E.g. [[star1, end1],[star2, end2], [star3, end3]...]
#     """

#     beat = librosa.beat.beat_track(y=data, sr=44100)[1] * 1000

#     critical_time = []

#     ### Get every fourth beat and return it in critical_time
#     for i in range(4, len(beat), 8):
#         critical_time.append([beat[i - 4], beat[i] + 500])
#     return critical_time
