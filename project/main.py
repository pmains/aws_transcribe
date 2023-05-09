import json
import re

import boto3
import openai

from flask import Blueprint, Response, redirect, request, render_template, jsonify
from flask_login import login_required
from dotenv import load_dotenv
import os

import requests

load_dotenv()

main = Blueprint('main', __name__)

BUCKET_NAME = os.getenv('BUCKET_NAME')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')


@main.route('/')
@login_required
def index():
    return render_template('index.html')


# Uploading files
@main.route('/upload', methods=['POST'])
@login_required
def upload():
    """Upload an MP3 file to S3 bucket"""

    file_path = os.path.join('uploads', request.files['file'].filename)

    request.files['file'].save(file_path)
    s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
    s3_client.upload_file('uploads/' + request.files['file'].filename, BUCKET_NAME, request.files['file'].filename)

    os.unlink(file_path)

    return redirect('/audio/')


# Start job
@main.route('/audio/')
@login_required
def audio():
    """List all audio files in the S3 bucket"""

    s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

    objects = s3_client.list_objects(Bucket=BUCKET_NAME)
    if 'Contents' in objects:
        file_names = [item['Key'] for item in objects['Contents']]
    else:
        file_names = []
    context = {'files': file_names}

    return render_template('list-audio.html', **context)


@main.route('/audio/delete')
@login_required
def delete_audio():
    """Delete an audio file from the S3 bucket"""

    s3_client = boto3.client('s3', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

    file_name = request.args['filename']
    s3_client.delete_object(Bucket=BUCKET_NAME, Key=file_name)

    return redirect('/audio/')


@main.route('/transcribe')
@login_required
def transcribe():
    """Start a transcription job on an audio file"""

    client = boto3.client(
        'transcribe', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='us-east-1'
    )
    file_name = request.args['filename']
    audio_key = re.sub(
        r'[^a-zA-Z0-9_\-]', '', file_name.replace(' ', '-').replace('.', '-')
    ).lower()
    job_name = 'transcribe-job-{}'.format(audio_key)

    if file_name.endswith('mp3'):
        media_format = 'mp3'
    elif file_name.endswith('m4a'):
        media_format = 'mp4'
    else:
        raise Exception('Unsupported file format')

    client.start_transcription_job(
        TranscriptionJobName=job_name, LanguageCode='en-US', MediaFormat=media_format,
        Media={'MediaFileUri': f'https://s3.amazonaws.com/{BUCKET_NAME}/{file_name}'},
    )

    return redirect('/transcript/status')


# Check job status
@main.route('/transcript/status')
@login_required
def transcripts():
    """List all transcription jobs and their status"""

    client = boto3.client(
        'transcribe', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='us-east-1'
    )

    jobs = client.list_transcription_jobs()['TranscriptionJobSummaries']

    return render_template('list-jobs.html', jobs=jobs)


@main.route('/transcript/delete')
@login_required
def delete_transcript():
    """Delete a transcription job"""

    client = boto3.client(
        'transcribe', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='us-east-1'
    )

    job_name = request.args['job_name']
    client.delete_transcription_job(TranscriptionJobName=job_name)

    return redirect('/transcript/status')


def get_transcript(job_name):
    client = boto3.client(
        'transcribe', aws_access_key_id=AWS_ACCESS_KEY_ID, aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name='us-east-1'
    )

    job = client.get_transcription_job(TranscriptionJobName=job_name)

    uri = job['TranscriptionJob']['Transcript']['TranscriptFileUri']
    transcript = json.loads(requests.get(uri).text)['results']['transcripts'][0]['transcript']

    return transcript


# Download transcript
@main.route('/transcript/download')
@login_required
def download_transcript():
    """Download a transcript job's results as a text file"""

    job_name = request.args['job_name']
    transcript = get_transcript(job_name)

    return Response(
        transcript, mimetype='text/plain', headers={'Content-Disposition': f'attachment; filename={job_name}.txt'}
    )


@main.route('/transcript/summarize')
@login_required
def summarize_transcript():
    """Feed transcript to OpenAI and summarize it"""

    instructions = """
    Create meeting minutes from the following transcript. Include sections for attendees, a list of topics, decision
    making processes, decisions reached and action items coming out of the meeting. Include bullet points and numbered
    lists where appropriate.
    """

    job_name = request.args['job_name']
    transcript = get_transcript(job_name)

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": transcript},
        ]
    )

    # Get the first response from OpenAI
    content = response['choices'][0]['message']['content']
    # Return the response as a text file
    return Response(
        content, mimetype='text/plain', headers={'Content-Disposition': f'attachment; filename={job_name}-summary.txt'}
    )
