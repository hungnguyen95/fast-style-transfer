import argparse
import http.client
import httplib2
import os
import random
import time

import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

httplib2.RETRIES = 1

MAX_RETRIES = 10

RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, http.client.NotConnected,
  http.client.IncompleteRead, http.client.ImproperConnectionState,
  http.client.CannotSendRequest, http.client.CannotSendHeader,
  http.client.ResponseNotReady, http.client.BadStatusLine)

RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

CLIENT_SECRETS_FILE = 'client_secret.json'

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

VALID_PRIVACY_STATUSES = ('public', 'private', 'unlisted')

class Youtube(object):
  def __init__(self, account_path, channel_path):
    self.channel_path = channel_path
    self.account_path = account_path
  
  def create_channel_creds(self, account_name, channel_name):
    client_secret_file = f"{self.account_path}/{account_name}.json"

    scopes = ['https://www.googleapis.com/auth/youtube']
    flow = InstalledAppFlow.from_client_secrets_file(
              client_secret_file, scopes)
    cred = flow.run_console()

    from googleapiclient.discovery import build
    youtube = build(API_SERVICE_NAME, API_VERSION, credentials = cred)
    response = youtube.channels().list(
        part = 'id',
        mine = True
    ).execute()
    channel_id = response['items'][0]['id']

    cred_file = f"{self.channel_path}/{channel_name}.json"
    with open(cred_file, 'w', encoding = 'UTF-8') as json_file:
        json_file.write(cred.to_json())
  
  def upload_youtube(self, channel_name, options):
    from google.oauth2.credentials import Credentials
    cred_file = f"{self.channel_path}/{channel_name}.json"

    if not os.path.isfile(cred_file):
      print("The credfile {} is not existed".format(cred_file))
      return

    cred = Credentials.from_authorized_user_file(cred_file)

    from google.auth.transport.requests import Request
    assert cred and cred.refresh_token
    if cred.expired:
        cred.refresh(Request())
        with open(cred_file, 'w', encoding = 'UTF-8') as json_file:
            json_file.write(cred.to_json())

    from googleapiclient.discovery import build
    youtube = build(API_SERVICE_NAME, API_VERSION, credentials = cred)

    self._initialize_upload(youtube, options)

  def _initialize_upload(self, youtube, options):
    tags = None
    if options.get('keywords', None):
      tags = options['keywords'].split(',')

    body=dict(
      snippet=dict(
        title=options['title'],
        description=options['description'],
        tags=tags,
        categoryId=options['category']
      ),
      status=dict(
        privacyStatus=options['status']
      )
    )

    insert_request = youtube.videos().insert(
      part=','.join(body.keys()),
      body=body,
      media_body=MediaFileUpload(options['file'], chunksize=-1, resumable=True)
    )

    self._resumable_upload(insert_request)
  
  def _resumable_upload(self, request):
    response = None
    error = None
    retry = 0
    while response is None:
      try:
        print('Uploading file...')
        status, response = request.next_chunk()
        if response is not None:
          if 'id' in response:
            print('Video id "%s" was successfully uploaded.' % response['id'])
          else:
            exit('The upload failed with an unexpected response: %s' % response)
      except HttpError as e:
        if e.resp.status in RETRIABLE_STATUS_CODES:
          error = 'A retriable HTTP error %d occurred:\n%s' % (e.resp.status,
                                                              e.content)
        else:
          raise
      except RETRIABLE_EXCEPTIONS as e:
        error = 'A retriable error occurred: %s' % e

      if error is not None:
        print(error)
        retry += 1
        if retry > MAX_RETRIES:
          exit('No longer attempting to retry.')

        max_sleep = 2 ** retry
        sleep_seconds = random.random() * max_sleep
        print('Sleeping %f seconds and then retrying...' % sleep_seconds)
        time.sleep(sleep_seconds)
