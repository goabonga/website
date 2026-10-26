# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for audio_utils.feature."""

import numpy as np
from asterisk.audio_utils import AudioBuffer, resample_8k_to_24k, resample_24k_to_8k
from behave import given, then, when


def _tone(sample_rate: int, samples: int) -> bytes:
    t = np.arange(samples) / sample_rate
    return (np.sin(2 * np.pi * 440 * t) * 16000).astype("<i2").tobytes()


def _samples(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype="<i2")


@given("{size:d} bytes of silence")
def step_silence(context, size):
    context.input_audio = b"\x00" * size


@given("a 440 Hz tone at {rate:d} kHz with {count:d} samples")
def step_tone(context, rate, count):
    context.input_audio = _tone(rate * 1000, count)


@given("{count:d} samples at the maximum amplitude")
def step_max_amplitude(context, count):
    context.input_audio = np.full(count, 32767, dtype="<i2").tobytes()


@given("1 byte of audio")
def step_one_byte(context):
    context.input_audio = b"\x01"


@when("I resample from 8 kHz to 24 kHz")
def step_upsample(context):
    context.output_audio = resample_8k_to_24k(context.input_audio)


@when("I resample from 24 kHz to 8 kHz")
def step_downsample(context):
    context.output_audio = resample_24k_to_8k(context.input_audio)


@then("the output should be {size:d} bytes")
def step_output_size(context, size):
    assert len(context.output_audio) == size


@then("the output should contain {count:d} samples")
def step_output_samples(context, count):
    assert len(_samples(context.output_audio)) == count


@then("all output samples should be zero")
def step_output_zero(context):
    assert len(context.output_audio) > 0
    assert not _samples(context.output_audio).any()


@then("the output should contain non-zero samples")
def step_output_non_zero(context):
    assert _samples(context.output_audio).any()


@then("every output sample should stay within the 16-bit range")
def step_output_range(context):
    samples = _samples(context.output_audio)
    assert len(samples) > 0
    assert samples.min() >= -32768
    assert samples.max() == 32767


@given("an AudioBuffer with chunk size {size:d}")
def step_buffer(context, size):
    context.buffer = AudioBuffer(chunk_size=size)


@when("I add {size:d} bytes to the buffer")
def step_buffer_add(context, size):
    context.buffer_result = context.buffer.add(b"\x01" * size)


@when("I add {size:d} bytes to the buffer as chunks")
def step_buffer_add_chunks(context, size):
    context.chunks = context.buffer.add_and_get_chunks(b"\x01" * size)


@then("the buffer should return no data")
def step_buffer_empty(context):
    assert context.buffer_result == b""


@then("the buffer should return {size:d} bytes")
def step_buffer_returned(context, size):
    assert len(context.buffer_result) == size


@then("I should receive {count:d} chunks of {size:d} bytes")
def step_chunks(context, count, size):
    assert [len(chunk) for chunk in context.chunks] == [size] * count


@then("flushing the buffer should return {size:d} bytes")
def step_flush(context, size):
    assert len(context.buffer.flush()) == size
