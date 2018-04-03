
from apiclient import discovery
import httplib2
import gspread
from oauth2client.service_account import ServiceAccountCredentials

spreadsheet_id = '1vx07agIPaboRHthtGGjJqiLQbXzzM1Mr5gUxxnrexq0'

def get_credentials():
    creds_path = 'credentials/gcp_service_creds.json'
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    return ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)

credentials = get_credentials()
client = gspread.authorize(credentials)
# http = credentials.authorize(httplib2.Http())
# service = discovery.build('drive', 'v3', http=http)

cheflist = client.open_by_key(spreadsheet_id).sheet1

data = cheflist.get_all_records(empty2zero=False, head=1, default_blank='')

print(data)
# [{'Channel Name': 'a', 'Github Repo URL': 'b', 'Command': 'c'}]
