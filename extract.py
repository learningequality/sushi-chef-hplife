#!/usr/bin/env python
import csv
import os
import pickle

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request


# Creds storage
CLIENT_SECRET_FILE = 'credentials/client_secret.json'  # server application -- this will request OAuth2 login
CLIENT_TOKEN_PICKLE = 'credentials/token.pickle'
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

class MemoryCache():
    # workaround for error "file_cache is unavailable when using oauth2client >= 4.0.0 or google-auth'"
    # via https://github.com/googleapis/google-api-python-client/issues/325#issuecomment-274349841
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content



def get_service(service_name=None, service_version=None):
    creds = None
    # The file credentials/token.pickle stores the user access and refresh tokens
    # it is created automatically after the first authorization flow completes
    if os.path.exists(CLIENT_TOKEN_PICKLE):
        with open(CLIENT_TOKEN_PICKLE, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server()
        # Save the credentials for the next run
        with open(CLIENT_TOKEN_PICKLE, 'wb') as token:
            pickle.dump(creds, token)
    service = build(service_name, service_version, credentials=creds, cache=MemoryCache())
    return service




FOLDER_MIMETYPE = 'application/vnd.google-apps.folder'

# drive = get_service(service_name='drive', service_version='v3')
# 
# def iterfiles(name=None, is_folder=None, parent=None, order_by='folder,name,createdTime'):
#     q = []
#     if name is not None:
#         q.append("name = '%s'" % name.replace("'", "\\'"))
#     if is_folder is not None:
#         q.append("mimeType %s '%s'" % ('=' if is_folder else '!=', FOLDER_MIMETYPE))
#     if parent is not None:
#         q.append("'%s' in parents" % parent.replace("'", "\\'"))
#     params = {'pageToken': None, 'orderBy': order_by}
#     if q:
#         params['q'] = ' and '.join(q)
#     while True:
#         response = service.files().list(**params).execute()
#         for f in response['files']:
#             yield f
#         try:
#             params['pageToken'] = response['nextPageToken']
#         except KeyError:
#             return
# 
# def walk(top):
#     top, = iterfiles(name=top, is_folder=True)
#     stack = [((top['name'],), top)]
#     while stack:
#         path, top = stack.pop()
#         dirs, files = is_file = [], []
#         for f in iterfiles(parent=top['id']):
#             is_file[f['mimeType'] != FOLDER_MIMETYPE].append(f)
#         yield path, top, dirs, files
#         if dirs:
#             stack.extend((path + (d['name'],), d) for d in dirs)
# 
# for testdir in ['spam', 'folders']:
#     for path, root, dirs, files in walk(testdir):
#         print('%s\t%d %d' % ('/'.join(path), len(dirs), len(files)))
# 
# 
#         csv_savefile.close()


def list_folder(folder_id=''):
    drive = get_service(service_name='drive', service_version='v3')
    folderfields = 'nextPageToken, files(id,kind,name,mimeType,version,webViewLink,createdTime,modifiedTime)'
    response = drive.files().list(q="'"+folder_id+"' in parents", fields=folderfields).execute()
    from pprint import pprint
    pprint(response['files'])

if __name__ == '__main__':
    folder_id = '1ev7-_hahZQmsGZeeM8El2GLJD2FPAIfB'
    list_folder(folder_id)
