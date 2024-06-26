import os
import typing as ty
from pathlib import Path

import click
import pydra
from pydra.mark import annotate
from pydra.mark import task as pydratask

from .process import to_features, verify_speaker_from_files
from .process import VoiceConversion, SpeechToText, Audio

@click.group()
def main():
    pass

@main.command()
@click.argument("filename", type=click.Path(exists=True))
@click.argument("subject", type=str, default="unknown")
@click.argument("task", type=str, default="unknown")
@click.option("--outdir", type=click.Path(), default=os.getcwd(), show_default=True)
@click.option("--n_mels", type=int, default=20, show_default=True)
@click.option("--n_coeff", type=int, default=20, show_default=True)
@click.option("--compute_deltas/--no-compute_deltas", default=True, show_default=True)
@click.option("--output_format", type=str, default="pt", show_default=True)
def convert(filename, subject, task, outdir, n_mels, n_coeff, compute_deltas, output_format):
    to_features(
        filename,
        subject,
        task,
        outdir=Path(outdir),
        n_mels=n_mels,
        n_coeff=n_coeff,
        compute_deltas=compute_deltas,
        output_format=output_format,
    )


@main.command()
@click.argument("csvfile", type=click.Path(exists=True))
@click.option("--outdir", type=click.Path(), default=os.getcwd(), show_default=True)
@click.option("--n_mels", type=int, default=20, show_default=True)
@click.option("--n_coeff", type=int, default=20, show_default=True)
@click.option("--compute_deltas/--no-compute_deltas", default=True, show_default=True)
@click.option(
    "-p",
    "--plugin",
    nargs=2,
    default=["cf", "n_procs=1"],
    help="Pydra plugin to use",
    show_default=True,
)
@click.option(
    "-c",
    "--cache",
    default=os.path.join(os.getcwd(), "cache-wf"),
    help="Cache dir",
    show_default=True,
)
def batchconvert(csvfile, outdir, n_mels, n_coeff, compute_deltas, plugin, cache):
    plugin_args = dict()
    for item in plugin[1].split():
        key, value = item.split("=")
        if plugin[0] == "cf" and key == "n_procs":
            value = int(value)
        plugin_args[key] = value
    with open(csvfile, "r") as f:
        lines = [line.strip() for line in f.readlines()]
    filenames = []
    subjects = []
    tasks = []
    for line in lines:
        filename, subject, task = line.split(",")
        filenames.append(Path(filename).absolute().as_posix())
        subjects.append(subject)
        tasks.append(task)
    featurize_pdt = pydratask(annotate({"return": {"features": ty.Any}})(to_features))
    Path(outdir).mkdir(exist_ok=True, parents=True)
    featurize_task = featurize_pdt(
        outdir=Path(outdir).absolute(),
        n_mels=n_mels,
        n_coeff=n_coeff,
        compute_deltas=compute_deltas,
        cache_dir=Path(cache).absolute(),
    )
    featurize_task.split(
        splitter=("filename", "subject", "task"),
        filename=filenames,
        subject=subjects,
        task=tasks,
    )

    cwd = os.getcwd()
    with pydra.Submitter(plugin=plugin[0], **plugin_args) as sub:
        sub(runnable=featurize_task)
    os.chdir(cwd)


@main.command()
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.argument("model", type=str)
@click.option("--device", type=str, default=None, show_default=True)
def verify(file1, file2, model, device=None):
    score, prediction = verify_speaker_from_files(file1, file2, model=model)
    print(f"Score: {float(score):.2f} Prediction: {bool(prediction)}")


@main.command()
@click.argument("source_file", type=click.Path(exists=True))
@click.argument("target_voice_file", type=click.Path(exists=True))
@click.argument("output_file", type=click.Path())
@click.option("--model_name", type=str, default="voice_conversion_models/multilingual/vctk/freevc24", show_default=True)
@click.option("--device", type=str, default=None, show_default=True, help="Device to use for inference.")
@click.option("--progress_bar", type=bool, default=True, show_default=True)
def convert_voice(source_file, target_voice_file, output_file, model_name, device, progress_bar):
    """
    Converts the voice in the source_file to match the voice in the target_voice_file,
    and saves the output to output_file.
    """
    vc = VoiceConversion(model_name=model_name, progress_bar=progress_bar, device=device)
    vc.convert_voice(source_file, target_voice_file, output_file)
    print(f"Conversion complete. Output saved to: {output_file}")


@main.command()
@click.argument("audio_file", type=click.Path(exists=True))
@click.option("--model_id", type=str, default="openai/whisper-tiny", show_default=True)
@click.option("--max_new_tokens", type=int, default=128, show_default=True)
@click.option("--chunk_length_s", type=int, default=30, show_default=True)
@click.option("--batch_size", type=int, default=16, show_default=True)
@click.option("--batch_size", type=int, default=16, show_default=True)
@click.option("--device", type=str, default=None, help="Device to use for inference.")
@click.option('--return_timestamps', type=str, default='false', help="Return timestamps with the transcription. Can be 'true', 'false', or 'word'.")
@click.option("--language", type=str, default=None, help="Language of the audio for transcription (default is multi-language).")
def transcribe(audio_file, model_id, max_new_tokens, chunk_length_s, batch_size, device, return_timestamps, language):
    """
    Transcribes the audio_file.
    """
    # Convert return_timestamps to the correct type
    if return_timestamps.lower() == 'true':
        return_timestamps = True
    elif return_timestamps.lower() == 'false':
        return_timestamps = False
    else:
        return_timestamps = 'word'

    stt = SpeechToText(
        model_id=model_id,
        max_new_tokens=max_new_tokens,
        chunk_length_s=chunk_length_s,
        batch_size=batch_size,
        return_timestamps=return_timestamps,
        device=device
    )

    audio_data = Audio.from_file(audio_file)
    transcription = stt.transcribe(audio_data, language=language)
    print("Transcription:", transcription)
