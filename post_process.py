from moviepy.editor import *
import numpy as np
import librosa
import soundfile as sf
import numpy as np
import shutil
import os
import parselmouth
from parselmouth.praat import call

def augment_1(y):
  return librosa.effects.percussive(y, margin=2.0)

def augment_2(y, sr):
  S_full, phase = librosa.magphase(librosa.stft(y))
  S_filter = librosa.decompose.nn_filter(S_full,
                                       aggregate=np.median,
                                       metric='cosine',
                                       width=int(librosa.time_to_frames(2, sr=sr)))

  # The output of the filter shouldn't be greater than the input
  # if we assume signals are additive.  Taking the pointwise minimium
  # with the input spectrum forces this.
  S_filter = np.minimum(S_full, S_filter)
  margin_i, margin_v = 2, 10
  power = 2

  mask_i = librosa.util.softmask(S_filter,
                                margin_i * (S_full - S_filter),
                                power=power)

  mask_v = librosa.util.softmask(S_full - S_filter,
                                margin_v * S_filter,
                                power=power)

  # Once we have the masks, simply multiply them with the input spectrum
  # to separate the components

  S_foreground = mask_v * S_full

  return librosa.istft(S_foreground * phase)

def augment_3(y, sr):
  return librosa.effects.pitch_shift(y, sr, n_steps=2)

def change_pitch(sound, factor):
  manipulation = call(sound, "To Manipulation", 0.01, 75, 600)

  pitch_tier = call(manipulation, "Extract pitch tier")

  call(pitch_tier, "Multiply frequencies", sound.xmin, sound.xmax, factor)

  call([pitch_tier, manipulation], "Replace pitch tier")
  return call(manipulation, "Get resynthesis (overlap-add)")

def add_effect_to_audio(audio, temp_audio_path, process_audio_path, impulse_path, process_reverb_audio_path, SAMPLING_RATE, factor):
  audio.write_audiofile(temp_audio_path, SAMPLING_RATE, 2, 2000,"pcm_s32le", progress_bar=False)
  sound = parselmouth.Sound(temp_audio_path)
  sound_changed_pitch = change_pitch(sound, factor)
  sound_changed_pitch.save(process_audio_path, "WAV")

  os.system(f"ffmpeg -y -i {process_audio_path} -i {impulse_path} -filter_complex '[0] [1] afir=dry=10:wet=10 [reverb]; [0] [reverb] amix=inputs=2:weights=1 1' {process_reverb_audio_path}")

  return AudioFileClip(process_reverb_audio_path)

def post_process_video(step_time, cut_sec_array, background_music_path, intro_path, impulse_path, file_path, style_path, output_path, SAMPLING_RATE=44100, factor=0.6):
    if os.path.isfile(output_path):
      print(f"Output path: {output_path} is already existed")
      return

    file_ext = style_path.split('/')[-1]
    filename = file_ext.split('.')[0]
    temp_audio_path = f"source/{filename}_temp_audio.wav"
    process_audio_path = f"source/{filename}_process_audio.wav"
    process_reverb_audio_path = f"source/{filename}_process_reverb_audio.wav"
    post_process_save_path = f"source/{filename}_process.mp4"
    chain_clip = []

    raw_video = VideoFileClip(file_path)
    raw_audio = raw_video.audio
    style_video = VideoFileClip(style_path)
    style_video = style_video.set_audio(raw_audio)

    for cut_sec in cut_sec_array:
        from_sec = cut_sec[0]
        to_sec = cut_sec[1]
        clip = style_video.subclip(from_sec, to_sec)
        chain_clip.append(clip)

    final_clip = concatenate_videoclips(chain_clip, method='chain')
    process_audio = add_effect_to_audio(final_clip.audio, temp_audio_path, process_audio_path, impulse_path, process_reverb_audio_path, SAMPLING_RATE, factor)
    final_clip = final_clip.set_audio(process_audio)

    # duration = final_clip.duration
    # steps = int(duration/60)
    # intro = VideoFileClip(intro_path)
    # chain = []
    # for step in range(steps):
    #   cut = final_clip.subclip(step*60, (step+1)*60)
    #   # cut = cut.fx(vfx.speedx, 1.25)
    #   chain.append(cut)

    #   if step % step_time == step_time - 1:
    #     chain.append(intro)
    
    # if (step+1)*60 < duration:
    #   chain.append(final_clip.subclip((step+1)*60))
    
    # final_clip = concatenate_videoclips(chain, method='chain')

    background_music = AudioFileClip(background_music_path)
    background_audio = background_music.audio_loop(duration=final_clip.duration)
    background_audio = (background_audio.fx(afx.audio_normalize)
                          .fx( afx.volumex, 0.03)
                          .fx( afx.audio_fadein, 1.0)
                          .fx( afx.audio_fadeout, 1.0))

    mixed_audio = CompositeAudioClip([final_clip.audio, background_audio])
    final_clip = final_clip.set_audio(mixed_audio)

    final_clip.write_videofile(post_process_save_path, threads=4, fps=24, preset='ultrafast', progress_bar=False)
    shutil.copyfile(post_process_save_path, output_path)
    os.remove(temp_audio_path)
    os.remove(process_audio_path)
    os.remove(process_reverb_audio_path)
    os.remove(post_process_save_path)

def merge_videos(videos_path, intro_path, output_path):
    chain = []

    intro = VideoFileClip(intro_path)
    start_time = 0
    result = ""
    for video_path in videos_path:
      hour = int(start_time/3600)
      minute = int((start_time - hour*3600)/60)
      second = int(start_time - hour*3600 - minute*60)

      result += f"Video: {video_path} start at: {hour}:{minute}:{second}\n"
      video = VideoFileClip(video_path)
      chain.append(video)
      chain.append(intro)
      start_time += (video.duration + intro.duration)

    final_clip = concatenate_videoclips(chain, method='chain')
    final_clip.write_videofile(output_path, threads=4, fps=24, preset='ultrafast', progress_bar=False)

    return result