# Audio resampling

Asterisk and OpenAI do not speak the same audio format. AudioSocket carries
16-bit signed little-endian mono PCM at 8 kHz, while the OpenAI Realtime
API expects the same encoding at 24 kHz. The `asterisk.audio_utils`
module converts between the two and batches small chunks of audio. It is
a pure library: nothing in the daemon calls it until the call handler
feature.

## What it does

- `resample_8k_to_24k(audio)` upsamples by a factor of 3 with linear
  interpolation (`numpy.interp`). `N` input samples give `3 * N` output
  samples. Values are clipped to the 16-bit range.
- `resample_24k_to_8k(audio)` applies a 3-sample moving average as a
  simple anti-aliasing low-pass filter (`numpy.convolve`, `valid` mode),
  then keeps one sample out of three. A 480-sample (20 ms) input gives
  160 samples. Amplitudes are logged at `DEBUG` level.
- Both functions return `b""` for input that is empty or too short to
  convert (fewer than 2 bytes for upsampling, fewer than 3 samples for
  downsampling).
- `AudioBuffer(chunk_size=4800)` accumulates bytes:
    - `add(data)` returns everything buffered once at least `chunk_size`
      bytes are available, otherwise `b""`.
    - `add_and_get_chunks(data)` returns a list of exact `chunk_size`
      chunks and keeps the remainder.
    - `flush()` returns and empties the buffer, `clear()` empties it.

The call handler uses a 640-byte input buffer (40 ms of 8 kHz audio) and
a 320-byte output buffer (one AudioSocket frame).

## Settings

None.

## Data model

None.

## Dependencies

Adds `numpy` to the project dependencies.

## Tests

- pytest: `tests/test_audio_utils.py` covers both directions (silence,
  tones, sample counts, clipping, odd and empty input) and every
  `AudioBuffer` method.
- behave: `features/audio_utils.feature` with scenarios for silence and
  tone conversion in both directions, clipping, too short input, and the
  two ways of filling an `AudioBuffer`.
