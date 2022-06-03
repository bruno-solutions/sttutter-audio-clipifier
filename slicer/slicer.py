"""Slicer homonymous submodule."""

import random
import numpy
import pydub
import librosa
from matplotlib.pyplot import plot, show


class CriticalTimeIndexes:
    """Saves, mixes, and convert critical time indexes into intervals."""

    def get_array_of_critical_point(self, major_pitch_change, major_tempo_change, generate_from_beats, major_volume_change):
        self.critical_point = numpy.append(major_pitch_change, major_tempo_change, generate_from_beats, major_volume_change)
        self.critical_point = numpy.sort(self.critical_point)

    def __init__(self):
        self.host = None

    @classmethod
    def generate_from_beats(cls, data):
        """
        Author: Johnson Lin

        Return a list of pair list of critical times in ms.
        E.g. [[star1, end1],[star2, end2], [star3, end3]...]
        """

        beat = librosa.beat.beat_track(y=data, sr=44100)[1] * 1000

        critical_time = []

        ### Get every fourth beat and return it in critical_time
        for i in range(4, len(beat), 8):
            critical_time.append([beat[i - 4], beat[i] + 500])
        return critical_time


class VolumeChangeDetector:
    """A handler that hosts the volume change slicer."""

    def __init__(self, host):
        self.host = host

        self.db_profile = None
        self.critical = CriticalTimeIndexes()

        self.parse_data()

    @staticmethod
    def angled_lp_filter(db_profile, weight=0.1):
        """Filter out unusually high and short volume spikes."""

        buoy = -20.

        for volume in db_profile:
            if buoy < volume <= buoy+weight:
                buoy = volume

            elif buoy+weight < volume:
                buoy += weight

        return buoy

    def parse_data(self, filter_width=441):
        """Extract data and convert it to desired formats."""

        this_data_1 = numpy.pad(librosa.amplitude_to_db(self.host.data), (0,len(self.host.data)%filter_width)).reshape((len(self.host.data)-1)//filter_width+1, filter_width)
        self.filtered = [self.angled_lp_filter(db_profile) for db_profile in this_data_1]

        pass

    def generate_intervals(self):
        """DEBUG FUNC"""


class Slicer:
    """The primary object of the slicer module."""

    def __init__(self, base_seg, count):
        self.base_seg = base_seg
        self.count = count

        self.data = None
        self.convert_data()

        self.intervals = []
        self.clips = []

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

        data_raw_left  = data_raw_stereo[::2]
        data_raw_right = data_raw_stereo[1::2]

        data_raw_mono = (
            data_raw_left + data_raw_right
        ) / 2

        # Convert int16 or int32 data to float (-1. ~ 1.)
        self.data = data_raw_mono / ( 1 << (
            self.base_seg.sample_width * 8
        ) - 1 )

    def execute_slicing(self):
        """Execute slicing."""

        ### Use clip intervals to segment the clip
        for i in self.intervals:
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
        data = self.data # pylint: disable=unused-variable

        # The total amount of clips desired is stored
        # in self.count. Loop for self.count.
        for index in range(self.count): # pylint: disable=unused-variable

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
            self.intervals.append((start_ms, end_ms))

        # Mandatory return-self.
        return self

    def slice_at_volume_change(self):
        """Slice the audio at moments of rapid volume changes."""
        VolumeChangeDetector(self).generate_intervals()
        return self

    # all functions to find critical points
    def major_pitch_change(self):
        """
        Output is in ms
        Identify major pitch change time
        return 4/173 or 23 ms if pitch change occurs at the first/second frame
        search pitch detection algorithm (PDA)
        Note:
            If multi-channel input is provided,
            frequency curves are estimated separately for each channel,
            so to prevent error, we might need to pass in single channel input
        """
        pitches = librosa.yin(self.data,fmin=40, fmax=2200, sr=22050, frame_length=2048)
        difference = math.fabs(pitches[2]-pitches[1])
        pos = -1
        for i in range(1, pitches.size-1):
            if (math.fabs(pitches[i+1]-pitches[i]))>difference:
                difference = math.fabs(pitches[i+1]-pitches[i])
                pos = i+1
        if pos == -1:
            return 4/173
        else:
            return pos * (4/173)
    
    def onset_detection(self):
        """
        Onset (major sound change) Detection (librosa has this exact function we can use)
        return an numpy array of onset appearances in time in ms
        only works for monophonic sound (I think this means single channel sound)
        """
        return librosa.onset.onset_detect(y = self.data, sr = 44100, units ='time')
        #multiplied_onsets = onsets*1000
        #return multiplied_onsets        
    
    def major_tempo_change(self):
         """
         Output is in ms
         Identify major tempo (beats per minute) change time
         return -1 if no tempo change
         return location of biggest tempo change
         Note that most songs could have the same tempo throughout
         """
         onset_env = librosa.onset.onset_strength(y = self.data, sr=44100)
         tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=44100,aggregate=None)

         difference = math.fabs(tempo[1]-tempo[0])

         pos=-1
         for i in range(tempo.size-1):
             if (math.fabs(tempo[i+1]-tempo[i])) >= difference+2:
                 difference = math.fabs(tempo[i+1]-tempo[i])
                 pos = i+1
         if difference == math.fabs(tempo[1]-tempo[0]):
             return -1

         time_from_frame = librosa.frames_to_time(pos, sr=44100)
         return time_from_frame
    
# functions that can be used for debugging if needed in the future

    def get_real_time_tempo(self):
        onset_env = librosa.onset.onset_strength(y=self.data,sr=44100)
        tempo = librosa.beat.tempo(onset_envelope=onset_env,sr=44100,aggregate=None)
        return tempo

    def get_tempo(self):
        return librosa.beat.beat_track(y = self.data, sr = 44100)[0]
        
    
    def get_beat_time(self):
        beats = librosa.beat.beat_track(y = self.data, sr = 44100)[1]
        return librosa.frames_to_time(beats, sr=44100)

    def get_pitch(self):
        return librosa.yin(self.data,fmin=40, fmax=2200, sr=22050, frame_length=2048)

    def get_amplitude(self):
        return self

    def get_volume(self):
        return librosa.amplitude_to_db(S=self.data,ref=0)
